"""The packaged layouts' pages and feeds, built from vaults with real Hugo."""

import datetime as dt
import re
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import override
from urllib.parse import unquote, urlsplit

import pytest

from mdblog.build import PACKAGED_THEME, build_site
from notes import published_text

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_VAULT = REPO_ROOT / "tests" / "fixtures" / "vault"
FIXTURE_URL = "https://example.org/"
AUTHOR = "Fixture Author"
SITE_FEED = FIXTURE_URL + "index.xml"
VOID_ELEMENTS = frozenset(("meta", "link", "img", "br", "hr", "input", "source", "wbr"))


@dataclass
class Element:
    """One parsed HTML element."""

    tag: str
    attrs: dict[str, str]
    children: list[Element | str] = field(default_factory=list["Element | str"])

    def iter(self) -> Iterator[Element]:
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.iter()

    def all(self, tag: str | None = None, cls: str | None = None) -> list[Element]:
        return [
            element
            for element in self.iter()
            if (tag is None or element.tag == tag)
            and (cls is None or cls in element.classes)
        ]

    def one(self, tag: str | None = None, cls: str | None = None) -> Element:
        found = self.all(tag, cls)
        assert len(found) == 1, (tag, cls, len(found))
        return found[0]

    @property
    def classes(self) -> list[str]:
        return self.attrs.get("class", "").split()

    @property
    def text(self) -> str:
        parts = (
            child if isinstance(child, str) else child.text for child in self.children
        )
        return " ".join("".join(parts).split())

    def hrefs(self) -> list[str]:
        return [element.attrs["href"] for element in self.all("a")]


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("#document", {})
        self.stack = [self.root]

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag, {name: value or "" for name, value in attrs})
        self.stack[-1].children.append(element)
        if tag not in VOID_ELEMENTS:
            self.stack.append(element)

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_ELEMENTS:
            return
        assert self.stack[-1].tag == tag, (self.stack[-1].tag, tag)
        self.stack.pop()

    @override
    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse_html(text: str) -> Element:
    builder = _TreeBuilder()
    builder.feed(text)
    builder.close()
    return builder.root


@dataclass(frozen=True)
class Site:
    """A built site's output directory."""

    root: Path

    def path(self, name: str) -> Path:
        path = self.root / name
        return path / "index.html" if path.is_dir() else path

    def raw(self, name: str) -> str:
        return self.path(name).read_text(encoding="utf-8")

    def page(self, name: str) -> Element:
        return parse_html(self.raw(name))

    def feed(self, name: str) -> ET.Element:
        channel = ET.fromstring(self.raw(name)).find("channel")
        assert channel is not None
        return channel

    def html_pages(self) -> list[str]:
        return sorted(
            path.relative_to(self.root).as_posix() for path in self.root.rglob("*.html")
        )

    def files(self) -> set[str]:
        return {
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob("*")
            if path.is_file()
        }


def _build(vault: Path, output: Path) -> Site:
    build_site(vault, output, ("hugo",))
    return Site(output)


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Site:
    return _build(FIXTURE_VAULT, tmp_path_factory.mktemp("fixture") / "output")


def _copy_fixture(root: Path, base_url: str = FIXTURE_URL) -> Path:
    vault = root / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    config = vault / "_site" / "mdblog.toml"
    text = config.read_text(encoding="utf-8").replace(FIXTURE_URL, base_url)
    config.write_text(text, encoding="utf-8")
    return vault


def _text(element: ET.Element, tag: str) -> str:
    return element.findtext(tag) or ""


def _items(channel: ET.Element) -> list[ET.Element]:
    return channel.findall("item")


def _item_links(channel: ET.Element) -> list[str]:
    return [_text(item, "link") for item in _items(channel)]


def _posts(*slugs: str) -> list[str]:
    return [f"{FIXTURE_URL}posts/{slug}/" for slug in slugs]


