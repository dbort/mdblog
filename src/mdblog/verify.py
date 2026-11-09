"""mdblog.verify: checks that a URL serves an mdblog site."""

import http.client
import json
import secrets
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from email.message import Message
from typing import IO, override
from urllib.parse import urlsplit

from mdblog.build import NOT_FOUND_MARKER

# Seconds urllib waits on each blocking socket operation: the connect and each read.
# It does not bound a whole request, so a server sending slowly in small pieces can
# hold one request longer.
TIMEOUT = 10.0
# Names the client and nothing else; no contact address.
USER_AGENT = "mdblog-verify"
# The keys of each `recent.json` item; `home.recent.json` states the contract.
RECENT_ITEM_KEYS = frozenset(("title", "url", "date"))
# The missing path's name ends with a random suffix, so no site can hold it.
MISSING_PREFIX = "mdblog-verify-missing-"


class VerifyError(Exception):
    """A URL that `verify_site` cannot check."""


class FetchError(Exception):
    """A request that got no HTTP response; the message names the URL and the cause."""


@dataclass(frozen=True)
class Response:
    """One HTTP response, whatever its status."""

    status: int
    # The media type alone, lowercased, without parameters such as `charset`.
    content_type: str
    body: bytes


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # Returning None makes urllib raise the 3xx response as an HTTPError.
    @override
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> None:
        return None


def site_url(url: str) -> str:
    """`url` with a trailing slash, so relative names resolve under its path.

    Raises `VerifyError` unless `url` is an http or https URL with a host.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise VerifyError(f"{url!r} is not an http or https URL")
    return url if url.endswith("/") else url + "/"


def fetch(url: str, timeout: float, follow_redirects: bool = True) -> Response:
    """The response to one GET of `url`, including error statuses.

    Without `follow_redirects`, a redirect is the response. Raises `FetchError` when
    the connection fails or a socket operation waits longer than `timeout` seconds.
    """
    handlers = () if follow_redirects else (_NoRedirect(),)
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(request, timeout=timeout) as response:
            return Response(
                response.status,
                response.headers.get_content_type(),
                response.read(),
            )
    except urllib.error.HTTPError as exc:
        with exc:
            return Response(exc.code, exc.headers.get_content_type(), exc.read())
    except urllib.error.URLError as exc:
        raise FetchError(f"{url}: {exc.reason}") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise FetchError(f"{url}: {exc}") from exc


def _status(response: Response, expected: int) -> str | None:
    if response.status != expected:
        return f"status {response.status}, expected {expected}"
    return None


def check_home(response: Response) -> str | None:
    """Why `response` is not a home page, or None when it is: status 200 and HTML."""
    if problem := _status(response, 200):
        return problem
    if response.content_type != "text/html":
        return f"content type {response.content_type}, expected text/html"
    return None


def check_feed(response: Response) -> str | None:
    """Why `response` is not an RSS 2.0 feed with a channel, or None when it is."""
    if problem := _status(response, 200):
        return problem
    try:
        root = ET.fromstring(response.body)
    except ET.ParseError as exc:
        return f"not XML: {exc}"
    if root.tag != "rss" or root.get("version") != "2.0":
        return "not an RSS 2.0 document"
    if root.find("channel") is None:
        return "no <channel>"
    return None


def recent_shape_problem(value: object) -> str | None:
    """Why the parsed JSON `value` breaks the `recent.json` contract, or None."""
    if not isinstance(value, dict) or list(value) != ["items"]:
        return "not an object whose only key is items"
    items: object = value["items"]
    if not isinstance(items, list):
        return "items is not an array"
    for index, item in enumerate(items):
        if not isinstance(item, dict) or set(item) != RECENT_ITEM_KEYS:
            return f"item {index} does not have exactly the keys date, title and url"
        if not all(isinstance(field, str) for field in item.values()):
            return f"item {index} has a value that is not a string"
    return None


def check_recent(response: Response) -> str | None:
    """Why `response` is not a `recent.json` file, or None when it is."""
    if problem := _status(response, 200):
        return problem
    try:
        # A site the verifier does not control supplies this value.
        value: object = json.loads(response.body)
    except ValueError as exc:
        return f"not JSON: {exc}"
    return recent_shape_problem(value)


def check_not_found(response: Response) -> str | None:
    """Why `response` is not the site's own 404 page, or None when it is."""
    if problem := _status(response, 404):
        return problem
    if NOT_FOUND_MARKER.encode() not in response.body:
        return f"body lacks the 404 marker {NOT_FOUND_MARKER}"
    return None


def verify_site(url: str, timeout: float = TIMEOUT) -> Iterator[tuple[str, str | None]]:
    """Each check's name and why it failed, or None when it passed, as it finishes.

    Makes one request per check, in a fixed order, and runs every check whatever the
    others found. A request that gets no response fails its check with the
    `FetchError` message. Raises `VerifyError` for a URL `site_url` refuses, before
    any request.
    """
    base = site_url(url)
    missing = f"{base}{MISSING_PREFIX}{secrets.token_hex(8)}/"
    checks = (
        ("home page", base, check_home, True),
        ("feed", base + "index.xml", check_feed, True),
        ("recent posts", base + "recent.json", check_recent, True),
        # A redirect here means the host's 404 handling is wrong.
        ("404 page", missing, check_not_found, False),
    )
    for name, target, check, follow in checks:
        try:
            yield name, check(fetch(target, timeout, follow))
        except FetchError as exc:
            yield name, str(exc)
