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
