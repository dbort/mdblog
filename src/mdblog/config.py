"""mdblog.config: reads one site's settings from the vault it describes."""

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

SITE_DIR = "_site"
CONFIG_FILE = "mdblog.toml"


class ConfigError(Exception):
    """A vault's configuration file is unusable; the message names the file."""


@dataclass(frozen=True)
class SiteConfig:
    """The settings one site's `mdblog.toml` must hold, one key per field."""

    # Hugo writes this into every absolute link and feed entry.
    base_url: str
    title: str
    # Layouts read it as `.Site.Params.author`.
    author: str


def load_config(vault: Path) -> SiteConfig:
    """The settings in `vault`'s `_site/mdblog.toml`.

    Raises `ConfigError` naming the file when it is missing, is reached through a
    symbolic link, is not valid TOML, lacks a key, holds a non-string value or holds
    an unknown key. One error lists every bad key.
    """
    path = vault / SITE_DIR / CONFIG_FILE
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

    names = [field.name for field in fields(SiteConfig)]
    values: dict[str, str] = {}
    problems: list[str] = []
    for name in names:
        value = table.get(name)
        if name not in table:
            problems.append(f"missing key {name!r}")
        elif isinstance(value, str):
            values[name] = value
        else:
            problems.append(f"key {name!r} must be a string")
    # A misspelled optional key must not be ignored silently.
    problems.extend(f"unknown key {key!r}" for key in sorted(table.keys() - set(names)))
    if problems:
        raise ConfigError(f"{path}: {'; '.join(problems)}")
    return SiteConfig(
        base_url=values["base_url"], title=values["title"], author=values["author"]
    )
