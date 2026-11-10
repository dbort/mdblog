import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path, PurePosixPath

import pytest

from mdblog import stage
from mdblog.build import MARKER, BuildError, build_site
from mdblog.cli import main
from mdblog.config import ConfigError, SiteConfig, WorkerConfig
from mdblog.serve import ServeError
from mdblog.stage import (
    ASSETS_DIR,
    COMPATIBILITY_DATE,
    WRANGLER_CONFIG,
    WRANGLER_ENV,
    base_path,
    find_wrangler,
    serve_bundle,
    stage_site,
    wrangler_config,
    wrangler_dev_argv,
)
from notes import published_text

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_VAULT = REPO_ROOT / "tests" / "fixtures" / "vault"
WORKER = '[worker]\nname = "test-site"\n'
ROUTES = 'routes = ["example.test/blog/*"]\n'
CONFIG = (
    'base_url = "https://example.test/blog/"\n'
    'title = "The Site Title"\n'
    'author = "The Site Author"\n'
)
# Stands in for Hugo: it writes the pages every site has, copies the source's static
# files as Hugo does, and records the base URL and whether drafts were asked for.
FAKE_HUGO = (
    sys.executable,
    "-c",
    "import json, pathlib, shutil, sys;"
    "argv = sys.argv[1:];"
    "source = pathlib.Path(argv[argv.index('--source') + 1]);"
    "destination = pathlib.Path(argv[argv.index('--destination') + 1]);"
    "[(destination / name).write_text(name) for name in"
    " ('index.html', '404.html', 'index.xml')];"
    "(source / 'static').is_dir() and shutil.copytree("
    " source / 'static', destination, dirs_exist_ok=True);"
    "(destination / 'seen.json').write_text(json.dumps({"
    "'drafts': '--buildDrafts' in argv,"
    "'config': (source / 'hugo.toml').read_text()}))",
)
FAILING_HUGO = (sys.executable, "-c", "raise SystemExit(3)")
# Wrangler would warn and fail on any request through these, so a test that passes
# with them set made no request.
NO_NETWORK = {"HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9"}
STARTUP_TIMEOUT = 60


def _make_vault(root: Path, config: str = CONFIG + WORKER) -> Path:
    vault = root / "vault"
    (vault / "_site").mkdir(parents=True)
    (vault / "_site" / "mdblog.toml").write_text(config, encoding="utf-8")
    (vault / "note.md").write_text(
        published_text("note", body="NOTE-BODY\n"), encoding="utf-8"
    )
    return vault


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): (
            path.read_bytes() if path.is_file(follow_symlinks=False) else None
        )
        for path in sorted(root.rglob("*"))
    }


def _previous_stage(root: Path) -> Path:
    output = root / "output"
    stage_site(_make_vault(root / "previous"), output, hugo=FAKE_HUGO)
    return output


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://example.test/", ""),
        ("https://example.test", ""),
        ("https://example.test/blog/", "blog"),
        ("https://example.test/a/b", "a/b"),
        ("https://example.test/my%20blog/", "my blog"),
        ("https://example.test/./blog/", "blog"),
    ],
)
def test_base_path_is_the_url_path_below_the_root(base_url: str, expected: str) -> None:
    assert base_path(base_url) == PurePosixPath(expected)


def test_base_path_refuses_a_parent_component() -> None:
    with pytest.raises(BuildError, match=r"'\.\.' path component"):
        base_path("https://example.test/a/../")


def test_wrangler_config_serves_the_assets_as_the_worker() -> None:
    config = SiteConfig("https://example.test/", "T", "A", WorkerConfig("my-site"))

    generated = wrangler_config(config)

    assert generated["name"] == "my-site"
    assert generated["compatibility_date"] == COMPATIBILITY_DATE
    assets = generated["assets"]
    assert isinstance(assets, dict)
    assert assets["directory"] == ASSETS_DIR
    assert assets["not_found_handling"] == "404-page"
    assert "main" not in generated


def test_wrangler_config_claims_the_routes_and_leaves_workers_dev() -> None:
    worker = WorkerConfig("my-site", ("b.test/blog/*", "a.test/blog/*"))
    config = SiteConfig("https://b.test/blog/", "T", "A", worker)

    generated = wrangler_config(config)

    assert generated["routes"] == ["b.test/blog/*", "a.test/blog/*"]
    assert generated["workers_dev"] is False


