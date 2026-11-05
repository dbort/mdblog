import datetime as dt
import json
from collections.abc import Callable

import pytest

from mdblog.properties import PageProperties, front_matter, validate_properties

# POSIX counts offsets west of UTC as positive, so this is UTC-5.
LOCAL_ZONE = "XXX5"
# Eastern time's daylight saving rule, UTC-5 in winter and UTC-4 in summer.
DAYLIGHT_ZONE = "EST5EDT,M3.2.0,M11.1.0"
ZONE = dt.timezone(dt.timedelta(hours=-5))
NOW = dt.datetime(2026, 6, 15, 12, 0, tzinfo=ZONE)
VALID: dict[object, object] = {
    "date": dt.date(2026, 1, 1),
    "slug": "a-note",
    "type": "post",
}


@pytest.fixture(autouse=True)
def _local_zone_matches_the_clock(local_zone: Callable[[str], None]) -> None:
    local_zone(LOCAL_ZONE)


def _validate(**changes: object) -> PageProperties | tuple[str, ...]:
    return validate_properties({**VALID, **changes}, "File Name", NOW)


def _page(**changes: object) -> PageProperties:
    page = _validate(**changes)
    assert isinstance(page, PageProperties), page
    return page


def _failures(**changes: object) -> tuple[str, ...]:
    failures = _validate(**changes)
    assert isinstance(failures, tuple), failures
    return failures


def test_validate_returns_every_property() -> None:
    page = _page(
        title="A title",
        type="link",
        url="https://example.test/page",
        tags=["one", "project/alpha"],
    )

    assert page == PageProperties(
        title="A title",
        date=dt.date(2026, 1, 1),
        slug="a-note",
        entry_type="link",
        tags=("one", "project/alpha"),
        link_url="https://example.test/page",
    )


def test_validate_reports_every_failure_of_a_note() -> None:
    failures = validate_properties(
        {"title": 1, "tags": 1, "date": "soon", "slug": "A", "type": "x"}, "n", NOW
    )

    assert isinstance(failures, tuple)
    assert [reason.split()[0] for reason in failures] == [
        "title",
        "date",
        "slug",
        "type",
        "tags",
    ]


@pytest.mark.parametrize("name", ["date", "slug", "type"])
def test_a_missing_required_property_fails(name: str) -> None:
    given = {key: value for key, value in VALID.items() if key != name}

    assert validate_properties(given, "n", NOW) == (f"{name} is required",)


@pytest.mark.parametrize("name", ["date", "slug", "type"])
def test_a_null_required_property_fails(name: str) -> None:
    assert validate_properties({**VALID, name: None}, "n", NOW) == (
        f"{name} is required",
    )


@pytest.mark.parametrize("changes", [{}, {"title": None}])
def test_a_missing_or_null_title_comes_from_the_file_name(
    changes: dict[str, None],
) -> None:
    assert _page(**changes).title == "File Name"


@pytest.mark.parametrize("title", [1, True, ["a"], dt.date(2026, 1, 1)])
def test_a_title_of_another_type_fails(title: object) -> None:
    assert _failures(title=title) == (f"title must be a string, not {title!r}",)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(dt.date(2026, 6, 15), id="today"),
        pytest.param(dt.datetime(2026, 6, 15, 11, 59, tzinfo=ZONE), id="aware-past"),
        # 16:59 UTC is 11:59 at the clock's offset, so the instant has passed.
        pytest.param(
            dt.datetime(2026, 6, 15, 16, 59, tzinfo=dt.UTC), id="other-zone-past"
        ),
    ],
)
def test_a_date_that_has_arrived_passes(value: dt.date) -> None:
    assert _page(date=value).date == value


def test_a_naive_datetime_that_has_arrived_gains_the_local_offset() -> None:
    page = _page(date=dt.datetime(2026, 6, 15, 11, 59))

    assert page.date == dt.datetime(2026, 6, 15, 11, 59, tzinfo=ZONE)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(dt.date(2026, 6, 16), id="tomorrow"),
        pytest.param(dt.datetime(2026, 6, 15, 12, 1), id="naive-future"),
        pytest.param(dt.datetime(2026, 6, 15, 12, 1, tzinfo=ZONE), id="aware-future"),
        # 17:01 UTC is 12:01 at the clock's offset, so the instant has not arrived.
        pytest.param(
            dt.datetime(2026, 6, 15, 17, 1, tzinfo=dt.UTC), id="other-zone-future"
        ),
    ],
)
def test_a_future_date_fails(value: dt.date) -> None:
    assert _failures(date=value) == (f"date {value.isoformat()} is in the future",)


