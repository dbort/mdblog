"""Drives the real `tools/check` as a subprocess, including its pixi hand-off."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECK = REPO_ROOT / "tools" / "check"
# A nested gate runs pytest, which would run this module again without end.
NESTED = "MDBLOG_CHECK_NESTED"
DEAD_PROXY = "http://127.0.0.1:9"

pytestmark = pytest.mark.skipif(
    NESTED in os.environ, reason="already inside a tools/check started by this module"
)


def _run(
    argv: list[str], cwd: Path, **env_overrides: str
) -> subprocess.CompletedProcess[str]:
    # A dead proxy turns any network use by pixi or a check into a failure.
    env = {
        **os.environ,
        NESTED: "1",
        "HTTP_PROXY": DEAD_PROXY,
        "HTTPS_PROXY": DEAD_PROXY,
        "ALL_PROXY": DEAD_PROXY,
        "http_proxy": DEAD_PROXY,
        "https_proxy": DEAD_PROXY,
        "all_proxy": DEAD_PROXY,
        **env_overrides,
    }
    return subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, text=True, check=False
    )


def _git_status() -> str:
    return _run(["git", "status", "--short"], REPO_ROOT).stdout


def _steps_run(stdout: str) -> list[str]:
    return [line[4:] for line in stdout.splitlines() if line.startswith("==> ")]


TOOL_STEPS = ["ruff format", "ruff check", "pyrefly", "pytest"]
HUGO_STEP = "hugo fixture build"


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        pytest.param([], [*TOOL_STEPS, HUGO_STEP], marks=pytest.mark.hugo),
        pytest.param(["--offline"], [*TOOL_STEPS, HUGO_STEP], marks=pytest.mark.hugo),
        (["--smoke"], TOOL_STEPS),
    ],
)
def test_gate_passes_from_the_filesystem_root(
    flags: list[str], expected: list[str]
) -> None:
    before = _git_status()

    result = _run([str(CHECK), *flags], Path("/"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert _steps_run(result.stdout) == expected
    assert _git_status() == before


def test_gate_fails_on_an_unknown_flag() -> None:
    result = _run([str(CHECK), "--no-such-flag"], Path("/"))

    assert result.returncode != 0


def test_gate_finds_its_repo_despite_cdpath(tmp_path: Path) -> None:
    # A relative `tools/..` would resolve against this decoy before the working directory.
    (tmp_path / "tools").mkdir()

    result = _run(["tools/check", "--help"], REPO_ROOT, CDPATH=str(tmp_path))

    assert result.returncode == 0, result.stderr


def test_smoke_passes_with_a_broken_hugo_fixture(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    for directory in ("src", "tests", "tools"):
        shutil.copytree(
            REPO_ROOT / directory,
            repo / directory,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    for name in (".gitignore", "pixi.lock", "pixi.toml", "pyproject.toml"):
        shutil.copy2(REPO_ROOT / name, repo / name)
    # test_project_config asks git about .gitignore.
    assert _run(["git", "init", "-q"], repo).returncode == 0
    layout = repo / "tests" / "fixtures" / "site" / "layouts" / "page.html"
    layout.write_text("{{ this does not parse", encoding="utf-8")

    # Python runs the copy's runner directly because pixi would install a new environment.
    result = _run([sys.executable, "tools/check_runner.py", "--smoke"], repo)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _steps_run(result.stdout) == TOOL_STEPS


def test_package_imports_from_any_directory() -> None:
    pixi = shutil.which("pixi")
    assert pixi is not None

    result = _run(
        [
            pixi,
            "run",
            "--manifest-path",
            str(REPO_ROOT / "pixi.toml"),
            "python",
            "-c",
            "import mdblog; print(mdblog.__file__)",
        ],
        Path("/"),
    )

    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).is_relative_to(REPO_ROOT / "src")


def test_gate_names_pixi_when_it_is_missing(tmp_path: Path) -> None:
    # PATH holds only what the wrapper itself needs, so pixi cannot be found on it.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("bash", "dirname"):
        found = shutil.which(tool)
        assert found is not None
        (bin_dir / tool).symlink_to(found)

    result = _run([str(CHECK)], Path("/"), PATH=str(bin_dir))

    assert result.returncode != 0
    assert "pixi" in result.stderr


def test_gate_fails_on_a_stale_lockfile(tmp_path: Path) -> None:
    (tmp_path / "tools").mkdir()
    shutil.copy2(CHECK, tmp_path / "tools" / "check")
    shutil.copytree(REPO_ROOT / "src", tmp_path / "src")
    for name in ("pixi.lock", "pyproject.toml"):
        shutil.copy2(REPO_ROOT / name, tmp_path / name)
    manifest = (REPO_ROOT / "pixi.toml").read_text(encoding="utf-8")
    (tmp_path / "pixi.toml").write_text(
        manifest.replace('pytest = "*"', 'pytest = "*"\ntree = "*"'), encoding="utf-8"
    )

    result = _run([str(tmp_path / "tools" / "check")], tmp_path)

    assert result.returncode != 0
    assert "lock" in result.stderr.lower()
