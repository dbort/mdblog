import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _toml(name: str) -> dict[str, object]:
    return tomllib.loads((REPO_ROOT / name).read_text(encoding="utf-8"))


def _table(parent: dict[str, object], key: str) -> dict[str, object]:
    value = parent[key]
    assert isinstance(value, dict)
    return value


def test_pixi_declares_the_platforms_channel_and_tools() -> None:
    manifest = _toml("pixi.toml")
    workspace = _table(manifest, "workspace")
    dependencies = _table(manifest, "dependencies")

    assert workspace["platforms"] == ["linux-64", "linux-aarch64", "osx-arm64"]
    assert workspace["channels"] == ["conda-forge"]
    assert {"python", "hugo", "ruff", "pyrefly", "pytest"} <= set(dependencies)
    assert dependencies["python"] == "3.14.*"


def test_hugo_minor_version_is_pinned() -> None:
    constraint = _table(_toml("pixi.toml"), "dependencies")["hugo"]

    assert isinstance(constraint, str)
    assert constraint.endswith(".*")
    assert constraint.count(".") == 2


def test_lockfile_covers_every_platform() -> None:
    lock = (REPO_ROOT / "pixi.lock").read_text(encoding="utf-8")

    for platform in ("linux-64", "linux-aarch64", "osx-arm64"):
        assert f"{platform}:" in lock


def test_environment_has_no_deployment_tools() -> None:
    for name in ("pixi.toml", "pixi.lock"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert "nodejs" not in text
        assert "wrangler" not in text


def test_pyrefly_runs_at_strict_with_warnings_promoted() -> None:
    tool = _table(_toml("pyproject.toml"), "tool")
    pyrefly = _table(tool, "pyrefly")
    errors = _table(pyrefly, "errors")

    assert pyrefly["preset"] == "strict"
    assert pyrefly["enabled-ignores"] == ["pyrefly"]
    for kind in (
        "deprecated",
        "redundant-cast",
        "redundant-condition",
        "unnecessary-type-conversion",
        "unreachable",
    ):
        assert errors[kind] == "error"


def test_gitignore_covers_toolchain_output() -> None:
    paths = [
        ".pixi/x",
        "__pycache__/x",
        "src/mdblog.egg-info/x",
        ".pytest_cache/x",
        ".ruff_cache/x",
        "dist/x",
        "build/x",
        "public/x",
        "resources/x",
        ".hugo_build.lock",
    ]

    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--", *paths],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert sorted(result.stdout.splitlines()) == sorted(paths)
