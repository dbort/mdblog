"""mdblog.markdown: finds code, comments, block IDs, headings, links and the summary callout in a note's Markdown.

Every function that scans a note's text leaves code untouched: fenced and indented code
blocks, including ones nested in quotes and lists, and inline code spans.
"""

import bisect
import itertools
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import override

from markdown_it import MarkdownIt
from markdown_it.token import Token

COMMENT_MARKER = "%%"
# Obsidian's block ID: letters, digits and hyphens after a caret that starts the line or
# follows whitespace, at the end of the line.
BLOCK_ID = re.compile(
    r"(?:(?<![^\r\n])|[ \t]+)\^([A-Za-z0-9-]+)[ \t]*(?=\r\n|\r|\n|\Z)"
)
WIKILINK = re.compile(r"(!?)\[\[([^\[\]\r\n]+)\]\]")
IMAGE_SUFFIXES = frozenset(
    (".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp")
)
# `![[image.png|300]]` sets a width and `|300x200` a width and height.
IMAGE_SIZE = re.compile(r"(\d+)(?:x(\d+))?")
URL_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
# Goldmark's attribute syntax, which Hugo enables for headings: `## Title {#id .class}`.
# Braces holding anything else stay in the heading's text.
_ATTRIBUTE = r"""(?:#[^\s#.{}]+|\.[^\s#.{}]+|[A-Za-z_:][\w.:-]*=(?:"[^"]*"|'[^']*'|[^\s"'{}]+))"""
HEADING_ATTRIBUTES = re.compile(rf"\s*\{{\s*((?:{_ATTRIBUTE}\s*)+)\}}\s*\Z")
EXPLICIT_ID = re.compile(r"(?:^|\s)#([^\s#.{}]+)")


class _Parser(MarkdownIt):
    """A CommonMark parser that reports every destination exactly as written."""

    def __init__(self) -> None:
        super().__init__("commonmark")

    @override
    def validateLink(self, url: str) -> bool:
        # The default drops `javascript:` and similar links, which then go unreported.
        return True

    @override
    def normalizeLink(self, url: str) -> str:
        # The default percent-encodes, and a failure message should quote the note.
        return url


_PARSER = _Parser()
# Hugo renders GFM tables, which `_PARSER` reads as paragraphs.
_TABLE_PARSER = _Parser().enable("table")


def _line_starts(text: str) -> list[int]:
    # markdown-it's line numbers count \r\n, \r and \n, and str.splitlines counts more.
    return [0, *(match.end() for match in re.finditer(r"\r\n|\r|\n", text))]


def _code_span_ranges(text: str, start: int, end: int) -> list[tuple[int, int]]:
    # CommonMark: a run of n backticks opens a span that the next run of exactly n
    # closes. A backslash escapes a backtick only outside a span.
    ranges: list[tuple[int, int]] = []
    position = start
    while position < end:
        char = text[position]
        if char == "\\":
            position += 2
            continue
        if char != "`":
            position += 1
            continue
        run_end = position
        while run_end < end and text[run_end] == "`":
            run_end += 1
        length = run_end - position
        search = run_end
        closing = None
        while search < end:
            if text[search] != "`":
                search += 1
                continue
            close_end = search
            while close_end < end and text[close_end] == "`":
                close_end += 1
            if close_end - search == length:
                closing = close_end
                break
            search = close_end
        if closing is None:
            position = run_end
        else:
            ranges.append((position, closing))
            position = closing
    return ranges


