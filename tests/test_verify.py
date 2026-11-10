import re
import socket

import pytest

from fake_site import FEED, HOME, NOT_FOUND, FakeSite, Reply
from mdblog.build import NOT_FOUND_MARKER
from mdblog.cli import main
from mdblog.verify import USER_AGENT, recent_shape_problem, verify_site

OK_LINES = ["home page: ok", "feed: ok", "recent posts: ok", "404 page: ok"]


def _verify(url: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str]]:
    status = main(["verify", url])
    out, err = capsys.readouterr()
    assert err == ""
    return status, out.splitlines()


@pytest.mark.parametrize("trailing_slash", [True, False])
def test_a_site_that_passes_every_check_exits_0(
    fake_site: FakeSite, capsys: pytest.CaptureFixture[str], trailing_slash: bool
) -> None:
    url = fake_site.url if trailing_slash else fake_site.url.removesuffix("/")

    assert _verify(url, capsys) == (0, OK_LINES)
    paths = [path for path, _ in fake_site.requests]
    assert paths[:3] == ["/blog/", "/blog/index.xml", "/blog/recent.json"]
    assert re.fullmatch(r"/blog/mdblog-verify-missing-[0-9a-f]{16}/", paths[3])
    assert len(paths) == 4
    assert {agent for _, agent in fake_site.requests} == {USER_AGENT}


def test_the_missing_path_differs_on_each_run(fake_site: FakeSite) -> None:
    list(verify_site(fake_site.url))
    list(verify_site(fake_site.url))

    missing = [path for path, _ in fake_site.requests if "missing" in path]
    assert len(set(missing)) == 2


FEED_WITHOUT_CHANNEL = b'<rss version="2.0"><title>Site</title></rss>'
ATOM = b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Site</title></feed>'
REDIRECT = Reply(301, "text/html", b"", {"Location": "/blog/"})


@pytest.mark.parametrize(
    ("path", "reply", "line"),
    [
        ("/blog/", Reply(500, "text/html", b""), "home page: status 500, expected 200"),
        (
            "/blog/",
            Reply(200, "text/plain", b"hi"),
            "home page: content type text/plain, expected text/html",
        ),
        (
            "/blog/index.xml",
            Reply(404, "text/html", b""),
            "feed: status 404, expected 200",
        ),
        ("/blog/index.xml", Reply(200, "application/xml", b"<rss"), "feed: not XML: "),
        (
            "/blog/index.xml",
            Reply(200, "application/xml", ATOM),
            "feed: not an RSS 2.0 document",
        ),
        (
            "/blog/index.xml",
            Reply(200, "application/xml", FEED_WITHOUT_CHANNEL),
            "feed: no <channel>",
        ),
        (
            "/blog/recent.json",
            Reply(500, "text/html", b""),
            "recent posts: status 500, expected 200",
        ),
        (
            "/blog/recent.json",
            Reply(200, "application/json", b"{"),
            "recent posts: not JSON: ",
        ),
        (
            "/blog/recent.json",
            Reply(200, "application/json", b"[]"),
            "recent posts: not an object whose only key is items",
        ),
        (None, HOME, "404 page: status 200, expected 404"),
        (None, REDIRECT, "404 page: status 301, expected 404"),
        (
            None,
            Reply(404, "text/html", b"Not found"),
            f"404 page: body lacks the 404 marker {NOT_FOUND_MARKER}",
        ),
    ],
)
def test_a_failing_check_names_its_reason_and_the_others_still_run(
    fake_site: FakeSite,
    capsys: pytest.CaptureFixture[str],
    path: str | None,
    reply: Reply,
    line: str,
) -> None:
    if path is None:
        fake_site.not_found = reply
    else:
        fake_site.routes[path] = reply

    status, lines = _verify(fake_site.url, capsys)

    assert status == 1
    [failed] = [index for index, text in enumerate(lines) if not text.endswith(": ok")]
    assert lines[failed].startswith(line)
    assert (
        lines[:failed] + lines[failed + 1 :]
        == OK_LINES[:failed] + OK_LINES[failed + 1 :]
    )


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        ({"items": []}, None),
        (
            {"items": [{"title": "T", "url": "U", "date": "D", "summary": ""}]},
            None,
        ),
        ({"items": [], "more": 1}, "not an object whose only key is items"),
        ({"items": {}}, "items is not an array"),
        (
            {"items": [{"title": "T", "url": "U", "date": "D"}]},
            "item 0 does not have exactly the keys date, summary, title, url",
        ),
        (
            {
                "items": [
                    {"title": "T", "url": "U", "date": "D", "summary": "S"},
                    "entry",
                ]
            },
            "item 1 does not have exactly the keys date, summary, title, url",
        ),
        (
            {"items": [{"title": 1, "url": "U", "date": "D", "summary": "S"}]},
            "item 0 has a value that is not a string",
        ),
    ],
)
def test_recent_shape_problem_names_the_first_break_of_the_contract(
    value: object, problem: str | None
) -> None:
    assert recent_shape_problem(value) == problem


def test_a_refused_connection_fails_every_check_naming_its_url(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}/blog/"

    status, lines = _verify(url, capsys)

    assert status == 1
    assert [line.split(": ")[0] for line in lines] == [
        line.split(": ")[0] for line in OK_LINES
    ]
    targets = [
        url,
        url + "index.xml",
        url + "recent.json",
        url + "mdblog-verify-missing-",
    ]
    for line, target in zip(lines, targets, strict=True):
        assert f": {target}" in line
        assert "Connection refused" in line


@pytest.mark.parametrize(
    ("check", "path"),
    [
        # Before the status line arrives.
        ("feed", "index.xml"),
        # In an error response's body, after its status and headers arrived.
        ("404 page", None),
    ],
)
def test_a_timeout_fails_only_the_slow_request(
    fake_site: FakeSite, check: str, path: str | None
) -> None:
    # The handler threads are daemons, so the test waits out only the timeout.
    if path is None:
        fake_site.not_found = Reply(404, "text/html", NOT_FOUND.body, body_delay=5.0)
    else:
        fake_site.routes["/blog/" + path] = Reply(200, "text/xml", FEED.body, delay=5.0)

    results = dict(verify_site(fake_site.url, timeout=0.3))

    slow = fake_site.url + (path or "mdblog-verify-missing-")
    problem = results.pop(check)
    assert problem is not None and problem.startswith(slow)
    assert problem.endswith(": timed out")
    assert set(results.values()) == {None}


@pytest.mark.parametrize(
    "url", ["ftp://example.test/blog/", "example.test/blog/", "http:///"]
)
def test_verify_refuses_a_url_that_is_not_http_before_any_request(
    capsys: pytest.CaptureFixture[str], url: str
) -> None:
    assert main(["verify", url]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert err == f"mdblog: {url!r} is not an http or https URL\n"
