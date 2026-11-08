"""mdblog serve end to end, with real Hugo and real file watching."""

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

import pytest

from mdblog.build import MARKER
from notes import published_text

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_VAULT = REPO_ROOT / "tests" / "fixtures" / "vault"
# The Must Have's limit on how long a change takes to reach the served site.
CHANGE_TIMEOUT = 10
# Hugo's first build and the watcher's setup take longer than a rebuild.
STARTUP_TIMEOUT = 30


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def _get(url: str) -> tuple[int, str]:
    """The status and body of `url`, with status 0 while nothing answers."""
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            status: int = response.status
            return status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except urllib.error.URLError:
        return 0, ""


def _wait(
    what: str, ready: Callable[[], bool], timeout: float = CHANGE_TIMEOUT
) -> None:
    deadline = time.monotonic() + timeout
    while not ready():
        if time.monotonic() > deadline:
            pytest.fail(f"timed out after {timeout}s waiting for {what}")
        time.sleep(0.2)


def _serves(url: str, text: str) -> Callable[[], bool]:
    def ready() -> bool:
        status, body = _get(url)
        return status == 200 and text in body

    return ready


def test_serve_follows_vault_changes_and_cleans_up(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    config = vault / "_site" / "mdblog.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "https://example.org/", "https://example.test/blog/"
        ),
        encoding="utf-8",
    )
    offset_note = vault / "projects" / "offset-time.md"
    temp = tmp_path / "temp"
    temp.mkdir()
    port = _free_port()
    site = f"http://localhost:{port}/blog/"
    output = temp / f"mdblog-serve-{port}"
    stderr_path = tmp_path / "stderr.txt"
    env = {**os.environ, "TMPDIR": str(temp), "HUGO_BASEURL": "http://hugo.example/"}
    command = [
        sys.executable,
        "-c",
        "import sys; from mdblog.cli import main; sys.exit(main())",
        "serve",
        str(vault),
        "--port",
        str(port),
    ]
    with stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            command, env=env, stdout=subprocess.DEVNULL, stderr=stderr
        )
    try:
        _wait(
            "the first page",
            _serves(f"{site}posts/offset-time/", "FIXTURE-OFFSET-BODY"),
            STARTUP_TIMEOUT,
        )
        assert (output / MARKER).is_file()
        assert f'href="{site}index.xml"' in _get(site)[1]
        leaks = [
            path
            for path in output.rglob("*")
            if path.is_file() and b"example.test" in path.read_bytes()
        ]
        assert leaks == []

        offset_note.write_text(
            offset_note.read_text(encoding="utf-8").replace(
                "FIXTURE-OFFSET-BODY", "EDITED-BODY"
            ),
            encoding="utf-8",
        )
        _wait("an edit", _serves(f"{site}posts/offset-time/", "EDITED-BODY"))

        added = vault / "added.md"
        added.write_text(published_text("added", body="ADDED-BODY\n"), "utf-8")
        _wait("an added note", _serves(f"{site}posts/added/", "ADDED-BODY"))

        bad = vault / "bad.md"
        bad.write_text("---\npublish: yes\n---\n", encoding="utf-8")
        _wait(
            "the failure",
            lambda: "bad.md: publish must be true or false" in stderr_path.read_text(),
        )
        assert _serves(f"{site}posts/offset-time/", "EDITED-BODY")()

        bad.unlink()
        added.unlink()
        _wait("a removed note", lambda: _get(f"{site}posts/added/")[0] == 404)
        assert not (output / "posts" / "added").exists()
        assert _serves(f"{site}posts/offset-time/", "EDITED-BODY")()

        config.write_text(
            config.read_text(encoding="utf-8").replace("mdblog fixture", "NEW-TITLE"),
            encoding="utf-8",
        )
        _wait("a settings change", _serves(site, "NEW-TITLE"))

        bio = vault / "_site" / "bio.md"
        bio.write_text(
            bio.read_text(encoding="utf-8").replace("FIXTURE-BIO", "EDITED-BIO"),
            encoding="utf-8",
        )
        _wait("a bio change", _serves(site, "EDITED-BIO"))

        footer = vault / "_site" / "layouts" / "_partials" / "footer.html"
        footer.parent.mkdir(parents=True)
        footer.write_text("<footer>LAYOUT-ONE</footer>\n", encoding="utf-8")
        _wait("a new layout", _serves(site, "LAYOUT-ONE"))
        footer.write_text("<footer>LAYOUT-TWO</footer>\n", encoding="utf-8")
        _wait("a layout change", _serves(site, "LAYOUT-TWO"))

        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=30) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    assert list(temp.iterdir()) == []


