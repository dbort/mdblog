import json
import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from fake_site import FakeSite, Reply
from mdblog import stage
from mdblog.build import BuildError
from mdblog.cli import main
from mdblog.config import ConfigError, load_config
from mdblog.deploy import DeployError, await_verified, deploy_site
from mdblog.stage import ASSETS_DIR, WRANGLER_CONFIG, WRANGLER_ENV, wrangler_config
from notes import published_text

# Stands in for Hugo: it writes the pages every site has.
FAKE_HUGO = (
    sys.executable,
    "-c",
    "import pathlib, sys;"
    "argv = sys.argv[1:];"
    "destination = pathlib.Path(argv[argv.index('--destination') + 1]);"
    "[(destination / name).write_text(name) for name in"
    " ('index.html', '404.html', 'index.xml')]",
)
# Records what wrangler would see, then exits with MDBLOG_FAKE_WRANGLER_STATUS.
FAKE_WRANGLER = f"""#!{sys.executable}
import json, os, pathlib, sys
argv = sys.argv[1:]
config = pathlib.Path(argv[argv.index("--config") + 1])
pathlib.Path(os.environ["MDBLOG_FAKE_WRANGLER_LOG"]).write_text(json.dumps({{
    "argv": argv,
    "cwd": os.getcwd(),
    "env": dict(os.environ),
    "config": json.loads(config.read_text()),
    "assets": sorted(
        p.relative_to(config.parent).as_posix()
        for p in (config.parent / "{ASSETS_DIR}").rglob("*")
    ),
}}))
sys.exit(int(os.environ.get("MDBLOG_FAKE_WRANGLER_STATUS", "0")))
"""


class Wrangler:
    """A fake wrangler executable and the log of its one run, if any."""

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.path = root / "wrangler"
        self.path.write_text(FAKE_WRANGLER, encoding="utf-8")
        self.path.chmod(0o755)
        self.log = root / "wrangler.json"
        monkeypatch.setenv("MDBLOG_FAKE_WRANGLER_LOG", str(self.log))

    @property
    def argv(self) -> tuple[str, ...]:
        return (str(self.path),)

    def ran(self) -> bool:
        return self.log.exists()

    def seen(self) -> dict[str, object]:
        recorded: dict[str, object] = json.loads(self.log.read_text(encoding="utf-8"))
        return recorded


@pytest.fixture
def wrangler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Wrangler:
    return Wrangler(tmp_path, monkeypatch)


@pytest.fixture
def scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """The temporary-files directory deploy uses, which must end up empty."""
    directory = tmp_path / "tmp"
    directory.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(directory))
    yield directory
    assert list(directory.iterdir()) == []


def _vault(root: Path, base_url: str, worker: bool = True) -> Path:
    vault = root / "vault"
    (vault / "_site").mkdir(parents=True)
    config = f'base_url = "{base_url}"\ntitle = "T"\nauthor = "A"\n'
    if worker:
        config += '[worker]\nname = "test-site"\nroutes = ["example.test/blog/*"]\n'
    (vault / "_site" / "mdblog.toml").write_text(config, encoding="utf-8")
    (vault / "note.md").write_text(published_text("note"), encoding="utf-8")
    return vault