class CodeMap:
    """The character ranges of `text` that hold code, sorted and non-overlapping."""

    def __init__(self, text: str) -> None:
        starts = [*_line_starts(text), len(text)]

        def offset(line: int) -> int:
            return starts[min(line, len(starts) - 1)]

        ranges: list[tuple[int, int]] = []
        for token in _PARSER.parse(text):
            if token.map is None:
                continue
            first, last = token.map
            if token.type in ("fence", "code_block"):
                ranges.append((offset(first), offset(last)))
            elif token.type == "inline":
                # Code spans exist only in inline content, and never cross out of the
                # paragraph or heading that holds them.
                ranges.extend(_code_span_ranges(text, offset(first), offset(last)))
        ranges.sort()
        self._starts = [start for start, _ in ranges]
        self._ends = [end for _, end in ranges]

    def overlaps(self, start: int, end: int) -> bool:
        """Whether any code range shares a character with `text[start:end]`."""
        index = bisect.bisect_left(self._starts, end) - 1
        return index >= 0 and self._ends[index] > start


def remove_comments(text: str) -> str:
    """`text` without its `%%` comments, which may span lines.

    A `%%` with no closing marker removes the rest of the text, because leaking a private
    aside is worse than losing text. A marker that overlaps
    code is literal.
    """
    code = CodeMap(text)
    pieces: list[str] = []
    kept_from = 0
    opening: int | None = None
    for match in re.finditer(re.escape(COMMENT_MARKER), text):
        if code.overlaps(match.start(), match.end()):
            continue
        if opening is None:
            opening = match.start()
        else:
            pieces.append(text[kept_from:opening])
            kept_from = match.end()
            opening = None
    pieces.append(text[kept_from:opening])
    return "".join(pieces)


def remove_block_ids(text: str) -> tuple[str, frozenset[str]]:
    """`text` without trailing `^block-id` markers, and the IDs removed, casefolded.

    A marker is removed with the whitespace before it, so a marker alone on its line
    leaves an empty line. Line endings are kept.
    """
    code = CodeMap(text)
    ids: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        if code.overlaps(match.start(), match.end()):
            return match[0]
        ids.add(match[1].casefold())
        return ""

    return BLOCK_ID.sub(replace, text), frozenset(ids)


def split_wikilink(inner: str) -> tuple[str, str | None]:
    """The target and the alias, if any, of the text between `[[` and `]]`.

    The alias follows the first `\\|`, which a table needs, or otherwise the first `|`.
    Both parts are stripped of surrounding whitespace.
    """
    separator = "\\|" if "\\|" in inner else "|"
    target, found, alias = inner.partition(separator)
    return target.strip(), alias.strip() if found else None


def wikilink_text(embed: bool, target: str, alias: str | None) -> str:
    """The text a converted wikilink shows, from its parts as `split_wikilink` returns them.

    An image embed shows its alt text: an alias that is not a size, or otherwise the
    file name of the target. Every other link shows the alias, or otherwise the target.
    """
    name = target.partition("#")[0].strip().rsplit("/", 1)[-1]
    if embed and PurePosixPath(name).suffix.casefold() in IMAGE_SUFFIXES:
        if alias and IMAGE_SIZE.fullmatch(alias) is None:
            return alias
        return name
    return alias or target


def escape_text(text: str) -> str:
    """`text` with every ASCII punctuation character backslash-escaped, so Markdown
    renders it literally: `_a_` stays underscores and `<b>` stays visible."""
    return re.sub(r"([!-/:-@\[-`{-~])", r"\\\1", text)


def _with_wikilinks_as_text(text: str) -> str:
    # Hugo reads a heading after conversion, where a wikilink is its escaped link text.
    code = CodeMap(text)

    def replace(match: re.Match[str]) -> str:
        if code.overlaps(match.start(), match.end()):
            return match[0]
        return escape_text(wikilink_text(match[1] == "!", *split_wikilink(match[2])))

    return WIKILINK.sub(replace, text)


def _plain_text(children: Sequence[Token]) -> str:
    # Mirrors the text Hugo 0.169 builds a heading ID from: an autolink and raw HTML add
    # nothing, an image adds its alt text, and a line break discards the text before it.
    text = ""
    in_autolink = False
    for child in children:
        if child.type == "link_open" and child.markup == "autolink":
            in_autolink = True
        elif child.type == "link_close":
            in_autolink = False
        elif in_autolink:
            continue
        elif child.type in ("text", "code_inline"):
            text += child.content
        elif child.type == "image":
            text += _plain_text(child.children or [])
        elif child.type in ("softbreak", "hardbreak"):
            text = ""
    return text


