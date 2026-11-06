import datetime as dt
from pathlib import Path

import pytest

from mdblog.links import IMAGE_SUFFIXES, Conversion, Page, base_path, convert_notes
from mdblog.publish import BIO_PATH, select_notes
from notes import published_text

NOW = dt.datetime(2026, 6, 15, 12, 0, tzinfo=dt.UTC)
SOURCE = "notes/source.md"
TARGET = (
    "# Café & Über: 100%!\n"
    "## Outer\n"
    "### Target Heading\n"
    "A paragraph ^blk\n"
    "%%\n"
    "## Commented Heading\n"
    "commented ^gone\n"
    "%%\n"
)


def _write(vault: Path, relative: str, data: str | bytes = "") -> Path:
    path = vault / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return path


def _note(vault: Path, relative: str, body: str, slug: str | None = None) -> None:
    _write(vault, relative, published_text(slug or Path(relative).stem, body=body))


def _vault(root: Path, source_body: str) -> Path:
    """A vault whose `notes/source.md` holds `source_body`, with targets for its links."""
    _note(root, SOURCE, f"## Own Heading\nmine ^mine\n{source_body}", slug="source")
    _note(root, "notes/target.md", TARGET)
    _note(root, "folder/deep.md", "")
    _note(root, "top.md", "")
    _note(root, "_draft notes_.md", "", slug="draft-notes")
    _write(root, "drafts/draft.md", "---\npublish: false\n---\nDRAFT-TEXT\n")
    _write(root, "broken.md", "---\npublish: true\nslug: broken\n---\n")
    _write(root, "images/a.png", b"PNG-A")
    _write(root, "images/my pic.png", b"PNG-SPACE")
    _write(root, "paper.pdf", b"PDF")
    _write(root, "clip.mp4", b"MP4")
    _write(root, "_site/mdblog.toml", "")
    _write(root, "_site/site-image.png", b"PNG")
    _write(root, ".hidden/secret.png", b"PNG")
    return root


def _convert(vault: Path, base_url: str = "https://example.test/") -> Conversion:
    return convert_notes(select_notes(vault, NOW), base_url)


def _page(conversion: Conversion, slug: str = "source") -> Page:
    for page in conversion.pages:
        if page.note.page.slug == slug:
            return page
    raise AssertionError(f"no page {slug!r}: {conversion.failures}")


def _body(conversion: Conversion, slug: str = "source") -> str:
    return _page(conversion, slug).body.decode("utf-8")


def _link_failures(conversion: Conversion) -> list[str]:
    return [
        f"{failure.path.as_posix()}: {failure.reason}"
        for failure in conversion.failures
        # broken.md fails validation, which select_notes reports.
        if failure.path.as_posix() != "broken.md"
    ]


def _converted(
    tmp_path: Path, text: str, base_url: str = "https://example.test/"
) -> str:
    conversion = _convert(_vault(tmp_path, text + "\n"), base_url)
    assert _link_failures(conversion) == []
    return _body(conversion).removeprefix("## Own Heading\nmine\n").removesuffix("\n")


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        ("[[target]]", "[target](/posts/target/)"),
        ("[[target|the alias]]", "[the alias](/posts/target/)"),
        ("[[TARGET]]", "[TARGET](/posts/target/)"),
        ("[[target.md]]", "[target\\.md](/posts/target/)"),
        ("[[ target ]]", "[target](/posts/target/)"),
        ("[[folder/deep]]", "[folder\\/deep](/posts/deep/)"),
        ("[[Folder/Deep.md]]", "[Folder\\/Deep\\.md](/posts/deep/)"),
        ("[[../top]]", "[\\.\\.\\/top](/posts/top/)"),
        ("[[./target]]", "[\\.\\/target](/posts/target/)"),
        (
            "[[target#Target Heading]]",
            "[target\\#Target Heading](/posts/target/#target-heading)",
        ),
        ("[[target#target heading|alias]]", "[alias](/posts/target/#target-heading)"),
        (
            "[[target#Outer#Target Heading]]",
            "[target\\#Outer\\#Target Heading](/posts/target/#target-heading)",
        ),
        (
            "[[target#Café & Über: 100%!]]",
            "[target\\#Café \\& Über\\: 100\\%\\!](/posts/target/#caf%C3%A9--%C3%BCber-100)",
        ),
        ("[[#Own Heading]]", "[\\#Own Heading](/posts/source/#own-heading)"),
        ("[[target#^blk]]", "[target\\#\\^blk](/posts/target/)"),
        ("[[target#^BLK|alias]]", "[alias](/posts/target/)"),
        ("[[#^mine]]", "[\\#\\^mine](/posts/source/)"),
        ("![[target]]", "[target](/posts/target/)"),
        (
            "![[target#Target Heading]]",
            "[target\\#Target Heading](/posts/target/#target-heading)",
        ),
        ("| [[target\\|alias]] | x |", "| [alias](/posts/target/) | x |"),
        ("[[target|back\\slash\\]]", "[back\\\\slash\\\\](/posts/target/)"),
        (
            "[[_draft notes_|<b> *c* -- d]]",
            "[\\<b\\> \\*c\\* \\-\\- d](/posts/draft-notes/)",
        ),
        ("[[_draft notes_]]", "[\\_draft notes\\_](/posts/draft-notes/)"),
    ],
)
def test_wikilinks_become_markdown_links(
    tmp_path: Path, link: str, expected: str
) -> None:
    assert _converted(tmp_path, link) == expected