def test_wrangler_config_without_routes_sets_neither_key() -> None:
    config = SiteConfig("https://example.test/", "T", "A", WorkerConfig("my-site"))

    generated = wrangler_config(config)

    assert "routes" not in generated
    assert "workers_dev" not in generated


def test_stage_puts_the_site_under_its_base_path(tmp_path: Path) -> None:
    output = tmp_path / "output"

    assert stage_site(_make_vault(tmp_path), output, hugo=FAKE_HUGO) == PurePosixPath(
        "blog"
    )

    assert sorted(p.name for p in output.iterdir()) == sorted(
        [MARKER, WRANGLER_CONFIG, ASSETS_DIR]
    )
    assets = output / ASSETS_DIR
    assert [p.name for p in assets.iterdir()] == ["blog"]
    for name in ("index.html", "404.html", "index.xml"):
        assert (assets / "blog" / name).is_file()
    generated = json.loads((output / WRANGLER_CONFIG).read_text(encoding="utf-8"))
    assert generated["name"] == "test-site"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["output", "vault"]


def test_stage_puts_a_root_site_at_the_assets_root(tmp_path: Path) -> None:
    config = CONFIG.replace("/blog/", "/") + WORKER
    output = tmp_path / "output"

    stage_site(_make_vault(tmp_path, config), output, hugo=FAKE_HUGO)

    assert (output / ASSETS_DIR / "index.html").is_file()