def _entry(page: Element, slug: str) -> Element:
    """The h-entry whose permalink is that of `slug`."""
    url = _posts(slug)[0]
    found = [
        entry
        for entry in page.all(cls="h-entry")
        if entry.one(cls="u-url").attrs["href"] == url
    ]
    assert len(found) == 1, slug
    return found[0]


# Newest first. offset-time's 23:30 at -07:00 is after syntax's UTC midnight.
NEWEST_FIRST = (
    "long-post",
    "offset-time",
    "syntax",
    "link-target",
    "first-note",
    "last-year",
)


def test_fixture_vault_builds_end_to_end(site: Site) -> None:
    files = {name: site.path(name).read_bytes() for name in site.files()}
    assert (
        b"The fixture note reached the generated page."
        in files["posts/first-note/index.html"]
    )
    assert b"The fixture link target." in files["posts/link-target/index.html"]
    assert "tags/project/alpha/index.html" in files
    syntax = files["posts/syntax/index.html"].decode("utf-8")
    for fragment in (
        '<a href="/posts/first-note/">the first note</a>',
        '<a href="/posts/link-target/#details">link-target#Details</a>',
        '<a href="/posts/link-target/">projects/link-target#^detail-block</a>',
        '<a href="/posts/syntax/#linking-out">#Linking Out</a>',
        '<img src="/posts/syntax/diagram.svg" alt="diagram.svg" width="120" height="80">',
        '<details class="callout callout-tip">',
        "<mark>FIXTURE-HIGHLIGHT</mark> text.</p>",
        "<code>[[first-note]] %% kept %% ^kept\n</code>",
    ):
        assert fragment in syntax, fragment
    assert "^syntax-block" not in syntax
    assert b"FIXTURE-DIAGRAM" in files["posts/syntax/diagram.svg"]
    assert "^detail-block" not in files["posts/link-target/index.html"].decode("utf-8")
    for needle in (
        b"UNPUBLISHED-COMMENT",
        b"UNPUBLISHED-UNUSED-IMAGE",
        b"UNPUBLISHED-DRAFT-IMAGE",
        b"UNPUBLISHED-MARKED-FALSE",
        b"UNPUBLISHED-NO-PROPERTY",
        b"UNPUBLISHED-NO-FRONT-MATTER",
        b"UNPUBLISHED-SITE-DIRECTORY",
        b"UNPUBLISHED-OBSIDIAN",
        b"UNPUBLISHED-TRASH",
    ):
        assert not [name for name, data in files.items() if needle in data], needle


def test_a_built_site_has_no_draft_labels_or_preview_banner(site: Site) -> None:
    # The fixture holds drafts, and the stylesheet names these classes, so only pages
    # and feeds are searched.
    for name in site.files():
        if name.endswith((".html", ".xml")):
            text = site.raw(name)
            assert "entry-status" not in text, name
            assert "preview-banner" not in text, name
            assert "Draft preview" not in text, name


def test_every_sidebar_shows_the_converted_bio_and_home_main_holds_none(
    site: Site,
) -> None:
    main = site.page("index.html").one("main")
    sections = [child for child in main.children if isinstance(child, Element)]
    assert "h-feed" in sections[0].classes
    assert main.all(cls="bio") == []
    for name in site.html_pages():
        bio = site.page(name).one("aside", "sidebar").one(cls="bio")
        assert bio.text.startswith("FIXTURE-BIO about the author"), name
        assert bio.hrefs() == ["/posts/first-note/"], name
        assert bio.one("img").attrs["src"] == "/headshot.svg", name
    assert b"FIXTURE-HEADSHOT" in site.path("headshot.svg").read_bytes()
    # The bio's front matter has a title and `publish: false`, and neither applies.
    assert "Ignored bio title" not in site.raw("index.html")


def _sidebar_sections(page: Element) -> list[tuple[str, list[str]]]:
    """Each sidebar section's label and the hrefs in it, in order."""
    sidebar = page.one("aside", "sidebar")
    return [
        (section.one(cls="sidebar-label").text, section.hrefs())
        for section in sidebar.all("section")
    ]


