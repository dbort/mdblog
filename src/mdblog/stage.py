"""mdblog.stage: lays out a production build as a bundle a static-assets Worker serves."""

import json
import os
import subprocess
import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from mdblog.build import MARKER, BuildError, build_site, check_output, swap_in
from mdblog.config import ConfigError, SiteConfig, config_path, load_config
from mdblog.serve import HOST, ServeError, ServerProcess, stop_requests

# The bundle holds the wrangler config and the marker beside this directory, never in
# it: wrangler uploads everything under the assets directory to Cloudflare.
ASSETS_DIR = "public"
WRANGLER_CONFIG = "wrangler.json"
# wrangler dev's own default port.
WRANGLER_PORT = 8787
# Pinned so the runtime behavior a deployed site gets changes only with this code. It
# must not be later than the newest date the installed wrangler's runtime supports.
COMPATIBILITY_DATE = "2026-11-01"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# mdblog runs from a checkout, whose package-lock.json pins this wrangler.
WRANGLER = REPO_ROOT / "node_modules" / ".bin" / "wrangler"
# Keeps wrangler from contacting Cloudflare or npm unasked, and from prompting.
WRANGLER_ENV = {
    "WRANGLER_SEND_METRICS": "false",
    "WRANGLER_SEND_ERROR_REPORTS": "false",
    # The banner checks npm for a newer wrangler.
    "WRANGLER_HIDE_BANNER": "true",
    # wrangler dev otherwise downloads a sample `Request.cf` object from Cloudflare.
    "CLOUDFLARE_CF_FETCH_ENABLED": "false",
    # Wrangler otherwise offers to install its agent skills when it detects a coding
    # agent.
    "WRANGLER_NO_SKILLS_UPDATE_PROMPTS": "true",
}
# How often, in seconds, the serve loop checks whether wrangler exited on its own.
POLL_SECONDS = 0.5


def base_path(base_url: str) -> PurePosixPath:
    """The path of `base_url` below the site root, percent-decoded, as relative parts.

    Empty for a root URL. Raises `BuildError` for a `..` component, which would place
    the site outside the assets directory.
    """
    path = PurePosixPath(unquote(urlsplit(base_url).path).strip("/"))
    if ".." in path.parts:
        raise BuildError(f"base_url {base_url!r} has a '..' path component")
    return path


def wrangler_config(config: SiteConfig) -> dict[str, object]:
    """The wrangler config that serves the assets directory as `config`'s Worker.

    Raises `ValueError` when `config` has no `[worker]` table.
    """
    if config.worker is None:
        raise ValueError("config has no [worker] table")
    routes: dict[str, object] = {}
    if config.worker.routes:
        routes = {
            # Wrangler finds each pattern's zone from its host.
            "routes": list(config.worker.routes),
            # Hugo writes base_url into every link, so a copy on workers.dev would
            # link away from itself and duplicate the site.
            "workers_dev": False,
        }
    return {
        "name": config.worker.name,
        **routes,
        "compatibility_date": COMPATIBILITY_DATE,
        # No `main` script: the Worker serves only static assets, and no code of ours
        # runs per request.
        "assets": {
            "directory": ASSETS_DIR,
            # Hugo writes each page as `<path>/index.html` and links to `<path>/`,
            # which this mode serves, redirecting `<path>/index.html` to `<path>/`.
            "html_handling": "auto-trailing-slash",
            # Serves the nearest `404.html` at or above the requested path with status
            # 404, so a site under a base path finds `<base>/404.html`.
            "not_found_handling": "404-page",
        },
    }