def test_stage_keeps_every_marker_out_of_the_assets(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    static = vault / "_site" / "static"
    (static / "nested").mkdir(parents=True)
    (static / MARKER).write_text("", encoding="utf-8")
    (static / "nested" / MARKER).write_text("", encoding="utf-8")
    (static / "kept.txt").write_text("", encoding="utf-8")
    output = tmp_path / "output"

    stage_site(vault, output, hugo=FAKE_HUGO)

    assets = output / ASSETS_DIR
    assert (assets / "blog" / "kept.txt").is_file()
    assert list(assets.rglob(MARKER)) == []
    assert (output / MARKER).is_file()


def test_stage_builds_with_the_config_it_is_given(tmp_path: Path) -> None:
    config = SiteConfig(
        "https://preview.test/other/", "T", "A", WorkerConfig("preview-site")
    )
    output = tmp_path / "output"

    stage_site(_make_vault(tmp_path), output, config, hugo=FAKE_HUGO)

    seen = json.loads(
        (output / ASSETS_DIR / "other" / "seen.json").read_text(encoding="utf-8")
    )
    assert 'baseURL = "https://preview.test/other/"' in seen["config"]
    generated = json.loads((output / WRANGLER_CONFIG).read_text(encoding="utf-8"))
    assert generated["name"] == "preview-site"


def test_stage_makes_a_production_build(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    (vault / "draft.md").write_text("---\npublish: false\n---\nDRAFT\n", "utf-8")
    output = tmp_path / "output"

    stage_site(vault, output, hugo=FAKE_HUGO)

    seen = json.loads(
        (output / ASSETS_DIR / "blog" / "seen.json").read_text(encoding="utf-8")
    )
    assert not seen["drafts"]
    assert "mdblog_preview" not in seen["config"]


def test_stage_replaces_a_build_output_without_keeping_any_of_it(
    tmp_path: Path,
) -> None:
    vault = _make_vault(tmp_path)
    output = tmp_path / "output"
    build_site(vault, output, FAKE_HUGO)
    (output / "stale.html").write_text("stale", encoding="utf-8")

    stage_site(vault, output, hugo=FAKE_HUGO)

    assert not (output / "stale.html").exists()
    assert not (output / "index.html").exists()
    assert (output / ASSETS_DIR / "blog" / "index.html").is_file()


def test_stage_replaces_a_previous_stage(tmp_path: Path) -> None:
    output = _previous_stage(tmp_path)
    (output / ASSETS_DIR / "blog" / "stale.html").write_text("", encoding="utf-8")

    stage_site(_make_vault(tmp_path), output, hugo=FAKE_HUGO)

    assert not (output / ASSETS_DIR / "blog" / "stale.html").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "output",
        "previous",
        "vault",
    ]


def test_stage_without_a_worker_names_the_setting_and_writes_nothing(
    tmp_path: Path,
) -> None:
    vault = _make_vault(tmp_path, CONFIG)
    output = tmp_path / "output"

    with pytest.raises(ConfigError) as exc:
        stage_site(vault, output, hugo=FAKE_HUGO)

    assert "mdblog.toml" in str(exc.value)
    assert "[worker] name" in str(exc.value)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["vault"]


def _bad_notes(vault: Path) -> None:
    (vault / "bad.md").write_text("---\npublish: yes\n---\n", encoding="utf-8")


def _bad_config(vault: Path) -> None:
    (vault / "_site" / "mdblog.toml").write_text("title = ", encoding="utf-8")


@pytest.mark.parametrize(
    ("spoil", "hugo", "error"),
    [
        pytest.param(_bad_notes, FAKE_HUGO, BuildError, id="bad-notes"),
        pytest.param(_bad_config, FAKE_HUGO, ConfigError, id="bad-config"),
        pytest.param(None, FAILING_HUGO, BuildError, id="hugo-failure"),
    ],
)
def test_a_failed_stage_leaves_the_output_unchanged(
    tmp_path: Path,
    spoil: Callable[[Path], None] | None,
    hugo: tuple[str, ...],
    error: type[Exception],
) -> None:
    output = _previous_stage(tmp_path)
    vault = _make_vault(tmp_path)
    if spoil is not None:
        spoil(vault)
    before = _snapshot(tmp_path)

    with pytest.raises(error):
        stage_site(vault, output, hugo=hugo)

    assert _snapshot(tmp_path) == before


def test_stage_refuses_an_unmarked_output_and_changes_nothing(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    (output / "precious.txt").write_text("keep", encoding="utf-8")
    before = _snapshot(tmp_path)

    with pytest.raises(BuildError, match="refusing output"):
        stage_site(vault, output, hugo=FAKE_HUGO)

    assert _snapshot(tmp_path) == before


def test_stage_refuses_an_output_inside_the_vault(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    before = _snapshot(tmp_path)

    with pytest.raises(BuildError, match="refusing output"):
        stage_site(vault, vault / "output", hugo=FAKE_HUGO)

    assert _snapshot(tmp_path) == before


def test_wrangler_dev_listens_on_localhost_only(tmp_path: Path) -> None:
    argv = wrangler_dev_argv(("wrangler",), tmp_path, 9000)

    assert argv[:2] == ["wrangler", "dev"]
    assert argv[argv.index("--ip") + 1] == "127.0.0.1"
    assert argv[argv.index("--port") + 1] == "9000"
    assert argv[argv.index("--config") + 1] == str(tmp_path / WRANGLER_CONFIG)


def test_a_missing_wrangler_is_named_with_how_to_install_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "node_modules" / ".bin" / "wrangler"
    monkeypatch.setattr(stage, "WRANGLER", missing)

    with pytest.raises(ServeError) as exc:
        find_wrangler()

    assert str(missing) in str(exc.value)
    assert "npm ci" in str(exc.value)


def _fake_wrangler(tmp_path: Path, body: str) -> tuple[str, ...]:
    script = tmp_path / "fake_wrangler.py"
    script.write_text(body, encoding="utf-8")
    return (sys.executable, str(script))


def test_serve_bundle_reports_wrangler_exiting_on_its_own(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = tmp_path / "seen.json"
    wrangler = _fake_wrangler(
        tmp_path,
        "import json, os, subprocess, sys\n"
        # A grandchild that outlives the fake, as workerd can outlive wrangler.
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(seen)!r}, 'w').write(json.dumps("
        "{'env': dict(os.environ), 'cwd': os.getcwd(), 'child': child.pid}))\n"
        "sys.exit(3)\n",
    )

    with pytest.raises(ServeError, match="wrangler exited with status 3"):
        serve_bundle(tmp_path, PurePosixPath("blog"), 9000, wrangler)

    assert "http://127.0.0.1:9000/blog/" in capsys.readouterr().out
    recorded = json.loads(seen.read_text(encoding="utf-8"))
    assert recorded["cwd"] == str(tmp_path)
    for name, value in WRANGLER_ENV.items():
        assert recorded["env"][name] == value
    assert _exits(recorded["child"])


def test_serve_bundle_stops_wrangler_on_sigint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    started = tmp_path / "started"
    wrangler = _fake_wrangler(
        tmp_path,
        "import os, pathlib, subprocess, sys, time\n"
        # A grandchild, as wrangler's server is, records its pid.
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"pathlib.Path({str(started)!r}).write_text(str(child.pid))\n"
        "time.sleep(60)\n",
    )

    def interrupt() -> None:
        deadline = time.monotonic() + 30
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        os.kill(os.getpid(), signal.SIGINT)

    threading.Thread(target=interrupt, daemon=True).start()
    serve_bundle(tmp_path, PurePosixPath(), 9000, wrangler)

    assert "http://127.0.0.1:9000/\n" in capsys.readouterr().out
    assert _exits(int(started.read_text(encoding="utf-8")))


def _exits(pid: int) -> bool:
    """Whether process `pid` is gone within 10 seconds."""
    deadline = time.monotonic() + 10
    while _alive(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def _alive(pid: int) -> bool:
    # The grandchild is reparented to init, which reaps it, so a gone pid means it exited.
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = Path(f"/proc/{pid}/stat")
    return not (stat.exists() and stat.read_text().split()[2] == "Z")


def _staged_fixture(root: Path) -> Path:
    """A copy of the fixture vault with a `/blog/` base, a Worker name and a route,
    so the tests that run wrangler also show it accepts the generated routes."""
    vault = root / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    config = vault / "_site" / "mdblog.toml"
    text = config.read_text(encoding="utf-8")
    config.write_text(
        text.replace("https://example.org/", "https://example.test/blog/")
        + WORKER
        + ROUTES,
        encoding="utf-8",
    )
    return vault


def test_stage_of_the_fixture_holds_hugo_output_under_the_base_path(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"

    stage_site(_staged_fixture(tmp_path), output)

    assets = output / ASSETS_DIR
    assert [p.name for p in assets.iterdir()] == ["blog"]
    for name in ("index.html", "404.html", "index.xml"):
        assert (assets / "blog" / name).is_file()
    assert list(assets.rglob(MARKER)) == []


def _wrangler_env(tmp_path: Path) -> dict[str, str]:
    """The environment with no Cloudflare credentials, no network and a private
    wrangler config directory."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLOUDFLARE_")}
    return {**env, **NO_NETWORK, "XDG_CONFIG_HOME": str(tmp_path / "xdg")}


@pytest.mark.wrangler
def test_wrangler_accepts_the_staged_config_without_credentials_or_network(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    stage_site(_staged_fixture(tmp_path), output)

    result = subprocess.run(
        [str(find_wrangler()), "deploy", "--dry-run"],
        cwd=output,
        env={**_wrangler_env(tmp_path), **WRANGLER_ENV},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "--dry-run: exiting now." in result.stdout


def _status(url: str) -> int:
    """The status of `url`, or 0 while nothing answers."""
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            status: int = response.status
            return status
    except urllib.error.HTTPError as exc:
        return exc.code
    except urllib.error.URLError:
        return 0


def _startup_failure(process: subprocess.Popen[bytes], log: Path) -> str:
    """Why `process` never served the site, with the end of its output, so a crash
    can be told from a slow start."""
    status = process.poll()
    outcome = (
        f"it exited with status {status}"
        if status is not None
        else f"it was still running after {STARTUP_TIMEOUT} seconds"
    )
    tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
    return "\n".join(
        [f"wrangler dev never served the home page: {outcome}. Its output ends:", *tail]
    )


@pytest.mark.wrangler
def test_stage_serve_passes_verify(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = _staged_fixture(tmp_path)
    output = tmp_path / "output"
    port = _free_port()
    site = f"http://127.0.0.1:{port}/blog/"
    log_path = tmp_path / "output.txt"
    command = [
        sys.executable,
        "-c",
        "import sys; from mdblog.cli import main; sys.exit(main())",
        "stage",
        str(vault),
        "--output",
        str(output),
        "--serve",
        "--port",
        str(port),
    ]
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            env=_wrangler_env(tmp_path),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    try:
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while _status(site) != 200:
            if time.monotonic() > deadline or process.poll() is not None:
                pytest.fail(_startup_failure(process, log_path))
            time.sleep(0.2)
        verified = main(["verify", site])
        process.send_signal(signal.SIGINT)
        assert process.wait(timeout=30) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()

    assert verified == 0, capsys.readouterr().out
    assert site in log_path.read_text(encoding="utf-8")
