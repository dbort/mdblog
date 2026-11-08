import os
import shutil
import socket
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

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
        pytest.param(["serve"], "VAULT", id="serve-no-vault"),
        pytest.param(["check"], "VAULT", id="check-no-vault"),
        pytest.param(
            ["check", "v", "--output", "o"],
            "unrecognized arguments: --output",
            id="check-output",
        ),
        pytest.param(
            ["check", "v", "--drafts"],
            "unrecognized arguments: --drafts",
            id="check-drafts",
        ),
        pytest.param(
            ["build", "v", "--output", "o", "--drafts"],
            "unrecognized arguments: --drafts",
            id="build-drafts",
        ),
        pytest.param(["serve", "v", "--port", "0"], "from 1 to 65535", id="port-0"),
        pytest.param(["serve", "v", "--port", "x"], "from 1 to 65535", id="port-text"),
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
    assert "cannot run hugo" in capsys.readouterr().err
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


def test_serve_on_a_busy_port_exits_nonzero_naming_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port: int = listener.getsockname()[1]

        status = main(["serve", str(FIXTURE_VAULT), "--port", str(port)])

    assert status == 1
    assert f"mdblog: cannot listen on 127.0.0.1 port {port}:" in capsys.readouterr().err


# Stands in for Hugo on PATH. It prints to both streams, as Hugo does, and exits with
# MDBLOG_FAKE_HUGO_STATUS, or 0 after writing a page.
FAKE_HUGO = f"""#!{sys.executable}
import os, pathlib, sys
argv = sys.argv[1:]
print("FAKE-HUGO-STDOUT")
print("FAKE-HUGO-STDERR", file=sys.stderr)
status = int(os.environ.get("MDBLOG_FAKE_HUGO_STATUS", "0"))
if status == 0:
    destination = pathlib.Path(argv[argv.index("--destination") + 1])
    (destination / "index.html").write_text("page")
sys.exit(status)
"""


@dataclass(frozen=True)
class Isolated:
    """Where a check could leave files, with a fake `hugo` first on PATH."""

    # A copy of the fixture vault.
    vault: Path
    # The current directory.
    cwd: Path
    # The directory `tempfile` creates in.
    temp: Path


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Isolated:
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    cwd = tmp_path / "cwd"
    temp = tmp_path / "temp"
    bin_dir = tmp_path / "bin"
    for directory in (cwd, temp, bin_dir):
        directory.mkdir()
    hugo = bin_dir / "hugo"
    hugo.write_text(FAKE_HUGO, encoding="utf-8")
    hugo.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("MDBLOG_FAKE_HUGO_STATUS", raising=False)
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    return Isolated(vault, cwd, temp)


def _tree(root: Path) -> dict[str, bytes | None]:
    """Every path under `root`, mapped to its bytes, or None for a directory or link."""
    return {
        path.relative_to(root).as_posix(): (
            path.read_bytes() if path.is_file(follow_symlinks=False) else None
        )
        for path in sorted(root.rglob("*"))
    }


def _check_leaves_nothing(
    place: Isolated, capfd: pytest.CaptureFixture[str]
) -> tuple[int, str, str]:
    """The exit status, stdout and stderr of `mdblog check`, after asserting it wrote
    nothing under the vault, the current directory or the temporary directory."""
    before = _tree(place.vault)
    capfd.readouterr()

    status = main(["check", str(place.vault)])

    out, err = capfd.readouterr()
    assert _tree(place.vault) == before
    assert list(place.cwd.iterdir()) == []
    assert list(place.temp.iterdir()) == []
    return status, out, err


def _build_stderr(
    place: Isolated, tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> str:
    capfd.readouterr()
    status = main(["build", str(place.vault), "--output", str(tmp_path / "out")])
    assert status == 1
    return capfd.readouterr().err


def test_check_counts_the_notes_that_would_publish(
    isolated: Isolated, capfd: pytest.CaptureFixture[str]
) -> None:
    status, out, err = _check_leaves_nothing(isolated, capfd)

    assert status == 0
    assert out == "6 notes would publish\n"
    assert err == "FAKE-HUGO-STDERR\n"


def test_check_says_note_for_a_single_one(
    isolated: Isolated, capfd: pytest.CaptureFixture[str]
) -> None:
    for note in isolated.vault.rglob("*.md"):
        if note.name != "first-note.md" and not note.is_relative_to(
            isolated.vault / "_site"
        ):
            note.unlink()

    status, out, _ = _check_leaves_nothing(isolated, capfd)

    assert (status, out) == (0, "1 note would publish\n")


def test_check_reports_failing_notes_as_build_does(
    isolated: Isolated, tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    (isolated.vault / "typo.md").write_text(
        "---\npublish: yes\n---\n", encoding="utf-8"
    )

    status, out, err = _check_leaves_nothing(isolated, capfd)

    assert (status, out) == (1, "")
    assert "typo.md: publish must be" in err
    assert err == _build_stderr(isolated, tmp_path, capfd)


def test_check_reports_unusable_settings_as_build_does(
    isolated: Isolated, tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    (isolated.vault / "_site" / "mdblog.toml").write_text(
        "title = \n", encoding="utf-8"
    )

    status, out, err = _check_leaves_nothing(isolated, capfd)

    assert (status, out) == (1, "")
    assert "mdblog.toml" in err
    assert err == _build_stderr(isolated, tmp_path, capfd)


def test_check_reports_a_hugo_failure_as_build_does(
    isolated: Isolated,
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MDBLOG_FAKE_HUGO_STATUS", "3")

    status, out, err = _check_leaves_nothing(isolated, capfd)

    assert (status, out) == (1, "")
    assert err == "FAKE-HUGO-STDERR\nmdblog: hugo exited with status 3\n"
    assert err == _build_stderr(isolated, tmp_path, capfd)
