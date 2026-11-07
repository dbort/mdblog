import datetime as dt
import json
import os
import re
import stat
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from mdblog.build import (
    MARKER,
    BuildError,
    build_site,
    check_output,
    hugo_config,
    path_contains,
    swap_in,
)
from mdblog.config import ConfigError, SiteConfig
from mdblog.markdown import headings
from notes import HEADINGS, published_text

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_VAULT = REPO_ROOT / "tests" / "fixtures" / "vault"
CONFIG = (
    'base_url = "https://example.test/blog/"\n'
    'title = "The Site Title"\n'
    'author = "The Site Author"\n'
)
PUBLISHED = published_text("published", body="PUBLISHED-TEXT\n")
UNPUBLISHED = "---\npublish: false\n---\nUNPUBLISHED-TEXT\n"
# Stands in for Hugo: it copies the content directory to the destination and records
# what the build passed it.
FAKE_HUGO = (
    sys.executable,
    "-c",
    "import json, os, pathlib, shutil, sys;"
    "argv = sys.argv[1:];"
    "source = pathlib.Path(argv[argv.index('--source') + 1]);"
    "destination = pathlib.Path(argv[argv.index('--destination') + 1]);"
    "shutil.copytree(source / 'content', destination, dirs_exist_ok=True);"
    "(destination / 'seen.json').write_text(json.dumps({"
    "'argv': argv, 'cwd': os.getcwd(), 'env': sorted(os.environ),"
    "'config': (source / 'hugo.toml').read_text(),"
    "'theme': sorted(p.name for p in (source / 'themes/mdblog/layouts').iterdir()),"
    "**{name: sorted(p.relative_to(source / name).as_posix()"
    " for p in (source / name).rglob('*'))"
    " for name in ('layouts', 'assets', 'static')},"
    "}))",
)
FAILING_HUGO = (sys.executable, "-c", "raise SystemExit(3)")


def _make_vault(root: Path) -> Path:
    vault = root / "vault"
    (vault / "_site").mkdir(parents=True)
    (vault / "_site" / "mdblog.toml").write_text(CONFIG, encoding="utf-8")
    (vault / "notes").mkdir()
    (vault / "notes" / "published.md").write_text(PUBLISHED, encoding="utf-8")
    (vault / "unpublished.md").write_text(UNPUBLISHED, encoding="utf-8")
    return vault


def _snapshot(root: Path) -> dict[str, bytes | None]:
    """Every path under `root`, mapped to its bytes, or None for a directory or link."""
    return {
        path.relative_to(root).as_posix(): (
            path.read_bytes() if path.is_file(follow_symlinks=False) else None
        )
        for path in sorted(root.rglob("*"))
    }


def _make_previous_output(root: Path) -> Path:
    output = root / "output"
    output.mkdir()
    (output / MARKER).write_text("", encoding="utf-8")
    (output / "stale.html").write_text("stale", encoding="utf-8")
    return output


def _assert_no_leftovers(output: Path) -> None:
    assert sorted(p.name for p in output.parent.iterdir() if ".mdblog" in p.name) == []


