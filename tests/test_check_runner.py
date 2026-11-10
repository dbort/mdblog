import json
import sys
from dataclasses import fields, replace
from pathlib import Path

import pytest

from check_runner import (
    INSTALL_STAMP,
    OFFLINE_ENV,
    Commands,
    lock_problems,
    main,
    shell_scripts,
)

PASS = (sys.executable, "-c", "pass")
FAIL = (sys.executable, "-c", "raise SystemExit(3)")
PASSING = Commands(
    npm_install=PASS,
    format_check=PASS,
    lint=PASS,
    typecheck=PASS,
    test=PASS,
    shellcheck=PASS,
)
STEPS = [field.name for field in fields(Commands)]
MANIFEST = {"name": "tools", "devDependencies": {"wrangler": "1.2.3"}}
LOCK = {
    "name": "tools",
    "lockfileVersion": 3,
    "packages": {
        "": {"devDependencies": {"wrangler": "1.2.3"}},
        "node_modules/wrangler": {"version": "1.2.3"},
    },
}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo root whose package.json and package-lock.json agree."""
    (tmp_path / "package.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    (tmp_path / "package-lock.json").write_text(json.dumps(LOCK), encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    return tmp_path


def _env_check(expected: str | None) -> tuple[str, ...]:
    """A test command that passes only when the offline variable is `expected`."""
    return (
        sys.executable,
        "-c",
        f"import os, sys; sys.exit(os.environ.get({OFFLINE_ENV!r}) != {expected!r})",
    )


def test_main_exits_zero_when_every_step_passes(repo: Path) -> None:
    assert main([], repo_root=repo, commands=PASSING) == 0


@pytest.mark.parametrize("step", STEPS)
def test_main_exits_nonzero_when_one_step_fails(repo: Path, step: str) -> None:
    commands = replace(PASSING, **{step: FAIL})

    assert main([], repo_root=repo, commands=commands) != 0


@pytest.mark.parametrize("step", STEPS)
def test_main_exits_nonzero_when_a_tool_is_missing(repo: Path, step: str) -> None:
    commands = replace(PASSING, **{step: ("mdblog-no-such-tool",)})

    assert main([], repo_root=repo, commands=commands) != 0


def test_shell_scripts_finds_scripts_by_shebang_or_suffix(tmp_path: Path) -> None:
    files = {
        "tools/posix": "#!/bin/sh\n",
        "tools/bash-env": "#!/usr/bin/env bash\n",
        "tools/flags": "#!/bin/bash -eu\n",
        "templates/deploy.sh": "echo no shebang\n",
        "tests/nested/dir/run": "#!/bin/dash\n",
        "tools/python": "#!/usr/bin/env python3\n",
        "tools/zsh": "#!/bin/zsh\n",
        "tools/later": "text\n#!/bin/sh\n",
        "docs/elsewhere.sh": "#!/bin/sh\n",
    }
    for relative, text in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    assert shell_scripts(tmp_path) == [
        "templates/deploy.sh",
        "tests/nested/dir/run",
        "tools/bash-env",
        "tools/flags",
        "tools/posix",
    ]


def test_lock_problems_is_empty_when_the_files_agree(repo: Path) -> None:
    assert lock_problems(repo) == []


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        pytest.param(
            {**MANIFEST, "devDependencies": {"wrangler": "1.2.4"}},
            "devDependencies",
            id="changed-version",
        ),
        pytest.param(
            {**MANIFEST, "dependencies": {"left-pad": "1.0.0"}},
            "dependencies",
            id="added-field",
        ),
        pytest.param({**MANIFEST, "name": "renamed"}, "name", id="renamed"),
    ],
)
def test_lock_problems_names_the_field_that_disagrees(
    repo: Path, manifest: dict[str, object], expected: str
) -> None:
    (repo / "package.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert lock_problems(repo) == [
        f"package-lock.json disagrees with package.json on {expected}; run npm install"
    ]


def test_main_fails_on_a_stale_lockfile_even_when_installed(repo: Path) -> None:
    assert main([], repo_root=repo, commands=PASSING) == 0
    stale = {**MANIFEST, "devDependencies": {"wrangler": "9.9.9"}}
    (repo / "package.json").write_text(json.dumps(stale), encoding="utf-8")

    assert main([], repo_root=repo, commands=PASSING) != 0


def test_main_skips_the_install_when_node_modules_matches_the_lock(
    repo: Path,
) -> None:
    assert main([], repo_root=repo, commands=PASSING) == 0
    assert (repo / INSTALL_STAMP).is_file()

    assert main([], repo_root=repo, commands=replace(PASSING, npm_install=FAIL)) == 0


def test_main_reinstalls_after_the_lock_changes(repo: Path) -> None:
    assert main([], repo_root=repo, commands=PASSING) == 0
    changed = {**LOCK, "lockfileVersion": 2}
    (repo / "package-lock.json").write_text(json.dumps(changed), encoding="utf-8")

    assert main([], repo_root=repo, commands=replace(PASSING, npm_install=FAIL)) != 0


def test_main_does_not_record_a_failed_install(repo: Path) -> None:
    assert main([], repo_root=repo, commands=replace(PASSING, npm_install=FAIL)) != 0

    assert not (repo / INSTALL_STAMP).exists()


def test_offline_skips_the_install_and_tells_pytest(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    commands = replace(PASSING, npm_install=FAIL, test=_env_check("1"))

    assert main(["--offline"], repo_root=repo, commands=commands) == 0
    assert "--offline skipped npm ci and the wrangler tests" in capsys.readouterr().out


def test_a_default_run_clears_an_inherited_offline_variable(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(OFFLINE_ENV, "1")

    assert (
        main([], repo_root=repo, commands=replace(PASSING, test=_env_check(None))) == 0
    )