@pytest.mark.parametrize(
    ("embed", "expected"),
    [
        ("![[a.png]]", "![a\\.png](/posts/source/a.png)"),
        ("[[a.png]]", "[a\\.png](/posts/source/a.png)"),
        ("[[a.png|the file]]", "[the file](/posts/source/a.png)"),
        ("![[images/a.png]]", "![a\\.png](/posts/source/a.png)"),
        ("![[A.PNG]]", "![A\\.PNG](/posts/source/a.png)"),
        ("![[a.png|300]]", "![a\\.png](/posts/source/a.png?mdblog-width=300)"),
        (
            "![[a.png|300x200]]",
            "![a\\.png](/posts/source/a.png?mdblog-width=300&mdblog-height=200)",
        ),
        ("![[a.png|some text]]", "![some text](/posts/source/a.png)"),
        ("![[a.png|300 wide]]", "![300 wide](/posts/source/a.png)"),
        ("![[my pic.png]]", "![my pic\\.png](/posts/source/my%20pic.png)"),
    ],
)
def test_image_embeds_and_links(tmp_path: Path, embed: str, expected: str) -> None:
    assert _converted(tmp_path, embed) == expected


@pytest.mark.parametrize("suffix", sorted(IMAGE_SUFFIXES))
def test_every_image_suffix_is_supported_in_any_case(
    tmp_path: Path, suffix: str
) -> None:
    vault = _vault(tmp_path, f"![[lower{suffix}]] ![[upper{suffix.upper()}]]\n")
    _write(vault, f"lower{suffix}", b"IMG")
    _write(vault, f"upper{suffix.upper()}", b"IMG")

    conversion = _convert(vault)

    assert _link_failures(conversion) == []
    assert [p.as_posix() for p in _page(conversion).images] == [
        f"lower{suffix}",
        f"upper{suffix.upper()}",
    ]


def test_a_page_lists_each_image_it_uses_once(tmp_path: Path) -> None:
    vault = _vault(
        tmp_path, "![[a.png]] [[a.png]] ![[images/A.png|20]] ![[my pic.png]]\n"
    )

    conversion = _convert(vault)

    source = _page(conversion)
    assert [p.as_posix() for p in source.images] == [
        "images/a.png",
        "images/my pic.png",
    ]
    assert all(page.images == () for page in conversion.pages if page is not source)


@pytest.mark.parametrize(
    ("base_url", "page", "image"),
    [
        (
            "https://example.test/blog/",
            "/blog/posts/target/",
            "/blog/posts/source/a.png",
        ),
        (
            "https://example.test/blog",
            "/blog/posts/target/",
            "/blog/posts/source/a.png",
        ),
        ("https://example.test/", "/posts/target/", "/posts/source/a.png"),
        ("https://example.test", "/posts/target/", "/posts/source/a.png"),
    ],
)
def test_urls_start_with_the_base_path(
    tmp_path: Path, base_url: str, page: str, image: str
) -> None:
    converted = _converted(tmp_path, "[[target]] ![[a.png]]", base_url)

    assert converted == f"[target]({page}) ![a\\.png]({image})"


def test_base_path_drops_the_trailing_slash() -> None:
    assert base_path("https://example.test/a/b/") == "/a/b"
    assert base_path("https://example.test") == ""


