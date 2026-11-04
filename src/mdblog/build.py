"""mdblog.build: turns one vault into a Hugo site in an output directory."""

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from mdblog.config import SITE_DIR, SiteConfig, load_config
from mdblog.publish import PublishedNote, select_notes

MARKER = ".mdblog-output"
THEME = "mdblog"
PACKAGED_THEME = Path(__file__).resolve().parent / "theme"


class BuildError(Exception):
    """A build was refused or failed; the output directory is unchanged."""


def path_contains(outer: Path, inner: Path) -> bool:
    """Whether `inner` is `outer` or lies below it.

    Existing directories also compare by identity, because a case-insensitive filesystem
    gives one directory several spellings.
    """
    if inner.is_relative_to(outer):
        return True
    if not outer.exists():
        return False
    return any(
        path.exists() and path.samefile(outer) for path in (inner, *inner.parents)
    )


def check_output(vault: Path, output: Path) -> None:
    """Raises `BuildError` unless a build may replace `output`.

    A missing directory, an empty directory and a directory holding the marker are
    accepted. A non-directory, the vault, a path inside the vault, a path containing the
    vault and a non-empty directory with no marker are refused. Changes nothing.
    """
    if output.exists() and not output.is_dir():
        raise BuildError(f"refusing output {output}: it is not a directory")
    if path_contains(vault, output):
        raise BuildError(f"refusing output {output}: it is the vault or inside it")
    if path_contains(output, vault):
        raise BuildError(f"refusing output {output}: it contains the vault {vault}")
    if (
        output.is_dir()
        and not (output / MARKER).is_file(follow_symlinks=False)
        and any(output.iterdir())
    ):
        raise BuildError(
            f"refusing output {output}: it is a non-empty directory with no {MARKER} file"
        )


def _toml_string(value: str) -> str:
    # JSON's escapes are all valid in a TOML basic string. ensure_ascii would write an
    # astral character as a surrogate pair, which TOML rejects, and JSON leaves DEL raw,
    # which TOML also rejects.
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")


def hugo_config(config: SiteConfig) -> str:
    """The text of a `hugo.toml` that applies `config` and the packaged theme."""
    return (
        f"baseURL = {_toml_string(config.base_url)}\n"
        f"title = {_toml_string(config.title)}\n"
        f"theme = {_toml_string(THEME)}\n"
        "\n"
        "[params]\n"
        f"author = {_toml_string(config.author)}\n"
    )


def _symlinks_in(directory: str | os.PathLike[str], names: list[str]) -> list[str]:
    return [name for name in names if (Path(directory) / name).is_symlink()]


def _assemble_source(
    source: Path, vault: Path, config: SiteConfig, notes: Sequence[PublishedNote]
) -> None:
    (source / "hugo.toml").write_text(hugo_config(config), encoding="utf-8")
    content = source / "content"
    content.mkdir()
    for note in notes:
        destination = content / note.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(note.content)
    shutil.copytree(PACKAGED_THEME, source / "themes" / THEME)
    # Hugo prefers a project layout to the theme's with the same name, and the theme
    # supplies the rest.
    layouts = vault / SITE_DIR / "layouts"
    if layouts.is_dir() and not layouts.is_symlink():
        shutil.copytree(layouts, source / "layouts", ignore=_symlinks_in)


def _run_hugo(hugo: Sequence[str], source: Path, destination: Path) -> None:
    # A HUGO* variable overrides site configuration: HUGO_BASEURL replaces the configured URL.
    env = {k: v for k, v in os.environ.items() if not k.startswith("HUGO")}
    argv = [
        *hugo,
        "--source",
        str(source),
        "--destination",
        str(destination),
        # The default cache lives under the user's home or system temp directory.
        "--cacheDir",
        str(source / ".cache"),
    ]
    try:
        status = subprocess.run(argv, cwd=source, env=env, check=False).returncode
    except OSError as exc:
        raise BuildError(f"cannot run {hugo[0]}: {exc.strerror}") from exc
    if status != 0:
        raise BuildError(f"{hugo[0]} exited with status {status}")


def swap_in(site: Path, output: Path, previous: Path) -> None:
    """Renames `site` to `output`, moving any existing `output` to `previous` first.

    All three paths must share a filesystem. If the second rename fails, `output` is
    restored and the `OSError` propagates.
    """
    # Python has no atomic exchange, so a crash between the renames leaves no output
    # directory. That is safe to retry and never exposes a partial site.
    existed = output.exists()
    if existed:
        output.rename(previous)
    try:
        site.rename(output)
    except OSError:
        if existed:
            previous.rename(output)
        raise


def build_site(vault: Path, output: Path, hugo: Sequence[str] = ("hugo",)) -> None:
    """Replaces `output` with the site built from `vault`, running Hugo as `hugo`.

    On success `output` holds Hugo's output plus the marker file. Raises `BuildError`
    or `ConfigError` on any refusal or failure, with `output` unchanged. A `BuildError`
    for bad notes lists every one with its reason. Writes nothing under `vault`.
    """
    vault = vault.resolve()
    output = output.resolve()
    if not vault.is_dir():
        raise BuildError(f"vault {vault} is not a directory")
    try:
        check_output(vault, output)
        config = load_config(vault)
        selection = select_notes(vault)
        if selection.failures:
            details = "".join(
                f"\n  {failure.path}: {failure.reason}"
                for failure in selection.failures
            )
            raise BuildError(f"cannot build from these notes:{details}")
        # Hugo writes .hugo_build.lock and resources/ into its source, so the source is
        # a temporary directory that keeps them out of the vault and the repo.
        with tempfile.TemporaryDirectory(prefix="mdblog-") as source_name:
            source = Path(source_name)
            _assemble_source(source, vault, config, selection.published)
            output.parent.mkdir(parents=True, exist_ok=True)
            # A sibling shares the output's filesystem, which the renames require.
            with tempfile.TemporaryDirectory(
                prefix=".mdblog-build-", dir=output.parent
            ) as staging_name:
                staging = Path(staging_name)
                # A subdirectory, because mkdtemp's 0700 mode must not reach the output.
                site = staging / "site"
                site.mkdir()
                _run_hugo(hugo, source, site)
                (site / MARKER).write_text(
                    "Generated by mdblog build, which replaces this directory.\n",
                    encoding="utf-8",
                )
                swap_in(site, output, staging / "previous")
    except OSError as exc:
        raise BuildError(f"cannot build into {output}: {exc}") from exc
