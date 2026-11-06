import pytest

from mdblog.markdown import (
    CodeMap,
    Heading,
    anchor_base,
    heading_key,
    headings,
    internal_destinations,
    is_external,
    remove_block_ids,
    remove_comments,
    split_wikilink,
    wikilink_text,
)
from notes import HEADINGS


def _code(text: str, needle: str) -> bool:
    start = text.index(needle)
    return CodeMap(text).overlaps(start, start + len(needle))


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        pytest.param("a\n```\nX\n```\nb\n", "X", id="fence"),
        pytest.param("a\n~~~py\nX\n~~~\n", "X", id="tilde-fence"),
        pytest.param("a\n```\nX\n", "X", id="unclosed-fence"),
        pytest.param("a\n\n    X\n", "X", id="indented"),
        pytest.param("> q\n> ```\n> X\n> ```\n", "X", id="fence-in-quote"),
        pytest.param("- item\n\n  ```\n  X\n  ```\n", "X", id="fence-in-list"),
        pytest.param("a `X` b\n", "X", id="span"),
        pytest.param("a ``x ` X`` b\n", "X", id="span-of-two"),
        pytest.param("a `x\nX` b\n", "X", id="span-across-lines"),
        pytest.param("# a `X`\n", "X", id="span-in-heading"),
        pytest.param("a\r\n```\r\nX\r\n```\r\n", "X", id="crlf"),
    ],
)
def test_code_map_finds_code(text: str, needle: str) -> None:
    assert _code(text, needle)


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        pytest.param("a\n```\nx\n```\nX\n", "X", id="after-fence"),
        pytest.param("para\n    X\n", "X", id="lazy-continuation"),
        pytest.param("a \\`X` b\n", "X", id="escaped-backtick"),
        pytest.param("a ``X` b\n", "X", id="unmatched-run"),
        pytest.param("a `x\n\nX` b\n", "X", id="span-cannot-cross-paragraphs"),
        pytest.param("# a `x\nX` b\n", "X", id="span-cannot-leave-heading"),
    ],
)
def test_code_map_leaves_prose(text: str, needle: str) -> None:
    assert not _code(text, needle)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("a %%hidden%% b\n", "a  b\n", id="inline"),
        pytest.param("a\n%%\nhidden\n%%\nb\n", "a\n\nb\n", id="across-lines"),
        pytest.param("a %%one%% b %%two%% c", "a  b  c", id="two"),
        pytest.param("a\n%% hidden\nmore\n", "a\n", id="unterminated"),
        pytest.param("a %%%% b", "a  b", id="empty"),
        pytest.param("a `%%` b %%x%%", "a `%%` b ", id="marker-in-span"),
        pytest.param("```\n%%\n```\n%%x%%", "```\n%%\n```\n", id="marker-in-fence"),
        pytest.param("%% a `x` b %% c", " c", id="code-inside-comment"),
    ],
)
def test_remove_comments(text: str, expected: str) -> None:
    assert remove_comments(text) == expected


@pytest.mark.parametrize(
    ("text", "expected", "ids"),
    [
        pytest.param("para ^abc\n", "para\n", {"abc"}, id="end-of-line"),
        pytest.param("para\n\n^tbl\n", "para\n\n\n", {"tbl"}, id="own-line"),
        pytest.param("  ^A-1  \r\nx", "\r\nx", {"a-1"}, id="indented-crlf-case"),
        pytest.param("## Heading ^h\n", "## Heading\n", {"h"}, id="heading"),
        pytest.param("> quote ^q", "> quote", {"q"}, id="quote-at-end"),
        pytest.param("x^2 and y\n", "x^2 and y\n", set(), id="no-space-before"),
        pytest.param("a ^b c\n", "a ^b c\n", set(), id="not-at-end"),
        pytest.param("a [^1]\n", "a [^1]\n", set(), id="footnote"),
        pytest.param("a `x ^b`\n", "a `x ^b`\n", set(), id="in-span"),
        pytest.param("```\nx ^b\n```\n", "```\nx ^b\n```\n", set(), id="in-fence"),
    ],
)
def test_remove_block_ids(text: str, expected: str, ids: set[str]) -> None:
    assert remove_block_ids(text) == (expected, frozenset(ids))


