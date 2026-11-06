"""mdblog.publish: decides which of a vault's notes reach the site."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError

from mdblog.config import SITE_DIR
from mdblog.properties import PageProperties, valid_slug, validate_properties

NOTE_SUFFIX = ".md"
FENCE = b"---"


class FrontMatterError(Exception):
    """A note's front matter is unusable; the message gives the reason."""


@dataclass(frozen=True)
class PublishedNote:
    """A note that passed validation and belongs on the site."""

    # Relative to the vault.
    path: Path
    page: PageProperties
    # The bytes after the front matter, read once so a later edit cannot bypass the rules.
    body: bytes


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
    # Every regular file a selected note could link to, notes included, relative to the
    # vault and sorted.
    files: tuple[Path, ...]


def split_note(data: bytes) -> tuple[bytes, bytes] | None:
    """A note's front matter block with LF line endings and its exact body, or None.

    None means the note has no block. A block opens only with `---` alone on the first
    line and closes at the next line holding only `---`, and the body starts on the line
    after that. Works on bytes because a note with no block may hold any encoding.
    """
    raw_lines = data.split(b"\n")
    lines = [line.removesuffix(b"\r") for line in raw_lines]
    if lines[0] != FENCE:
        return None
    try:
        closing = lines.index(FENCE, 1)
    except ValueError:
        return None
    return b"\n".join(lines[1:closing]), b"\n".join(raw_lines[closing + 1 :])


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
    # The broad catch is deliberate: this untyped loader also raises errors of its own
    # choosing, such as ValueError for an out-of-range date, and any loader error
    # becomes a named report so the run still names the other bad notes.
    except Exception as exc:
        raise FrontMatterError(
            f"front matter is invalid YAML: {_yaml_problem(exc)}"
        ) from exc
    if not isinstance(loaded, dict):
        raise FrontMatterError("front matter is not a mapping")
    return loaded


def published_parts(data: bytes) -> tuple[Mapping[object, object], bytes] | None:
    """The properties and body of a note marked for publishing, otherwise None.

    Returns them only for the boolean `publish: true`. None for `publish: false`, no
    `publish` property and no front matter. Raises `FrontMatterError` for a non-boolean
    `publish`, any failure of `parse_properties`, or a published note whose body is not
    UTF-8.
    """
    parts = split_note(data)
    if parts is None:
        return None
    block, body = parts
    properties = parse_properties(block)
    if "publish" not in properties:
        return None
    value = properties["publish"]
    # An identity check, because `1 == True` in Python.
    if value is False:
        return None
    if value is not True:
        raise FrontMatterError(f"publish must be true or false, not {value!r}")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FrontMatterError("note is not UTF-8") from exc
    return properties, body


def _slug_collisions(users: Mapping[str, list[Path]]) -> list[NoteFailure]:
    failures: list[NoteFailure] = []
    for slug, paths in users.items():
        if len(paths) > 1:
            names = ", ".join(sorted(path.as_posix() for path in paths))
            reason = f"slug {slug!r} is used by more than one note: {names}"
            failures.extend(NoteFailure(path, reason) for path in paths)
    return failures


def select_notes(vault: Path, now: datetime) -> Selection:
    """Validates each selected note in `vault` and returns the published ones and all failures.

    A selected note is a regular `*.md` file outside `_site/` at the vault's root, with
    no path component starting with `.`. Symbolic links are neither followed nor selected.
    An unreadable note or directory is a failure, and so is a published note whose
    properties fail `validate_properties` at the time `now`, with one failure per reason.
    Every note sharing a slug is a failure that names the others, even when the note has
    other failures. A note with any failure is not in `published`. `files` lists every
    regular file under the same rules as notes, whatever its suffix.
    """
    published: list[PublishedNote] = []
    failures: list[NoteFailure] = []
    files: list[Path] = []
    slug_users: dict[str, list[Path]] = {}

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
            if name.startswith(".") or not note.is_file(follow_symlinks=False):
                continue
            relative = note.relative_to(vault)
            files.append(relative)
            if note.suffix != NOTE_SUFFIX:
                continue
            try:
                parts = published_parts(note.read_bytes())
            except OSError as exc:
                failures.append(NoteFailure(relative, f"cannot read: {exc.strerror}"))
                continue
            except FrontMatterError as exc:
                failures.append(NoteFailure(relative, str(exc)))
                continue
            if parts is None:
                continue
            properties, body = parts
            slug = valid_slug(properties.get("slug"))
            if slug is not None:
                slug_users.setdefault(slug, []).append(relative)
            page = validate_properties(properties, note.stem, now)
            if isinstance(page, PageProperties):
                published.append(PublishedNote(relative, page, body))
            else:
                failures.extend(NoteFailure(relative, reason) for reason in page)
    failures.extend(_slug_collisions(slug_users))
    failed = {failure.path for failure in failures}
    return Selection(
        published=tuple(
            sorted(
                (note for note in published if note.path not in failed),
                key=lambda note: note.path,
            )
        ),
        failures=tuple(sorted(failures, key=lambda failure: failure.path)),
        files=tuple(sorted(files)),
    )
