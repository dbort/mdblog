"""manual_qa: walks the author through the checks no automated test can make.

Each check runs its command on its own scratch copy of the fixture vault, prints the
steps, and records the author's verdict and notes. The log written at the end is what
the author hands back to the agent running `/work`.
"""

import argparse
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_VAULT = REPO_ROOT / "tests" / "fixtures" / "vault"
# Seconds a check's server gets to answer before the steps are shown anyway.
READY_TIMEOUT = 30
# Lines of a failed check's command output copied into the log.
OUTPUT_TAIL = 40


@dataclass(frozen=True)
class Places:
    """The values a check's command, URL and steps refer to by `{name}`."""

    # The scratch copy of the fixture vault.
    vault: Path
    port: int

    def fill(self, text: str) -> str:
        """`text` with every `{name}` replaced; the site ends in a slash."""
        return text.format(
            vault=self.vault,
            port=self.port,
            site=f"http://localhost:{self.port}/",
        )


@dataclass(frozen=True)
class Check:
    """One manual check."""

    name: str
    # Runs for the whole check and is stopped with SIGTERM after the verdict.
    command: tuple[str, ...]
    # Polled until it answers, so the steps appear once the server is up.
    url: str
    steps: tuple[str, ...]
    # Vault-relative paths and texts written into the scratch vault before the command
    # runs, for notes the shared fixture vault must not hold.
    files: tuple[tuple[str, str], ...] = ()


# A plain build would fail on this note, so only the vaults of checks that serve
# drafts hold it.
INVALID_NOTE = (
    "projects/invalid-note.md",
    "---\npublish: true\ntitle: An invalid note\ndate: next week\n"
    "tags: [project/alpha]\n---\n"
    "A published note with an invalid date and no slug, linking to [[nowhere]].\n",
)

CHECKS = (
    Check(
        name="serve: live reload",
        command=("mdblog", "serve", "{vault}", "--port", "{port}"),
        url="{site}",
        steps=(
            "Open {site}posts/first-note/ in a browser.",
            "Edit {vault}/projects/first-note.md: change a word of its body and save.",
            "Pass if the open page shows the change without a manual refresh.",
        ),
    ),
    Check(
        name="design: restyle with sidebar, phone and desktop, light and dark",
        command=("mdblog", "serve", "{vault}", "--drafts", "--port", "{port}"),
        url="{site}",
        files=(INVALID_NOTE,),
        steps=(
            "With the system in light mode, open {site} in a desktop-width window. "
            "The Draft preview banner is expected: this check serves drafts.",
            "Visit the home page, Archive, Tags, {site}tags/project/alpha/, "
            "{site}posts/syntax/ and {site}404.html.",
            "Compare each with the decisions in "
            "tasks/active/task-012-restyle-default-theme.md, section Advice: serif "
            "text on ivory with red links, a right-hand sidebar of dashed boxes with "
            "red ring markers, no bio above the home page's entries, and a muted "
            "« before the site title on every page but home.",
            "Repeat at phone width: the browser's device toolbar set to 375px wide. "
            "The sidebar sits after the content and before the footer, and the "
            "header shows the Archive, Tags and RSS links.",
            "Switch the system to dark mode and repeat both widths: blue links and "
            "markers, solid sidebar borders.",
            "On posts/syntax/, open and close each callout and scroll the code block "
            "and the table sideways. On the home page and Archive, find the Draft "
            "label on marked-false and the Invalid label on An invalid note.",
            "Pass if every page matches those decisions and reads well in both modes "
            "at both widths, and no page scrolls sideways as a whole. Note anything "
            "to change.",
        ),
    ),
    Check(
        name="drafts: labels and banner",
        command=("mdblog", "serve", "{vault}", "--drafts", "--port", "{port}"),
        url="{site}",
        files=(INVALID_NOTE,),
        steps=(
            "With the system in light mode, open {site} in a desktop-width window.",
            "On the home page, find marked-false labeled Draft and An invalid note "
            "labeled Invalid, beside entries with no label, and the banner at the top.",
            "Visit Archive, {site}tags/project/alpha/, {site}posts/marked-false/, "
            "{site}posts/invalid-note/ and {site}posts/first-note/.",
            "Repeat at phone width: the browser's device toolbar set to 375px wide.",
            "Switch the system to dark mode and repeat both widths.",
            "Pass if the labels and the banner read clearly and fit the design on every "
            "page in both modes at both widths, and first-note shows no label. Note "
            "anything to change.",
        ),
    ),
)


