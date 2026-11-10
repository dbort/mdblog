"""mdblog.publish: decides which of a vault's notes reach the site."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError

from mdblog.config import SITE_DIR
from mdblog.properties import (
    EntryStatus,
    PageProperties,
    file_slug,
    preview_properties,
    valid_slug,
    validate_properties,
)

NOTE_SUFFIX = ".md"
FENCE = b"---"
# Relative to the vault.
BIO_PATH = Path(SITE_DIR, "bio.md")


class FrontMatterError(Exception):
    """A note's front matter is unusable; the message gives the reason."""


@dataclass(frozen=True)
class PublishedNote:
    """A note that renders on the site: outside draft mode, one that passed validation."""

    # Relative to the vault.
    path: Path
    page: PageProperties
    # The bytes after the front matter, read once so a later edit cannot bypass the rules.
    body: bytes
    # Always PUBLISHED outside draft mode.
    status: EntryStatus = EntryStatus.PUBLISHED


@dataclass(frozen=True)
class NoteFailure:
    """A note or directory that makes the build fail, or under draft mode, a warning."""

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


def marked_parts(data: bytes) -> tuple[bool, Mapping[object, object], bytes] | None:
    """The boolean `publish` value, properties and body of a note, or None.

    None for a note with no front matter or no `publish` property. Raises
    `FrontMatterError` for a non-boolean `publish` or any failure of `parse_properties`.
    The body may be in any encoding.
    """
    parts = split_note(data)
    if parts is None:
        return None
    block, body = parts
    properties = parse_properties(block)
    if "publish" not in properties:
        return None
    value = properties["publish"]
    # Identity checks, because `1 == True` in Python.
    if value is not True and value is not False:
        raise FrontMatterError(f"publish must be true or false, not {value!r}")
    return value is True, properties, body


def _require_utf8(data: bytes) -> None:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FrontMatterError("note is not UTF-8") from exc


def published_parts(data: bytes) -> tuple[Mapping[object, object], bytes] | None:
    """The properties and body of a note marked for publishing, otherwise None.

    Returns them only for the boolean `publish: true`. None for `publish: false`, no
    `publish` property and no front matter. Raises `FrontMatterError` for a non-boolean
    `publish`, any failure of `parse_properties`, or a published note whose body is not
    UTF-8.
    """
    marked = marked_parts(data)
    if marked is None or not marked[0]:
        return None
    _require_utf8(data)
    return marked[1], marked[2]


def _slug_collisions(users: Mapping[str, list[Path]]) -> list[NoteFailure]:
    failures: list[NoteFailure] = []
    for slug, paths in users.items():
        if len(paths) > 1:
            names = ", ".join(sorted(path.as_posix() for path in paths))
            reason = f"slug {slug!r} is used by more than one note: {names}"
            failures.extend(NoteFailure(path, reason) for path in paths)
    return failures


@dataclass(frozen=True)
class SlugClaim:
    """What one note brings to draft mode's slug assignment."""

    # Relative to the vault.
    path: Path
    # The note's own valid slug, or None to generate one from the file name.
    own: str | None
    # Marked `publish: true`, so its own slug wins over a draft's.
    published: bool


def assign_slugs(claims: Iterable[SlugClaim]) -> dict[Path, tuple[str, str | None]]:
    """Each claim's slug, unique across `claims`, with a reason when it is suffixed.

    A note keeps its own slug unless an earlier claim by path holds it, and a published
    note's own slug wins over every draft's. Then, in path order, each other note takes
    its generated `file_slug`, or its own slug when it lost, and adds the first free
    `-2`, `-3`, ... suffix when that slug is already used. The reason for a suffix
    names the note holding the unsuffixed slug. Every returned slug matches the slug
    rule when every own slug does.
    """
    ordered = sorted(claims, key=lambda claim: claim.path)
    holders: dict[str, Path] = {}
    # A stable sort keeps path order among published notes and among drafts.
    for claim in sorted(ordered, key=lambda claim: not claim.published):
        if claim.own is not None:
            holders.setdefault(claim.own, claim.path)
    assigned: dict[Path, tuple[str, str | None]] = {}
    for claim in ordered:
        if claim.own is not None and holders[claim.own] == claim.path:
            assigned[claim.path] = (claim.own, None)
            continue
        base = claim.own or file_slug(claim.path.stem)
        holder = holders.get(base)
        if holder is None:
            holders[base] = claim.path
            assigned[claim.path] = (base, None)
            continue
        number = 2
        while f"{base}-{number}" in holders:
            number += 1
        slug = f"{base}-{number}"
        holders[slug] = claim.path
        reason = f"slug {base!r} is already used by {holder.as_posix()}; using {slug!r}"
        assigned[claim.path] = (slug, reason)
    return assigned