def test_build_writes_published_notes_and_the_marker(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    output = tmp_path / "output"

    build_site(vault, output, FAKE_HUGO)

    page = (output / "posts" / "published" / "index.md").read_bytes()
    assert page.endswith(b"}\nPUBLISHED-TEXT\n")
    assert not [name for name in _snapshot(output) if "unpublished" in name]
    assert (output / MARKER).is_file()
    _assert_no_leftovers(output)


def test_build_output_directory_is_not_private(tmp_path: Path) -> None:
    previous = os.umask(0o022)
    try:
        build_site(_make_vault(tmp_path), tmp_path / "output", FAKE_HUGO)
    finally:
        os.umask(previous)

    assert stat.S_IMODE((tmp_path / "output").stat().st_mode) == 0o755


def test_build_creates_missing_parents_of_the_output(tmp_path: Path) -> None:
    output = tmp_path / "a" / "b" / "output"

    build_site(_make_vault(tmp_path), output, FAKE_HUGO)

    assert (output / MARKER).is_file()


def test_build_accepts_an_empty_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()

    build_site(_make_vault(tmp_path), output, FAKE_HUGO)

    assert (output / MARKER).is_file()


def test_build_replaces_a_previous_output(tmp_path: Path) -> None:
    output = _make_previous_output(tmp_path)

    build_site(_make_vault(tmp_path), output, FAKE_HUGO)

    assert not (output / "stale.html").exists()
    assert (output / MARKER).is_file()
    _assert_no_leftovers(output)


def test_build_passes_a_temporary_source_and_a_filtered_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))
    monkeypatch.setattr("tempfile.tempdir", None)
    monkeypatch.setenv("HUGO_BASEURL", "https://wrong.test/")
    monkeypatch.setenv("HUGOxPARAMSxAUTHOR", "wrong")
    monkeypatch.setenv("MDBLOG_KEPT", "kept")
    output = tmp_path / "output"

    build_site(_make_vault(tmp_path), output, FAKE_HUGO)

    seen = _seen(output)
    argv = seen["argv"]
    assert isinstance(argv, list)
    assert Path(str(argv[argv.index("--source") + 1])).is_relative_to(scratch.resolve())
    assert Path(str(argv[argv.index("--cacheDir") + 1])).is_relative_to(
        scratch.resolve()
    )
    destination = Path(str(argv[argv.index("--destination") + 1]))
    assert destination.parent.parent == output.parent.resolve()
    assert Path(str(seen["cwd"])).resolve().is_relative_to(scratch.resolve())
    env = seen["env"]
    assert isinstance(env, list)
    assert "MDBLOG_KEPT" in env
    assert not [name for name in env if str(name).startswith("HUGO")]


