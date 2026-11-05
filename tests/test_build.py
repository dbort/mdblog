import json
import os
import stat
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest

import mdblog
from mdblog.build import (
    MARKER,
    PACKAGED_THEME,
    BuildError,
    build_site,
    check_output,
    hugo_config,
    path_contains,
    swap_in,
)
from mdblog.config import ConfigError, SiteConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_VAULT = REPO_ROOT / "tests" / "fixtures" / "vault"
CONFIG = (
    'base_url = "https://example.test/blog/"\n'
    'title = "The Site Title"\n'
    'author = "The Site Author"\n'
)
PUBLISHED = "---\npublish: true\n---\nPUBLISHED-TEXT\n"
UNPUBLISHED = "---\npublish: false\n---\nUNPUBLISHED-TEXT\n"
# Stands in for Hugo so the build's logic stays covered by `--smoke`: it copies the
# content directory to the destination and records what the build passed it.
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
    "'layouts': sorted(p.name for p in (source / 'layouts').iterdir())"
    " if (source / 'layouts').exists() else [],"
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

    assert (output / "notes" / "published.md").read_text(encoding="utf-8") == PUBLISHED
    assert not (output / "unpublished.md").exists()
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


def test_build_supplies_the_packaged_theme_and_vault_layouts(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    elsewhere = tmp_path / "elsewhere.html"
    elsewhere.write_text("", encoding="utf-8")
    layouts = vault / "_site" / "layouts"
    layouts.mkdir()
    (layouts / "page.html").write_text("", encoding="utf-8")
    (layouts / "linked.html").symlink_to(elsewhere)
    output = tmp_path / "output"

    build_site(vault, output, FAKE_HUGO)

    seen = _seen(output)
    assert seen["theme"] == ["home.html", "list.html", "page.html", "section.html"]
    assert seen["layouts"] == ["page.html"]


def test_build_does_not_follow_symlinked_layouts(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "page.html").write_text("", encoding="utf-8")
    (vault / "_site" / "layouts").symlink_to(elsewhere)
    output = tmp_path / "output"

    build_site(vault, output, FAKE_HUGO)

    assert _seen(output)["layouts"] == []


def test_build_does_not_publish_a_symlinked_note(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text(PUBLISHED, encoding="utf-8")
    (vault / "linked.md").symlink_to(outside)
    output = tmp_path / "output"

    build_site(vault, output, FAKE_HUGO)

    assert not (output / "linked.md").exists()


def test_build_keeps_package_layouts_inside_the_package() -> None:
    assert PACKAGED_THEME.parent == Path(mdblog.__file__).resolve().parent
    for name in ("home.html", "page.html", "section.html"):
        assert (PACKAGED_THEME / "layouts" / name).is_file()


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


@pytest.mark.hugo
def test_unpublished_text_reaches_no_output_file(tmp_path: Path) -> None:
    output = tmp_path / "output"

    build_site(FIXTURE_VAULT, output, ("hugo",))

    files = {name: data for name, data in _snapshot(output).items() if data is not None}
    assert "projects/first-note/index.html" in files
    assert any(b"reached the generated page" in data for data in files.values())
    for needle in (
        b"UNPUBLISHED-MARKED-FALSE",
        b"UNPUBLISHED-NO-PROPERTY",
        b"UNPUBLISHED-NO-FRONT-MATTER",
        b"UNPUBLISHED-SITE-DIRECTORY",
        b"UNPUBLISHED-OBSIDIAN",
        b"UNPUBLISHED-TRASH",
    ):
        assert not [name for name, data in files.items() if needle in data], needle


@pytest.mark.hugo
@pytest.mark.parametrize("change", ["unpublish", "delete"])
def test_a_note_that_stops_publishing_leaves_no_file(
    tmp_path: Path, change: str
) -> None:
    vault = _make_vault(tmp_path)
    note = vault / "notes" / "published.md"
    (vault / "kept.md").write_text("---\npublish: true\n---\nKEPT\n", encoding="utf-8")
    output = tmp_path / "output"
    build_site(vault, output, ("hugo",))
    assert (output / "notes" / "published" / "index.html").is_file()
    assert any(b"PUBLISHED-TEXT" in (d or b"") for d in _snapshot(output).values())

    if change == "unpublish":
        note.write_text("No front matter. PUBLISHED-TEXT\n", encoding="utf-8")
    else:
        note.unlink()
    build_site(vault, output, ("hugo",))

    after = _snapshot(output)
    assert (output / "kept" / "index.html").is_file()
    assert not [name for name in after if "published" in name]
    assert not [name for name, d in after.items() if b"PUBLISHED-TEXT" in (d or b"")]


@pytest.mark.hugo
def test_generated_site_uses_the_configuration(tmp_path: Path) -> None:
    output = tmp_path / "output"

    build_site(_make_vault(tmp_path), output, ("hugo",))

    feed = (output / "index.xml").read_text(encoding="utf-8")
    assert "<link>https://example.test/blog/notes/published/</link>" in feed
    home = (output / "index.html").read_text(encoding="utf-8")
    assert "<title>The Site Title</title>" in home
    assert 'content="The Site Author"' in home
    page = (output / "notes" / "published" / "index.html").read_text(encoding="utf-8")
    assert 'content="The Site Author"' in page


@pytest.mark.hugo
def test_author_reaches_an_overriding_layout(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    layouts = vault / "_site" / "layouts"
    layouts.mkdir()
    (layouts / "page.html").write_text(
        "AUTHOR={{ .Site.Params.author }}", encoding="utf-8"
    )
    output = tmp_path / "output"

    build_site(vault, output, ("hugo",))

    page = (output / "notes" / "published" / "index.html").read_text(encoding="utf-8")
    assert page == "AUTHOR=The Site Author"


@pytest.mark.hugo
def test_vault_layout_replaces_only_the_page_default(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    layouts = vault / "_site" / "layouts"
    layouts.mkdir()
    (layouts / "page.html").write_text("OVERRIDDEN PAGE", encoding="utf-8")
    output = tmp_path / "output"

    build_site(vault, output, ("hugo",))

    page = (output / "notes" / "published" / "index.html").read_text(encoding="utf-8")
    assert page == "OVERRIDDEN PAGE"
    home = (output / "index.html").read_text(encoding="utf-8")
    assert "OVERRIDDEN PAGE" not in home
    assert "<title>The Site Title</title>" in home


@pytest.mark.hugo
def test_a_title_needing_escapes_reaches_the_site(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    (vault / "_site" / "mdblog.toml").write_text(
        'base_url = "https://example.test/"\n'
        "title = 'A \"quoted\" \\ title 🙂'\n"
        'author = "An author"\n',
        encoding="utf-8",
    )
    output = tmp_path / "output"

    build_site(vault, output, ("hugo",))

    home = (output / "index.html").read_text(encoding="utf-8")
    assert "🙂" in home
    assert "quoted" in home


@pytest.mark.hugo
def test_hugo_environment_does_not_change_the_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUGO_BASEURL", "https://wrong.test/")
    output = tmp_path / "output"

    build_site(_make_vault(tmp_path), output, ("hugo",))

    feed = (output / "index.xml").read_text(encoding="utf-8")
    assert "https://example.test/blog/" in feed
    assert "wrong.test" not in feed


@pytest.mark.hugo
def test_hugo_failure_leaves_the_previous_output_byte_for_byte(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    output = tmp_path / "output"
    build_site(vault, output, ("hugo",))
    before = _snapshot(output)
    layouts = vault / "_site" / "layouts"
    layouts.mkdir()
    (layouts / "page.html").write_text("{{ this does not parse", encoding="utf-8")

    with pytest.raises(BuildError, match="hugo exited"):
        build_site(vault, output, ("hugo",))

    assert _snapshot(output) == before
    _assert_no_leftovers(output)


@pytest.mark.hugo
def test_build_writes_nothing_under_the_vault(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    layouts = vault / "_site" / "layouts"
    layouts.mkdir()
    (layouts / "page.html").write_text("{{ .Content }}", encoding="utf-8")
    before = _snapshot(vault)

    build_site(vault, tmp_path / "output", ("hugo",))

    assert _snapshot(vault) == before


@pytest.mark.hugo
def test_build_prints_no_hugo_warning_for_a_tagged_note(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    vault = _make_vault(tmp_path)
    (vault / "tagged.md").write_text(
        "---\npublish: true\ntags: [one]\n---\nTagged\n", encoding="utf-8"
    )

    build_site(vault, tmp_path / "output", ("hugo",))

    captured = capfd.readouterr()
    assert "WARN" not in captured.out + captured.err