@dataclass(frozen=True)
class Heading:
    """One heading of a note, in document order."""

    # The heading's text as a reader sees it, with a wikilink as its `wikilink_text`.
    text: str
    # The `id` Hugo gives the rendered heading.
    anchor: str


def anchor_base(text: str) -> str:
    """The ID Hugo's `github` style generates from heading text, before deduplication.

    Spaces and hyphens become hyphens, letters lowercase, and digits and underscores
    stay. Every other character is dropped.
    """
    characters: list[str] = []
    for char in text.strip():
        if char in "- ":
            characters.append("-")
        elif char == "_" or char.isalpha() or unicodedata.category(char) == "Nd":
            # Go lowercases one rune to one rune, and Python lowercases İ to two.
            characters.append(char.lower()[0])
    return "".join(characters)


def headings(text: str) -> tuple[Heading, ...]:
    """Every heading in `text` with the ID Hugo gives it, in document order.

    An explicit `{#id}` is used as written. Other IDs come from `anchor_base`, with
    `heading` for an empty result and `-1`, `-2` and so on appended to avoid any ID
    already given.
    """
    tokens = _PARSER.parse(_with_wikilinks_as_text(text))
    found: list[Heading] = []
    given: set[str] = set()
    for opening, inline in itertools.pairwise(tokens):
        if opening.type != "heading_open" or inline.type != "inline":
            continue
        plain = _plain_text(inline.children or [])
        if not plain.strip():
            # Hugo gives an empty heading no ID.
            continue
        explicit = None
        attributes = HEADING_ATTRIBUTES.search(plain)
        if attributes is not None:
            plain = plain[: attributes.start()]
            explicit = EXPLICIT_ID.search(attributes[1])
        if explicit is not None:
            anchor = explicit[1]
        else:
            base = anchor_base(plain) or "heading"
            anchor = base
            suffix = 1
            while anchor in given:
                anchor = f"{base}-{suffix}"
                suffix += 1
        given.add(anchor)
        found.append(Heading(plain.strip(), anchor))
    return tuple(found)


def heading_key(text: str) -> str:
    """The form in which a link's heading matches a note's heading.

    Case is ignored and each run of characters other than letters and digits counts as
    one space, so `[[note#Café Über]]` matches the heading `Café & Über:`.
    """
    return " ".join(
        "".join(char if char.isalnum() else " " for char in text.casefold()).split()
    )


def _destinations(tokens: Sequence[Token]) -> list[str]:
    found: list[str] = []
    for token in tokens:
        attribute = {"link_open": "href", "image": "src"}.get(token.type)
        if attribute is not None:
            found.append(str(token.attrGet(attribute) or ""))
        if token.children:
            found.extend(_destinations(token.children))
    return found


def is_external(destination: str) -> bool:
    """Whether a Markdown destination has a URL scheme or starts with `#`."""
    return destination.startswith("#") or URL_SCHEME.match(destination) is not None


def internal_destinations(text: str) -> tuple[str, ...]:
    """The destination of every standard link and image in `text` that `is_external` rejects.

    Inline and reference-style links both count, and code never does. In document order.
    """
    return tuple(
        destination
        for destination in _destinations(_PARSER.parse(text))
        if not is_external(destination)
    )


# Hugo's rule for a callout's first line, with the type fixed: `[!summary]` in any case,
# then any fold sign and title, which a lede ignores.
LEDE_MARKER = re.compile(r"\[!summary\].*", re.IGNORECASE)
# One line's quote marker, as CommonMark strips it. A lazy continuation line has none.
_QUOTE_MARKER = re.compile(r" {0,3}> ?")
FOOTNOTE_REFERENCE = re.compile(r"\[\^[^\[\]\r\n]+\]")
_LEDE_BLOCKS = {
    "bullet_list_open": "a list",
    "ordered_list_open": "a list",
    "heading_open": "a heading",
    "fence": "a code block",
    "code_block": "a code block",
    "table_open": "a table",
    "hr": "a thematic break",
    "blockquote_open": "a quote or callout",
    "html_block": "an HTML block",
}