SITE_LINKS = ("Site", ["/posts/", "/tags/", "/index.xml"])
TAG_LINKS = ("Tags", ["/tags/node.js/", "/tags/project/alpha/", "/tags/"])


def test_every_page_ends_main_with_the_sidebar_in_section_order(site: Site) -> None:
    for name in site.html_pages():
        page = site.page(name)
        layout = [child for child in page.one(cls="layout").children]
        tags = [child.tag for child in layout if isinstance(child, Element)]
        assert tags == ["main", "aside"], name
        labels = [label for label, _ in _sidebar_sections(page)]
        expected = ["About", "Tags", "Site"]
        if name != "index.html":
            expected.insert(1, "Recent posts")
        assert labels == expected, name
        assert _sidebar_sections(page)[-2:] == [TAG_LINKS, SITE_LINKS], name
    assert "404.html" in site.html_pages()


def _recent(page: Element) -> list[tuple[str, str, str]]:
    section = page.one("aside", "sidebar").one(cls="sidebar-recent")
    return [
        (
            item.one("a").attrs["href"],
            item.one(cls="sidebar-recent-title").text,
            item.one("time").text,
        )
        for item in section.all("li")
    ]


def test_recent_posts_lists_the_five_newest_other_entries_then_the_archive(
    site: Site,
) -> None:
    titles = {
        "long-post": ("Tips & Tricks", "Jan 4, 2026"),
        "offset-time": ("Offset time", "Jan 2, 2026"),
        "syntax": ("syntax", "Jan 3, 2026"),
        "link-target": ("link-target", "Jan 2, 2026"),
        "first-note": ("first-note", "Jan 1, 2026"),
        "last-year": ("A note from last year", "Jun 1, 2025"),
    }

    def expected(*slugs: str) -> list[tuple[str, str, str]]:
        return [(f"/posts/{slug}/", *titles[slug]) for slug in slugs]

    assert _recent(site.page("posts/index.html")) == expected(*NEWEST_FIRST[:5])
    assert _recent(site.page("404.html")) == expected(*NEWEST_FIRST[:5])
    assert _recent(site.page("posts/long-post/index.html")) == expected(
        *NEWEST_FIRST[1:]
    )
    without_syntax = [slug for slug in NEWEST_FIRST if slug != "syntax"]
    assert _recent(site.page("posts/syntax/index.html")) == expected(*without_syntax)
    recent = site.page("posts/index.html").one(cls="sidebar-recent")
    assert recent.hrefs()[-1] == "/posts/"
    assert recent.all(cls="dt-published") == []


