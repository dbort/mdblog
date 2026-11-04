"""mdblog.publish: decides which of a vault's notes reach the site."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError, YAMLError

from mdblog.config import SITE_DIR

NOTE_SUFFIX = ".md"
FENCE = b"---"


class FrontMatterError(Exception):
    """A note's front matter is unusable; the message gives the reason."""


@dataclass(frozen=True)
class PublishedNote:
    """A note that passed validation and belongs on the site."""

    # Relative to the vault.
    path: Path
    # The bytes that were validated, so a later edit to the file cannot bypass the rule.
    content: bytes


@dataclass(frozen=True)
class NoteFailure:
    """A note or directory that makes the build fail."""

    # Relative to the vault.
    path: Path
    reason: str


@dataclass(frozen=True)
class Selection:
    """The outcome of validating every selected note in a vault."""

    # Sorted by path.
    published: tuple[PublishedNote, ...]
    # Sorted by path.
    failures: tuple[NoteFailure, ...]


def front_matter_block(data: bytes) -> bytes | None:
    """The bytes between a note's fences with LF line endings, or None if it has no block.

    A block opens only with `---` alone on the first line and closes at the next line
    holding only `---`. Works on bytes because a note with no block may hold any encoding.
    """
    lines = [line.removesuffix(b"\r") for line in data.split(b"\n")]
    if lines[0] != FENCE:
        return None
    try:
        closing = lines.index(FENCE, 1)
    except ValueError:
        return None
    return b"\n".join(lines[1:closing])


def _is_blank(text: str) -> bool:
    return all(
        not line.strip() or line.lstrip().startswith("#") for line in text.splitlines()
    )


def _yaml_problem(exc: Exception) -> str:
    if isinstance(exc, MarkedYAMLError) and exc.problem is not None:
        return str(exc.problem)
    return " ".join(str(exc).split())


def parse_properties(block: bytes) -> Mapping[object, object]:
    """The properties in a front matter block; empty for a blank or comment-only block.

    Raises `FrontMatterError` when the block is not UTF-8, is invalid YAML, has a
    duplicate key or is not a mapping.
    """
    try:
        text = block.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FrontMatterError("front matter is not UTF-8") from exc
    # The loader returns None for a blank block and for an explicit `null`, and only
    # the second is a non-mapping.
    if _is_blank(text):
        return {}
    # YAML 1.2 keeps `yes` a string, and the safe loader raises on a duplicate key.
    yaml = YAML(typ="safe", pure=True)
    try:
        # ruamel.yaml is untyped, so its result is narrowed to `object` here.
        loaded: object = yaml.load(text)
    # An out-of-range date raises a plain ValueError, and deep nesting exhausts the
    # pure loader's recursion.
    except (YAMLError, ValueError, RecursionError) as exc:
        raise FrontMatterError(
            f"front matter is invalid YAML: {_yaml_problem(exc)}"
        ) from exc
    if not isinstance(loaded, dict):
        raise FrontMatterError("front matter is not a mapping")
    return loaded


def is_published(data: bytes) -> bool:
    """Whether a note's bytes mark it for publishing.

    True only for the boolean `publish: true`. False for `publish: false`, no `publish`
    property and no front matter. Raises `FrontMatterError` for a non-boolean `publish`,
    any failure of `parse_properties`, or a published note whose body is not UTF-8.
    """
    block = front_matter_block(data)
    if block is None:
        return False
    properties = parse_properties(block)
    if "publish" not in properties:
        return False
    value = properties["publish"]
    # An identity check, because `1 == True` in Python.
    if value is False:
        return False
    if value is not True:
        raise FrontMatterError(f"publish must be true or false, not {value!r}")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FrontMatterError("note is not UTF-8") from exc
    return True


def select_notes(vault: Path) -> Selection:
    """Validates each selected note in `vault` and returns the published ones and all failures.

    A selected note is a regular `*.md` file outside `_site/` at the vault's root, with
    no path component starting with `.`. Symbolic links are neither followed nor selected.
    An unreadable note or directory is a failure.
    """
    published: list[PublishedNote] = []
    failures: list[NoteFailure] = []

    def record_walk_error(error: OSError) -> None:
        path = Path(error.filename).relative_to(vault)
        failures.append(NoteFailure(path, f"cannot read: {error.strerror}"))

    for directory, subdirectories, filenames in vault.walk(on_error=record_walk_error):
        subdirectories[:] = [
            name
            for name in subdirectories
            if not name.startswith(".")
            and not (directory == vault and name == SITE_DIR)
        ]
        for name in filenames:
            note = directory / name
            if (
                name.startswith(".")
                or note.suffix != NOTE_SUFFIX
                or not note.is_file(follow_symlinks=False)
            ):
                continue
            relative = note.relative_to(vault)
            try:
                data = note.read_bytes()
                if is_published(data):
                    published.append(PublishedNote(relative, data))
            except OSError as exc:
                failures.append(NoteFailure(relative, f"cannot read: {exc.strerror}"))
            except FrontMatterError as exc:
                failures.append(NoteFailure(relative, str(exc)))
    return Selection(
        published=tuple(sorted(published, key=lambda note: note.path)),
        failures=tuple(sorted(failures, key=lambda failure: failure.path)),
    )