class Verdict(StrEnum):
    """The author's verdict on one check."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


def parse_verdict(answer: str) -> Verdict | None:
    """The verdict `answer` names by its first letter or in full, or None if none."""
    word = answer.strip().lower()
    for verdict in Verdict:
        if word and verdict.value.startswith(word):
            return verdict
    return None


@dataclass(frozen=True)
class Result:
    """What one check recorded."""

    check: Check
    # The command as run, with places filled in.
    command: tuple[str, ...]
    verdict: Verdict
    notes: str
    # The command's exit status when it stopped before the verdict, else None.
    early_exit: int | None
    # The end of the command's output, kept only for a failed check.
    output_tail: str


def render_log(results: Sequence[Result], started: datetime, commit: str) -> str:
    """The Markdown log of `results`, in order, with every verdict and note."""
    lines = [
        "# Manual QA log",
        "",
        f"- Started: {started.isoformat(timespec='seconds')}",
        f"- Commit: {commit}",
        "",
    ]
    for result in results:
        lines += [
            f"## {result.check.name}: {result.verdict.value.upper()}",
            "",
            f"- Command: `{' '.join(result.command)}`",
        ]
        if result.early_exit is not None:
            lines.append(
                f"- The command exited with status {result.early_exit} before the verdict."
            )
        lines += ["", "Notes:", "", result.notes or "(none)", ""]
        if result.output_tail:
            lines += [
                "Command output (last lines):",
                "",
                "```",
                result.output_tail,
                "```",
                "",
            ]
    return "\n".join(lines)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("", 0))
        port: int = probe.getsockname()[1]
        return port


def _answers(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


def _wait_until_ready(url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + READY_TIMEOUT
    while process.poll() is None and time.monotonic() < deadline:
        if _answers(url):
            return
        time.sleep(0.3)
    print(f"  (nothing answered at {url}; see the command output)")


def _ask_verdict(ask: Callable[[str], str]) -> Verdict:
    while True:
        verdict = parse_verdict(ask("Verdict [p]ass, [f]ail or [s]kip: "))
        if verdict is not None:
            return verdict


def _type_notes(ask: Callable[[str], str]) -> str:
    print("Notes, ending with an empty line:")
    lines: list[str] = []
    while line := ask("> "):
        lines.append(line)
    return "\n".join(lines)


def editor_command() -> list[str]:
    """`$VISUAL`, else `$EDITOR`, else `vi`, split into words as a shell would."""
    return shlex.split(os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi")


def _edit(path: Path) -> None:
    subprocess.run([*editor_command(), str(path)], check=False)


def ask_notes(
    ask: Callable[[str], str], edit: Callable[[Path], None], path: Path
) -> str:
    """The author's notes, stripped, or "" when they decline to add any.

    Notes the author accepts are written by `edit` into `path`. When the editor cannot
    start, the notes are typed line by line instead.
    """
    while True:
        answer = ask("Add notes? [y/N]: ").strip().lower()
        if answer in ("", "n", "no"):
            return ""
        if answer in ("y", "yes"):
            break
    path.write_text("", encoding="utf-8")
    try:
        edit(path)
    except OSError as error:
        print(f"  (could not start the editor: {error})")
        return _type_notes(ask).strip()
    return path.read_text(encoding="utf-8").strip()


def _tail(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return "\n".join(text.splitlines()[-OUTPUT_TAIL:])


def run_check(
    check: Check,
    places: Places,
    work: Path,
    ask: Callable[[str], str],
    edit: Callable[[Path], None],
) -> Result:
    """Runs `check` with `places`, writing its command output and notes under `work`."""
    command = tuple(places.fill(part) for part in check.command)
    stem = check.name.replace(":", "").replace(" ", "-")
    output = work / f"{stem}.log"
    print(f"\n== {check.name}\n$ {' '.join(command)}\n  (output: {output})")
    print(f"  (scratch vault: {places.vault})")
    with output.open("wb") as sink:
        process = subprocess.Popen(command, stdout=sink, stderr=subprocess.STDOUT)
    try:
        _wait_until_ready(places.fill(check.url), process)
        for number, step in enumerate(check.steps, start=1):
            print(f"{number}. {places.fill(step)}")
        verdict = _ask_verdict(ask)
        notes = ask_notes(ask, edit, work / f"{stem}-notes.md")
        early_exit = process.poll()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
    return Result(
        check=check,
        command=command,
        verdict=verdict,
        notes=notes,
        early_exit=early_exit,
        output_tail=_tail(output) if verdict is Verdict.FAIL else "",
    )


def scratch_vault(path: Path, check: Check) -> Path:
    """`path`, made a copy of the fixture vault holding `check`'s extra files."""
    shutil.copytree(FIXTURE_VAULT, path)
    for relative, text in check.files:
        note = path / relative
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text(text, encoding="utf-8")
    return path


def _commit() -> str:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
        ).stdout.strip()

    dirty = " (uncommitted changes)" if git("status", "--porcelain") else ""
    # The author runs QA on a detached HEAD, where there is no branch to name.
    branch = git("branch", "--show-current")
    on_branch = f" on {branch}" if branch else ""
    return f"{git('rev-parse', '--short', 'HEAD')}{on_branch}{dirty}"


def main(argv: Sequence[str] | None = None) -> int:
    """Runs the selected checks interactively; returns 0 once the log is written."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "names",
        nargs="*",
        metavar="TEXT",
        help="run only checks whose name contains TEXT (default: every check)",
    )
    parser.add_argument(
        "--log", type=Path, metavar="PATH", help="where to write the log"
    )
    parser.add_argument("--list", action="store_true", help="list the checks and exit")
    args = parser.parse_args(argv)
    names: list[str] = args.names
    checks = [c for c in CHECKS if not names or any(n in c.name for n in names)]
    if args.list or not checks:
        for check in checks or CHECKS:
            print(check.name)
        return 0 if checks else 2
    started = datetime.now().astimezone()
    log: Path = args.log or Path(tempfile.gettempdir()) / (
        f"mdblog-qa-{started:%Y%m%d-%H%M%S}.md"
    )
    results: list[Result] = []
    with tempfile.TemporaryDirectory(prefix="mdblog-qa-") as work_name:
        work = Path(work_name)
        port = _free_port()
        try:
            for number, check in enumerate(checks, start=1):
                vault = scratch_vault(work / f"vault-{number}", check)
                places = Places(vault=vault, port=port)
                results.append(run_check(check, places, work, input, _edit))
        except KeyboardInterrupt, EOFError:
            print("\nStopped; the log holds the checks finished so far.")
        finally:
            log.write_text(render_log(results, started, _commit()), encoding="utf-8")
    print(f"\nLog written to {log}\nGive that path to Claude.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
