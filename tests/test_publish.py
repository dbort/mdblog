import datetime as dt
from collections.abc import Callable
from pathlib import Path

import pytest

from mdblog.publish import (
    BIO_PATH,
    FrontMatterError,
    NoteFailure,
    published_parts,
    read_bio,
    select_notes,
    split_note,
)
from notes import published_text

NOW = dt.datetime(2026, 6, 15, 12, 0, tzinfo=dt.UTC)


def _write(vault: Path, relative: str, data: str | bytes | None = None) -> Path:
    path = vault / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if data is None:
        data = published_text(path.stem.lstrip("."))
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return path


def _published(vault: Path) -> list[str]:
    selection = select_notes(vault, NOW)
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
def test_split_note_finds_the_block(data: bytes, expected: bytes | None) -> None:
    parts = split_note(data)

    assert (parts[0] if parts else None) == expected


@pytest.mark.parametrize(
    ("data", "body"),
    [
        pytest.param(b"---\na: 1\n---\nbody\n", b"body\n", id="lf"),
        pytest.param(b"---\r\na: 1\r\n---\r\nb\r\n\r\n", b"b\r\n\r\n", id="crlf"),
        pytest.param(b"---\na: 1\n---", b"", id="closing-at-end-of-file"),
        pytest.param(b"---\n---\n\n\n  x\n---\ny", b"\n\n  x\n---\ny", id="exact"),
    ],
)
def test_split_note_keeps_the_body_exactly(data: bytes, body: bytes) -> None:
    parts = split_note(data)

    assert parts is not None
    assert parts[1] == body


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
def test_published_parts_finds_only_marked_notes(note: bytes, expected: bool) -> None:
    assert (published_parts(note) is not None) is expected