def _seen(output: Path) -> dict[str, object]:
    loaded: object = json.loads((output / "seen.json").read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_build_supplies_the_packaged_theme(tmp_path: Path) -> None:
    output = tmp_path / "output"

    build_site(_make_vault(tmp_path), output, FAKE_HUGO)

    assert _seen(output)["theme"] == [
        "404.html",
        "_markup",
        "_partials",
        "baseof.html",
        "home.html",
        "home.rss.xml",
        "page.html",
        "section.html",
        "taxonomy.html",
        "term.html",
        "term.rss.xml",
    ]


@pytest.mark.parametrize("name", ["layouts", "assets", "static"])
def test_build_supplies_a_site_directory_without_symlinks(
    tmp_path: Path, name: str
) -> None:
    vault = _make_vault(tmp_path)
    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_text("", encoding="utf-8")
    directory = vault / "_site" / name
    (directory / "nested").mkdir(parents=True)
    (directory / "nested" / "file.txt").write_text("", encoding="utf-8")
    (directory / "linked.txt").symlink_to(elsewhere)
    output = tmp_path / "output"

    build_site(vault, output, FAKE_HUGO)

    assert _seen(output)[name] == ["nested", "nested/file.txt"]


@pytest.mark.parametrize("name", ["layouts", "assets", "static"])
def test_build_does_not_follow_a_symlinked_site_directory(
    tmp_path: Path, name: str
) -> None:
    vault = _make_vault(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "file.txt").write_text("", encoding="utf-8")
    (vault / "_site" / name).symlink_to(elsewhere)
    output = tmp_path / "output"

    build_site(vault, output, FAKE_HUGO)

    assert _seen(output)[name] == []


def test_build_does_not_publish_a_symlinked_note(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text(published_text("linked"), encoding="utf-8")
    (vault / "linked.md").symlink_to(outside)
    output = tmp_path / "output"

    build_site(vault, output, FAKE_HUGO)

    assert not (output / "posts" / "linked").exists()


def test_build_rejects_a_missing_vault(tmp_path: Path) -> None:
    with pytest.raises(BuildError, match="not a directory"):
        build_site(tmp_path / "missing", tmp_path / "output", FAKE_HUGO)


def test_build_names_every_bad_note_and_leaves_the_output(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    (vault / "typo.md").write_text("---\npublish: yes\n---\n", encoding="utf-8")
    (vault / "notes" / "broken.md").write_text("---\na: [\n---\n", encoding="utf-8")
    output = _make_previous_output(tmp_path)
    before = _snapshot(output)

    with pytest.raises(BuildError) as exc:
        build_site(vault, output, FAKE_HUGO)

    assert "typo.md: publish must be" in str(exc.value)
    assert "broken.md: front matter is invalid YAML" in str(exc.value)
    assert _snapshot(output) == before


def test_build_reports_property_failures_and_leaves_the_output(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    (vault / "no-date.md").write_text(
        "---\npublish: true\nslug: no-date\n---\n", encoding="utf-8"
    )
    (vault / "twin-one.md").write_text(published_text("twin"), encoding="utf-8")
    (vault / "twin-two.md").write_text(published_text("twin"), encoding="utf-8")
    output = _make_previous_output(tmp_path)
    before = _snapshot(output)

    with pytest.raises(BuildError) as exc:
        build_site(vault, output, FAKE_HUGO)

    assert "no-date.md: date is required" in str(exc.value)
    assert "twin-one.md: slug 'twin'" in str(exc.value)
    assert "twin-two.md: slug 'twin'" in str(exc.value)
    assert _snapshot(output) == before


def test_build_writes_the_bio_as_home_content_with_its_images(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    (vault / "photo.png").write_bytes(b"PHOTO")
    (vault / "_site" / "bio.md").write_text(
        "---\npublish: false\n---\nBIO-TEXT [[published]] ![[photo.png]]\n",
        encoding="utf-8",
    )
    output = tmp_path / "output"

    build_site(vault, output, FAKE_HUGO)

    assert (output / "_index.md").read_text(encoding="utf-8") == (
        "{}\nBIO-TEXT [published](/blog/posts/published/)"
        " ![photo\\.png](/blog/photo.png)\n"
    )
    assert (output / "photo.png").read_bytes() == b"PHOTO"


def test_build_without_a_bio_writes_no_home_content(tmp_path: Path) -> None:
    output = tmp_path / "output"

    build_site(_make_vault(tmp_path), output, FAKE_HUGO)

    assert not (output / "_index.md").exists()


def test_build_reports_bio_failures_with_note_failures(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    (vault / "_site" / "bio.md").write_text(
        "[[missing]] [[unpublished]]\n", encoding="utf-8"
    )
    (vault / "typo.md").write_text("---\npublish: yes\n---\n", encoding="utf-8")
    output = _make_previous_output(tmp_path)
    before = _snapshot(output)

    with pytest.raises(BuildError) as exc:
        build_site(vault, output, FAKE_HUGO)

    message = str(exc.value)
    assert "_site/bio.md: [[missing]]: matches no note or file" in message
    assert "_site/bio.md: [[unpublished]]: unpublished.md is not published" in message
    assert "typo.md: publish must be" in message
    assert _snapshot(output) == before


def test_build_refuses_a_symlinked_bio_with_note_failures(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    outside = tmp_path / "bio.md"
    outside.write_text("BIO-TEXT\n", encoding="utf-8")
    (vault / "_site" / "bio.md").symlink_to(outside)
    (vault / "typo.md").write_text("---\npublish: yes\n---\n", encoding="utf-8")
    output = _make_previous_output(tmp_path)
    before = _snapshot(output)

    with pytest.raises(BuildError) as exc:
        build_site(vault, output, FAKE_HUGO)

    assert "_site/bio.md: is a symbolic link" in str(exc.value)
    assert "typo.md: publish must be" in str(exc.value)
    assert _snapshot(output) == before


def _site_files(output: Path) -> dict[str, bytes | None]:
    # seen.json records the temporary paths of one run.
    return {k: v for k, v in _snapshot(output).items() if k != "seen.json"}


def test_a_notes_folder_and_file_name_do_not_change_the_site(tmp_path: Path) -> None:
    text = published_text("a-note", extra="title: A title\n", body="Body\n")
    vault = _make_vault(tmp_path)
    note = vault / "notes" / "before.md"
    note.write_text(text, encoding="utf-8")
    first = tmp_path / "first"
    build_site(vault, first, FAKE_HUGO)

    (vault / "elsewhere" / "deep").mkdir(parents=True)
    note.rename(vault / "elsewhere" / "deep" / "after.md")
    second = tmp_path / "second"
    build_site(vault, second, FAKE_HUGO)

    assert (first / "posts" / "a-note" / "index.md").is_file()
    assert _site_files(first) == _site_files(second)


def test_properties_hugo_would_read_do_not_change_the_site(tmp_path: Path) -> None:
    plain = _make_vault(tmp_path / "plain")
    (plain / "note.md").write_text(
        published_text("a-note", extra="title: A title\n", body="Body\n"),
        encoding="utf-8",
    )
    colliding = _make_vault(tmp_path / "colliding")
    (colliding / "note.md").write_text(
        published_text(
            "a-note",
            extra=(
                "title: A title\n"
                "aliases: [/old/]\n"
                "url: https://clipped.test/source\n"
                "weight: -5\n"
                "published: 2099-01-01\n"
                "expiryDate: 2000-01-01\n"
                "headless: true\n"
                "build: {render: never, list: never}\n"
                "layout: other\n"
                "type: other\n"
                "draft: true\n"
                "cascade: {params: {author: other}}\n"
                "outputs: [json]\n"
            ),
            body="Body\n",
        ),
        encoding="utf-8",
    )

    build_site(plain, tmp_path / "plain-site", FAKE_HUGO)
    build_site(colliding, tmp_path / "colliding-site", FAKE_HUGO)

    assert (tmp_path / "plain-site" / "posts" / "a-note" / "index.md").is_file()
    assert _site_files(tmp_path / "plain-site") == _site_files(
        tmp_path / "colliding-site"
    )


def test_a_notes_body_reaches_hugo_byte_for_byte(tmp_path: Path) -> None:
    body = b"\n\n---\n  {{ text }}\r\n\xc3\xa9\r\n\n"
    vault = _make_vault(tmp_path)
    (vault / "note.md").write_bytes(published_text("a-note").encode() + body)
    output = tmp_path / "output"

    build_site(vault, output, FAKE_HUGO)

    assert (
        (output / "posts" / "a-note" / "index.md").read_bytes().endswith(b"}\n" + body)
    )


def test_build_judges_dates_by_the_local_clock(
    tmp_path: Path, local_zone: Callable[[str], None]
) -> None:
    # These zones are 26 hours apart, so they are never on the same date.
    ahead = dt.timezone(dt.timedelta(hours=14))
    today_ahead = dt.datetime.now(ahead).date().isoformat()
    vault = _make_vault(tmp_path)
    (vault / "dated.md").write_text(
        published_text("dated", date=today_ahead), encoding="utf-8"
    )
    output = tmp_path / "output"

    # POSIX counts offsets west of UTC as positive, so XXX-14 is UTC+14.
    local_zone("XXX-14")
    build_site(vault, output, FAKE_HUGO)
    assert (output / "posts" / "dated" / "index.md").is_file()

    local_zone("XXX12")
    with pytest.raises(BuildError, match="is in the future"):
        build_site(vault, output, FAKE_HUGO)


def test_build_leaves_the_output_on_a_bad_config(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    (vault / "_site" / "mdblog.toml").write_text("not toml", encoding="utf-8")
    output = _make_previous_output(tmp_path)
    before = _snapshot(output)

    with pytest.raises(ConfigError, match=r"mdblog\.toml"):
        build_site(vault, output, FAKE_HUGO)

    assert _snapshot(output) == before


def test_build_leaves_the_output_when_hugo_fails(tmp_path: Path) -> None:
    output = _make_previous_output(tmp_path)
    before = _snapshot(output)

    with pytest.raises(BuildError, match="status 3"):
        build_site(_make_vault(tmp_path), output, FAILING_HUGO)

    assert _snapshot(output) == before
    _assert_no_leftovers(output)


def test_build_names_a_hugo_it_cannot_start(tmp_path: Path) -> None:
    output = _make_previous_output(tmp_path)
    before = _snapshot(output)

    with pytest.raises(BuildError, match="mdblog-no-such-hugo"):
        build_site(_make_vault(tmp_path), output, ("mdblog-no-such-hugo",))

    assert _snapshot(output) == before
    _assert_no_leftovers(output)


def test_check_output_accepts_missing_empty_and_marked(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()

    check_output(vault, tmp_path / "missing")
    check_output(vault, empty)
    check_output(vault, _make_previous_output(tmp_path))


def _output_is_file(root: Path, _vault: Path) -> Path:
    path = root / "file"
    path.write_text("", encoding="utf-8")
    return path


def _output_is_unmarked(root: Path, _vault: Path) -> Path:
    path = root / "unmarked"
    path.mkdir()
    (path / "precious.txt").write_text("", encoding="utf-8")
    return path


def _output_marker_is_directory(root: Path, _vault: Path) -> Path:
    path = root / "marker-directory"
    (path / MARKER).mkdir(parents=True)
    return path


def _output_is_vault(_root: Path, vault: Path) -> Path:
    return vault


def _output_inside_vault(_root: Path, vault: Path) -> Path:
    return vault / "public"


def _marked_output_inside_vault(_root: Path, vault: Path) -> Path:
    path = vault / "public"
    path.mkdir()
    (path / MARKER).write_text("", encoding="utf-8")
    return path


def _output_contains_vault(root: Path, _vault: Path) -> Path:
    return root


def _marked_output_contains_vault(root: Path, _vault: Path) -> Path:
    (root / MARKER).write_text("", encoding="utf-8")
    return root


def _symlink_to_vault(root: Path, vault: Path) -> Path:
    path = root / "link"
    path.symlink_to(vault)
    return path


def _dotted_path_to_vault(root: Path, _vault: Path) -> Path:
    return root / "other" / ".." / "vault"


@pytest.mark.parametrize(
    "make_output",
    [
        _output_is_file,
        _output_is_unmarked,
        _output_marker_is_directory,
        _output_is_vault,
        _output_inside_vault,
        _marked_output_inside_vault,
        _output_contains_vault,
        _marked_output_contains_vault,
        _symlink_to_vault,
        _dotted_path_to_vault,
    ],
)
def test_build_refuses_a_dangerous_output_and_changes_nothing(
    tmp_path: Path, make_output: Callable[[Path, Path], Path]
) -> None:
    vault = _make_vault(tmp_path)
    output = make_output(tmp_path, vault)
    before = _snapshot(tmp_path)

    with pytest.raises(BuildError, match="refusing output"):
        build_site(vault, output, FAKE_HUGO)

    assert _snapshot(tmp_path) == before


def test_path_contains_compares_existing_directories_by_identity(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "alias").symlink_to(real)

    assert path_contains(real, tmp_path / "alias" / "new" / "output")
    assert not path_contains(real, tmp_path / "other" / "output")
    assert not path_contains(tmp_path / "missing", real)


def test_swap_in_restores_the_output_when_the_second_rename_fails(
    tmp_path: Path,
) -> None:
    output = _make_previous_output(tmp_path)
    before = _snapshot(output)

    with pytest.raises(OSError):
        swap_in(tmp_path / "missing-site", output, tmp_path / "previous")

    assert _snapshot(output) == before


@pytest.mark.parametrize(
    "value",
    [
        'quote " and backslash \\',
        "line\nbreak\ttab",
        "accent é and emoji 🙂",
        "delete \x7f and control \x01",
    ],
)
def test_hugo_config_round_trips_any_string(value: str) -> None:
    config = SiteConfig(base_url=value, title=value, author=value)

    table = tomllib.loads(hugo_config(config))

    assert table["baseURL"] == value
    assert table["title"] == value
    assert table["theme"] == "mdblog"
    assert table["params"] == {"author": value}


@pytest.mark.parametrize("change", ["unpublish", "delete"])
def test_a_note_that_stops_publishing_leaves_no_file(
    tmp_path: Path, change: str
) -> None:
    vault = _make_vault(tmp_path)
    note = vault / "notes" / "published.md"
    (vault / "kept.md").write_text(published_text("kept"), encoding="utf-8")
    output = tmp_path / "output"
    build_site(vault, output, FAKE_HUGO)
    assert (output / "posts" / "published" / "index.md").is_file()

    if change == "unpublish":
        note.write_text("No front matter. PUBLISHED-TEXT\n", encoding="utf-8")
    else:
        note.unlink()
    build_site(vault, output, FAKE_HUGO)

    after = _snapshot(output)
    assert (output / "posts" / "kept" / "index.md").is_file()
    assert not [name for name in after if "published" in name]
    assert not [name for name, d in after.items() if b"PUBLISHED-TEXT" in (d or b"")]


def test_generated_site_uses_the_configuration(tmp_path: Path) -> None:
    output = tmp_path / "output"

    build_site(_make_vault(tmp_path), output, ("hugo",))

    feed = (output / "index.xml").read_text(encoding="utf-8")
    assert "<link>https://example.test/blog/posts/published/</link>" in feed
    home = (output / "index.html").read_text(encoding="utf-8")
    assert "<title>The Site Title</title>" in home
    assert 'content="The Site Author"' in home
    page = (output / "posts" / "published" / "index.html").read_text(encoding="utf-8")
    assert 'content="The Site Author"' in page


def test_a_vault_without_a_bio_builds_a_home_page_without_one(tmp_path: Path) -> None:
    output = tmp_path / "output"

    build_site(_make_vault(tmp_path), output, ("hugo",))

    home = (output / "index.html").read_text(encoding="utf-8")
    assert 'class="h-feed' in home
    assert 'class="bio"' not in home
    assert 'name="description"' not in home


def test_vault_layout_replaces_only_the_page_default(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    layouts = vault / "_site" / "layouts"
    layouts.mkdir()
    (layouts / "page.html").write_text(
        "OVERRIDDEN PAGE {{ .Title }}",
        encoding="utf-8",
    )
    (vault / "other.md").write_text(
        published_text("other", extra="title: Another title\n"), encoding="utf-8"
    )
    output = tmp_path / "output"

    build_site(vault, output, ("hugo",))

    page = (output / "posts" / "other" / "index.html").read_text(encoding="utf-8")
    assert page == "OVERRIDDEN PAGE Another title"
    home = (output / "index.html").read_text(encoding="utf-8")
    assert "OVERRIDDEN PAGE" not in home
    assert "<title>The Site Title</title>" in home


def test_build_writes_nothing_under_the_vault(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    layouts = vault / "_site" / "layouts"
    layouts.mkdir()
    (layouts / "page.html").write_text("{{ .Content }}", encoding="utf-8")
    before = _snapshot(vault)

    build_site(vault, tmp_path / "output", FAKE_HUGO)

    assert _snapshot(vault) == before


def test_a_note_dated_today_builds_while_that_date_is_ahead_of_utc(
    tmp_path: Path,
) -> None:
    # A clock a day ahead of the real one stands for a zone already on the next date:
    # validation accepts the date, while Hugo's clock still has it in the future.
    tomorrow = dt.datetime.now(dt.UTC) + dt.timedelta(days=1)
    vault = _make_vault(tmp_path)
    (vault / "today.md").write_text(
        published_text("today", date=tomorrow.date().isoformat(), body="TODAY-TEXT\n"),
        encoding="utf-8",
    )
    output = tmp_path / "output"

    build_site(vault, output, ("hugo",), now=tomorrow)

    page = (output / "posts" / "today" / "index.html").read_text(encoding="utf-8")
    assert "TODAY-TEXT" in page


def test_accepted_tags_write_only_under_the_tags_section(tmp_path: Path) -> None:
    # Hugo decides a tag's path, so a rule change there would silently move these pages.
    tags = ["c++", "node.js", ".net", "a..b", "日本語/カナ", "a_b-c", "project/alpha"]
    plain = _make_vault(tmp_path / "plain")
    tagged = _make_vault(tmp_path / "tagged")
    (tagged / "notes" / "published.md").write_text(
        published_text(
            "published", extra=f"tags: {json.dumps(tags)}\n", body="PUBLISHED-TEXT\n"
        ),
        encoding="utf-8",
    )

    build_site(plain, tmp_path / "plain-site", ("hugo",))
    build_site(tagged, tmp_path / "tagged-site", ("hugo",))

    def outside_tags(site: Path) -> set[str]:
        ignored = ("tags/", "sitemap.xml")
        return {name for name in _snapshot(site) if not name.startswith(ignored)}

    assert outside_tags(tmp_path / "tagged-site") == outside_tags(
        tmp_path / "plain-site"
    )
    for tag in tags:
        page = tmp_path / "tagged-site" / "tags" / tag / "index.html"
        assert page.is_file(), tag


def _set_base_url(vault: Path, base_url: str) -> None:
    config = CONFIG.replace("https://example.test/blog/", base_url)
    (vault / "_site" / "mdblog.toml").write_text(config, encoding="utf-8")


def _page_html(output: Path, slug: str) -> str:
    return (output / "posts" / slug / "index.html").read_text(encoding="utf-8")


def _entry_body(output: Path, slug: str) -> str:
    """The rendered body of an entry page, without the layout's navigation."""
    page = _page_html(output, slug)
    match = re.search(
        r'<div class="e-content[^"]*">(.*?)</div>\s*</article>', page, re.S
    )
    assert match is not None
    return match[1]


ANCHOR_TARGET = published_text(
    "target",
    body="# Café & Über: 100%!\n## Same\n## Same\n## C++ and `code` stuff\n",
)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://example.test/blog/",
        "https://example.test/blog",
        "https://example.test/",
    ],
)
def test_generated_links_reach_their_targets_in_hugos_output(
    tmp_path: Path, base_url: str
) -> None:
    vault = _make_vault(tmp_path)
    _set_base_url(vault, base_url)
    (vault / "target.md").write_text(ANCHOR_TARGET, encoding="utf-8")
    (vault / "my pic.png").write_bytes(b"PNG")
    (vault / "source.md").write_text(
        published_text(
            "source",
            body=(
                "[[target]] [[target#Café & Über: 100%!]] [[target#Same]]\n"
                "[[target#C++ and code stuff]] ![[my pic.png|40]] [[my pic.png]]\n"
            ),
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output"

    build_site(vault, output, ("hugo",))

    target = _page_html(output, "target")
    for anchor in ("café--über-100", "same", "same-1", "c-and-code-stuff"):
        assert f'id="{anchor}"' in target
    prefix = urlsplit(base_url).path.rstrip("/")
    urls = re.findall(r'(?:href|src)="([^"]*)"', _entry_body(output, "source"))
    reached: list[str] = []
    for url in urls:
        assert url.startswith(f"{prefix}/posts/"), url
        parts = urlsplit(url)
        path = output / unquote(parts.path).removeprefix(prefix).lstrip("/")
        file = path / "index.html" if path.is_dir() else path
        assert file.is_file(), url
        if parts.fragment:
            assert f'id="{unquote(parts.fragment)}"' in file.read_text(encoding="utf-8")
        reached.append(
            f"{file.relative_to(output).as_posix()}#{unquote(parts.fragment)}"
        )
    assert reached == [
        "posts/target/index.html#",
        "posts/target/index.html#café--über-100",
        "posts/target/index.html#same",
        "posts/target/index.html#c-and-code-stuff",
        "posts/source/my pic.png#",
        "posts/source/my pic.png#",
    ]


def test_default_render_hooks_and_extensions(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    (vault / "a.png").write_bytes(b"PNG")
    (vault / "hooks.md").write_text(
        published_text(
            "hooks",
            body=(
                "> [!note]\n> Note body\n\n"
                "> [!warning] Careful *now*\n> Warning body\n\n"
                "> [!faq]- Folded\n> Closed body\n\n"
                "> [!tip]+\n> Open body\n\n"
                "> A plain quote\n\n"
                "Some ==highlighted== text with #inline-tag.\n\n"
                "![[a.png|300x200]] ![[a.png|40]] ![[a.png|alt words]] ![[a.png]]\n\n"
                '<img src="draft.png">\n\n'
                'Inline <img src="inline-draft.png"> HTML.\n'
            ),
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output"

    build_site(vault, output, ("hugo",))

    page = _page_html(output, "hooks")
    assert (
        '<div class="callout callout-note">\n<p class="callout-title">Note</p>' in page
    )
    assert '<p class="callout-title">Careful <em>now</em></p>' in page
    assert (
        '<details class="callout callout-faq">\n<summary class="callout-title">Folded'
        in page
    )
    assert (
        '<details class="callout callout-tip" open>\n<summary class="callout-title">Tip'
        in page
    )
    assert "<blockquote>\n<p>A plain quote</p>\n</blockquote>" in page
    assert "<mark>highlighted</mark>" in page
    assert "#inline-tag" in page
    assert not (output / "tags" / "inline-tag").exists()
    src = "/blog/posts/hooks/a.png"
    assert f'<img src="{src}" alt="a.png" width="300" height="200">' in page
    assert f'<img src="{src}" alt="a.png" width="40"> ' in page
    assert f'<img src="{src}" alt="alt words"> ' in page
    assert f'<img src="{src}" alt="a.png"></p>' in page
    assert "draft.png" not in page


def test_a_site_overrides_a_default_markup_layout(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    markup = vault / "_site" / "layouts" / "_markup"
    markup.mkdir(parents=True)
    (markup / "render-image.html").write_text(
        "SITE-IMAGE {{ .Destination }}", encoding="utf-8"
    )
    (vault / "a.png").write_bytes(b"PNG")
    (vault / "note.md").write_text(
        published_text("note", body="![[a.png]]\n\n> [!note]\n> Body\n"),
        encoding="utf-8",
    )
    output = tmp_path / "output"

    build_site(vault, output, ("hugo",))

    page = _page_html(output, "note")
    assert "SITE-IMAGE /blog/posts/note/a.png" in page
    assert '<div class="callout callout-note">' in page


def test_only_images_that_published_notes_use_are_copied(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    for name in ("shared.png", "unused.png", "draft-only.png", "commented.png"):
        (vault / name).write_bytes(name.encode())
    (vault / "one.md").write_text(
        published_text("one", body="![[shared.png]] %%![[commented.png]]%%\n"),
        encoding="utf-8",
    )
    (vault / "two.md").write_text(
        published_text("two", body="[[shared.png]]\n"), encoding="utf-8"
    )
    (vault / "draft.md").write_text(
        "---\npublish: false\n---\n![[draft-only.png]]\n", encoding="utf-8"
    )
    output = tmp_path / "output"

    build_site(vault, output, FAKE_HUGO)

    images = sorted(name for name in _snapshot(output) if name.endswith(".png"))
    assert images == ["posts/one/shared.png", "posts/two/shared.png"]
    assert (output / "posts" / "one" / "shared.png").read_bytes() == b"shared.png"


def test_links_to_unpublished_material_fail_and_leak_nothing(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    (vault / "draft.md").write_text(
        "---\npublish: false\n---\nDRAFT-TEXT ![[draft.png]]\n", encoding="utf-8"
    )
    (vault / "draft.png").write_bytes(b"DRAFT-IMAGE")
    (vault / ".private").mkdir()
    (vault / ".private" / "secret.png").write_bytes(b"SECRET-IMAGE")
    (vault / "linking.md").write_text(
        published_text(
            "linking", body="[[draft]] ![[draft]] ![[.private/secret.png]]\n"
        ),
        encoding="utf-8",
    )
    (vault / "typo.md").write_text("---\npublish: yes\n---\n", encoding="utf-8")
    output = _make_previous_output(tmp_path)
    before = _snapshot(output)

    with pytest.raises(BuildError) as exc:
        build_site(vault, output, FAKE_HUGO)

    message = str(exc.value)
    assert "linking.md: [[draft]]: draft.md is not published" in message
    assert "linking.md: ![[draft]]: draft.md is not published" in message
    assert "linking.md: ![[.private/secret.png]]: targets a path under" in message
    assert "typo.md: publish must be true or false" in message
    assert _snapshot(output) == before
    for needle in (b"DRAFT-TEXT", b"DRAFT-IMAGE", b"SECRET-IMAGE"):
        assert not [
            name for name, data in _snapshot(output).items() if needle in (data or b"")
        ]


def test_heading_ids_match_hugos(tmp_path: Path) -> None:
    # A wrong ID sends a link nowhere without any error, so every rule is compared.
    vault = _make_vault(tmp_path)
    (vault / "images").mkdir()
    (vault / "images" / "a.png").write_bytes(b"PNG")
    (vault / "target.md").write_text(
        published_text("target", body=HEADINGS), encoding="utf-8"
    )
    (vault / "_draft notes_.md").write_text(
        published_text("draft-notes"), encoding="utf-8"
    )
    output = tmp_path / "output"

    build_site(vault, output, ("hugo",))

    page = _page_html(output, "target")
    hugo_ids = re.findall(r'<h[1-6][^>]*\bid="([^"]*)"', page)
    assert hugo_ids == [heading.anchor for heading in headings(HEADINGS)]
