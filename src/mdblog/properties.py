"""mdblog.properties: validates a published note's properties and writes its front matter."""

import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

SLUG_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
TAG_PUNCTUATION = "-_+."
# The slug a file name yields when it holds no ASCII letter or digit.
EMPTY_NAME_SLUG = "note"
# The Hugo page param that marks a published note rendering despite failures. Vault
# properties never reach Hugo, so only mdblog can set it.
INVALID_PARAM = "mdblog_invalid"
# The Hugo page param holding a note's converted lede Markdown, which the layouts show
# in place of an excerpt.
LEDE_PARAM = "mdblog_lede"


class EntryStatus(StrEnum):
    """What an entry is under draft mode, which decides its label."""

    PUBLISHED = "published"
    # Marked `publish: false`.
    DRAFT = "draft"
    # Marked `publish: true` but failing validation or a link.
    INVALID = "invalid"


@dataclass(frozen=True)
class PageProperties:
    """The validated properties of one published note."""

    title: str
    # A `date` is a whole day. A `datetime` is an instant and always holds its offset.
    date: date
    # Sets the page's URL, `/posts/<slug>/`.
    slug: str
    tags: tuple[str, ...]


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


def _is_word_character(character: str) -> bool:
    category = unicodedata.category(character)
    return category == "Nd" or category.startswith("L")


def _is_safe_tag_segment(segment: str) -> bool:
    # Hugo makes a tag's text the page's path after removing the characters it dislikes,
    # so `!..` becomes `..`, which writes outside `/tags/` or over the home page. The
    # allowlist holds only characters Hugo keeps. Hugo's Unicode tables can be older than
    # Python's and drop a letter they do not know, so a part with a dot must hold an
    # ASCII letter or digit, which no table can drop.
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
        f"tag {tag!r} must be /-separated parts using only letters, combining marks, "
        "digits, -, _, + and ., each holding a letter or digit, and any part with . "
        "an ASCII one"
        for tag in unsafe
    )
    return None if unsafe else tags


def validate_properties(
    properties: Mapping[object, object], stem: str, now: datetime
) -> PageProperties | tuple[str, ...]:
    """The validated properties of a published note, or the reason for every failure.

    `stem` is the note's file name without its suffix, and is the title when `title` is
    missing. `now` is the timezone-aware current time, and its date is today, so it
    should be in the local zone. A datetime with no offset means local time and is
    returned with its offset. A null property counts as missing. Reads `title`,
    `date`, `slug` and `tags`. Other properties have no effect.
    """
    failures: list[str] = []
    title = _title(properties.get("title"), stem, failures)
    page_date = _date(properties.get("date"), now, failures)
    slug = _slug(properties.get("slug"), failures)
    tags = _tags(properties.get("tags"), failures)
    if failures or title is None or page_date is None or slug is None or tags is None:
        return tuple(failures)
    return PageProperties(title=title, date=page_date, slug=slug, tags=tags)


@dataclass(frozen=True)
class PreviewProperties:
    """A note's usable properties under draft mode, with unusable ones left to the caller."""

    # The file name's stem when `title` is missing or invalid.
    title: str
    # None when `date` is missing or invalid.
    date: date | None
    # The note's own slug, or None when `slug` is missing or invalid.
    slug: str | None
    # Empty when `tags` is missing or invalid.
    tags: tuple[str, ...]


def preview_properties(
    properties: Mapping[object, object], stem: str, now: datetime, draft: bool
) -> tuple[PreviewProperties, tuple[str, ...]]:
    """The usable properties of a note under draft mode, and the reason for each failure.

    For a published note (`draft` false) the reasons are exactly those of
    `validate_properties`, but a future date is still returned. A draft has no reason
    for a missing `date` or `slug` or a future date, so only a present but invalid
    property gives one.
    """
    failures: list[str] = []
    title = _title(properties.get("title"), stem, failures)
    date_value = properties.get("date")
    date_failures: list[str] = []
    _date(date_value, now, date_failures)
    if draft and (date_value is None or isinstance(date_value, date)):
        date_failures = []
    failures.extend(date_failures)
    slug_value = properties.get("slug")
    slug_failures: list[str] = []
    slug = _slug(slug_value, slug_failures)
    if not draft or slug_value is not None:
        failures.extend(slug_failures)
    tags = _tags(properties.get("tags"), failures)
    page = PreviewProperties(
        title=stem if title is None else title,
        date=_with_local_offset(date_value) if isinstance(date_value, date) else None,
        slug=slug,
        tags=() if tags is None else tags,
    )
    return page, tuple(failures)


def file_slug(stem: str) -> str:
    """A slug made from the file name `stem`, always matching `SLUG_PATTERN`.

    Each run of characters other than ASCII letters and digits becomes one hyphen in the
    lowercased stem, without leading or trailing hyphens. A stem with no ASCII letter or
    digit gives `EMPTY_NAME_SLUG`.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return slug or EMPTY_NAME_SLUG


def front_matter(
    page: PageProperties,
    status: EntryStatus = EntryStatus.PUBLISHED,
    lede: str | None = None,
) -> bytes:
    """The Hugo front matter for `page`, ending in a newline.

    The result is one JSON object holding `title`, `date` and, when there are any,
    `tags`. A draft adds `draft: true`, and an invalid entry adds `INVALID_PARAM`
    under `params`. A published entry adds neither. A `lede` is `LEDE_PARAM` under
    `params`.
    """
    data: dict[str, object] = {"title": page.title, "date": page.date.isoformat()}
    if page.tags:
        data["tags"] = list(page.tags)
    params: dict[str, object] = {}
    # Hugo's own draft flag, so Hugo leaves a draft out of any build without
    # --buildDrafts.
    if status is EntryStatus.DRAFT:
        data["draft"] = True
    elif status is EntryStatus.INVALID:
        params[INVALID_PARAM] = True
    if lede is not None:
        params[LEDE_PARAM] = lede
    if params:
        data["params"] = params
    # Hugo reads a leading JSON object as front matter, and JSON has one reading of each
    # string, where a YAML reader could take a title of `yes` for a boolean.
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
