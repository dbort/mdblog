"""check_runner: the merge gate's steps, which `tools/check` runs inside the pixi environment."""

import argparse
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

CHECKED_PATHS = ("src", "tests", "tools")


@dataclass(frozen=True)
class Commands:
    """The argv of each external tool, replaceable so tests can inject failures."""

    format_check: Sequence[str] = ("ruff", "format", "--check", *CHECKED_PATHS)
    lint: Sequence[str] = ("ruff", "check", *CHECKED_PATHS)
    # With no file arguments pyrefly checks the project-includes in pyproject.toml,
    # which name the same directories as CHECKED_PATHS.
    typecheck: Sequence[str] = ("pyrefly", "check")
    test: Sequence[str] = ("pytest", "tests")


def run_command(argv: Sequence[str], cwd: Path) -> int:
    """The exit status of `argv`; 127 when it cannot start, so a missing tool fails."""
    try:
        return subprocess.run(argv, cwd=cwd, check=False).returncode
    except OSError as exc:
        print(f"check: cannot run {argv[0]}: {exc}", file=sys.stderr)
        return 127


def run_steps(commands: Commands, repo_root: Path) -> int:
    """Runs every step, even after a failure; returns 0 if all passed, otherwise 1."""
    steps = (
        ("ruff format", commands.format_check),
        ("ruff check", commands.lint),
        ("pyrefly", commands.typecheck),
        ("pytest", commands.test),
    )
    failed: list[str] = []
    for name, argv in steps:
        print(f"==> {name}", flush=True)
        if run_command(argv, repo_root) != 0:
            failed.append(name)
    if failed:
        print(f"check: FAILED: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("check: all steps passed", flush=True)
    return 0


def main(
    argv: Sequence[str] | None = None,
    repo_root: Path | None = None,
    commands: Commands | None = None,
) -> int:
    """The gate's exit status for `argv`; argparse exits 2 on an unknown flag."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke", action="store_true", help="accepted; every check is already fast"
    )
    # Every check is local, so this selects the same steps as a default run. Only
    # environment installation needs the network, and that precedes this module.
    parser.add_argument(
        "--offline", action="store_true", help="accepted; no check needs the network"
    )
    parser.parse_args(argv)
    return run_steps(
        commands or Commands(),
        repo_root or Path(__file__).resolve().parent.parent,
    )


if __name__ == "__main__":
    sys.exit(main())
