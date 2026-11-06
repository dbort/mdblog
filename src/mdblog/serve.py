"""mdblog.serve: previews one vault's site with Hugo's server, rebuilding as it changes."""

import ipaddress
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from types import FrameType
from typing import Protocol

import watchfiles

from mdblog.build import (
    MARKER,
    BuildError,
    assemble_source,
    check_output,
    convert_vault,
    hugo_env,
)
from mdblog.config import ConfigError
from mdblog.links import base_path

DEFAULT_PORT = 1313
DEFAULT_BIND = "127.0.0.1"
# Hugo writes these into its source while it runs, and the assembled source never has them.
HUGO_OWNED = frozenset((".cache", ".hugo_build.lock", "resources"))
# How often, in milliseconds, the watch loop wakes with no change to check on Hugo.
POLL_MS = 1000
# Seconds Hugo gets to exit after SIGTERM before it is killed.
STOP_TIMEOUT = 10


class ServeError(Exception):
    """Serve was refused or cannot continue; the message says why."""


def check_bind(bind: str) -> None:
    """Raises `ServeError` when `bind` is a wildcard address such as 0.0.0.0 or ::."""
    try:
        address = ipaddress.ip_address(bind)
    except ValueError:
        return
    if address.is_unspecified:
        raise ServeError(
            f"refusing --bind {bind}: links need one host, so give a specific address"
        )


def server_base_url(base_url: str, bind: str, port: int) -> str:
    """The base URL whose links point at `bind`:`port`, keeping `base_url`'s path.

    An IPv6 address is bracketed. The result always ends in a slash.
    """
    try:
        is_ipv6 = ipaddress.ip_address(bind).version == 6
    except ValueError:
        is_ipv6 = False
    host = f"[{bind}]" if is_ipv6 else bind
    return f"http://{host}:{port}{base_path(base_url)}/"


def _bound_port(bind: str, port: int) -> int:
    family = socket.AF_INET6 if ":" in bind else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        probe.bind((bind, port))
        # typeshed types getsockname as Any. Item 1 is the port for IPv4 and IPv6.
        bound: int = probe.getsockname()[1]
        return bound


def choose_port(bind: str, requested: int | None) -> int:
    """A port that is free on `bind`: `requested`, else 1313, else any free port.

    Raises `ServeError` naming the port when `requested` cannot be bound, or when no
    port can be bound on `bind`. The port is free when probed; another process can
    still take it before Hugo binds it.
    """
    port = DEFAULT_PORT if requested is None else requested
    try:
        return _bound_port(bind, port)
    except OSError as exc:
        if requested is not None:
            raise ServeError(
                f"cannot listen on {bind} port {port}: {exc.strerror}"
            ) from exc
    try:
        return _bound_port(bind, 0)
    except OSError as exc:
        raise ServeError(f"cannot listen on {bind}: {exc.strerror}") from exc


def default_output(port: int) -> Path:
    """`mdblog-serve-<port>` in the system temporary directory."""
    return Path(tempfile.gettempdir()) / f"mdblog-serve-{port}"


def is_hidden(vault: Path, path: Path) -> bool:
    """Whether any component of `path` below `vault` starts with a dot.

    A path outside `vault` is not hidden.
    """
    if not path.is_relative_to(vault):
        return False
    return any(part.startswith(".") for part in path.relative_to(vault).parts)


