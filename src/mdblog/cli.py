"""mdblog.cli: the `mdblog` command line."""

import argparse
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from mdblog.build import BuildError, build_site
from mdblog.config import ConfigError
from mdblog.serve import ServeError, serve_site


def _port(text: str) -> int:
    try:
        port = int(text)
    except ValueError:
        port = 0
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"{text!r} is not a port from 1 to 65535")
    return port


def check_vault(vault: Path) -> int:
    """The number of notes `mdblog build` would publish from `vault` now.

    Runs the full build, Hugo included, into a temporary directory that is removed
    afterward, with Hugo's standard output discarded. Raises what `build_site` raises.
    Writes nothing under `vault` or the current directory.
    """
    with tempfile.TemporaryDirectory(prefix="mdblog-check-") as scratch:
        return build_site(vault, Path(scratch) / "site", quiet=True)


def main(argv: Sequence[str] | None = None) -> int:
    """The process exit status for `argv`, which defaults to the process arguments.

    Returns 0 on success and 1 after reporting a failure on stderr. argparse exits 2
    with a usage message on bad arguments.
    """
    parser = argparse.ArgumentParser(prog="mdblog", allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser(
        "build", help="build the site from one vault", allow_abbrev=False
    )
    build.add_argument("vault", type=Path, metavar="VAULT", help="the vault to build")
    build.add_argument(
        "--output",
        type=Path,
        required=True,
        metavar="DIR",
        help="the directory to replace with the site",
    )
    check = commands.add_parser(
        "check",
        help="report whether one vault would build, without keeping the site",
        allow_abbrev=False,
    )
    check.add_argument("vault", type=Path, metavar="VAULT", help="the vault to check")
    serve = commands.add_parser(
        "serve",
        help="preview one vault's site, rebuilding as the vault changes",
        allow_abbrev=False,
    )
    serve.add_argument("vault", type=Path, metavar="VAULT", help="the vault to serve")
    serve.add_argument(
        "--output",
        type=Path,
        metavar="DIR",
        help="the directory to render into and keep (default: a temporary directory)",
    )
    serve.add_argument(
        "--port",
        type=_port,
        metavar="N",
        help="the port to serve on (default: 1313, or a free port if it is busy)",
    )
    serve.add_argument(
        "--drafts",
        action="store_true",
        help="also show notes with publish: false, and show notes that fail "
        "validation with warnings instead of waiting for a fix",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            build_site(args.vault, args.output)
        elif args.command == "check":
            count = check_vault(args.vault)
            print(f"{count} {'note' if count == 1 else 'notes'} would publish")
        else:
            serve_site(args.vault, args.output, args.port, drafts=args.drafts)
    except (BuildError, ConfigError, ServeError) as exc:
        print(f"mdblog: {exc}", file=sys.stderr)
        return 1
    return 0
