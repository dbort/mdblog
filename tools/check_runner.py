"""check_runner: the merge gate's steps, which `tools/check` runs inside the pixi environment."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from mdblog.publish import copy_notes

FIXTURE_NOTE_TEXT = "The fixture note reached the generated page."
FIXTURE_PAGE = Path("projects/first-note/index.html")
HUGO_STEP = "hugo fixture build"
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
    hugo: Sequence[str] = ("hugo",)


@dataclass(frozen=True)
class Step:
    """One gate check."""

    name: str
    # Returns the check's exit status; 0 means it passed.
    action: Callable[[], int]


def run_command(
    argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None
) -> int:
    """The exit status of `argv`; 127 when it cannot start, so a missing tool fails."""
    try:
        return subprocess.run(argv, cwd=cwd, env=env, check=False).returncode
    except OSError as exc:
        print(f"check: cannot run {argv[0]}: {exc}", file=sys.stderr)
        return 127


def hugo_fixture_build(repo_root: Path, hugo: Sequence[str]) -> int:
    """Builds the fixture vault with Hugo and returns 0 if the note's text is in the page.

    Nonzero means Hugo failed or the page lacks the text. Reads the fixtures under
    `repo_root` and writes only to a temporary directory.
    """
    fixtures = repo_root / "tests" / "fixtures"
    # A HUGO_* variable overrides site configuration, which would let the caller's
    # environment change what the fixture build reads.
    env = {k: v for k, v in os.environ.items() if not k.startswith("HUGO")}
    with tempfile.TemporaryDirectory(prefix="mdblog-check-") as tmp:
        root = Path(tmp)
        site = root / "site"
        # Hugo writes .hugo_build.lock and resources/ into its source, so it builds a
        # copy to leave the repository untouched.
        shutil.copytree(fixtures / "site", site)
        copy_notes(fixtures / "vault", site / "content")
        public = root / "public"
        status = run_command(
            [
                *hugo,
                "--source",
                str(site),
                "--destination",
                str(public),
                # The default cache lives under the user's home or system temp directory.
                "--cacheDir",
                str(root / "cache"),
            ],
            cwd=root,
            env=env,
        )
        if status != 0:
            return status
        page = public / FIXTURE_PAGE
        if not page.is_file():
            print(f"check: Hugo did not generate {FIXTURE_PAGE}", file=sys.stderr)
            return 1
        if FIXTURE_NOTE_TEXT not in page.read_text(encoding="utf-8"):
            print(f"check: {FIXTURE_PAGE} lacks the note's text", file=sys.stderr)
            return 1
    return 0


def pytest_argv(test: Sequence[str], *, smoke: bool, nested: bool) -> list[str]:
    """`test`, deselecting `hugo` tests when `smoke` and `wrapper` tests when `nested`."""
    excluded = [
        f"not {marker}"
        for marker, exclude in (("hugo", smoke), ("wrapper", nested))
        if exclude
    ]
    return [*test, "-m", " and ".join(excluded)] if excluded else [*test]


def build_steps(
    repo_root: Path, *, smoke: bool, commands: Commands, nested: bool = False
) -> list[Step]:
    """The gate's steps in run order; `smoke` leaves out the Hugo build, in pytest too.

    `nested` leaves out only the tests that start this gate themselves.
    """

    def tool(name: str, argv: Sequence[str]) -> Step:
        return Step(name, lambda: run_command(argv, repo_root))

    steps = [
        tool("ruff format", commands.format_check),
        tool("ruff check", commands.lint),
        tool("pyrefly", commands.typecheck),
        tool("pytest", pytest_argv(commands.test, smoke=smoke, nested=nested)),
    ]
    if not smoke:
        steps.append(
            Step(HUGO_STEP, lambda: hugo_fixture_build(repo_root, commands.hugo))
        )
    return steps


def run_steps(steps: Sequence[Step]) -> int:
    """Runs every step, even after a failure; returns 0 if all passed, otherwise 1."""
    failed: list[str] = []
    for step in steps:
        print(f"==> {step.name}", flush=True)
        if step.action() != 0:
            failed.append(step.name)
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
        "--smoke", action="store_true", help="leave out the Hugo fixture build"
    )
    # Every check is local, so this selects the same steps as a default run. Only
    # environment installation needs the network, and that precedes this module.
    parser.add_argument(
        "--offline", action="store_true", help="accepted; no check needs the network"
    )
    parser.add_argument(
        "--nested",
        action="store_true",
        help="internal: the gate's own tests pass this so pytest does not start them again",
    )
    args = parser.parse_args(argv)
    return run_steps(
        build_steps(
            repo_root or Path(__file__).resolve().parent.parent,
            smoke=args.smoke,
            commands=commands or Commands(),
            nested=args.nested,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