def _split_lines(text: str) -> list[str]:
    starts = [*_line_starts(text), len(text)]
    return [text[start:end] for start, end in itertools.pairwise(starts)]


def _unquote(lines: Sequence[str]) -> str:
    return "".join(_QUOTE_MARKER.sub("", line, count=1) for line in lines)


@dataclass(frozen=True)
class LedeCallout:
    """A summary callout that is the first block of a note's text."""

    # The callout's first line in that text.
    start: int
    # The line after the callout's last line.
    end: int
    # The first line of the content, after the line holding `LEDE_MARKER`.
    content_start: int
    # The callout's content without quote markers or surrounding whitespace, or None
    # when it is blank.
    lede: str | None
    # Why the content cannot be a lede, in document order. Empty for a usable lede.
    failures: tuple[str, ...]

    def split(self, text: str) -> tuple[str, str | None]:
        """`text` without the callout's lines, and the content of those lines as `lede` is.

        `text` must have the line structure of the text the callout was found in, which
        holds for that text after wikilink conversion, since no converted wikilink
        spans or adds a line.
        """
        lines = _split_lines(text)
        body = "".join(lines[: self.start] + lines[self.end :])
        content = _unquote(lines[self.content_start : self.end]).strip()
        return body, content or None


def _lede_failures(content: str) -> list[str]:
    failures: list[str] = []
    for token in _TABLE_PARSER.parse(content):
        kind = _LEDE_BLOCKS.get(token.type)
        if token.level == 0 and kind is not None:
            failures.append(
                f"summary callout holds {kind}; it may hold only paragraphs of text"
            )
        for child in token.children or []:
            if child.type == "image":
                failures.append(
                    f"summary callout holds the image {child.attrGet('src')!r}"
                )
            elif child.type == "link_open":
                destination = str(child.attrGet("href") or "")
                if destination.startswith("#"):
                    failures.append(
                        f"summary callout links to {destination!r}, which would point "
                        "into the page listing it; use a wikilink like [[#heading]]"
                    )
    code = CodeMap(content)
    for match in WIKILINK.finditer(content):
        if match[1] and not code.overlaps(match.start(), match.end()):
            failures.append(f"summary callout holds the embed {match[0]}")
    for match in FOOTNOTE_REFERENCE.finditer(content):
        if not code.overlaps(match.start(), match.end()):
            failures.append(f"summary callout holds the footnote reference {match[0]}")
    return failures


def find_lede(text: str) -> LedeCallout | None:
    """The summary callout that is `text`'s first block, or None if the first block is
    anything else.

    The callout is a quote whose first paragraph's first line, after its quote marker,
    starts with `LEDE_MARKER`. Its content is everything after that line, and is a usable lede only
    when it holds paragraphs of inline Markdown with no image, embed, footnote
    reference or link to a `#` destination.
    """
    tokens = _PARSER.parse(text)
    if len(tokens) < 2 or tokens[0].type != "blockquote_open":
        return None
    if tokens[0].map is None or tokens[1].type != "paragraph_open":
        return None
    start, end = tokens[0].map
    # Blank quoted lines can come before the paragraph that holds the marker.
    marker = start if tokens[1].map is None else tokens[1].map[0]
    lines = _split_lines(text)
    if LEDE_MARKER.match(_unquote(lines[marker : marker + 1])) is None:
        return None
    content = _unquote(lines[marker + 1 : end])
    failures = tuple(_lede_failures(content))
    return LedeCallout(start, end, marker + 1, content.strip() or None, failures)