@dataclass(frozen=True)
class SyncResult:
    """What one `sync_tree` call changed, as paths relative to the live tree."""

    # Files whose bytes changed or that are new, and directories that are new.
    written: frozenset[PurePosixPath]
    removed: frozenset[PurePosixPath]


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def sync_tree(staging: Path, live: Path) -> SyncResult:
    """Makes `live` hold the same files as `staging`, touching only what differs.

    A file whose bytes already match is left alone, mtime included. Paths in `live`
    absent from `staging` are removed, except the top-level names in `HUGO_OWNED`.
    Raises `OSError` when a file cannot be read or written.
    """
    written: set[PurePosixPath] = set()
    wanted: set[PurePosixPath] = set()
    for path in sorted(staging.rglob("*")):
        relative = PurePosixPath(path.relative_to(staging).as_posix())
        wanted.add(relative)
        target = live / relative
        if path.is_dir():
            if target.is_dir() and not target.is_symlink():
                continue
            if target.exists() or target.is_symlink():
                _remove(target)
            target.mkdir()
            written.add(relative)
            continue
        data = path.read_bytes()
        if target.is_file() and not target.is_symlink():
            if target.read_bytes() == data:
                continue
        elif target.exists() or target.is_symlink():
            _remove(target)
        target.write_bytes(data)
        written.add(relative)
    removed: set[PurePosixPath] = set()
    # Sorted, so a directory comes before its contents and is removed with them.
    for path in sorted(live.rglob("*")):
        relative = PurePosixPath(path.relative_to(live).as_posix())
        if relative.parts[0] in HUGO_OWNED or relative in wanted:
            continue
        if any(parent in removed for parent in relative.parents):
            continue
        _remove(path)
        removed.add(relative)
    return SyncResult(written=frozenset(written), removed=frozenset(removed))


def needs_restart(result: SyncResult) -> bool:
    """Whether Hugo must restart to serve the synced source correctly.

    Hugo's server never deletes a removed page's files from its destination and keeps
    serving them, and it watches only the directories present when it started. A new
    `hugo.toml` can also change the path it serves under. So any removal, and any new
    or changed top-level path, needs a restart into an emptied destination.
    """
    return bool(result.removed) or any(len(p.parts) == 1 for p in result.written)


@dataclass(frozen=True)
class Rebuilt:
    """One good rebuild."""

    sync: SyncResult
    # The `base_url` in the vault's settings when it was rebuilt.
    base_url: str


def rebuild(vault: Path, source: Path, now: datetime) -> Rebuilt | None:
    """Syncs the Hugo source for `vault` into `source`, or reports why it cannot.

    On a validation or file error, prints the failure to stderr as `mdblog build` does,
    leaves `source` untouched and returns None.
    """
    try:
        site = convert_vault(vault, now)
        with tempfile.TemporaryDirectory(prefix="mdblog-stage-") as staging_name:
            staging = Path(staging_name)
            assemble_source(staging, vault, site)
            return Rebuilt(sync_tree(staging, source), site.config.base_url)
    except (BuildError, ConfigError) as exc:
        print(f"mdblog: {exc}", file=sys.stderr)
    except OSError as exc:
        print(f"mdblog: cannot assemble the site: {exc}", file=sys.stderr)
    return None


class Server(Protocol):
    """A running Hugo server."""

    def poll(self) -> int | None:
        """Hugo's exit status, or None while it runs."""
        ...

    def stop(self) -> None:
        """Stops Hugo and waits for it to exit; does nothing if it already has."""
        ...


def watch_loop(
    vault: Path,
    source: Path,
    batches: Iterable[Collection[object]],
    start: Callable[[str], Server],
    clock: Callable[[], datetime],
) -> None:
    """Rebuilds `source` from `vault` once, then again after each non-empty batch.

    Calls `start` with the configured base URL to start the server after the first good
    rebuild, and to restart it, after stopping it, whenever `needs_restart` says so. An
    empty batch only checks the server. Returns when `batches` is exhausted, having
    stopped the server. Raises `ServeError` if the server exits on its own. `clock`
    gives the time each rebuild compares dates to.
    """
    server: Server | None = None
    try:
        if rebuilt := rebuild(vault, source, clock()):
            server = start(rebuilt.base_url)
        else:
            print("mdblog: waiting for a change that fixes the vault", file=sys.stderr)
        for batch in batches:
            if server is not None and (status := server.poll()) is not None:
                raise ServeError(f"hugo exited with status {status}")
            if not batch or not (rebuilt := rebuild(vault, source, clock())):
                continue
            if server is None:
                server = start(rebuilt.base_url)
            elif needs_restart(rebuilt.sync):
                server.stop()
                server = start(rebuilt.base_url)
    finally:
        if server is not None:
            server.stop()


