"""check_runner: the merge gate's steps, which `tools/check` runs inside the pixi environment."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

CHECKED_PATHS = ("src", "tests", "tools")
MANIFEST = "package.json"
LOCKFILE = "package-lock.json"
# Holds the SHA-256 of the lockfile `npm ci` last installed, so an unchanged lockfile
# skips the reinstall. npm's own `node_modules/.package-lock.json` cannot serve: it
# leaves out the other platforms' optional packages, so it never equals the lockfile.
INSTALL_STAMP = Path("node_modules") / ".mdblog-installed-lock"
# The fields of package.json that npm copies into the lockfile's root package.
DEPENDENCY_FIELDS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)
# Tells pytest that the gate runs under --offline; tests/conftest.py reads it.
OFFLINE_ENV = "MDBLOG_CHECK_OFFLINE"
# npm otherwise checks the registry for a newer npm on every run.
NPM_ENV = {"NPM_CONFIG_UPDATE_NOTIFIER": "false"}


@dataclass(frozen=True)
class Commands:
    """The argv of each external tool, replaceable so tests can inject failures."""

    # `npm ci` installs exactly the lockfile and fails when package.json disagrees.
    # package.json's `allowScripts` turns off esbuild's and workerd's install scripts:
    # each only checks the platform binary npm already installed as an optional
    # package, and npm blocks dependency install scripts unless they are listed.
    npm_install: Sequence[str] = ("npm", "ci", "--no-audit", "--no-fund")
    format_check: Sequence[str] = ("ruff", "format", "--check", *CHECKED_PATHS)
    lint: Sequence[str] = ("ruff", "check", *CHECKED_PATHS)
    # With no file arguments pyrefly checks the project-includes in pyproject.toml,
    # which name the same directories as CHECKED_PATHS.
    typecheck: Sequence[str] = ("pyrefly", "check")
    test: Sequence[str] = ("pytest", "tests")


def run_command(
    argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None
) -> int:
    """The exit status of `argv`; 127 when it cannot start, so a missing tool fails."""
    try:
        return subprocess.run(argv, cwd=cwd, env=env, check=False).returncode
    except OSError as exc:
        print(f"check: cannot run {argv[0]}: {exc}", file=sys.stderr)
        return 127


def _json_object(path: Path) -> dict[str, object]:
    # json.loads returns Any; the isinstance check gives the rest of the module a type.
    data: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("is not a JSON object")
    return {str(key): value for key, value in data.items()}


def lock_problems(repo_root: Path) -> list[str]:
    """Each way `package-lock.json` disagrees with `package.json`; empty if they agree.

    Compares the package name and every field in `DEPENDENCY_FIELDS`, an absent field
    matching an empty one. An unreadable or malformed file is a problem too.
    `pixi run --locked` checks pixi.lock but not this lockfile.
    """
    try:
        manifest = _json_object(repo_root / MANIFEST)
        lock = _json_object(repo_root / LOCKFILE)
    except (OSError, ValueError) as exc:
        return [f"cannot read {MANIFEST} and {LOCKFILE}: {exc}"]
    packages = lock.get("packages")
    root = packages.get("") if isinstance(packages, dict) else None
    if not isinstance(root, dict):
        return [f"{LOCKFILE} has no root package"]
    problems: list[str] = []
    if lock.get("name") != manifest.get("name"):
        problems.append("name")
    problems.extend(
        field
        for field in DEPENDENCY_FIELDS
        if (manifest.get(field) or {}) != (root.get(field) or {})
    )
    return [
        f"{LOCKFILE} disagrees with {MANIFEST} on {field}; run npm install"
        for field in problems
    ]


def _lock_digest(repo_root: Path) -> str:
    return hashlib.sha256((repo_root / LOCKFILE).read_bytes()).hexdigest()


def install_is_current(repo_root: Path) -> bool:
    """Whether `node_modules/` was installed by `npm ci` from the current lockfile."""
    try:
        stamp = (repo_root / INSTALL_STAMP).read_text(encoding="utf-8")
        return stamp == _lock_digest(repo_root)
    except OSError:
        return False


def record_install(repo_root: Path) -> None:
    """Marks `node_modules/` as installed from the current lockfile."""
    (repo_root / INSTALL_STAMP).write_text(_lock_digest(repo_root), encoding="utf-8")


def _check_lock(repo_root: Path) -> bool:
    problems = lock_problems(repo_root)
    for problem in problems:
        print(f"check: {problem}", file=sys.stderr)
    return not problems


def _install(argv: Sequence[str], repo_root: Path, offline: bool) -> bool:
    if offline:
        print("check: skipped under --offline", flush=True)
        return True
    if install_is_current(repo_root):
        print(f"check: node_modules matches {LOCKFILE}; not reinstalling", flush=True)
        return True
    if run_command(argv, repo_root, {**os.environ, **NPM_ENV}) != 0:
        return False
    record_install(repo_root)
    return True


def run_steps(commands: Commands, repo_root: Path, offline: bool = False) -> int:
    """Runs every step, even after a failure; returns 0 if all passed, otherwise 1.

    With `offline`, skips the npm install and tells pytest to skip the tests that
    need wrangler, and the closing line names both skips.
    """
    test_env = {k: v for k, v in os.environ.items() if k != OFFLINE_ENV}
    if offline:
        test_env[OFFLINE_ENV] = "1"
    steps = (
        ("npm lockfile", lambda: _check_lock(repo_root)),
        ("npm ci", lambda: _install(commands.npm_install, repo_root, offline)),
        ("ruff format", lambda: run_command(commands.format_check, repo_root) == 0),
        ("ruff check", lambda: run_command(commands.lint, repo_root) == 0),
        ("pyrefly", lambda: run_command(commands.typecheck, repo_root) == 0),
        ("pytest", lambda: run_command(commands.test, repo_root, test_env) == 0),
    )
    failed: list[str] = []
    for name, step in steps:
        print(f"==> {name}", flush=True)
        if not step():
            failed.append(name)
    if failed:
        print(f"check: FAILED: {', '.join(failed)}", file=sys.stderr)
        return 1
    skipped = " (--offline skipped npm ci and the wrangler tests)" if offline else ""
    print(f"check: all steps passed{skipped}", flush=True)
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
    parser.add_argument(
        "--offline",
        action="store_true",
        help="skip the npm install and the tests that run wrangler",
    )
    args = parser.parse_args(argv)
    return run_steps(
        commands or Commands(),
        repo_root or Path(__file__).resolve().parent.parent,
        offline=args.offline,
    )


if __name__ == "__main__":
    sys.exit(main())
