"""mdblog.deploy: publishes a vault's site to its Cloudflare Worker and checks it."""

import os
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from mdblog.config import load_config
from mdblog.stage import WRANGLER_CONFIG, WRANGLER_ENV, stage_site
from mdblog.verify import site_url, verify_site

# Seconds deploy keeps retrying verification after the upload: a new version can take
# a moment to reach every Cloudflare location.
VERIFY_PATIENCE = 60.0
# Seconds between verification attempts.
VERIFY_INTERVAL = 5.0

type Verifier = Callable[[str], Iterable[tuple[str, str | None]]]


class DeployError(Exception):
    """An upload or post-upload check that failed; the message says which."""


def wrangler_deploy_argv(wrangler: Sequence[str], bundle: Path) -> list[str]:
    """The command that uploads `bundle` as the Worker its wrangler config names."""
    return [*wrangler, "deploy", "--config", str(bundle / WRANGLER_CONFIG)]


def upload(wrangler: Sequence[str], bundle: Path) -> None:
    """Runs wrangler deploy on `bundle`, its output going to this process's streams.

    Wrangler reads its credentials from the environment or its own login. Raises
    `DeployError` when wrangler cannot start or exits nonzero.
    """
    try:
        status = subprocess.run(
            wrangler_deploy_argv(wrangler, bundle),
            cwd=bundle,
            env={**os.environ, **WRANGLER_ENV},
            stdin=subprocess.DEVNULL,
            check=False,
        ).returncode
    except OSError as exc:
        raise DeployError(f"cannot run {wrangler[0]}: {exc.strerror}") from exc
    if status != 0:
        raise DeployError(f"wrangler deploy exited with status {status}")


def await_verified(
    url: str,
    verify: Verifier = verify_site,
    patience: float = VERIFY_PATIENCE,
    interval: float = VERIFY_INTERVAL,
) -> None:
    """Returns once every check of `verify` on `url` passes.

    Tries at least once, and again every `interval` seconds until `patience` seconds
    have passed since the first try. Raises `DeployError` listing the last attempt's
    failed checks and saying the site is live.
    """
    deadline = time.monotonic() + patience
    while True:
        failed = [f"{name}: {problem}" for name, problem in verify(url) if problem]
        if not failed:
            return
        if time.monotonic() + interval > deadline:
            raise DeployError(
                f"uploaded the site, so it is live, but it fails verification at "
                f"{url}: {'; '.join(failed)}"
            )
        time.sleep(interval)


def deploy_site(
    vault: Path,
    wrangler: Sequence[str],
    hugo: Sequence[str] = ("hugo",),
    verify: Verifier = verify_site,
    patience: float = VERIFY_PATIENCE,
) -> str:
    """Publishes a production build of `vault` to its Worker and returns its URL.

    Stages into a temporary directory that is removed afterward, uploads it with
    `wrangler`, then waits as `await_verified` does for the site at the vault's
    `base_url` to pass `verify`. Raises what `load_config`, `site_url` and
    `stage_site` raise, before running wrangler, and `DeployError` from the upload
    or the verification.
    """
    config = load_config(vault.resolve())
    url = site_url(config.base_url)
    with tempfile.TemporaryDirectory(prefix="mdblog-deploy-") as scratch:
        bundle = Path(scratch) / "bundle"
        stage_site(vault, bundle, config, hugo)
        upload(wrangler, bundle)
    await_verified(url, verify, patience)
    return url