@pytest.mark.parametrize(
    ("inner", "expected"),
    [
        ("note", ("note", None)),
        (" note | alias ", ("note", "alias")),
        ("note|a|b", ("note", "a|b")),
        ("note\\|alias", ("note", "alias")),
        ("note|", ("note", "")),
    ],
)
def test_split_wikilink(inner: str, expected: tuple[str, str | None]) -> None:
    assert split_wikilink(inner) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Café & Über: 100%!", "café--über-100"),
        ("C++ and code stuff", "c-and-code-stuff"),
        ("Tab\there_under-score", "tabhere_under-score"),
        ("İstanbul ß", "istanbul-ß"),
        ("Ünï ½ ² ٣", "ünï---٣"),
        ("  padded  ", "padded"),
        ("!!!", ""),
    ],
)
def test_anchor_base_matches_hugo(text: str, expected: str) -> None:
    assert anchor_base(text) == expected


def test_headings_follow_hugos_ids() -> None:
    assert headings(HEADINGS) == (
        Heading("Café & Über: 100%!", "café--über-100"),
        Heading("Same", "same"),
        Heading("Same", "same-1"),
        Heading("C++ and code stuff", "c-and-code-stuff"),
        Heading("!!!", "heading"),
        Heading("Explicit", "same-2"),
        Heading("Same", "same-3"),
        Heading("Classed", "classed"),
        Heading("Braces {a, b}", "braces-a-b"),
        Heading("See Alias and target", "see-alias-and-target"),
        Heading("Sized a.png and a.png", "sized-apng-and-apng"),
        Heading("Alt alt words and a.png", "alt-alt-words-and-apng"),
        Heading(
            "Odd _lead_ <b>x</b> &amp; and _draft notes_",
            "odd-_lead_-bxb-amp-and-_draft-notes_",
        ),
        Heading("Auto  y", "auto--y"),
        Heading("raw html", "raw-html"),
        # Hugo builds a multi-line setext heading's ID from its last line.
        Heading("second line", "second-line"),
    )


@pytest.mark.parametrize(
    ("embed", "target", "alias", "expected"),
    [
        (True, "images/a.png", None, "a.png"),
        (True, "a.PNG#x", "300x200", "a.PNG"),
        (True, "a.png", "alt words", "alt words"),
        (False, "images/a.png", None, "images/a.png"),
        (True, "note", None, "note"),
        (True, "note#Heading", "alias", "alias"),
    ],
)
def test_wikilink_text(
    embed: bool, target: str, alias: str | None, expected: str
) -> None:
    assert wikilink_text(embed, target, alias) == expected


@pytest.mark.parametrize(
    ("link", "heading", "matches"),
    [
        ("Café & Über: 100%!", "Café & Über: 100%!", True),
        ("café über 100", "Café & Über: 100%!", True),
        ("a-b", "A B", True),
        ("Cafe Uber 100", "Café & Über: 100%!", False),
        ("ab", "A B", False),
    ],
)
def test_heading_key_ignores_case_and_punctuation(
    link: str, heading: str, matches: bool
) -> None:
    assert (heading_key(link) == heading_key(heading)) is matches


@pytest.mark.parametrize(
    ("destination", "external"),
    [
        ("https://example.test/", True),
        ("mailto:a@example.test", True),
        ("javascript:alert(1)", True),
        ("#section", True),
        ("note.md", False),
        ("/posts/x/", False),
        ("//example.test/x", False),
        ("", False),
    ],
)
def test_is_external(destination: str, external: bool) -> None:
    assert is_external(destination) is external


def test_internal_destinations_finds_inline_and_reference_links_and_images() -> None:
    text = (
        "[a](note.md) ![b](draft.png) [c](https://example.test/) [d](#top)\n"
        "[e][ref] ![f][img] <https://example.test/auto> <a@example.test>\n"
        "`[g](code.md)`\n"
        "\n"
        "    [h](indented.md)\n"
        "\n"
        "> [i](quoted%20name.md)\n"
        "\n"
        "[ref]: other.md\n"
        "[img]: picture.png\n"
        "[unused]: unused.md\n"
    )

    assert internal_destinations(text) == (
        "note.md",
        "draft.png",
        "other.md",
        "picture.png",
        "quoted%20name.md",
    )