def test_a_lone_untagged_entry_without_a_bio_gets_only_site_links(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    (vault / "_site").mkdir(parents=True)
    shutil.copy(FIXTURE_VAULT / "_site" / "mdblog.toml", vault / "_site")
    (vault / "lone.md").write_text(published_text("lone"), encoding="utf-8")

    built = _build(vault, tmp_path / "output")

    assert _sidebar_sections(built.page("posts/lone/index.html")) == [SITE_LINKS]
    assert [
        label for label, _ in _sidebar_sections(built.page("posts/index.html"))
    ] == [
        "Recent posts",
        "Site",
    ]


def test_sidebar_tags_are_the_ten_most_used_then_by_name(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "_site").mkdir(parents=True)
    shutil.copy(FIXTURE_VAULT / "_site" / "mdblog.toml", vault / "_site")
    # Tag t<n> is on the first n notes, so counts fall from 12 to 1; ties come from
    # the extra tags that share a count with one of those.
    counts = {f"t{n:02}": n for n in range(1, 13)} | {"a-tie": 9, "z-tie": 9}
    for number in range(1, 13):
        tags = sorted(tag for tag, count in counts.items() if count >= number)
        (vault / f"n{number:02}.md").write_text(
            published_text(f"n{number:02}", extra=f"tags: [{', '.join(tags)}]\n"),
            encoding="utf-8",
        )

    built = _build(vault, tmp_path / "output")

    section = (
        built.page("posts/index.html").one("aside", "sidebar").one(cls="sidebar-tags")
    )
    shown = [
        (item.one("a", "tag").text, item.one(cls="tag-count").text)
        for item in section.all("li")
    ]
    assert shown == [
        ("t12 12", "12"),
        ("t11 11", "11"),
        ("t10 10", "10"),
        ("a-tie 9", "9"),
        ("t09 9", "9"),
        ("z-tie 9", "9"),
        ("t08 8", "8"),
        ("t07 7", "7"),
        ("t06 6", "6"),
        ("t05 5", "5"),
    ]
    assert section.all("li")[0].hrefs() == ["/tags/t12/"]
    assert section.hrefs()[-1] == "/tags/"


def test_home_lists_entries_newest_first_then_links_the_archive(site: Site) -> None:
    main = site.page("index.html").one("main")
    items = main.one(cls="h-feed").all(cls="h-entry")
    assert [item.one(cls="u-url").attrs["href"] for item in items] == _posts(
        *NEWEST_FIRST
    )
    assert main.hrefs()[-1] == "/posts/"


def test_lists_show_each_entry_with_its_summary_and_metadata(site: Site) -> None:
    for name in ("index.html", "tags/node.js/index.html"):
        post = _entry(site.page(name), "long-post")
        title = post.one(cls="p-name")
        assert title.text == "Tips & Tricks"
        assert title.hrefs() == ["/posts/long-post/"]
        summary = post.one(cls="p-summary")
        assert summary.text == "FIXTURE-BEFORE-MORE & more."
        assert post.one("time").text == "Jan 4, 2026"
        assert [tag.text for tag in post.all(cls="p-category")] == ["node.js"]
        offset = _entry(site.page(name), "offset-time")
        assert offset.one(cls="p-summary").text == "FIXTURE-OFFSET-BODY."
    target = _entry(site.page("index.html"), "link-target")
    assert target.one(cls="p-name").hrefs() == ["/posts/link-target/"]
    assert target.one(cls="p-summary").text.startswith("The fixture link target.")


def test_no_page_labels_an_entry_or_marks_up_another_url(site: Site) -> None:
    for name in site.html_pages():
        page = site.page(name)
        assert page.all(cls="entry-label") == [], name
        url_classes = {
            cls for element in page.iter() for cls in element.classes if cls[:2] == "u-"
        }
        assert url_classes <= {"u-url"}, name


def test_archive_lists_every_entry_under_year_headings(site: Site) -> None:
    page = site.page("posts/index.html")
    assert page.one("title").text == "All posts | mdblog fixture"
    main = page.one("main")
    assert main.one("h1").text == "All posts"
    assert [heading.text for heading in main.all("h2")] == ["2026", "2025"]
    years = main.all(cls="archive-year")
    lines = [[item.text for item in year.all("li")] for year in years]
    assert lines == [
        [
            "Tips & Tricks Jan 4, 2026",
            "Offset time Jan 2, 2026",
            "syntax Jan 3, 2026",
            "link-target Jan 2, 2026",
            "first-note Jan 1, 2026",
        ],
        ["A note from last year Jun 1, 2025"],
    ]
    assert main.all(cls="p-summary") == []
    assert main.all(cls="p-category") == []


def test_tag_pages_list_their_entries_and_the_index_lists_every_tag(
    site: Site,
) -> None:
    tag = site.page("tags/node.js/index.html").one(cls="h-feed")
    assert tag.one("h1").text == "node.js"
    urls = [entry.one(cls="u-url").attrs["href"] for entry in tag.all(cls="h-entry")]
    assert urls == _posts("long-post", "offset-time")
    index = site.page("tags/index.html").one("main")
    assert [(item.hrefs(), item.text) for item in index.all("li")] == [
        (["/tags/node.js/"], "node.js 2"),
        (["/tags/project/alpha/"], "project/alpha 1"),
    ]


def test_a_nested_tags_parent_gets_no_page(site: Site) -> None:
    assert site.path("tags/project/alpha/index.html").is_file()
    assert not (site.root / "tags" / "project" / "index.html").exists()


def test_entry_page_shows_the_entry_and_no_other_entry_links(site: Site) -> None:
    entry = site.page("posts/long-post/index.html").one("main").one(cls="h-entry")
    assert entry.one("h1").text == "Tips & Tricks"
    assert entry.one("time").text == "Jan 4, 2026"
    content = entry.one(cls="e-content")
    assert "FIXTURE-AFTER-MORE" in content.text
    outside_content = [href for href in entry.hrefs() if href not in content.hrefs()]
    assert outside_content == [
        "/posts/long-post/",
        "https://example.org/posts/long-post/",
        "/tags/node.js/",
    ]
    target = site.page("posts/link-target/index.html").one(cls="h-entry")
    assert target.one("h1").hrefs() == ["/posts/link-target/"]


def test_dates_show_the_day_in_their_own_offset(site: Site) -> None:
    time = site.page("posts/offset-time/index.html").one("main").one("time")
    assert time.attrs["datetime"] == "2026-01-02T23:30:00-07:00"
    assert time.text == "Jan 2, 2026"


def test_a_date_only_value_shows_its_own_day_in_any_zone(
    tmp_path: Path, local_zone: Callable[[str], None]
) -> None:
    vault = tmp_path / "vault"
    (vault / "_site").mkdir(parents=True)
    shutil.copy(FIXTURE_VAULT / "_site" / "mdblog.toml", vault / "_site")
    (vault / "dated.md").write_text(
        published_text("dated", date="2026-01-02"), encoding="utf-8"
    )
    local_zone("Pacific/Kiritimati")

    built = _build(vault, tmp_path / "output")

    time = built.page("posts/dated/index.html").one("main").one("time")
    assert time.text == "Jan 2, 2026"
    assert time.attrs["datetime"].startswith("2026-01-02T")


def _check_h_entry(entry: Element, slug: str, tags: list[str], *, listed: bool) -> None:
    assert len(entry.all(cls="p-name")) == 1
    assert entry.one(cls="u-url").attrs["href"] == _posts(slug)[0]
    assert len(entry.all(cls="dt-published")) == 1
    assert [tag.text for tag in entry.all(cls="p-category")] == tags
    author = entry.one(cls="p-author")
    assert "h-card" in author.classes
    assert author.text == AUTHOR
    # A list hides the single author's name from readers but keeps the h-card.
    assert ("hidden" in author.attrs) == listed


TAGS = {
    "long-post": ["node.js"],
    "offset-time": ["node.js"],
    "first-note": ["project/alpha"],
}


def test_lists_and_entry_pages_carry_h_entry_markup(site: Site) -> None:
    for name in ("index.html", "tags/node.js/index.html"):
        feed = site.page(name).one("main").one(cls="h-feed")
        for entry in feed.all(cls="h-entry"):
            slug = urlsplit(entry.one(cls="u-url").attrs["href"]).path.split("/")[2]
            _check_h_entry(entry, slug, TAGS.get(slug, []), listed=True)
            assert len(entry.all(cls="p-summary")) == 1, (name, slug)
            assert entry.all(cls="e-content") == [], (name, slug)
    for slug in NEWEST_FIRST:
        entry = site.page(f"posts/{slug}/index.html").one(cls="h-entry")
        _check_h_entry(entry, slug, TAGS.get(slug, []), listed=False)
        assert len(entry.all(cls="e-content")) == 1


def test_every_page_has_the_header_and_footer(site: Site) -> None:
    for name in site.html_pages():
        page = site.page(name)
        header = page.one("header", "site-header")
        links = [(a.text, a.attrs["href"]) for a in header.all("a")]
        brand = "mdblog fixture" if name == "index.html" else "« mdblog fixture"
        assert links == [
            (brand, "/"),
            ("All posts", "/posts/"),
            ("Tags", "/tags/"),
            ("RSS", "/index.xml"),
        ], name
        assert page.one("footer").text == f"© {AUTHOR}", name


def _meta(head: Element, key: str, value: str) -> list[str]:
    return [m.attrs["content"] for m in head.all("meta") if m.attrs.get(key) == value]


def test_every_page_head_has_its_metadata(site: Site) -> None:
    for name in site.html_pages():
        head = site.page(name).one("head")
        url = FIXTURE_URL + name.removesuffix("index.html")
        assert head.one("title").text, name
        assert _meta(head, "name", "author") == [AUTHOR], name
        canonical = [
            link.attrs["href"]
            for link in head.all("link")
            if link.attrs["rel"] == "canonical"
        ]
        assert canonical == [url], name
        assert len(_meta(head, "property", "og:title")) == 1, name
        assert _meta(head, "property", "og:url") == [url], name
        assert _meta(head, "property", "og:site_name") == ["mdblog fixture"], name
        kind = (
            "article"
            if name.startswith("posts/") and name != "posts/index.html"
            else "website"
        )
        assert _meta(head, "property", "og:type") == [kind], name
        described = kind == "article" or name == "index.html"
        assert len(_meta(head, "name", "description")) == int(described), name
        assert len(_meta(head, "property", "og:description")) == int(described), name


def test_descriptions_are_plain_text_escaped_once(site: Site) -> None:
    raw = site.raw("posts/long-post/index.html")
    assert "<title>Tips &amp; Tricks | mdblog fixture</title>" in raw
    assert '<meta name="description" content="FIXTURE-BEFORE-MORE &amp; more.">' in raw
    assert (
        '<meta property="og:description" content="FIXTURE-BEFORE-MORE &amp; more.">'
        in raw
    )
    assert "&amp;amp;" not in raw
    home = site.page("index.html").one("head")
    assert _meta(home, "name", "description") == [
        "FIXTURE-BIO about the author, who wrote first-note."
    ]


def _advertised(head: Element) -> list[str]:
    return [
        link.attrs["href"]
        for link in head.all("link")
        if link.attrs["rel"] == "alternate"
        and link.attrs["type"] == "application/rss+xml"
    ]


def _stylesheets(head: Element) -> list[str]:
    return [
        link.attrs["href"]
        for link in head.all("link")
        if link.attrs["rel"] == "stylesheet"
    ]


def test_every_page_links_the_packaged_stylesheet_by_its_fingerprint(
    site: Site,
) -> None:
    linked: set[str] = set()
    for name in site.html_pages():
        hrefs = _stylesheets(site.page(name).one("head"))
        assert len(hrefs) == 1, name
        assert re.fullmatch(r"/css/main\.[0-9a-f]{64}\.css", hrefs[0]), name
        linked.add(hrefs[0])
    (href,) = linked
    css = site.raw(href.removeprefix("/"))
    packaged = PACKAGED_THEME / "assets" / "css" / "main.css"
    assert css == packaged.read_text(encoding="utf-8")
    assert "@font-face" not in css
    assert "@import" not in css


def test_a_vault_stylesheet_replaces_the_packaged_one(tmp_path: Path) -> None:
    vault = _copy_fixture(tmp_path)
    stylesheet = vault / "_site" / "assets" / "css" / "main.css"
    stylesheet.parent.mkdir(parents=True)
    stylesheet.write_text(".site-stylesheet { color: red; }\n", encoding="utf-8")

    built = _build(vault, tmp_path / "output")

    (href,) = _stylesheets(built.page("index.html").one("head"))
    assert built.raw(href.removeprefix("/")) == ".site-stylesheet { color: red; }\n"


def test_every_page_fits_a_phone_and_runs_no_script(site: Site) -> None:
    for name in site.html_pages():
        viewport = _meta(site.page(name).one("head"), "name", "viewport")
        assert len(viewport) == 1, name
        assert "width=device-width" in viewport[0], name
        assert "<script" not in site.raw(name), name


def test_fenced_code_with_a_language_is_highlighted_by_class(site: Site) -> None:
    page = site.page("posts/syntax/index.html")
    block = page.one("pre", "chroma")
    assert block.one("code").attrs["data-lang"] == "python"
    assert "k" in {cls for element in block.iter() for cls in element.classes}
    assert [element.tag for element in page.iter() if "style" in element.attrs] == []


def test_the_404_page_has_the_site_chrome_a_message_and_a_link_home(
    site: Site,
) -> None:
    page = site.page("404.html")
    page.one("header", "site-header")
    page.one("footer", "site-footer")
    main = page.one("main")
    assert main.one("h1").text == "Page not found"
    assert main.hrefs() == ["/"]


def test_every_page_advertises_the_site_feed(site: Site) -> None:
    for name in site.html_pages():
        advertised = _advertised(site.page(name).one("head"))
        if name.startswith("tags/") and name != "tags/index.html":
            own = FIXTURE_URL + name.removesuffix("index.html") + "index.xml"
            assert advertised == [own, SITE_FEED], name
        else:
            assert advertised == [SITE_FEED], name


def test_feeds_exist_for_the_site_and_each_tag_only(site: Site) -> None:
    feeds = sorted(name for name in site.files() if name.endswith(".xml"))
    assert feeds == [
        "index.xml",
        "sitemap.xml",
        "tags/node.js/index.xml",
        "tags/project/alpha/index.xml",
    ]
    assert not (site.root / "types").exists()
    assert not (site.root / "categories").exists()


def test_feed_channels_name_their_scope(site: Site) -> None:
    expected = {
        "index.xml": ("mdblog fixture", FIXTURE_URL),
        "tags/node.js/index.xml": (
            "mdblog fixture: node.js",
            FIXTURE_URL + "tags/node.js/",
        ),
    }
    for name, (title, link) in expected.items():
        channel = site.feed(name)
        assert (_text(channel, "title"), _text(channel, "link")) == (title, link)
        assert _text(channel, "description"), name


def test_feeds_list_their_entries_newest_first(site: Site) -> None:
    assert _item_links(site.feed("index.xml")) == _posts(*NEWEST_FIRST)
    assert _item_links(site.feed("tags/node.js/index.xml")) == _posts(
        "long-post", "offset-time"
    )


def _item(channel: ET.Element, slug: str) -> ET.Element:
    for item in _items(channel):
        if _text(item, "link") == _posts(slug)[0]:
            return item
    raise AssertionError(slug)


def test_feed_items_hold_full_text_with_absolute_urls(site: Site) -> None:
    item = _item(site.feed("index.xml"), "long-post")
    assert _text(item, "guid") == _text(item, "link") == _posts("long-post")[0]
    html = _text(item, "description")
    assert "FIXTURE-BEFORE-MORE" in html
    assert "FIXTURE-AFTER-MORE" in html
    assert "FIXTURE-FOOTNOTE" in html
    assert "]]&gt; &amp; more" in html
    assert "<code>href=&quot;/x&quot;</code>" in html
    urls = re.findall(r'(?:href|src)="([^"]*)"', html)
    assert urls == [
        "https://example.org/posts/long-post/#fn:1",
        "https://example.org/posts/syntax/#linking-out",
        "https://example.org/posts/long-post/diagram.svg",
        "https://example.org/posts/long-post/#fnref:1",
    ]


def _first_block(element: Element) -> tuple[str, str]:
    first = next(child for child in element.children if isinstance(child, Element))
    return first.tag, first.text


def test_feed_items_start_with_the_entrys_own_content(site: Site) -> None:
    for name in ("index.xml", "tags/node.js/index.xml"):
        for item in _items(site.feed(name)):
            slug = urlsplit(_text(item, "link")).path.split("/")[2]
            page = site.page(f"posts/{slug}/index.html")
            html = _text(item, "description")
            assert html.startswith("<"), slug
            assert _first_block(parse_html(html)) == _first_block(
                page.one(cls="e-content")
            ), slug


def test_static_files_reach_the_output(site: Site) -> None:
    assert site.path("favicon.ico").read_bytes() == b"FIXTURE-FAVICON"


def test_home_and_feeds_hold_only_their_latest_entries(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "_site").mkdir(parents=True)
    shutil.copy(FIXTURE_VAULT / "_site" / "mdblog.toml", vault / "_site")
    first_day = dt.date(2026, 1, 1)
    posts = [f"post-{number:02}" for number in range(51, 0, -1)]
    for slug in posts:
        date = first_day + dt.timedelta(days=int(slug.removeprefix("post-")))
        (vault / f"{slug}.md").write_text(
            published_text(slug, date=date.isoformat()), encoding="utf-8"
        )

    built = _build(vault, tmp_path / "output")

    home = built.page("index.html").one(cls="h-feed").all(cls="h-entry")
    home_urls = [entry.one(cls="u-url").attrs["href"] for entry in home]
    assert home_urls == _posts(*posts[:15])
    assert _item_links(built.feed("index.xml")) == _posts(*posts[:50])


def _internal_urls(site: Site, origin: str) -> list[str]:
    urls: list[str] = []
    for name in site.html_pages():
        for element in site.page(name).iter():
            for attribute in ("href", "src"):
                value = element.attrs.get(attribute)
                # A fragment-only href is a same-page reference, valid at any path.
                if value is not None and not value.startswith("#"):
                    urls.append(value)
    for name in site.files():
        if not name.endswith(".xml") or name == "sitemap.xml":
            continue
        root = ET.fromstring(site.raw(name))
        for element in root.iter():
            if element.tag == "description" and element.text:
                urls.extend(re.findall(r'(?:href|src)="([^"]*)"', element.text))
            elif element.tag in ("link", "guid") and element.text:
                urls.append(element.text)
            elif "href" in element.attrib:
                urls.append(element.attrib["href"])
    return [url for url in urls if url.startswith(("/", origin))]


def test_a_site_under_a_sub_path_links_only_within_it(tmp_path: Path) -> None:
    base_url = "https://example.test/blog/"
    built = _build(_copy_fixture(tmp_path / "a", base_url), tmp_path / "a" / "output")
    unslashed = _build(
        _copy_fixture(tmp_path / "b", base_url.rstrip("/")), tmp_path / "b" / "output"
    )

    urls = _internal_urls(built, "https://example.test")
    assert urls
    for url in urls:
        parts = urlsplit(url)
        assert parts.path.startswith("/blog/"), url
        assert url.startswith(("/blog/", base_url)), url
        path = built.root / unquote(parts.path).removeprefix("/blog/")
        file = path / "index.html" if path.is_dir() else path
        assert file.is_file(), url
    bio_image = built.page("posts/syntax/index.html").one(cls="bio").one("img")
    assert bio_image.attrs["src"] == "/blog/headshot.svg"
    not_found = built.page("404.html")
    assert _stylesheets(not_found.one("head"))[0].startswith("/blog/css/")
    assert not_found.one("main").hrefs() == ["/blog/"]
    assert {name: built.path(name).read_bytes() for name in built.files()} == {
        name: unslashed.path(name).read_bytes() for name in unslashed.files()
    }


@pytest.mark.parametrize(
    "layout",
    sorted(
        path.relative_to(PACKAGED_THEME / "layouts").as_posix()
        for path in (PACKAGED_THEME / "layouts").rglob("*")
        if path.is_file()
    ),
)
def test_a_site_overrides_each_packaged_layout_by_name(
    tmp_path: Path, layout: str
) -> None:
    vault = _copy_fixture(tmp_path)
    override = vault / "_site" / "layouts" / layout
    override.parent.mkdir(parents=True)
    override.write_text("SITE-OVERRIDE", encoding="utf-8")

    built = _build(vault, tmp_path / "output")

    assert [
        name
        for name in built.files()
        if b"SITE-OVERRIDE" in built.path(name).read_bytes()
    ], layout
