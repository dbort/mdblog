import datetime as dt
import os
from collections.abc import Callable
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from mdblog.properties import EntryStatus, PageProperties
from mdblog.publish import (
    BIO_PATH,
    FrontMatterError,
    NoteFailure,
    PublishedNote,
    SlugClaim,
    assign_slugs,
    marked_parts,
    published_parts,
    read_bio,
    select_notes,
    split_note,
)
from notes import published_text

REPO_ROOT = Path(__file__).resolve().parent.parent
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


def _claim(path: str, own: str | None = None, published: bool = False) -> SlugClaim:
    return SlugClaim(Path(path), own, published)


def _assigned(*claims: SlugClaim) -> dict[str, tuple[str, str | None]]:
    return {path.as_posix(): result for path, result in assign_slugs(claims).items()}


def test_assign_slugs_keeps_own_slugs_and_generates_the_rest() -> None:
    assert _assigned(
        _claim("a/My Draft.md"), _claim("b.md", "own"), _claim("日本語.md")
    ) == {
        "a/My Draft.md": ("my-draft", None),
        "b.md": ("own", None),
        "日本語.md": ("note", None),
    }


def test_an_own_slug_wins_over_an_earlier_generated_one() -> None:
    assert _assigned(_claim("a/same.md"), _claim("b.md", "same")) == {
        "a/same.md": ("same-2", "slug 'same' is already used by b.md; using 'same-2'"),
        "b.md": ("same", None),
    }


def test_generated_slugs_take_suffixes_in_path_order() -> None:
    assert _assigned(_claim("b/Same.md"), _claim("a/same.md"), _claim("c/SAME.md")) == {
        "a/same.md": ("same", None),
        "b/Same.md": (
            "same-2",
            "slug 'same' is already used by a/same.md; using 'same-2'",
        ),
        "c/SAME.md": (
            "same-3",
            "slug 'same' is already used by a/same.md; using 'same-3'",
        ),
    }


def test_a_suffix_skips_slugs_that_notes_own() -> None:
    assert _assigned(_claim("a/x.md"), _claim("b.md", "x"), _claim("c.md", "x-2")) == {
        "a/x.md": ("x-3", "slug 'x' is already used by b.md; using 'x-3'"),
        "b.md": ("x", None),
        "c.md": ("x-2", None),
    }


def test_the_first_published_note_by_path_keeps_a_shared_own_slug() -> None:
    assert _assigned(
        _claim("b.md", "same", published=True),
        _claim("a.md", "same", published=True),
    ) == {
        "a.md": ("same", None),
        "b.md": ("same-2", "slug 'same' is already used by a.md; using 'same-2'"),
    }


def test_a_published_note_keeps_its_own_slug_over_an_earlier_draft() -> None:
    assert _assigned(
        _claim("a.md", "same"), _claim("b.md", "same", published=True)
    ) == {
        "a.md": ("same-2", "slug 'same' is already used by b.md; using 'same-2'"),
        "b.md": ("same", None),
    }


# Five hours west of UTC, matching the TZ string the draft tests set.
LOCAL = dt.timezone(dt.timedelta(hours=-5))
MODIFIED = dt.datetime(2026, 3, 4, 5, 6, 7, tzinfo=LOCAL)


@pytest.fixture
def _local(local_zone: Callable[[str], None]) -> None:
    local_zone("XXX5")


def _draft_note(vault: Path, relative: str, text: str) -> Path:
    path = _write(vault, relative, text)
    os.utime(path, (MODIFIED.timestamp(), MODIFIED.timestamp()))
    return path


def _preview(vault: Path) -> tuple[dict[str, PublishedNote], list[tuple[str, str]]]:
    selection = select_notes(vault, NOW, drafts=True)
    entries = {note.path.as_posix(): note for note in selection.published}
    assert list(entries) == sorted(entries)
    warnings = [
        (failure.path.as_posix(), failure.reason) for failure in selection.failures
    ]
    return entries, warnings


@pytest.mark.usefixtures("_local")
def test_a_draft_falls_back_to_its_modification_time_in_the_site_zone(
    tmp_path: Path,
) -> None:
    _draft_note(tmp_path, "draft.md", "---\npublish: false\n---\nBODY\n")

    selection = select_notes(tmp_path, NOW, drafts=True, zone=ZoneInfo("Asia/Tokyo"))

    (entry,) = selection.published
    assert entry.page.date == MODIFIED
    assert entry.page.date.isoformat() == "2026-03-04T19:06:07+09:00"


@pytest.mark.usefixtures("_local")
def test_drafts_are_publish_false_notes_with_file_fallbacks(tmp_path: Path) -> None:
    _draft_note(tmp_path, "notes/My Draft.md", "---\npublish: false\n---\nBODY\n")
    _write(tmp_path, "no-property.md", "---\ntitle: x\nslug: x\n---\n")
    _write(tmp_path, "no-front-matter.md", "text\n")

    entries, warnings = _preview(tmp_path)

    assert entries == {
        "notes/My Draft.md": PublishedNote(
            Path("notes/My Draft.md"),
            PageProperties("My Draft", MODIFIED, "my-draft", ()),
            b"BODY\n",
            EntryStatus.DRAFT,
        )
    }
    date = entries["notes/My Draft.md"].page.date
    assert isinstance(date, dt.datetime)
    assert date.utcoffset() == dt.timedelta(hours=-5)
    assert warnings == []
    assert select_notes(tmp_path, NOW).published == ()


