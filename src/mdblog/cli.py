"""mdblog.cli: the `mdblog` command line."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from mdblog.build import BuildError, build_site
from mdblog.config import ConfigError


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
    args = parser.parse_args(argv)
    try:
        build_site(args.vault, args.output)
    except (BuildError, ConfigError) as exc:
        print(f"mdblog: {exc}", file=sys.stderr)
        return 1
    return 0
