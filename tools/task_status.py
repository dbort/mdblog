"""task_status: the `tasks/active/` backlog in dependency order, and the next free id.

Status is derived from where a task file lives, whether its `task-XXX` branch
exists, and the last `## Review log` round on that branch
(`.claude/docs/pipeline.md` § Status). The tool only reads the repository.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


class TaskParseError(Exception):
    """A task file's frontmatter is missing or malformed."""


@dataclass(frozen=True)
class Frontmatter:
    """The frontmatter fields the pipeline reads; other keys are ignored."""

    id: str
    title: str
    blocked_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskEntry:
    """One active task's derived status."""

    id: str
    title: str
    path: str
    status: str
    # Blockers not yet in the working tree's tasks/completed/.
    unmet_blockers: tuple[str, ...]


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_FIELD_RE = re.compile(r"^([A-Za-z_][\w-]*):(?:\s+(.*?))?\s*$")
_DOUBLE_QUOTED_RE = re.compile(r'^("(?:[^"\\]|\\.)*")(?:\s+#.*)?$')
_SINGLE_QUOTED_RE = re.compile(r"^'((?:[^']|'')*)'(?:\s+#.*)?$")
_TRAILING_COMMENT_RE = re.compile(r"\s+#.*$")
_ROUND_RE = re.compile(r"^### Round (\d+): (APPROVED|REJECTED)\s*$", re.MULTILINE)
_ID_RE = re.compile(r"^task-(\d+)$")
_PATH_ID_RE = re.compile(r"(?:^|/)(task-\d+)-[^/]+\.md$")
_TASK_SUBDIRS = ("active", "completed", "abandoned")


def _parse_scalar(raw: str) -> str:
    """`raw` without its quotes or trailing comment; raises on a broken quote."""
    if raw.startswith('"'):
        match = _DOUBLE_QUOTED_RE.match(raw)
        if match is None:
            raise TaskParseError(f"malformed quoted value: {raw}")
        try:
            return str(json.loads(match.group(1)))
        except json.JSONDecodeError as exc:
            raise TaskParseError(f"malformed quoted value: {raw}") from exc
    if raw.startswith("'"):
        match = _SINGLE_QUOTED_RE.match(raw)
        if match is None:
            raise TaskParseError(f"malformed quoted value: {raw}")
        return match.group(1).replace("''", "'")
    return _TRAILING_COMMENT_RE.sub("", raw)


def _parse_id_list(raw: str) -> tuple[str, ...]:
    """The ids of an inline `[a, b]` list; raises on any other form."""
    value = _TRAILING_COMMENT_RE.sub("", raw)
    if not (value.startswith("[") and value.endswith("]")):
        raise TaskParseError("`blocked_by` must be a list of task ids")
    items = [item.strip() for item in value[1:-1].split(",")]
    return tuple(_parse_scalar(item) for item in items if item)