DRAFT_LABEL = '<span class="entry-status entry-status-draft">Draft</span>'
INVALID_LABEL = '<span class="entry-status entry-status-invalid">Invalid</span>'
BANNER = '<p class="preview-banner">'


def _draft_vault(root: Path) -> Path:
    vault = root / "vault"
    notes = {
        "_site/mdblog.toml": 'base_url = "https://example.test/"\n'
        'title = "Preview Site"\nauthor = "A"\n',
        "_site/bio.md": "BIO-TEXT [[missing bio link]]\n",
        "drafts/My Draft.md": "---\npublish: false\ntags: [shared]\n---\n"
        "DRAFT-BODY [[nowhere]]\n",
        "broken.md": "---\npublish: true\ntitle: Broken Entry\ntags: shared\n---\n"
        "BROKEN-BODY\n",
        "good.md": published_text(
            "good", extra="tags: shared\n", body="GOOD-BODY [[My Draft]]\n"
        ),
    }
    for relative, text in notes.items():
        path = vault / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return vault


def test_serve_drafts_labels_entries_and_shows_the_banner(tmp_path: Path) -> None:
    vault = _draft_vault(tmp_path)
    port = _free_port()
    site = f"http://localhost:{port}/"
    stderr_path = tmp_path / "stderr.txt"
    command = [
        sys.executable,
        "-c",
        "import sys; from mdblog.cli import main; sys.exit(main())",
        "serve",
        str(vault),
        "--drafts",
        "--port",
        str(port),
        "--output",
        str(tmp_path / "output"),
    ]
    with stderr_path.open("wb") as stderr:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=stderr)
    try:
        _wait(
            "the first page",
            _serves(f"{site}posts/good/", "GOOD-BODY"),
            STARTUP_TIMEOUT,
        )
        pages = {
            name: _get(f"{site}{name}")[1]
            for name in ("", "posts/", "tags/shared/", "posts/good/")
        }
        for name in ("posts/my-draft/", "posts/broken/"):
            _wait(name, _serves(f"{site}{name}", BANNER))
            pages[name] = _get(f"{site}{name}")[1]
    finally:
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=30)

    assert all(BANNER in page for page in pages.values())
    for name in ("", "posts/", "tags/shared/"):
        assert pages[name].count(DRAFT_LABEL) == 1, name
        assert pages[name].count(INVALID_LABEL) == 1, name
    for name in ("", "tags/shared/"):
        assert f"</a> {DRAFT_LABEL}</h2>" in pages[name], name
        assert f"</a> {INVALID_LABEL}</h2>" in pages[name], name
    draft = pages["posts/my-draft/"]
    assert draft.count(DRAFT_LABEL) == 1
    assert f"</a> {DRAFT_LABEL}</h1>" in draft
    assert INVALID_LABEL not in draft
    assert "DRAFT-BODY [[nowhere]]" in draft
    broken = pages["posts/broken/"]
    assert broken.count(INVALID_LABEL) == 1
    assert DRAFT_LABEL not in broken
    good = pages["posts/good/"]
    assert "entry-status" not in good
    assert '<a href="/posts/my-draft/">My Draft</a>' in good
    assert "BIO-TEXT [[missing bio link]]" in pages[""]
    err = stderr_path.read_text(encoding="utf-8")
    for line in (
        "mdblog: warnings from these notes, shown in the draft preview anyway:",
        "  _site/bio.md: [[missing bio link]]: matches no note or file",
        "  broken.md: date is required",
        "  broken.md: slug is required",
        "  drafts/My Draft.md: [[nowhere]]: matches no note or file",
    ):
        assert line in err.splitlines(), line
