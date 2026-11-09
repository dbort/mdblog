import json
import re
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import override

import pytest

from mdblog.build import NOT_FOUND_MARKER
from mdblog.cli import main
from mdblog.verify import USER_AGENT, recent_shape_problem, verify_site


@dataclass(frozen=True)
class Reply:
    status: int
    content_type: str
    body: bytes
    headers: dict[str, str] = field(default_factory=dict[str, str])
    # Seconds the server waits before the status line.
    delay: float = 0.0
    # Seconds the server waits between the headers and the body.
    body_delay: float = 0.0


HOME = Reply(200, "text/html; charset=utf-8", b"<!doctype html><title>Site</title>")
FEED = Reply(
    200,
    "application/rss+xml",
    b'<?xml version="1.0"?><rss version="2.0"><channel><title>Site</title>'
    b"</channel></rss>",
)
RECENT = Reply(
    200,
    "application/json",
    json.dumps(
        {"items": [{"title": "T", "url": "https://x.test/", "date": "2026-01-01"}]}
    ).encode(),
)
NOT_FOUND = Reply(
    404,
    "text/html",
    f'<meta name="mdblog-not-found" content="{NOT_FOUND_MARKER}">'.encode(),
)
OK_LINES = ["home page: ok", "feed: ok", "recent posts: ok", "404 page: ok"]


class FakeSite:
    """A local HTTP server holding a site under `/blog/`; any other path gets
    `not_found`. It records each request's path and User-Agent."""

    def __init__(self) -> None:
        self.routes = {
            "/blog/": HOME,
            "/blog/index.xml": FEED,
            "/blog/recent.json": RECENT,
        }
        self.not_found = NOT_FOUND
        self.requests: list[tuple[str, str | None]] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                site.requests.append((self.path, self.headers.get("User-Agent")))
                reply = site.routes.get(self.path, site.not_found)
                time.sleep(reply.delay)
                self.send_response(reply.status)
                self.send_header("Content-Type", reply.content_type)
                self.send_header("Content-Length", str(len(reply.body)))
                for name, value in reply.headers.items():
                    self.send_header(name, value)
                self.end_headers()
                time.sleep(reply.body_delay)
                self.wfile.write(reply.body)

            @override
            def log_message(self, format: str, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/blog/"


@pytest.fixture
def fake_site() -> Iterator[FakeSite]:
    site = FakeSite()
    thread = threading.Thread(
        target=site.server.serve_forever, args=(0.01,), daemon=True
    )
    thread.start()
    yield site
    site.server.shutdown()
    site.server.server_close()


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
        ({"items": [{"title": "T", "url": "U", "date": "D"}]}, None),
        ({"items": [], "more": 1}, "not an object whose only key is items"),
        ({"items": {}}, "items is not an array"),
        (
            {"items": [{"title": "T", "url": "U"}]},
            "item 0 does not have exactly the keys date, title and url",
        ),
        (
            {"items": [{"title": "T", "url": "U", "date": "D"}, "entry"]},
            "item 1 does not have exactly the keys date, title and url",
        ),
        (
            {"items": [{"title": 1, "url": "U", "date": "D"}]},
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