def hugo_server_argv(
    hugo: Sequence[str],
    source: Path,
    destination: Path,
    port: int,
    bind: str,
    base_url: str | None,
) -> list[str]:
    """The command that serves `source` on `bind`:`port`, rendering into `destination`.

    With a `base_url`, links on served pages use it in place of Hugo's default
    `http://localhost:<port>`.
    """
    argv = [
        *hugo,
        "server",
        "--source",
        str(source),
        "--destination",
        str(destination),
        # The default cache lives under the user's home or system temp directory.
        "--cacheDir",
        str(source / ".cache"),
        # Validation has already rejected future dates; see _run_hugo in build.py.
        "--buildFuture",
        "--port",
        str(port),
        "--bind",
        bind,
        # Re-rendering every page on each change keeps the destination complete. Fast
        # render re-renders only the pages a browser has visited.
        "--disableFastRender",
    ]
    if base_url is not None:
        # Hugo cannot append a port to a bracketed IPv6 host, so the URL carries it.
        argv += ["--baseURL", base_url, "--appendPort=false"]
    return argv


def reset_output(output: Path) -> None:
    """Empties `output`, creating it if needed, and writes the marker into it."""
    if output.is_dir():
        for child in output.iterdir():
            _remove(child)
    output.mkdir(parents=True, exist_ok=True)
    (output / MARKER).write_text(
        "Generated by mdblog serve, which replaces this directory.\n",
        encoding="utf-8",
    )


@dataclass
class HugoProcess:
    """A Hugo server running as a child process."""

    process: subprocess.Popen[bytes]

    def poll(self) -> int | None:
        return self.process.poll()

    def stop(self) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=STOP_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def start_hugo(argv: Sequence[str], cwd: Path) -> HugoProcess:
    """Starts `argv` in `cwd` without `HUGO*` variables, in its own process group.

    Its output goes to this process's stdout and stderr. Raises `ServeError` when it
    cannot start.
    """
    try:
        # Its own group keeps a terminal's Ctrl+C from reaching Hugo, so Hugo exits
        # only when stopped and any other exit is a failure.
        process = subprocess.Popen(argv, cwd=cwd, env=hugo_env(), process_group=0)
    except OSError as exc:
        raise ServeError(f"cannot run {argv[0]}: {exc.strerror}") from exc
    return HugoProcess(process)


def serve_site(
    vault: Path,
    output: Path | None = None,
    port: int | None = None,
    bind: str | None = None,
    hugo: Sequence[str] = ("hugo",),
) -> None:
    """Serves `vault`'s site with Hugo until SIGINT or SIGTERM, rebuilding on changes.

    Renders into `output`, which is kept, or else into `default_output(port)`, which is
    removed on return. `port` defaults to 1313, or any free port when 1313 is busy.
    `bind` defaults to 127.0.0.1 with links to `localhost`; a given `bind` is also the
    links' host. Raises `ServeError` or `BuildError` for a refusal before serving
    starts, and `ServeError` if Hugo exits on its own. A vault that fails validation
    never raises: its failures go to stderr and serve waits for a fix.
    """
    vault = vault.resolve()
    if not vault.is_dir():
        raise BuildError(f"vault {vault} is not a directory")
    if bind is not None:
        check_bind(bind)
    listen = bind or DEFAULT_BIND
    chosen = choose_port(listen, port)
    destination = (output or default_output(chosen)).resolve()
    check_output(vault, destination)

    stopping = threading.Event()

    def request_stop(signum: int, frame: FrameType | None) -> None:
        stopping.set()

    handlers = {
        signum: signal.signal(signum, request_stop)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    source = Path(tempfile.mkdtemp(prefix="mdblog-serve-source-"))
    try:

        def start(configured: str) -> Server:
            base_url = (
                None if bind is None else server_base_url(configured, bind, chosen)
            )
            reset_output(destination)
            return start_hugo(
                hugo_server_argv(hugo, source, destination, chosen, listen, base_url),
                source,
            )

        batches = watchfiles.watch(
            vault,
            watch_filter=lambda _change, path: not is_hidden(vault, Path(path)),
            stop_event=stopping,
            rust_timeout=POLL_MS,
            yield_on_timeout=True,
            # Signals only set `stopping`; nothing raises KeyboardInterrupt.
            raise_interrupt=False,
        )
        watch_loop(vault, source, batches, start, lambda: datetime.now().astimezone())
    finally:
        shutil.rmtree(source, ignore_errors=True)
        if output is None:
            shutil.rmtree(destination, ignore_errors=True)
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
