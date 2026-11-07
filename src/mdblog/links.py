"""mdblog.links: resolves wikilinks and embeds against the vault and converts them to Markdown."""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit

from mdblog.config import SITE_DIR
from mdblog.markdown import (
    IMAGE_SIZE,
    IMAGE_SUFFIXES,
    WIKILINK,
    CodeMap,
    escape_text,
    heading_key,
    headings,
    internal_destinations,
    remove_block_ids,
    remove_comments,
    split_wikilink,
    wikilink_text,
)
from mdblog.properties import EntryStatus
from mdblog.publish import (
    BIO_PATH,
    NOTE_SUFFIX,
    NoteFailure,
    PublishedNote,
    Selection,
)

# The default render-image hook reads these and removes them from `src`.
WIDTH_PARAMETER = "mdblog-width"
HEIGHT_PARAMETER = "mdblog-height"


class LinkError(Exception):
    """A wikilink or embed cannot be converted; the message gives the reason."""


@dataclass(frozen=True)
class LinkTarget:
    """What a link to one published note can reach."""

    slug: str
    # Maps `heading_key` of each heading to the anchor of the first heading with it.
    anchors: Mapping[str, str]
    # Casefolded.
    block_ids: frozenset[str]


@dataclass(frozen=True)
class LinkIndex:
    """Every selected file a wikilink may name, and what each published note offers."""

    # Casefolded vault-relative POSIX path to every file with that path.
    by_path: Mapping[str, tuple[Path, ...]]
    # Casefolded file name to every file with that name.
    by_name: Mapping[str, tuple[Path, ...]]
    published: Mapping[Path, LinkTarget]
    # Notes that would publish but failed validation.
    failed: frozenset[Path]


def build_index(
    files: Iterable[Path],
    published: Mapping[Path, LinkTarget],
    failed: Iterable[Path] = (),
) -> LinkIndex:
    """A `LinkIndex` over `files`, which are relative to the vault."""
    by_path: dict[str, list[Path]] = {}
    by_name: dict[str, list[Path]] = {}
    for path in sorted(files):
        by_path.setdefault(path.as_posix().casefold(), []).append(path)
        by_name.setdefault(path.name.casefold(), []).append(path)
    return LinkIndex(
        by_path={key: tuple(paths) for key, paths in by_path.items()},
        by_name={key: tuple(paths) for key, paths in by_name.items()},
        published=published,
        failed=frozenset(failed),
    )