@pytest.mark.usefixtures("_local")
def test_a_draft_keeps_its_own_properties_and_a_future_date(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "draft.md",
        "---\npublish: false\ntitle: Later\ndate: 2027-01-01\nslug: later\n"
        "tags: [a]\n---\n",
    )

    entries, warnings = _preview(tmp_path)

    assert entries["draft.md"].page == PageProperties(
        "Later", dt.date(2027, 1, 1), "later", ("a",)
    )
    assert warnings == []


@pytest.mark.usefixtures("_local")
def test_invalid_draft_properties_warn_and_fall_back(tmp_path: Path) -> None:
    _draft_note(
        tmp_path,
        "Bad Draft.md",
        "---\npublish: false\ndate: soon\nslug: Bad Slug\ntags: 3\n---\n",
    )

    entries, warnings = _preview(tmp_path)

    assert entries["Bad Draft.md"].page == PageProperties(
        "Bad Draft", MODIFIED, "bad-draft", ()
    )
    assert entries["Bad Draft.md"].status is EntryStatus.DRAFT
    assert warnings == [
        ("Bad Draft.md", "date must be a YAML date or datetime, not 'soon'"),
        (
            "Bad Draft.md",
            "slug must be lowercase letters and digits joined by single hyphens, "
            "not 'Bad Slug'",
        ),
        ("Bad Draft.md", "tags must be a string or a list of strings, not 3"),
    ]


@pytest.mark.usefixtures("_local")
def test_a_failing_published_note_renders_as_invalid_with_each_reason(
    tmp_path: Path,
) -> None:
    _draft_note(tmp_path, "Broken.md", "---\npublish: true\ntags: 3\n---\n")
    _write(tmp_path, "future.md", published_text("future", date="2027-01-01"))
    _write(tmp_path, "good.md", published_text("good"))

    entries, warnings = _preview(tmp_path)

    assert entries["Broken.md"].page == PageProperties("Broken", MODIFIED, "broken", ())
    assert entries["future.md"].page.date == dt.date(2027, 1, 1)
    assert {path: note.status for path, note in entries.items()} == {
        "Broken.md": EntryStatus.INVALID,
        "future.md": EntryStatus.INVALID,
        "good.md": EntryStatus.PUBLISHED,
    }
    assert warnings == [
        ("Broken.md", "date is required"),
        ("Broken.md", "slug is required"),
        ("Broken.md", "tags must be a string or a list of strings, not 3"),
        ("future.md", "date 2027-01-01 is in the future"),
    ]


def test_slug_collisions_suffix_and_warn_under_draft_mode(tmp_path: Path) -> None:
    _write(tmp_path, "a.md", "---\npublish: false\nslug: same\n---\n")
    _write(tmp_path, "b.md", published_text("same"))
    _write(tmp_path, "c.md", published_text("same"))
    _write(tmp_path, "same.md", "---\npublish: false\n---\n")

    entries, warnings = _preview(tmp_path)

    assert {path: (n.page.slug, n.status) for path, n in entries.items()} == {
        "a.md": ("same-2", EntryStatus.DRAFT),
        "b.md": ("same", EntryStatus.PUBLISHED),
        "c.md": ("same-3", EntryStatus.INVALID),
        "same.md": ("same-4", EntryStatus.DRAFT),
    }
    assert warnings == [
        ("a.md", "slug 'same' is already used by b.md; using 'same-2'"),
        ("c.md", "slug 'same' is already used by b.md; using 'same-3'"),
        ("same.md", "slug 'same' is already used by b.md; using 'same-4'"),
    ]


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        pytest.param(b"---\na: [\n---\n", "front matter is invalid YAML", id="yaml"),
        pytest.param(
            b"---\npublish: yes\n---\n",
            "publish must be true or false, not 'yes'",
            id="non-boolean",
        ),
        pytest.param(
            b"---\npublish: false\n---\n\xe9\n", "note is not UTF-8", id="draft-body"
        ),
        pytest.param(
            b"---\npublish: true\n---\n\xe9\n", "note is not UTF-8", id="published-body"
        ),
        pytest.param(
            b"---\npublish: false\ntitle: \xe9\n---\n",
            "front matter is not UTF-8",
            id="front-matter",
        ),
    ],
)
def test_an_unusable_note_is_absent_with_a_warning_under_draft_mode(
    tmp_path: Path, data: bytes, reason: str
) -> None:
    _write(tmp_path, "bad.md", data)

    entries, warnings = _preview(tmp_path)

    assert entries == {}
    assert len(warnings) == 1
    assert warnings[0][0] == "bad.md"
    assert reason in warnings[0][1]


@pytest.mark.usefixtures("_local")
def test_the_post_template_filled_by_obsidian_is_a_clean_draft(tmp_path: Path) -> None:
    template = (REPO_ROOT / "templates" / "Post Template.md").read_text(
        encoding="utf-8"
    )
    placeholder = "{{date:YYYY-MM-DDTHH:mm:ssZ}}"
    assert placeholder in template
    filled = template.replace(placeholder, "2026-11-07T14:03:22-08:00")
    _draft_note(tmp_path, "notes/A New Post.md", filled)

    marked = marked_parts(filled.encode("utf-8"))
    entries, warnings = _preview(tmp_path)

    assert marked is not None
    publish, properties, _ = marked
    assert publish is False
    created = properties["created"]
    assert isinstance(created, dt.datetime)
    assert created.utcoffset() == dt.timedelta(hours=-8)
    assert warnings == []
    assert entries["notes/A New Post.md"].page == PageProperties(
        "A New Post", MODIFIED, "a-new-post", ()
    )