def test_a_note_wins_over_an_image_with_the_same_name(tmp_path: Path) -> None:
    vault = _vault(tmp_path, "[[photo.png]] [[v1.2 notes]]\n")
    _note(vault, "photo.png.md", "", slug="photo-note")
    _write(vault, "photo.png", b"PNG")
    _note(vault, "v1.2 notes.md", "", slug="version-notes")

    converted = _body(_convert(vault))

    assert (
        "[photo\\.png](/posts/photo-note/) [v1\\.2 notes](/posts/version-notes/)"
        in converted
    )


@pytest.mark.parametrize(
    ("link", "problem"),
    [
        ("[[missing]]", "matches no note or file"),
        ("![[missing.png]]", "matches no note or file"),
        ("[[dup]]", "matches more than one file: a/dup.md, b/dup.md"),
        ("[[Case]]", "matches more than one file: a/case.md, b/CASE.md"),
        ("[[a.png]]", "matches more than one file: images/a.png, other/a.png"),
        ("[[../../outside]]", "resolves outside the vault"),
        ("[[folder/../../outside]]", "resolves outside the vault"),
        ("[[_site/mdblog.toml]]", "targets a path under _site/ or a hidden folder"),
        ("![[_site/site-image.png]]", "targets a path under _site/ or a hidden folder"),
        ("![[.hidden/secret.png]]", "targets a path under _site/ or a hidden folder"),
        ("[[site-image.png]]", "matches no note or file"),
        ("[[secret.png]]", "matches no note or file"),
        ("[[draft]]", "drafts/draft.md is not published"),
        ("![[drafts/draft]]", "drafts/draft.md is not published"),
        ("[[broken]]", "broken.md has failures of its own"),
        ("[[target#Nope]]", "notes/target.md has no heading 'Nope'"),
        ("[[#Nope]]", "notes/source.md has no heading 'Nope'"),
        (
            "[[target#Commented Heading]]",
            "notes/target.md has no heading 'Commented Heading'",
        ),
        ("[[target#^nope]]", "notes/target.md has no block ^nope"),
        ("[[target#^gone]]", "notes/target.md has no block ^gone"),
        ("[[paper.pdf]]", "paper.pdf is not a note or a supported image"),
        ("![[clip.mp4]]", "clip.mp4 is not a note or a supported image"),
        ("[[|alias]]", "names no note"),
    ],
)
def test_a_link_that_cannot_resolve_fails(
    tmp_path: Path, link: str, problem: str
) -> None:
    vault = _vault(tmp_path, f"before {link} after\n")
    _note(vault, "a/dup.md", "", slug="dup-a")
    _note(vault, "b/dup.md", "", slug="dup-b")
    _note(vault, "a/case.md", "", slug="case-a")
    _note(vault, "b/CASE.md", "", slug="case-b")
    if link == "[[a.png]]":
        _write(vault, "other/a.png", b"PNG")

    conversion = _convert(vault)

    assert _link_failures(conversion) == [f"{SOURCE}: {link}: {problem}"]
    assert "source" not in [page.note.page.slug for page in conversion.pages]


def test_a_symlinked_image_is_not_found(tmp_path: Path) -> None:
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"PNG")
    vault = _vault(tmp_path / "vault", "![[linked.png]]\n")
    (vault / "linked.png").symlink_to(outside)

    assert _link_failures(_convert(vault)) == [
        f"{SOURCE}: ![[linked.png]]: matches no note or file"
    ]


def test_two_images_with_one_name_in_one_note_fail(tmp_path: Path) -> None:
    vault = _vault(tmp_path, "![[images/a.png]] ![[other/A.png]]\n")
    _write(vault, "other/A.png", b"OTHER")

    assert _link_failures(_convert(vault)) == [
        f"{SOURCE}: uses different images with one file name: images/a.png, other/A.png"
    ]


def test_notes_may_each_use_an_image_with_the_same_name(tmp_path: Path) -> None:
    vault = _vault(tmp_path, "![[images/a.png]]\n")
    _write(vault, "other/a.png", b"OTHER")
    _note(vault, "second.md", "![[other/a.png]]\n")

    conversion = _convert(vault)

    assert _link_failures(conversion) == []
    assert "![a\\.png](/posts/second/a.png)" in _body(conversion, "second")


def test_every_failure_in_every_note_is_reported(tmp_path: Path) -> None:
    vault = _vault(tmp_path, "[[missing]] [[draft]]\n")
    _note(vault, "second.md", "[[also-missing]] [x](draft.md)\n")

    assert _link_failures(_convert(vault)) == [
        "notes/source.md: [[missing]]: matches no note or file",
        "notes/source.md: [[draft]]: drafts/draft.md is not published",
        "second.md: Markdown link to 'draft.md' is internal; use a wikilink",
        "second.md: [[also-missing]]: matches no note or file",
    ]


