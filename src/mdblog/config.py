"""mdblog.config: reads one site's settings from the vault it describes."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

SITE_DIR = "_site"
CONFIG_FILE = "mdblog.toml"
# The keys every `mdblog.toml` holds at its top level, each a string.
REQUIRED_KEYS = ("base_url", "title", "author")
WORKER_TABLE = "worker"
# Cloudflare's rule for a Worker on a workers.dev subdomain, which a Worker without
# routes gets by default: at most 63 characters, letters, digits and hyphens, and no
# hyphen at either end. Wrangler also rejects uppercase. The name is a DNS label there.
WORKER_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class ConfigError(Exception):
    """A vault's configuration file is unusable; the message names the file."""


@dataclass(frozen=True)
class WorkerConfig:
    """The settings of a site's `[worker]` table, which `mdblog stage` needs."""

    # The Cloudflare Worker that serves the site, matching `WORKER_NAME`.
    name: str


@dataclass(frozen=True)
class SiteConfig:
    """The settings one site's `mdblog.toml` holds."""

    # Hugo writes this into every absolute link and feed entry.
    base_url: str
    title: str
    # Layouts read it as `.Site.Params.author`.
    author: str
    # None when the file has no `[worker]` table.
    worker: WorkerConfig | None = None


def config_path(vault: Path) -> Path:
    """Where `vault` keeps its `mdblog.toml`, whether or not the file exists."""
    return vault / SITE_DIR / CONFIG_FILE


def _worker(value: object) -> WorkerConfig | list[str]:
    if not isinstance(value, dict):
        return [f"[{WORKER_TABLE}] must be a table"]
    problems: list[str] = []
    name: object = value.get("name")
    if "name" not in value:
        problems.append(f"[{WORKER_TABLE}] is missing key 'name'")
    elif not isinstance(name, str):
        problems.append(f"[{WORKER_TABLE}] key 'name' must be a string")
    elif not WORKER_NAME.fullmatch(name):
        problems.append(
            f"[{WORKER_TABLE}] name {name!r} is not a valid Worker name: use 1 to 63 "
            "lowercase letters, digits and hyphens, with no hyphen at either end"
        )
    problems.extend(
        f"[{WORKER_TABLE}] has unknown key {key!r}"
        for key in sorted(str(key) for key in value.keys() - {"name"})
    )
    if problems or not isinstance(name, str):
        return problems
    return WorkerConfig(name=name)


def load_config(vault: Path) -> SiteConfig:
    """The settings in `vault`'s `_site/mdblog.toml`.

    Raises `ConfigError` naming the file when it is missing, is reached through a
    symbolic link, is not valid TOML, lacks a key, holds a non-string value, holds an
    unknown key, or has a `[worker]` that is not a table holding only a valid string
    `name`. One error lists every problem.
    """
    path = config_path(vault)
    if path.parent.is_symlink() or path.is_symlink():
        raise ConfigError(f"{path}: is reached through a symbolic link")
    try:
        with path.open("rb") as file:
            table = tomllib.load(file)
    except FileNotFoundError:
        raise ConfigError(f"{path}: file not found") from None
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read: {exc.strerror}") from exc
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"{path}: invalid TOML: {exc}") from exc

    values: dict[str, str] = {}
    problems: list[str] = []
    for name in REQUIRED_KEYS:
        value = table.get(name)
        if name not in table:
            problems.append(f"missing key {name!r}")
        elif isinstance(value, str):
            values[name] = value
        else:
            problems.append(f"key {name!r} must be a string")
    worker = _worker(table[WORKER_TABLE]) if WORKER_TABLE in table else None
    if isinstance(worker, list):
        problems.extend(worker)
    # A misspelled optional key must not be ignored silently.
    known = {*REQUIRED_KEYS, WORKER_TABLE}
    problems.extend(f"unknown key {key!r}" for key in sorted(table.keys() - known))
    if problems:
        raise ConfigError(f"{path}: {'; '.join(problems)}")
    return SiteConfig(
        base_url=values["base_url"],
        title=values["title"],
        author=values["author"],
        worker=worker if isinstance(worker, WorkerConfig) else None,
    )
