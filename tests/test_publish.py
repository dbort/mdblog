from pathlib import Path

import pytest

from mdblog.publish import (
    FrontMatterError,
    front_matter_block,
    is_published,
    select_notes,
)


def _write(
    vault: Path, relative: str, data: str | bytes = "---\npublish: true\n---\n"
) -> Path:
    path = vault / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return path


def _published(vault: Path) -> list[str]:
    selection = select_notes(vault)
    assert selection.failures == ()
    return [note.path.as_posix() for note in selection.published]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        pytest.param(b"---\na: 1\n---\nbody\n", b"a: 1", id="lf"),
        pytest.param(
            b"---\r\na: 1\r\nb: 2\r\n---\r\nbody\r\n", b"a: 1\nb: 2", id="crlf"
        ),
        pytest.param(b"---\na: 1\n---", b"a: 1", id="closing-at-end-of-file"),
        pytest.param(b"---\n---\n", b"", id="empty"),
        pytest.param(b"", None, id="empty-file"),
        pytest.param(b"body\n", None, id="no-fence"),
        pytest.param(b"---\nno closing line\n", None, id="no-closing"),
        pytest.param(b"---", None, id="only-a-fence"),
        pytest.param(b"\n---\na: 1\n---\n", None, id="not-on-first-line"),
        pytest.param(b"--- \na: 1\n---\n", None, id="opening-not-alone"),
        pytest.param(b"---\na: 1\n--- \n", None, id="closing-not-alone"),
        pytest.param(b"\xff\xfe\n", None, id="binary-body"),
    ],
)
def test_front_matter_block(data: bytes, expected: bytes | None) -> None:
    assert front_matter_block(data) == expected


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        pytest.param(b"---\npublish: true\n---\n", True, id="true"),
        pytest.param(b"---\r\npublish: true\r\n---\r\nbody\r\n", True, id="crlf"),
        pytest.param(b"---\npublish: false\n---\n", False, id="false"),
        pytest.param(b"---\ntitle: x\n---\n", False, id="no-property"),
        pytest.param(b"no front matter\n", False, id="no-front-matter"),
        pytest.param(b"---\npublish: true\n", False, id="no-closing-line"),
        pytest.param(b"---\n---\n", False, id="empty-block"),
        pytest.param(b"---\n# a comment\n---\n", False, id="comment-only-block"),
        pytest.param(b"body in latin-1: \xe9\n", False, id="unpublished-any-encoding"),
    ],
)
def test_is_published(note: bytes, expected: bool) -> None:
    assert is_published(note) is expected


@pytest.mark.parametrize(
    ("note", "reason"),
    [
        pytest.param(b'---\npublish: "true"\n---\n', "publish must be", id="string"),
        pytest.param(b"---\npublish: yes\n---\n", "publish must be", id="yes"),
        pytest.param(b"---\npublish: 1\n---\n", "publish must be", id="one"),
        pytest.param(b"---\npublish:\n---\n", "publish must be", id="null"),
        pytest.param(b"---\na: [\n---\n", "invalid YAML", id="invalid-yaml"),
        pytest.param(b"---\na: 1\na: 2\n---\n", "duplicate key", id="duplicate-key"),
        pytest.param(b"---\n- a\n---\n", "not a mapping", id="sequence"),
        pytest.param(b"---\nplain\n---\n", "not a mapping", id="scalar"),
        pytest.param(b"---\nnull\n---\n", "not a mapping", id="explicit-null"),
        pytest.param(b"---\ntitle: \xff\n---\n", "not UTF-8", id="not-utf-8"),
        pytest.param(b"---\ndate: 2026-13-45\n---\n", "invalid YAML", id="bad-date"),
        pytest.param(
            b"---\npublish: true\n---\n\xff\n", "not UTF-8", id="published-body"
        ),
    ],
)
def test_is_published_raises_with_the_reason(note: bytes, reason: str) -> None:
    with pytest.raises(FrontMatterError, match=reason):
        is_published(note)


def test_select_notes_keeps_relative_paths_sorted_and_bytes_verbatim(
    tmp_path: Path,
) -> None:
    deep = b"---\r\npublish: true\r\nurl: https://example.test\r\n---\r\n# Deep\r\n"
    _write(tmp_path, "z.md")
    _write(tmp_path, "a/b/deep.md", deep)
    _write(tmp_path, "m.md", "---\npublish: false\n---\n")

    selection = select_notes(tmp_path)

    assert [note.path.as_posix() for note in selection.published] == [
        "a/b/deep.md",
        "z.md",
    ]
    assert selection.published[0].content == deep