@dataclass(frozen=True)
class _MarkedNote:
    path: Path
    publish: bool
    properties: Mapping[object, object]
    body: bytes
    # In the site's zone, or the local one, with its offset.
    modified: datetime


def _marked_note(
    note: Path, relative: Path, data: bytes, zone: ZoneInfo | None
) -> _MarkedNote | None:
    marked = marked_parts(data)
    if marked is None:
        return None
    _require_utf8(data)
    publish, properties, body = marked
    modified = datetime.fromtimestamp(note.stat().st_mtime).astimezone(zone)
    return _MarkedNote(relative, publish, properties, body, modified)


def _preview_entries(
    notes: Iterable[_MarkedNote], now: datetime, zone: ZoneInfo | None
) -> tuple[list[PublishedNote], list[NoteFailure]]:
    ordered = sorted(notes, key=lambda note: note.path)
    previews = {
        note.path: preview_properties(
            note.properties, note.path.stem, now, draft=not note.publish, zone=zone
        )
        for note in ordered
    }
    slugs = assign_slugs(
        SlugClaim(note.path, previews[note.path][0].slug, note.publish)
        for note in ordered
    )
    entries: list[PublishedNote] = []
    warnings: list[NoteFailure] = []
    for note in ordered:
        preview, reasons = previews[note.path]
        slug, slug_reason = slugs[note.path]
        if slug_reason is not None:
            reasons = (*reasons, slug_reason)
        warnings.extend(NoteFailure(note.path, reason) for reason in reasons)
        if not note.publish:
            status = EntryStatus.DRAFT
        elif reasons:
            status = EntryStatus.INVALID
        else:
            status = EntryStatus.PUBLISHED
        page = PageProperties(
            title=preview.title,
            date=note.modified if preview.date is None else preview.date,
            slug=slug,
            tags=preview.tags,
        )
        entries.append(PublishedNote(note.path, page, note.body, status))
    return entries, warnings


def select_notes(
    vault: Path, now: datetime, drafts: bool = False, zone: ZoneInfo | None = None
) -> Selection:
    """Validates each selected note in `vault` and returns the published ones and all failures.

    A selected note is a regular `*.md` file outside `_site/` at the vault's root, with
    no path component starting with `.`. Symbolic links are neither followed nor selected.
    An unreadable note or directory is a failure, and so is a published note whose
    properties fail `validate_properties` at the time `now` in `zone`, with one failure
    per reason.
    Every note sharing a slug is a failure that names the others, even when the note has
    other failures. A note with any failure is not in `published`. `files` lists every
    regular file under the same rules as notes, whatever its suffix.

    With `drafts`, `published` also holds each `publish: false` note as a DRAFT and each
    published note with failures as INVALID, and `failures` are warnings. Their
    properties follow `preview_properties`: a missing or invalid date becomes the file's
    modification time in `zone`, and slugs follow `assign_slugs`. A note that is unreadable,
    has unusable front matter or is not UTF-8 is still absent with a failure.
    """
    published: list[PublishedNote] = []
    failures: list[NoteFailure] = []
    files: list[Path] = []
    slug_users: dict[str, list[Path]] = {}
    marked: list[_MarkedNote] = []

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
                data = note.read_bytes()
                if drafts:
                    found = _marked_note(note, relative, data, zone)
                    if found is not None:
                        marked.append(found)
                    continue
                parts = published_parts(data)
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
            page = validate_properties(properties, note.stem, now, zone)
            if isinstance(page, PageProperties):
                published.append(PublishedNote(relative, page, body))
            else:
                failures.extend(NoteFailure(relative, reason) for reason in page)
    if drafts:
        entries, warnings = _preview_entries(marked, now, zone)
        return Selection(
            published=tuple(entries),
            # A stable sort keeps each note's warnings in the order they were found.
            failures=tuple(
                sorted((*failures, *warnings), key=lambda failure: failure.path)
            ),
            files=tuple(sorted(files)),
        )
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


def read_bio(vault: Path) -> str | NoteFailure | None:
    """The body of `vault`'s `BIO_PATH`, after any front matter block, or None if absent.

    The front matter is never parsed, so nothing in it has an effect. Returns a failure
    naming `BIO_PATH` when the file is a symbolic link, is unreadable or has a body that
    is not UTF-8.
    """
    path = vault / BIO_PATH
    # The same rule as `load_config`: `_site/` content must come from the vault.
    if path.is_symlink():
        return NoteFailure(BIO_PATH, "is a symbolic link")
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        return NoteFailure(BIO_PATH, f"cannot read: {exc.strerror}")
    parts = split_note(data)
    body = data if parts is None else parts[1]
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return NoteFailure(BIO_PATH, "is not UTF-8")