@pytest.mark.parametrize(
    ("note", "reason"),
    [
        pytest.param(
            b'---\npublish: "true"\n---\n',
            "publish must be true or false, not 'true'",
            id="string",
        ),
        pytest.param(
            b"---\npublish: yes\n---\n",
            "publish must be true or false, not 'yes'",
            id="yes",
        ),
        pytest.param(
            b"---\npublish: 1\n---\n", "publish must be true or false, not 1", id="one"
        ),
        pytest.param(
            b"---\npublish:\n---\n",
            "publish must be true or false, not None",
            id="null",
        ),
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
def test_published_parts_raises_with_the_reason(note: bytes, reason: str) -> None:
    with pytest.raises(FrontMatterError, match=reason):
        published_parts(note)


def test_select_notes_keeps_relative_paths_sorted_and_bodies_verbatim(
    tmp_path: Path,
) -> None:
    deep = published_text("deep").replace("\n", "\r\n") + "# Deep\r\n\r\n"
    _write(tmp_path, "z.md")
    _write(tmp_path, "a/b/deep.md", deep)
    _write(tmp_path, "m.md", "---\npublish: false\n---\n")

    selection = select_notes(tmp_path, NOW)

    assert [note.path.as_posix() for note in selection.published] == [
        "a/b/deep.md",
        "z.md",
    ]
    assert selection.published[0].page.slug == "deep"
    assert selection.published[0].body == b"# Deep\r\n\r\n"


def test_select_notes_takes_a_missing_title_from_the_file_name(tmp_path: Path) -> None:
    _write(tmp_path, "My Note.md", published_text())

    assert select_notes(tmp_path, NOW).published[0].page.title == "My Note"


def test_select_notes_applies_property_rules_only_to_published_notes(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "false.md", "---\npublish: false\nslug: BAD\ntags: 1\n---\n")
    _write(tmp_path, "none.md", "---\ntitle: 1\ndate: soon\n---\n")
    _write(tmp_path, "plain.md", "No front matter.\n")

    assert _published(tmp_path) == []


def test_select_notes_lists_each_reason_for_a_published_note(tmp_path: Path) -> None:
    _write(tmp_path, "bad.md", "---\npublish: true\n---\n")
    _write(tmp_path, "other.md", published_text("other", extra="tags: 1\n"))
    _write(tmp_path, "good.md")

    selection = select_notes(tmp_path, NOW)

    assert [
        (failure.path.as_posix(), failure.reason) for failure in selection.failures
    ] == [
        ("bad.md", "date is required"),
        ("bad.md", "slug is required"),
        ("other.md", "tags must be a string or a list of strings, not 1"),
    ]
    assert [note.path.as_posix() for note in selection.published] == ["good.md"]


def test_select_notes_uses_the_clock_for_future_dates(tmp_path: Path) -> None:
    _write(tmp_path, "today.md", published_text("today", date="2026-06-15"))
    _write(tmp_path, "tomorrow.md", published_text("tomorrow", date="2026-06-16"))

    selection = select_notes(tmp_path, NOW)

    assert [note.page.slug for note in selection.published] == ["today"]
    assert [failure.reason for failure in selection.failures] == [
        "date 2026-06-16 is in the future"
    ]


def test_select_notes_reads_each_date_form_from_note_text(
    tmp_path: Path, local_zone: Callable[[str], None]
) -> None:
    # POSIX counts offsets west of UTC as positive, so this is UTC-5.
    local_zone("XXX5")
    for slug, date in (
        ("day", "2026-06-01"),
        ("offset", "2026-06-01T10:00:00+09:00"),
        ("utc", "2026-06-01T10:00:00Z"),
        ("naive", "2026-06-01T10:00:00"),
    ):
        _write(tmp_path, f"{slug}.md", published_text(slug, date=date))
    _write(tmp_path, "quoted.md", published_text("quoted", date='"2026-06-01"'))

    selection = select_notes(tmp_path, NOW)

    dates = {note.page.slug: note.page.date for note in selection.published}
    assert dates["day"] == dt.date(2026, 6, 1)
    assert not isinstance(dates["day"], dt.datetime)
    assert dates["offset"].isoformat() == "2026-06-01T10:00:00+09:00"
    assert dates["utc"].isoformat() == "2026-06-01T10:00:00+00:00"
    assert dates["naive"].isoformat() == "2026-06-01T10:00:00-05:00"
    assert [failure.reason for failure in selection.failures] == [
        "date must be a YAML date or datetime, not '2026-06-01'"
    ]


def test_select_notes_names_every_note_sharing_a_slug(tmp_path: Path) -> None:
    _write(tmp_path, "a/one.md", published_text("same"))
    _write(tmp_path, "b/two.md", published_text("same"))
    _write(tmp_path, "other.md")

    selection = select_notes(tmp_path, NOW)

    assert [note.page.slug for note in selection.published] == ["other"]
    reason = "slug 'same' is used by more than one note: a/one.md, b/two.md"
    assert [
        (failure.path.as_posix(), failure.reason) for failure in selection.failures
    ] == [("a/one.md", reason), ("b/two.md", reason)]


def test_select_notes_reports_a_shared_slug_beside_other_failures(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "a.md", published_text("same"))
    _write(tmp_path, "b.md", published_text("same", extra="tags: 1\n"))

    selection = select_notes(tmp_path, NOW)

    assert selection.published == ()
    reasons = [failure.reason for failure in selection.failures]
    assert sum("used by more than one note" in reason for reason in reasons) == 2
    assert "tags must be a string or a list of strings, not 1" in reasons


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

    selection = select_notes(tmp_path, NOW)

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

    selection = select_notes(tmp_path, NOW)

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
        selection = select_notes(tmp_path, NOW)
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
        selection = select_notes(tmp_path, NOW)
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


def test_read_bio_returns_the_body_and_ignores_front_matter(tmp_path: Path) -> None:
    _write(tmp_path, "_site/bio.md", "---\npublish: false\na: [\n---\nBIO-TEXT\n")

    assert read_bio(tmp_path) == "BIO-TEXT\n"


def test_read_bio_returns_a_bio_with_no_front_matter_whole(tmp_path: Path) -> None:
    _write(tmp_path, "_site/bio.md", "BIO-TEXT\n---\n")

    assert read_bio(tmp_path) == "BIO-TEXT\n---\n"


def test_read_bio_returns_none_without_a_bio(tmp_path: Path) -> None:
    (tmp_path / "_site").mkdir()

    assert read_bio(tmp_path) is None


def test_read_bio_refuses_a_symbolic_link(tmp_path: Path) -> None:
    outside = _write(tmp_path, "outside.md", "BIO-TEXT\n")
    (tmp_path / "_site").mkdir()
    (tmp_path / BIO_PATH).symlink_to(outside)

    assert read_bio(tmp_path) == NoteFailure(BIO_PATH, "is a symbolic link")


def test_read_bio_refuses_a_body_that_is_not_utf8(tmp_path: Path) -> None:
    _write(tmp_path, "_site/bio.md", b"---\ntitle: x\n---\n\xff\n")

    assert read_bio(tmp_path) == NoteFailure(BIO_PATH, "is not UTF-8")


def test_read_bio_reports_an_unreadable_bio(tmp_path: Path) -> None:
    bio = _write(tmp_path, "_site/bio.md", "BIO-TEXT\n")
    bio.chmod(0o000)
    if _can_read(bio):
        bio.chmod(0o644)
        pytest.skip("this user can read a file with no permissions")

    try:
        failure = read_bio(tmp_path)
    finally:
        bio.chmod(0o644)

    assert isinstance(failure, NoteFailure)
    assert failure.path == BIO_PATH
    assert failure.reason.startswith("cannot read")