def _vault_path(parts: Iterable[str]) -> str:
    kept: list[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not kept:
                raise LinkError("resolves outside the vault")
            kept.pop()
        else:
            kept.append(part)
    if any(part.startswith(".") for part in kept) or (
        kept and kept[0].casefold() == SITE_DIR
    ):
        raise LinkError(f"targets a path under {SITE_DIR}/ or a hidden folder")
    return "/".join(kept)


def _lookup(table: Mapping[str, tuple[Path, ...]], key: str) -> Path:
    folded = key.casefold()
    exact = table.get(folded, ())
    notes = [
        path
        for path in (*table.get(folded + NOTE_SUFFIX, ()), *exact)
        if path.suffix == NOTE_SUFFIX
    ]
    candidates = notes or list(exact)
    if not candidates:
        raise LinkError("matches no note or file")
    if len(candidates) > 1:
        names = ", ".join(path.as_posix() for path in candidates)
        raise LinkError(f"matches more than one file: {names}")
    return candidates[0]


def resolve(target: str, note: Path, index: LinkIndex) -> Path:
    """The vault-relative path of the file `target` names from `note`.

    A target starting with `./` or `../` is a path from the note's folder, any other
    target holding `/` is a path from the vault root, and anything else is a file name
    that must be unique across the vault. Case is ignored, and a note named with or
    without `.md` wins over another file. Raises `LinkError` when nothing or more than
    one file matches, or the path leaves the vault or enters `_site/` or a hidden folder.
    """
    if target.startswith(("./", "../")):
        key = _vault_path(
            [*PurePosixPath(note.as_posix()).parent.parts, *target.split("/")]
        )
        return _lookup(index.by_path, key)
    if "/" in target:
        return _lookup(index.by_path, _vault_path(target.split("/")))
    return _lookup(index.by_name, target)


def _fragment(subpath: str, path: Path, target: LinkTarget) -> str:
    # Obsidian nests headings as `note#a#b`, and only the last names the target.
    segments = [segment.strip() for segment in subpath.split("#") if segment.strip()]
    if not segments:
        return ""
    last = segments[-1]
    if last.startswith("^"):
        if last[1:].casefold() not in target.block_ids:
            raise LinkError(f"{path.as_posix()} has no block {last}")
        # Hugo gives a block no ID to link to, so the link goes to the top of the page.
        return ""
    anchor = target.anchors.get(heading_key(last))
    if anchor is None:
        raise LinkError(f"{path.as_posix()} has no heading {last!r}")
    return "#" + quote(anchor, safe="")


@dataclass(frozen=True)
class Converted:
    """One note's text with its wikilinks converted."""

    text: str
    # Vault-relative paths of the images the text uses, sorted, each once.
    images: tuple[Path, ...]
    # One reason per failed link or embed in document order, then one per file name
    # that several images share.
    failures: tuple[str, ...]


@dataclass
class _NoteContext:
    path: Path
    page_url: str
    index: LinkIndex
    base_path: str
    images: set[Path]

    def note_url(self, slug: str) -> str:
        return f"{self.base_path}/posts/{slug}/"

    def convert(self, embed: bool, inner: str) -> str:
        target, alias = split_wikilink(inner)
        name, _, subpath = target.partition("#")
        name = name.strip()
        if name:
            path = resolve(name, self.path, self.index)
        elif subpath.strip():
            path = self.path
        else:
            raise LinkError("names no note")
        if path.suffix == NOTE_SUFFIX:
            return self._note_link(path, subpath, alias or target)
        if path.suffix.casefold() not in IMAGE_SUFFIXES:
            raise LinkError(f"{path.as_posix()} is not a note or a supported image")
        self.images.add(path)
        url = self.page_url + quote(path.name)
        if not embed:
            return f"[{escape_text(alias or target)}]({url})"
        size = IMAGE_SIZE.fullmatch(alias or "")
        if size is not None:
            url += f"?{WIDTH_PARAMETER}={size[1]}"
            if size[2] is not None:
                url += f"&{HEIGHT_PARAMETER}={size[2]}"
        return f"![{escape_text(wikilink_text(True, target, alias))}]({url})"

    def _note_link(self, path: Path, subpath: str, text: str) -> str:
        target = self.index.published.get(path)
        if target is None:
            if path in self.index.failed:
                raise LinkError(f"{path.as_posix()} has failures of its own")
            raise LinkError(f"{path.as_posix()} is not published")
        url = self.note_url(target.slug) + _fragment(subpath, path, target)
        return f"[{escape_text(text)}]({url})"


def convert_wikilinks(
    text: str, note: Path, page_url: str, index: LinkIndex, base_path: str
) -> Converted:
    """`text` with each wikilink and embed outside code replaced by a Markdown link or image.

    `note` is the vault-relative path of the file holding `text`, and `page_url` the
    root-relative URL of the page it renders on, ending in `/`, under which its images
    are served. A link to a note is root-relative and starts with `base_path`, which has
    no trailing slash. A link that fails stays as written and adds a reason naming it.
    Two different images sharing a file name add a reason, because they would share one
    URL.
    """
    code = CodeMap(text)
    context = _NoteContext(note, page_url, index, base_path, set())
    failures: list[str] = []

    def replace(match: re.Match[str]) -> str:
        if code.overlaps(match.start(), match.end()):
            return match[0]
        try:
            return context.convert(match[1] == "!", match[2])
        except LinkError as exc:
            failures.append(f"{match[0]}: {exc}")
            return match[0]

    converted = WIKILINK.sub(replace, text)
    by_name: dict[str, list[Path]] = {}
    for image in sorted(context.images):
        by_name.setdefault(image.name.casefold(), []).append(image)
    for paths in by_name.values():
        if len(paths) > 1:
            names = ", ".join(path.as_posix() for path in paths)
            failures.append(f"uses different images with one file name: {names}")
    return Converted(converted, tuple(sorted(context.images)), tuple(failures))


@dataclass(frozen=True)
class Page:
    """A published note ready to write into its page bundle."""

    note: PublishedNote
    # The converted Markdown body, UTF-8.
    body: bytes
    # Vault-relative paths of the images to copy into the bundle.
    images: tuple[Path, ...]


@dataclass(frozen=True)
class Bio:
    """The site's bio ready to write as the home page's content."""

    # The converted Markdown body, UTF-8.
    body: bytes
    # Vault-relative paths of the images to copy beside the home page.
    images: tuple[Path, ...]


@dataclass(frozen=True)
class Conversion:
    """The pages converted from a selection, the bio, and every link failure."""

    # In the selection's order. A page whose note failed is absent outside draft mode.
    pages: tuple[Page, ...]
    # None when there is no bio, or outside draft mode, when it has failures.
    bio: Bio | None
    # Grouped by note in the selection's order, then the bio's. Within a file, internal
    # Markdown links come before wikilinks, each in document order.
    failures: tuple[NoteFailure, ...]


def base_path(base_url: str) -> str:
    """The path of `base_url` without a trailing slash, empty for a site at the root."""
    return urlsplit(base_url).path.rstrip("/")


def _convert_body(
    text: str, path: Path, page_url: str, index: LinkIndex, prefix: str
) -> tuple[Converted, list[str]]:
    reasons = [
        f"Markdown link to {destination!r} is internal; use a wikilink"
        for destination in internal_destinations(text)
    ]
    converted = convert_wikilinks(text, path, page_url, index, prefix)
    reasons.extend(converted.failures)
    return converted, reasons


def convert_notes(
    selection: Selection,
    base_url: str,
    bio: str | None = None,
    drafts: bool = False,
) -> Conversion:
    """Every published note in `selection`, and `bio`, with Obsidian syntax converted for Hugo.

    Comments are removed first, so a heading or block ID inside one is no link target,
    and block IDs next, so none stays in a heading's text. Then a standard Markdown
    link or image to an internal destination fails, and wikilinks convert against
    every file in the selection. Notes outside `selection.published`, which holds the
    drafts too when the selection was made with `drafts`, are never read. `bio` is the
    text of `BIO_PATH`, which renders on the home page and is no link target itself;
    its failures name `BIO_PATH`.

    With `drafts`, a page or bio with failures is kept with each failed link as
    written, its failures are still returned, and a PUBLISHED note among them becomes
    INVALID.
    """
    prefix = base_path(base_url)
    texts: dict[Path, str] = {}
    targets: dict[Path, LinkTarget] = {}
    for note in selection.published:
        text, block_ids = remove_block_ids(remove_comments(note.body.decode("utf-8")))
        texts[note.path] = text
        anchors: dict[str, str] = {}
        for heading in headings(text):
            anchors.setdefault(heading_key(heading.text), heading.anchor)
        targets[note.path] = LinkTarget(note.page.slug, anchors, block_ids)
    index = build_index(
        selection.files, targets, (failure.path for failure in selection.failures)
    )
    pages: list[Page] = []
    failures: list[NoteFailure] = []
    for note in selection.published:
        converted, reasons = _convert_body(
            texts[note.path],
            note.path,
            f"{prefix}/posts/{note.page.slug}/",
            index,
            prefix,
        )
        failures.extend(NoteFailure(note.path, reason) for reason in reasons)
        if reasons and not drafts:
            continue
        if reasons and note.status is EntryStatus.PUBLISHED:
            note = replace(note, status=EntryStatus.INVALID)
        pages.append(Page(note, converted.text.encode("utf-8"), converted.images))
    converted_bio = None
    if bio is not None:
        text, _ = remove_block_ids(remove_comments(bio))
        converted, reasons = _convert_body(text, BIO_PATH, f"{prefix}/", index, prefix)
        failures.extend(NoteFailure(BIO_PATH, reason) for reason in reasons)
        if drafts or not reasons:
            converted_bio = Bio(converted.text.encode("utf-8"), converted.images)
    return Conversion(tuple(pages), converted_bio, tuple(failures))
