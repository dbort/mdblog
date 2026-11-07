"""mdblog.build: turns one vault into a Hugo site in an output directory."""

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mdblog.config import SITE_DIR, SiteConfig, load_config
from mdblog.links import Bio, Page, convert_notes
from mdblog.properties import front_matter
from mdblog.publish import NoteFailure, read_bio, select_notes

MARKER = ".mdblog-output"
THEME = "mdblog"
PACKAGED_THEME = Path(__file__).resolve().parent / "theme"
# Every feed holds at most this many of its latest entries.
FEED_LIMIT = 50
# A vault's `_site/` directories that Hugo reads beside the packaged theme's.
SITE_DIRECTORIES = ("layouts", "assets", "static")


class BuildError(Exception):
    """A build was refused or failed; the output directory is unchanged."""


@dataclass(frozen=True)
class Site:
    """Everything a vault contributes to its Hugo source, already validated."""

    config: SiteConfig
    pages: tuple[Page, ...]
    bio: Bio | None


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
    """The text of a `hugo.toml` that applies `config` and the packaged theme.

    The site renders a feed at `/index.xml` and one per tag, and no other feed.
    """
    return (
        f"baseURL = {_toml_string(config.base_url)}\n"
        f"title = {_toml_string(config.title)}\n"
        f"theme = {_toml_string(THEME)}\n"
        "\n"
        "[params]\n"
        f"author = {_toml_string(config.author)}\n"
        "\n"
        # Renders `==text==` as <mark>. Raw HTML stays off, so a note cannot bypass the
        # link rules with an <img> or <a> of its own.
        "[markup.goldmark.extensions.extras.mark]\n"
        "enable = true\n"
        "\n"
        # Naming only `tag` drops Hugo's default `categories` taxonomy.
        "[taxonomies]\n"
        'tag = "tags"\n'
        "\n"
        "[outputs]\n"
        'home = ["html", "rss"]\n'
        'section = ["html"]\n'
        'taxonomy = ["html"]\n'
        'term = ["html", "rss"]\n'
        'page = ["html"]\n'
        "\n"
        # The feed layouts read the limit here, so a site's own feed layout can too.
        "[services.rss]\n"
        f"limit = {FEED_LIMIT}\n"
    )


def _symlinks_in(directory: str | os.PathLike[str], names: list[str]) -> list[str]:
    return [name for name in names if (Path(directory) / name).is_symlink()]


def convert_vault(vault: Path, now: datetime) -> Site:
    """The validated pages, bio and settings of `vault`, with dates compared to `now`.

    Raises `ConfigError` for unusable settings, and otherwise a `BuildError` listing
    every bad note with each of its reasons, including every failed link, and the bio's
    failures in the same message. Writes nothing.
    """
    config = load_config(vault)
    selection = select_notes(vault, now)
    bio = read_bio(vault)
    bio_failures = [bio] if isinstance(bio, NoteFailure) else []
    conversion = convert_notes(
        selection, config.base_url, bio if isinstance(bio, str) else None
    )
    # A stable sort keeps each note's reasons in the order they were found.
    failures = sorted(
        (*selection.failures, *bio_failures, *conversion.failures),
        key=lambda failure: failure.path,
    )
    if failures:
        details = "".join(
            f"\n  {failure.path}: {failure.reason}" for failure in failures
        )
        raise BuildError(f"cannot build from these notes:{details}")
    return Site(config=config, pages=conversion.pages, bio=conversion.bio)


def assemble_source(source: Path, vault: Path, site: Site) -> None:
    """Writes the Hugo source for `site` into the existing, empty directory `source`.

    Copies images and the vault's `_site/` directories from `vault`, skipping symbolic
    links in those directories. Raises `OSError` when a file cannot be read or written.
    """
    (source / "hugo.toml").write_text(hugo_config(site.config), encoding="utf-8")
    content = source / "content"
    content.mkdir()
    for page in site.pages:
        # The folder sets the URL. Writing Hugo's `url` or `slug` would add a second source.
        bundle = content / "posts" / page.note.page.slug
        bundle.mkdir(parents=True)
        (bundle / "index.md").write_bytes(front_matter(page.note.page) + page.body)
        # Hugo publishes a leaf bundle's files next to its page, so each note's images
        # get their own URLs and two notes never compete for one name.
        for image in page.images:
            shutil.copyfile(vault / image, bundle / image.name)
    if site.bio is not None:
        # Hugo renders this file as the home page's `.Content`. The empty front matter
        # keeps a bio that starts with `---` or `{` from being read as front matter.
        (content / "_index.md").write_bytes(b"{}\n" + site.bio.body)
        # The home page's own files, served at its URL, where the converter points them.
        for image in site.bio.images:
            shutil.copyfile(vault / image, content / image.name)
    shutil.copytree(PACKAGED_THEME, source / "themes" / THEME)
    # Hugo prefers a project file to the theme's with the same name, and the theme
    # supplies the rest.
    for name in SITE_DIRECTORIES:
        directory = vault / SITE_DIR / name
        if directory.is_dir() and not directory.is_symlink():
            shutil.copytree(directory, source / name, ignore=_symlinks_in)


def hugo_env() -> dict[str, str]:
    """The process environment without any variable whose name starts with `HUGO`."""
    # A HUGO* variable overrides site configuration: HUGO_BASEURL replaces the configured URL.
    return {k: v for k, v in os.environ.items() if not k.startswith("HUGO")}


def _run_hugo(hugo: Sequence[str], source: Path, destination: Path) -> None:
    argv = [
        *hugo,
        "--source",
        str(source),
        "--destination",
        str(destination),
        # The default cache lives under the user's home or system temp directory.
        "--cacheDir",
        str(source / ".cache"),
        # Hugo compares a date-only value as UTC midnight, which would hide a note dated
        # today at some local times. Validation has already rejected future dates.
        "--buildFuture",
    ]
    try:
        status = subprocess.run(
            argv, cwd=source, env=hugo_env(), check=False
        ).returncode
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


def build_site(
    vault: Path,
    output: Path,
    hugo: Sequence[str] = ("hugo",),
    now: datetime | None = None,
) -> None:
    """Replaces `output` with the site built from `vault`, running Hugo as `hugo`.

    On success `output` holds Hugo's output plus the marker file. Raises `BuildError`
    or `ConfigError` on any refusal or failure, with `output` unchanged. A `BuildError`
    for bad notes lists every one with each of its reasons, including every failed
    link, and lists the bio's failures in the same message. Writes nothing under
    `vault`. `now` is the timezone-aware time that decides which dates are in the
    future, by default the current local time.
    """
    vault = vault.resolve()
    output = output.resolve()
    if not vault.is_dir():
        raise BuildError(f"vault {vault} is not a directory")
    try:
        check_output(vault, output)
        site = convert_vault(vault, now or datetime.now().astimezone())
        # Hugo writes .hugo_build.lock and resources/ into its source, so the source is
        # a temporary directory that keeps them out of the vault and the repo.
        with tempfile.TemporaryDirectory(prefix="mdblog-") as source_name:
            source = Path(source_name)
            assemble_source(source, vault, site)
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