def parse_frontmatter(text: str) -> Frontmatter:
    """The task's frontmatter; raises `TaskParseError` if `id` or `title` is absent.

    Reads the subset of YAML the task template uses, so that projects need no
    YAML package. Keys other than the three the pipeline reads are ignored,
    along with any indented lines beneath them.
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        raise TaskParseError("no leading --- frontmatter block")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.startswith((" ", "\t", "#")):
            continue
        field = _FIELD_RE.match(line)
        if field is None:
            raise TaskParseError(f"frontmatter line is not a mapping entry: {line}")
        fields[field.group(1)] = field.group(2) or ""
    task_id = _parse_scalar(fields.get("id", ""))
    title = _parse_scalar(fields.get("title", ""))
    if not task_id or not title:
        raise TaskParseError("frontmatter needs string `id` and `title`")
    blocked_by = _parse_id_list(fields["blocked_by"]) if "blocked_by" in fields else ()
    return Frontmatter(task_id, title, blocked_by)


def last_review_round(text: str) -> tuple[int, str] | None:
    """`(round, verdict)` of the last `### Round N: VERDICT` heading, if any."""
    rounds = _ROUND_RE.findall(text)
    if not rounds:
        return None
    number, verdict = rounds[-1]
    return int(number), verdict


def derive_status(branch_exists: bool, task_text_on_branch: str | None) -> str:
    """The pipeline status label for an active task (`pipeline.md` § Status)."""
    if not branch_exists:
        return "planned"
    last = last_review_round(task_text_on_branch or "")
    if last is None:
        return "in progress"
    number, verdict = last
    if verdict == "APPROVED":
        return "awaiting /ship"
    return f"in progress, round {number} rejected"


def compute_next_id(existing_ids: Sequence[str]) -> str:
    """One past the highest `task-NNN` id at its zero-padded width; `task-001` if none."""
    parsed = [
        (int(m.group(1)), len(m.group(1)))
        for i in existing_ids
        if (m := _ID_RE.match(i))
    ]
    if not parsed:
        return "task-001"
    value, width = max(parsed)
    return f"task-{value + 1:0{width}d}"


def layered_topological_order(
    blocked_by_by_id: Mapping[str, Sequence[str]],
) -> tuple[list[list[str]], list[str]]:
    """`(layers, cyclic_ids)`: each layer's blockers all sit in earlier layers.

    Blockers outside `blocked_by_by_id`'s keys are ignored. Layers and
    `cyclic_ids` are sorted by id.
    """
    remaining = {
        k: {b for b in v if b in blocked_by_by_id} for k, v in blocked_by_by_id.items()
    }
    layers: list[list[str]] = []
    while ready := sorted(k for k, blockers in remaining.items() if not blockers):
        layers.append(ready)
        for task_id in ready:
            del remaining[task_id]
        for blockers in remaining.values():
            blockers.difference_update(ready)
    return layers, sorted(remaining)


def _git(repo_root: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def _ids_in(paths: Sequence[str]) -> set[str]:
    return {m.group(1) for p in paths if (m := _PATH_ID_RE.search(p))}


def all_task_ids(repo_root: Path) -> set[str]:
    """Every task id in the working tree's or any local branch's `tasks/*/`."""
    ids = _ids_in(
        [str(p) for d in _TASK_SUBDIRS for p in (repo_root / "tasks" / d).glob("*.md")]
    )
    for branch in (
        _git(repo_root, "for-each-ref", "--format=%(refname:short)", "refs/heads/")
        or ""
    ).split():
        listing = _git(
            repo_root, "ls-tree", "-r", "--name-only", branch, "--", "tasks/"
        )
        ids |= _ids_in((listing or "").splitlines())
    return ids


def _task_text_on_branch(repo_root: Path, branch: str, filename: str) -> str | None:
    for subdir in ("active", "completed"):
        text = _git(repo_root, "show", f"{branch}:tasks/{subdir}/{filename}")
        if text is not None:
            return text
    return None


def build_backlog(repo_root: Path) -> tuple[list[TaskEntry], list[str]]:
    """`(entries, errors)`: active tasks in dependency order, and unreadable files.

    Tasks in a `blocked_by` cycle come last.
    """
    completed = _ids_in(
        [p.name for p in (repo_root / "tasks" / "completed").glob("*.md")]
    )
    tasks: dict[str, tuple[Frontmatter, Path]] = {}
    errors: list[str] = []
    for path in sorted((repo_root / "tasks" / "active").glob("task-*.md")):
        try:
            fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        except TaskParseError as exc:
            errors.append(f"{path.relative_to(repo_root)}: {exc}")
            continue
        tasks[fm.id] = (fm, path)

    layers, cyclic = layered_topological_order(
        {k: fm.blocked_by for k, (fm, _) in tasks.items()}
    )
    entries: list[TaskEntry] = []
    for task_id in [i for layer in layers for i in layer] + cyclic:
        fm, path = tasks[task_id]
        branch_exists = (
            _git(repo_root, "rev-parse", "--verify", "--quiet", f"refs/heads/{task_id}")
            is not None
        )
        text = (
            _task_text_on_branch(repo_root, task_id, path.name)
            if branch_exists
            else None
        )
        entries.append(
            TaskEntry(
                id=task_id,
                title=fm.title,
                path=str(path.relative_to(repo_root)),
                status=derive_status(branch_exists, text),
                unmet_blockers=tuple(b for b in fm.blocked_by if b not in completed),
            )
        )
    return entries, errors


def render(entries: Sequence[TaskEntry], errors: Sequence[str], next_id: str) -> str:
    """The backlog as Markdown, one bullet per task in dependency order."""
    lines = [f"Next id: {next_id}", ""]
    for e in entries:
        blocked = (
            f"; blocked by {', '.join(e.unmet_blockers)}" if e.unmet_blockers else ""
        )
        lines.append(f"- {e.id} [{e.status}{blocked}]: {e.title} (`{e.path}`)")
    lines += [f"- unreadable: {err}" for err in errors]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None, repo_root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--next-id", action="store_true", help="print only the next free task id"
    )
    args = parser.parse_args(argv)
    repo_root = repo_root or Path(__file__).resolve().parent.parent
    next_id = compute_next_id(sorted(all_task_ids(repo_root)))
    if args.next_id:
        print(next_id)
        return 0
    entries, errors = build_backlog(repo_root)
    print(render(entries, errors, next_id))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