def test_select_notes_ignores_files_that_are_not_notes(tmp_path: Path) -> None:
    _write(tmp_path, "image.png")
    _write(tmp_path, "note.md.bak")
    (tmp_path / "folder.md").mkdir()

    assert _published(tmp_path) == []


@pytest.mark.parametrize(
    "relative",
    [
        "_site/note.md",
        "_site/deep/note.md",
        ".obsidian/note.md",
        ".trash/note.md",
        "projects/.hidden/note.md",
        ".hidden-note.md",
        "projects/.hidden-note.md",
    ],
)
@pytest.mark.parametrize(
    "data",
    [
        pytest.param("---\npublish: true\n---\n", id="publishable"),
        pytest.param("---\npublish: 1\n---\n", id="would-fail-validation"),
    ],
)
def test_select_notes_neither_selects_nor_validates_excluded_paths(
    tmp_path: Path, relative: str, data: str
) -> None:
    _write(tmp_path, relative, data)

    assert _published(tmp_path) == []


def test_select_notes_excludes_site_only_at_the_vault_root(tmp_path: Path) -> None:
    _write(tmp_path, "projects/_site/note.md")

    assert _published(tmp_path) == ["projects/_site/note.md"]


def test_select_notes_does_not_follow_symbolic_links(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    _write(outside, "linked.md")
    _write(outside, "directory/inner.md")
    vault = tmp_path / "vault"
    _write(vault, "real.md")
    (vault / "file-link.md").symlink_to(outside / "linked.md")
    (vault / "dir-link").symlink_to(outside / "directory")
    (vault / "dir-link.md").symlink_to(outside / "directory")
    (vault / "dangling.md").symlink_to(outside / "missing.md")

    assert _published(vault) == ["real.md"]


def test_select_notes_reports_every_failure_with_its_reason(tmp_path: Path) -> None:
    _write(tmp_path, "good.md")
    _write(tmp_path, "b/typo.md", "---\npublish: yes\n---\n")
    _write(tmp_path, "a/broken.md", "---\na: [\n---\n")

    selection = select_notes(tmp_path)

    assert [note.path.as_posix() for note in selection.published] == ["good.md"]
    assert [failure.path.as_posix() for failure in selection.failures] == [
        "a/broken.md",
        "b/typo.md",
    ]
    assert "invalid YAML" in selection.failures[0].reason
    assert "publish must be" in selection.failures[1].reason


def test_select_notes_names_other_notes_after_a_bad_date(tmp_path: Path) -> None:
    _write(tmp_path, "a-date.md", "---\ndate: 2026-13-45\n---\n")
    _write(tmp_path, "b-typo.md", "---\npublish: yes\n---\n")

    selection = select_notes(tmp_path)

    assert [failure.path.as_posix() for failure in selection.failures] == [
        "a-date.md",
        "b-typo.md",
    ]


def test_select_notes_reports_an_unreadable_note(tmp_path: Path) -> None:
    note = _write(tmp_path, "locked.md")
    note.chmod(0o000)
    if _can_read(note):
        note.chmod(0o644)
        pytest.skip("this user can read a file with no permissions")

    try:
        selection = select_notes(tmp_path)
    finally:
        note.chmod(0o644)

    assert [failure.path for failure in selection.failures] == [Path("locked.md")]
    assert "cannot read" in selection.failures[0].reason


def test_select_notes_reports_an_unreadable_directory(tmp_path: Path) -> None:
    directory = tmp_path / "locked"
    _write(tmp_path, "locked/note.md")
    directory.chmod(0o000)
    if _can_read(directory):
        directory.chmod(0o755)
        pytest.skip("this user can read a directory with no permissions")

    try:
        selection = select_notes(tmp_path)
    finally:
        directory.chmod(0o755)

    assert [failure.path for failure in selection.failures] == [Path("locked")]
    assert "cannot read" in selection.failures[0].reason


def _can_read(path: Path) -> bool:
    try:
        if path.is_dir():
            list(path.iterdir())
        else:
            path.read_bytes()
    except PermissionError:
        return False
    return True
