"""mdblog.properties: validates a published note's properties and writes its front matter."""

import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlsplit

SLUG_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
ENTRY_TYPES = ("post", "til", "link")
LINK_ENTRY = "link"
URL_SCHEMES = ("http", "https")
TAG_PUNCTUATION = "-_+."


@dataclass(frozen=True)
class PageProperties:
    """The validated properties of one published note."""

    title: str
    # A `date` is a whole day. A `datetime` is an instant and always holds its offset.
    date: date
    # Sets the page's URL, `/posts/<slug>/`.
    slug: str
    # One of `ENTRY_TYPES`.
    entry_type: str
    tags: tuple[str, ...]
    # Set only when `entry_type` is `LINK_ENTRY`.
    link_url: str | None


def valid_slug(value: object) -> str | None:
    """`value` if it is a string that is a usable slug, otherwise None."""
    if isinstance(value, str) and SLUG_PATTERN.fullmatch(value):
        return value
    return None


def _title(value: object, stem: str, failures: list[str]) -> str | None:
    if value is None:
        return stem
    if isinstance(value, str):
        return value
    failures.append(f"title must be a string, not {value!r}")
    return None


def _with_local_offset(value: date) -> date:
    # Hugo reads a datetime with no offset as UTC, so a local time has to carry its offset
    # to reach the site as the same instant. astimezone uses the offset for that date,
    # which can differ from today's across a daylight saving change.
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.astimezone()
    return value


def _is_future(value: date, now: datetime) -> bool:
    if isinstance(value, datetime):
        return value > now
    return value > now.date()


def _date(value: object, now: datetime, failures: list[str]) -> date | None:
    if value is None:
        failures.append("date is required")
    elif not isinstance(value, date):
        failures.append(f"date must be a YAML date or datetime, not {value!r}")
    else:
        resolved = _with_local_offset(value)
        if not _is_future(resolved, now):
            return resolved
        failures.append(f"date {value.isoformat()} is in the future")
    return None


def _slug(value: object, failures: list[str]) -> str | None:
    slug = valid_slug(value)
    if value is None:
        failures.append("slug is required")
    elif slug is None:
        failures.append(
            f"slug must be lowercase letters and digits joined by single hyphens, not {value!r}"
        )
    return slug


def _entry_type(value: object, failures: list[str]) -> str | None:
    if value is None:
        failures.append("type is required")
    elif isinstance(value, str) and value in ENTRY_TYPES:
        return value
    else:
        failures.append(f"type must be one of {', '.join(ENTRY_TYPES)}, not {value!r}")
    return None


def _is_word_character(character: str) -> bool:
    category = unicodedata.category(character)
    return category == "Nd" or category.startswith("L")


def _is_safe_tag_segment(segment: str) -> bool:
    # Hugo makes a tag's text the page's path after removing the characters it dislikes,
    # so `!..` becomes `..`, which writes outside `/tags/` or over the home page. An
    # allowlist holds only characters Hugo keeps. Its Unicode tables can be older than
    # Python's and drop a letter they do not know, so a dot needs an ASCII neighbor.
    if not all(
        character in TAG_PUNCTUATION
        or _is_word_character(character)
        or unicodedata.category(character).startswith("M")
        for character in segment
    ):
        return False
    if "." in segment:
        return any(c.isascii() and c.isalnum() for c in segment)
    return any(_is_word_character(character) for character in segment)


def _tag_list(value: object) -> tuple[str, ...] | None:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        tags = tuple(item for item in value if isinstance(item, str))
        if len(tags) == len(value):
            return tags
    return None


def _tags(value: object, failures: list[str]) -> tuple[str, ...] | None:
    if value is None:
        return ()
    tags = _tag_list(value)
    if tags is None:
        failures.append(f"tags must be a string or a list of strings, not {value!r}")
        return None
    unsafe = [
        tag
        for tag in tags
        if not all(_is_safe_tag_segment(segment) for segment in tag.split("/"))
    ]
    failures.extend(
        f"tag {tag!r} must be /-separated parts using only letters, digits, -, _, + "
        "and ., each holding a letter or digit, and any part with . an ASCII one"
        for tag in unsafe
    )
    return None if unsafe else tags


def _is_web_url(value: str) -> bool:
    if any(character.isspace() for character in value):
        return False
    try:
        parts = urlsplit(value)
    # urlsplit raises ValueError for a malformed host such as `http://[x`.
    except ValueError:
        return False
    return parts.scheme in URL_SCHEMES and bool(parts.netloc)


def _link_url(value: object, failures: list[str]) -> str | None:
    if value is None:
        failures.append("a link entry requires url")
    elif isinstance(value, str) and _is_web_url(value):
        return value
    else:
        failures.append(f"url must be an http or https URL, not {value!r}")
    return None


def validate_properties(
    properties: Mapping[object, object], stem: str, now: datetime
) -> PageProperties | tuple[str, ...]:
    """The validated properties of a published note, or the reason for every failure.

    `stem` is the note's file name without its suffix, and is the title when `title` is
    missing. `now` is the timezone-aware current time, and its date is today, so it
    should be in the local zone. A datetime with no offset means local time and is
    returned with its offset. A null property counts as missing. Reads `title`,
    `date`, `slug`, `type`, `tags` and, on a link entry only, `url`. Other properties
    have no effect.
    """
    failures: list[str] = []
    title = _title(properties.get("title"), stem, failures)
    page_date = _date(properties.get("date"), now, failures)
    slug = _slug(properties.get("slug"), failures)
    entry_type = _entry_type(properties.get("type"), failures)
    tags = _tags(properties.get("tags"), failures)
    link_url = None
    if entry_type == LINK_ENTRY:
        link_url = _link_url(properties.get("url"), failures)
    if (
        failures
        or title is None
        or page_date is None
        or slug is None
        or entry_type is None
        or tags is None
    ):
        return tuple(failures)
    return PageProperties(
        title=title,
        date=page_date,
        slug=slug,
        entry_type=entry_type,
        tags=tags,
        link_url=link_url,
    )


def front_matter(page: PageProperties) -> bytes:
    """The Hugo front matter for `page`, ending in a newline.

    The result is one JSON object holding `title`, `date`, `tags` when there are any,
    and `params`, which holds `entry_type` and any `link_url`.
    """
    params = {"entry_type": page.entry_type}
    if page.link_url is not None:
        params["link_url"] = page.link_url
    data: dict[str, object] = {"title": page.title, "date": page.date.isoformat()}
    if page.tags:
        data["tags"] = list(page.tags)
    data["params"] = params
    # Hugo reads a leading JSON object as front matter, and JSON has one reading of each
    # string, where a YAML reader could take a title of `yes` for a boolean.
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
