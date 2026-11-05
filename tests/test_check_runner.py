import sys
from dataclasses import fields, replace
from pathlib import Path

import pytest

from check_runner import Commands, main

PASS = (sys.executable, "-c", "pass")
FAIL = (sys.executable, "-c", "raise SystemExit(3)")
PASSING = Commands(format_check=PASS, lint=PASS, typecheck=PASS, test=PASS)
STEPS = [field.name for field in fields(Commands)]


def test_main_exits_zero_when_every_step_passes(tmp_path: Path) -> None:
    assert main([], repo_root=tmp_path, commands=PASSING) == 0


@pytest.mark.parametrize("step", STEPS)
def test_main_exits_nonzero_when_one_step_fails(tmp_path: Path, step: str) -> None:
    commands = replace(PASSING, **{step: FAIL})

    assert main([], repo_root=tmp_path, commands=commands) != 0


@pytest.mark.parametrize("step", STEPS)
def test_main_exits_nonzero_when_a_tool_is_missing(tmp_path: Path, step: str) -> None:
    commands = replace(PASSING, **{step: ("mdblog-no-such-tool",)})

    assert main([], repo_root=tmp_path, commands=commands) != 0