@pytest.mark.parametrize("value", ["2026-01-01", 2026, True, ["2026-01-01"]])
def test_a_date_of_another_type_fails(value: object) -> None:
    assert _failures(date=value) == (
        f"date must be a YAML date or datetime, not {value!r}",
    )


@pytest.mark.parametrize("slug", ["a", "a-note", "2026", "a1-b2-c3"])
def test_a_good_slug_passes(slug: str) -> None:
    assert _page(slug=slug).slug == slug


@pytest.mark.parametrize(
    "slug",
    ["A", "a_b", "a--b", "-a", "a-", "", "a b", "é", "a\n", 2026, ["a"]],
)
def test_a_bad_slug_fails(slug: object) -> None:
    assert _failures(slug=slug) == (
        "slug must be lowercase letters and digits joined by single hyphens, "
        f"not {slug!r}",
    )


@pytest.mark.parametrize("entry_type", ["post", "til"])
def test_url_has_no_effect_off_a_link_entry(entry_type: str) -> None:
    for url in ("not a url", 1, None, "https://example.test/"):
        page = _page(type=entry_type, url=url)
        assert page.entry_type == entry_type
        assert page.link_url is None


@pytest.mark.parametrize("entry_type", ["Post", "page", "", 1, ["post"]])
def test_another_type_fails(entry_type: object) -> None:
    assert _failures(type=entry_type) == (
        f"type must be one of post, til, link, not {entry_type!r}",
    )


@pytest.mark.parametrize("url", ["http://example.test", "HTTPS://example.test/a?b=c"])
def test_a_link_entry_keeps_a_web_url(url: str) -> None:
    assert _page(type="link", url=url).link_url == url


@pytest.mark.parametrize("changes", [{}, {"url": None}])
def test_a_link_entry_requires_url(changes: dict[str, None]) -> None:
    assert _failures(type="link", **changes) == ("a link entry requires url",)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.test/",
        "javascript:alert(1)",
        "example.test",
        "/posts/a/",
        "https://",
        "https://exa mple.test/",
        "http://[x",
        "",
        1,
    ],
)
def test_a_link_entry_with_a_bad_url_fails(url: object) -> None:
    assert _failures(type="link", url=url) == (
        f"url must be an http or https URL, not {url!r}",
    )


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        pytest.param(None, (), id="null"),
        pytest.param("one", ("one",), id="one-string"),
        pytest.param(["one", "two"], ("one", "two"), id="list"),
        pytest.param([], (), id="empty-list"),
    ],
)
def test_good_tags_pass(tags: object, expected: tuple[str, ...]) -> None:
    assert _page(tags=tags).tags == expected


@pytest.mark.parametrize("tags", [1, True, {"a": "b"}, ["one", 2], [None]])
def test_bad_tags_fail(tags: object) -> None:
    assert _failures(tags=tags) == (
        f"tags must be a string or a list of strings, not {tags!r}",
    )


def _front_matter(**changes: object) -> dict[str, object]:
    loaded: object = json.loads(front_matter(_page(**changes)))
    assert isinstance(loaded, dict)
    return loaded


def test_front_matter_holds_only_the_listed_keys() -> None:
    loaded = _front_matter(
        aliases=["/old/"], weight=1, draft=True, url="https://example.test/"
    )

    assert loaded == {
        "title": "File Name",
        "date": "2026-01-01",
        "params": {"entry_type": "post"},
    }


def test_front_matter_of_a_link_entry_with_tags() -> None:
    loaded = _front_matter(type="link", url="https://example.test/", tags="one")

    assert loaded["tags"] == ["one"]
    assert loaded["params"] == {
        "entry_type": "link",
        "link_url": "https://example.test/",
    }


def test_front_matter_keeps_a_datetime_and_its_offset() -> None:
    value = dt.datetime(2026, 1, 1, 10, 0, tzinfo=ZONE)

    assert _front_matter(date=value)["date"] == "2026-01-01T10:00:00-05:00"


@pytest.mark.parametrize(
    ("value", "written"),
    [
        pytest.param(
            dt.datetime(2026, 1, 1, 10, 0), "2026-01-01T10:00:00-05:00", id="winter"
        ),
        pytest.param(
            dt.datetime(2026, 6, 1, 10, 0), "2026-06-01T10:00:00-04:00", id="summer"
        ),
    ],
)
def test_front_matter_writes_a_naive_datetime_with_the_offset_for_its_date(
    local_zone: Callable[[str], None], value: dt.datetime, written: str
) -> None:
    local_zone(DAYLIGHT_ZONE)

    assert _front_matter(date=value)["date"] == written


@pytest.mark.parametrize("title", ['yes: "quoted" } { \\ é 🙂', "yes", "123"])
def test_front_matter_keeps_a_title_exactly(title: str) -> None:
    assert _front_matter(title=title)["title"] == title