@pytest.mark.parametrize(
    "markdown",
    [
        "[inline](target.md)",
        "![image](images/a.png)",
        "[reference][ref]\n\n[ref]: ../top.md",
        "![reference][img]\n\n[img]: images/a.png",
        "[absolute](/posts/target/)",
        "[empty]()",
    ],
)
def test_an_internal_markdown_link_fails(tmp_path: Path, markdown: str) -> None:
    conversion = _convert(_vault(tmp_path, markdown + "\n"))

    [failure] = _link_failures(conversion)
    assert failure.startswith(f"{SOURCE}: Markdown link to ")
    assert failure.endswith(" is internal; use a wikilink")


def test_an_external_or_fragment_markdown_link_passes_through(tmp_path: Path) -> None:
    text = (
        "[web](https://example.test/a) ![pic](https://example.test/p.png) "
        "[mail](mailto:a@example.test) [here](#own-heading) <https://example.test/>"
    )

    assert _converted(tmp_path, text) == text


def test_comments_are_removed_without_validating_their_contents(tmp_path: Path) -> None:
    text = "a %%[[missing]] [x](draft.md)%% b\n%%\n![[draft]]\n%%\nc %% ![[clip.mp4]]"

    assert _converted(tmp_path, text) == "a  b\n\nc "


def test_code_stays_byte_identical(tmp_path: Path) -> None:
    syntax = (
        "[[target]] ![[a.png]] [[missing]] %%open [[draft]] ==mark== "
        "[x](internal.md) #tag > [!note] ^blk-id"
    )
    text = (
        f"`{syntax}`\n"
        "\n"
        f"``{syntax} ` %%``\n"
        "\n"
        f"```\n{syntax}\n%%\n```\n"
        "\n"
        f"    {syntax}\n"
        "\n"
        f"> ```md\n> {syntax}\n> ```\n"
        "\n"
        f"- item\n\n  ~~~\n  {syntax}\n  ~~~\n"
    )

    assert _converted(tmp_path, text) == text


def test_inline_tags_stay_literal(tmp_path: Path) -> None:
    assert _converted(tmp_path, "#tag and #nested/tag") == "#tag and #nested/tag"


def test_block_ids_are_removed(tmp_path: Path) -> None:
    assert _converted(tmp_path, "para ^one\n\n^two\nend") == "para\n\n\nend"


def test_unpublished_notes_are_not_checked(tmp_path: Path) -> None:
    vault = _vault(tmp_path, "")
    _write(
        vault, "drafts/messy.md", "---\npublish: false\n---\n[[missing]] [x](y.md)\n"
    )
    _write(vault, "plain.md", "![[nothing.png]]\n")

    assert _link_failures(_convert(vault)) == []


def test_bio_converts_against_the_vault_with_images_at_the_home_page(
    tmp_path: Path,
) -> None:
    vault = _vault(tmp_path, "")
    bio = "%% PRIVATE [[draft]] %%[[target#Target Heading]] ![[a.png|40]] line ^id\n"

    conversion = convert_notes(
        select_notes(vault, NOW), "https://example.test/blog/", bio
    )

    assert conversion.bio is not None
    assert conversion.bio.body.decode("utf-8") == (
        "[target\\#Target Heading](/blog/posts/target/#target-heading)"
        " ![a\\.png](/blog/a.png?mdblog-width=40) line\n"
    )
    assert conversion.bio.images == (Path("images/a.png"),)
    assert _link_failures(conversion) == []


def test_bio_failures_name_the_bio_and_the_target(tmp_path: Path) -> None:
    vault = _vault(tmp_path, "")
    bio = "[[missing]] [[draft]] [text](top.md)\n"

    conversion = convert_notes(select_notes(vault, NOW), "https://example.test/", bio)

    assert conversion.bio is None
    assert _link_failures(conversion) == [
        f"{BIO_PATH.as_posix()}: Markdown link to 'top.md' is internal; use a wikilink",
        f"{BIO_PATH.as_posix()}: [[missing]]: matches no note or file",
        f"{BIO_PATH.as_posix()}: [[draft]]: drafts/draft.md is not published",
    ]


def test_no_bio_converts_to_none(tmp_path: Path) -> None:
    assert _convert(_vault(tmp_path, "")).bio is None