def stage_site(
    vault: Path,
    output: Path,
    config: SiteConfig | None = None,
    hugo: Sequence[str] = ("hugo",),
    now: datetime | None = None,
) -> PurePosixPath:
    """Replaces `output` with a Worker bundle of a production build of `vault`.

    Builds with `config`, by default the vault's own settings, which must have a
    `[worker]` table. Returns the site's `base_path`. On success `output` holds the
    marker, `WRANGLER_CONFIG` and `ASSETS_DIR`, and the assets hold Hugo's output under
    the base path and no marker. Raises what `build_site` raises, plus `ConfigError`
    for a missing `[worker]`, with `output` unchanged. `output` is refused under the
    rules of `check_output`.
    """
    vault = vault.resolve()
    output = output.resolve()
    if not vault.is_dir():
        raise BuildError(f"vault {vault} is not a directory")
    config = config or load_config(vault)
    if config.worker is None:
        raise ConfigError(
            f"{config_path(vault)}: mdblog stage needs [worker] name, the name of the "
            "Cloudflare Worker that serves the site"
        )
    check_output(vault, output)
    site_path = base_path(config.base_url)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        # A sibling shares the output's filesystem, which the renames require.
        with tempfile.TemporaryDirectory(
            prefix=".mdblog-stage-", dir=output.parent
        ) as staging_name:
            staging = Path(staging_name)
            built = staging / "site"
            build_site(vault, built, hugo, now, config=config)
            # Static files from the vault may carry the name too; none may upload.
            for marker in built.rglob(MARKER):
                marker.unlink()
            # A subdirectory, because mkdtemp's 0700 mode must not reach the output.
            bundle = staging / "bundle"
            assets = bundle / ASSETS_DIR / site_path
            assets.parent.mkdir(parents=True)
            # Hugo writes its output for the site root even when base_url has a path,
            # and Cloudflare serves the assets directory at the root of the URL.
            built.rename(assets)
            (bundle / WRANGLER_CONFIG).write_text(
                json.dumps(wrangler_config(config), indent=2) + "\n", encoding="utf-8"
            )
            (bundle / MARKER).write_text(
                "Generated by mdblog stage, which replaces this directory.\n",
                encoding="utf-8",
            )
            swap_in(bundle, output, staging / "previous")
    except OSError as exc:
        raise BuildError(f"cannot stage into {output}: {exc}") from exc
    return site_path


def find_wrangler() -> Path:
    """`WRANGLER`; raises `ServeError` naming it and how to install it when absent."""
    if not WRANGLER.is_file():
        raise ServeError(
            f"wrangler not found at {WRANGLER}; install it with "
            f"`pixi run npm ci` in {REPO_ROOT}"
        )
    return WRANGLER


def wrangler_dev_argv(wrangler: Sequence[str], bundle: Path, port: int) -> list[str]:
    """The command that serves `bundle` with wrangler dev on `HOST`:`port`."""
    return [
        *wrangler,
        "dev",
        "--config",
        str(bundle / WRANGLER_CONFIG),
        # Wrangler's default is `localhost`, which can also bind the IPv6 loopback.
        # This matches mdblog serve and the address choose_port probed.
        "--ip",
        HOST,
        "--port",
        str(port),
        # The hotkey session reads the terminal, which a background process group
        # cannot do without being stopped.
        "--show-interactive-dev-session=false",
    ]


def serve_bundle(
    bundle: Path, site_path: PurePosixPath, port: int, wrangler: Sequence[str]
) -> None:
    """Serves `bundle` with wrangler dev on `HOST`:`port` until SIGINT or SIGTERM.

    Prints the site's local URL, with `site_path` as its path, to stdout. Raises
    `ServeError` when wrangler cannot start or exits on its own. Wrangler keeps its
    local state in `bundle/.wrangler`, outside the assets directory.
    """
    bundle = bundle.resolve()
    path = f"/{site_path}/" if site_path.parts else "/"
    with stop_requests() as stopping:
        try:
            # Its own group keeps a terminal's Ctrl+C from reaching wrangler, so it
            # exits only when stopped and any other exit is a failure.
            process = subprocess.Popen(
                wrangler_dev_argv(wrangler, bundle, port),
                cwd=bundle,
                env={**os.environ, **WRANGLER_ENV},
                stdin=subprocess.DEVNULL,
                process_group=0,
            )
        except OSError as exc:
            raise ServeError(f"cannot run {wrangler[0]}: {exc.strerror}") from exc
        server = ServerProcess(process)
        try:
            print(f"mdblog: serving the staged site at http://{HOST}:{port}{path}")
            print("mdblog: press Ctrl+C to stop", flush=True)
            while not stopping.wait(POLL_SECONDS):
                if (status := server.poll()) is not None:
                    raise ServeError(f"wrangler exited with status {status}")
        finally:
            server.stop()
