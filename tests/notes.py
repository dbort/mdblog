"""notes: builds the text of published notes for tests."""


def published_text(
    slug: str = "a-note",
    *,
    extra: str = "",
    entry_type: str = "post",
    date: str = "2026-01-01",
    body: str = "",
) -> str:
    """A note holding every required property; `extra` is more front matter lines."""
    return (
        "---\n"
        "publish: true\n"
        f"slug: {slug}\n"
        f"type: {entry_type}\n"
        f"date: {date}\n"
        f"{extra}"
        "---\n"
        f"{body}"
    )


# Headings exercising each rule of Hugo's heading IDs. test_build.py builds them with
# real Hugo, and test_markdown.py states the expected IDs.
HEADINGS = (
    "# Café & Über: 100%!\n"
    "## Same\n"
    "## Same\n"
    "## C++ and `code` stuff\n"
    "## !!!\n"
    "##\n"
    "## Explicit {#same-2}\n"
    "## Same\n"
    "## Classed {.wide}\n"
    "## Braces {a, b}\n"
    "## See [[target|Alias]] and [[target]]\n"
    "## Sized ![[a.png|300]] and ![[images/a.png]]\n"
    "## Alt ![[a.png|alt words]] and [[a.png]]\n"
    "## Odd [[target|_lead_ <b>x</b> &amp;]] and [[_draft notes_]]\n"
    "## Auto <https://a.test/x> y\n"
    "## <span>raw</span> html\n"
    "First line\nsecond line\n===\n"
    "```\n# Not a heading\n```\n"
)