def test_deploy_uploads_the_staged_bundle_and_verifies_the_site(
    tmp_path: Path,
    fake_site: FakeSite,
    wrangler: Wrangler,
    scratch: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token-from-ci")

    url = deploy_site(_vault(tmp_path, fake_site.url), wrangler.argv, FAKE_HUGO)

    assert url == fake_site.url
    seen = wrangler.seen()
    argv = seen["argv"]
    assert isinstance(argv, list)
    assert argv[0] == "deploy"
    bundle = Path(str(seen["cwd"]))
    assert argv[1:] == ["--config", str(bundle / WRANGLER_CONFIG)]
    assert bundle.is_relative_to(scratch)
    assert seen["config"] == wrangler_config(load_config(tmp_path / "vault"))
    assert f"{ASSETS_DIR}/blog/index.html" in str(seen["assets"])
    env = seen["env"]
    assert isinstance(env, dict)
    for name, value in WRANGLER_ENV.items():
        assert env[name] == value
    assert env["CLOUDFLARE_API_TOKEN"] == "token-from-ci"
    assert len(fake_site.requests) == 4


def test_deploy_reports_wrangler_failing_and_makes_no_request(
    tmp_path: Path,
    fake_site: FakeSite,
    wrangler: Wrangler,
    scratch: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MDBLOG_FAKE_WRANGLER_STATUS", "4")

    with pytest.raises(DeployError, match="wrangler deploy exited with status 4"):
        deploy_site(_vault(tmp_path, fake_site.url), wrangler.argv, FAKE_HUGO)

    assert wrangler.ran()
    assert fake_site.requests == []


def test_deploy_reports_a_wrangler_it_cannot_run(
    tmp_path: Path, fake_site: FakeSite, scratch: Path
) -> None:
    missing = str(tmp_path / "no-such-wrangler")

    with pytest.raises(DeployError, match=f"cannot run {missing}"):
        deploy_site(_vault(tmp_path, fake_site.url), (missing,), FAKE_HUGO)

    assert fake_site.requests == []


def test_deploy_says_a_site_failing_verification_is_live(
    tmp_path: Path, fake_site: FakeSite, wrangler: Wrangler, scratch: Path
) -> None:
    fake_site.routes["/blog/"] = Reply(500, "text/html", b"")

    with pytest.raises(DeployError) as exc:
        deploy_site(
            _vault(tmp_path, fake_site.url), wrangler.argv, FAKE_HUGO, patience=0
        )

    message = str(exc.value)
    assert "uploaded the site, so it is live" in message
    assert fake_site.url in message
    assert "home page: status 500, expected 200" in message
    assert "feed" not in message
    assert wrangler.ran()


def _bad_note(vault: Path) -> None:
    (vault / "bad.md").write_text("---\npublish: yes\n---\n", encoding="utf-8")


def test_deploy_runs_no_wrangler_when_the_build_fails(
    tmp_path: Path, wrangler: Wrangler, scratch: Path
) -> None:
    vault = _vault(tmp_path, "https://example.test/blog/")
    _bad_note(vault)

    with pytest.raises(BuildError):
        deploy_site(vault, wrangler.argv, FAKE_HUGO)

    assert not wrangler.ran()


def test_deploy_runs_no_wrangler_without_a_worker(
    tmp_path: Path, wrangler: Wrangler, scratch: Path
) -> None:
    vault = _vault(tmp_path, "https://example.test/blog/", worker=False)

    with pytest.raises(ConfigError) as exc:
        deploy_site(vault, wrangler.argv, FAKE_HUGO)

    assert "mdblog.toml" in str(exc.value)
    assert "[worker]" in str(exc.value)
    assert not wrangler.ran()


class Verifications:
    """A verifier whose first `failures` calls fail the home page check."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def __call__(self, url: str) -> Iterator[tuple[str, str | None]]:
        self.calls += 1
        yield "home page", "status 503" if self.calls <= self.failures else None
        yield "feed", None


def test_await_verified_retries_until_the_site_passes() -> None:
    verify = Verifications(failures=2)

    await_verified("https://x.test/", verify, patience=10, interval=0.01)

    assert verify.calls == 3


def test_await_verified_gives_up_after_its_patience() -> None:
    verify = Verifications(failures=1000)

    with pytest.raises(DeployError, match="home page: status 503"):
        await_verified("https://x.test/", verify, patience=0.2, interval=0.05)

    assert 2 <= verify.calls <= 5


def test_await_verified_with_no_patience_tries_once() -> None:
    verify = Verifications(failures=1000)

    with pytest.raises(DeployError):
        await_verified("https://x.test/", verify, patience=0, interval=0.01)

    assert verify.calls == 1


def test_cli_deploy_prints_the_verified_url(
    tmp_path: Path,
    fake_site: FakeSite,
    wrangler: Wrangler,
    scratch: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(stage, "WRANGLER", wrangler.path)
    fake_hugo = tmp_path / "bin" / "hugo"
    fake_hugo.parent.mkdir()
    fake_hugo.write_text(
        f"#!{sys.executable}\nimport subprocess, sys\n"
        f"sys.exit(subprocess.run({list(FAKE_HUGO)!r} + sys.argv[1:]).returncode)\n",
        encoding="utf-8",
    )
    fake_hugo.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_hugo.parent}{os.pathsep}{os.environ['PATH']}")

    status = main(["deploy", str(_vault(tmp_path, fake_site.url))])

    assert status == 0
    assert f"mdblog: deployed and verified {fake_site.url}" in capsys.readouterr().out
    assert wrangler.ran()


def test_cli_deploy_without_wrangler_names_it_before_building(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    scratch: Path,
) -> None:
    missing = tmp_path / "node_modules" / ".bin" / "wrangler"
    monkeypatch.setattr(stage, "WRANGLER", missing)
    vault = _vault(tmp_path, "https://example.test/blog/")
    _bad_note(vault)

    status = main(["deploy", str(vault)])

    assert status == 1
    err = capsys.readouterr().err
    assert f"mdblog: wrangler not found at {missing}" in err
    assert "bad.md" not in err
