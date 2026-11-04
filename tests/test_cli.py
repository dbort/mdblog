import shutil
import subprocess
from pathlib import Path

import pytest

from mdblog.build import MARKER
from mdblog.cli import main

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_VAULT = REPO_ROOT / "tests" / "fixtures" / "vault"


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        pytest.param([], "usage:", id="no-command"),
        pytest.param(["build"], "usage:", id="nothing"),
        pytest.param(["build", "--output", "out"], "VAULT", id="no-vault"),
        pytest.param(["build", "vault"], "--output", id="no-output"),
    ],
)
def test_missing_arguments_exit_nonzero_with_usage(
    argv: list[str], expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(argv)

    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "usage:" in err
    assert expected in err


def test_absent_hugo_exits_nonzero_naming_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    empty = tmp_path / "bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))

    status = main(["build", str(FIXTURE_VAULT), "--output", str(tmp_path / "out")])

    assert status == 1
    assert "hugo" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_bad_config_exits_nonzero_naming_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status = main(["build", str(tmp_path), "--output", str(tmp_path.parent / "out")])

    assert status == 1
    assert "mdblog.toml" in capsys.readouterr().err


def test_bad_notes_exit_nonzero_naming_each_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    (vault / "typo.md").write_text("---\npublish: yes\n---\n", encoding="utf-8")
    (vault / "dup.md").write_text("---\na: 1\na: 2\n---\n", encoding="utf-8")

    status = main(["build", str(vault), "--output", str(tmp_path / "out")])

    assert status == 1
    err = capsys.readouterr().err
    assert "typo.md: publish must be" in err
    assert "dup.md: front matter is invalid YAML" in err
    assert "duplicate key" in err


def _pixi() -> str:
    pixi = shutil.which("pixi")
    assert pixi is not None
    return pixi


@pytest.mark.hugo
def test_console_script_builds_from_any_working_directory(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)

    # Relative paths prove that pixi's runner keeps the caller's working directory.
    result = subprocess.run(
        [
            _pixi(),
            "run",
            "--locked",
            "--manifest-path",
            str(REPO_ROOT / "pixi.toml"),
            "mdblog",
            "build",
            "vault",
            "--output",
            "out",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "out" / MARKER).is_file()
    assert (tmp_path / "out" / "projects" / "first-note" / "index.html").is_file()


@pytest.mark.hugo
def test_console_script_exits_nonzero_without_arguments(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            _pixi(),
            "run",
            "--locked",
            "--manifest-path",
            str(REPO_ROOT / "pixi.toml"),
            "mdblog",
            "build",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "usage:" in result.stderr
