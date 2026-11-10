"""fake_site: a local HTTP server standing in for a deployed site under `/blog/`."""

import json
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import override

from mdblog.build import NOT_FOUND_MARKER


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
        {
            "items": [
                {
                    "title": "T",
                    "url": "https://x.test/",
                    "date": "2026-01-01",
                    "summary": "S",
                }
            ]
        }
    ).encode(),
)
NOT_FOUND = Reply(
    404,
    "text/html",
    f'<meta name="mdblog-not-found" content="{NOT_FOUND_MARKER}">'.encode(),
)


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
