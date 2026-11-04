import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from check_runner import (
    CHECKED_PATHS,
    FIXTURE_NOTE_TEXT,
    FIXTURE_PAGE,
    HUGO_STEP,
    Commands,
    Step,
    build_steps,
    hugo_fixture_build,
    main,
    pytest_argv,
    run_command,
    run_steps,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PASS = (sys.executable, "-c", "pass")
FAIL = (sys.executable, "-c", "raise SystemExit(3)")
# Stands in for Hugo so the runner's logic stays covered by `--smoke`, which runs no Hugo.
FAKE_HUGO = (
    sys.executable,
    "-c",
    "import pathlib, sys;"
    "public = pathlib.Path(sys.argv[sys.argv.index('--destination') + 1]);"
    f"page = public / {str(FIXTURE_PAGE)!r};"
    "page.parent.mkdir(parents=True);"
    f"page.write_text({FIXTURE_NOTE_TEXT!r})",
)
PASSING = Commands(
    format_check=PASS, lint=PASS, typecheck=PASS, test=PASS, hugo=FAKE_HUGO
)
BROKEN_LAYOUT = "{{ this does not parse"


def test_main_exits_zero_when_every_step_passes() -> None:
    assert main([], repo_root=REPO_ROOT, commands=PASSING) == 0


@pytest.mark.parametrize("field", ["format_check", "lint", "typecheck", "test", "hugo"])
def test_main_exits_nonzero_when_one_step_fails(field: str) -> None:
    commands = replace(PASSING, **{field: FAIL})

    assert main([], repo_root=REPO_ROOT, commands=commands) != 0


@pytest.mark.parametrize("field", ["format_check", "lint", "typecheck", "test", "hugo"])
def test_main_exits_nonzero_when_a_tool_is_missing(field: str) -> None:
    commands = replace(PASSING, **{field: ("mdblog-no-such-tool",)})

    assert main([], repo_root=REPO_ROOT, commands=commands) != 0


def test_main_rejects_an_unknown_flag() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--no-such-flag"], repo_root=REPO_ROOT, commands=PASSING)

    assert exc.value.code == 2


def test_smoke_leaves_out_only_the_hugo_build() -> None:
    full = [s.name for s in build_steps(REPO_ROOT, smoke=False, commands=PASSING)]
    smoke = [s.name for s in build_steps(REPO_ROOT, smoke=True, commands=PASSING)]

    assert smoke == [name for name in full if name != HUGO_STEP]
    assert HUGO_STEP in full


def test_smoke_exit_status_ignores_a_failing_hugo() -> None:
    commands = replace(PASSING, hugo=FAIL)

    assert main(["--smoke"], repo_root=REPO_ROOT, commands=commands) == 0


def test_offline_still_runs_every_step() -> None:
    assert main(["--offline"], repo_root=REPO_ROOT, commands=PASSING) == 0
    commands = replace(PASSING, hugo=FAIL)
    assert main(["--offline"], repo_root=REPO_ROOT, commands=commands) != 0


def test_default_commands_cover_the_checked_directories() -> None:
    commands = Commands()

    assert CHECKED_PATHS == ("src", "tests", "tools")
    assert commands.format_check == ("ruff", "format", "--check", *CHECKED_PATHS)
    assert commands.lint == ("ruff", "check", *CHECKED_PATHS)
    # pyrefly takes its directories from project-includes; test_project_config pins them.
    assert commands.typecheck == ("pyrefly", "check")
    # pytest takes its directory from testpaths, pinned in the same place.
    assert commands.test == ("pytest",)


def test_only_smoke_deselects_the_hugo_tests() -> None:
    assert pytest_argv(("pytest",), smoke=True) == ["pytest", "-m", "not hugo"]
    assert pytest_argv(("pytest",), smoke=False) == ["pytest"]


def test_run_steps_runs_later_steps_after_a_failure() -> None:
    ran: list[str] = []

    def failing() -> int:
        ran.append("first")
        return 1

    def passing() -> int:
        ran.append("second")
        return 0

    assert run_steps([Step("first", failing), Step("second", passing)]) == 1
    assert ran == ["first", "second"]


def test_run_command_returns_127_for_a_missing_tool(tmp_path: Path) -> None:
    assert run_command(["mdblog-no-such-tool"], tmp_path) == 127


@pytest.mark.hugo
def test_hugo_build_passes_on_the_real_fixture() -> None:
    assert hugo_fixture_build(REPO_ROOT, ("hugo",)) == 0


def _copy_fixtures(repo_root: Path) -> Path:
    fixtures = repo_root / "tests" / "fixtures"
    shutil.copytree(REPO_ROOT / "tests" / "fixtures", fixtures)
    return fixtures


@pytest.mark.hugo
def test_hugo_build_fails_when_the_note_text_is_missing(tmp_path: Path) -> None:
    fixtures = _copy_fixtures(tmp_path)
    note = fixtures / "vault" / "projects" / "first-note.md"
    note.write_text("Some other text.\n", encoding="utf-8")

    assert hugo_fixture_build(tmp_path, ("hugo",)) != 0


@pytest.mark.hugo
def test_hugo_build_fails_on_a_broken_layout(tmp_path: Path) -> None:
    fixtures = _copy_fixtures(tmp_path)
    (fixtures / "site" / "layouts" / "page.html").write_text(
        BROKEN_LAYOUT, encoding="utf-8"
    )

    assert hugo_fixture_build(tmp_path, ("hugo",)) != 0


@pytest.mark.hugo
def test_hugo_build_fails_when_the_page_is_not_generated(tmp_path: Path) -> None:
    fixtures = _copy_fixtures(tmp_path)
    note = fixtures / "vault" / "projects" / "first-note.md"
    note.rename(note.with_name("renamed.md"))

    assert hugo_fixture_build(tmp_path, ("hugo",)) != 0


def test_fixture_note_holds_the_text_the_build_looks_for() -> None:
    note = REPO_ROOT / "tests" / "fixtures" / "vault" / "projects" / "first-note.md"

    assert FIXTURE_NOTE_TEXT in note.read_text(encoding="utf-8")


def test_hugo_build_points_every_path_at_its_temporary_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = tmp_path / "record.json"
    script = (
        "import json, os, sys, pathlib;"
        f"pathlib.Path({str(record)!r}).write_text(json.dumps("
        "{'argv': sys.argv[1:], 'cwd': os.getcwd(), 'env': sorted(os.environ)}))"
    )
    monkeypatch.setenv("HUGO_CONTENTDIR", "/somewhere/else")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))
    monkeypatch.setattr("tempfile.tempdir", None)

    # The stand-in writes no page, so the build reports failure after recording.
    assert hugo_fixture_build(REPO_ROOT, (sys.executable, "-c", script)) != 0

    seen = json.loads(record.read_text(encoding="utf-8"))
    argv = seen["argv"]
    for flag in ("--source", "--destination", "--cacheDir"):
        assert Path(argv[argv.index(flag) + 1]).is_relative_to(scratch.resolve())
    assert Path(seen["cwd"]).resolve().is_relative_to(scratch.resolve())
    assert "HUGO_CONTENTDIR" not in seen["env"]
