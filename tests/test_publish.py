from pathlib import Path

import pytest

from mdblog.publish import copy_notes


def test_copy_notes_preserves_relative_paths_and_skips_other_files(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    (vault / "a" / "b").mkdir(parents=True)
    (vault / "top.md").write_text("top", encoding="utf-8")
    (vault / "a" / "b" / "deep.md").write_text("deep", encoding="utf-8")
    (vault / "a" / "image.png").write_text("not a note", encoding="utf-8")
    content = tmp_path / "content"

    copy_notes(vault, content)

    assert (content / "top.md").read_text(encoding="utf-8") == "top"
    assert (content / "a" / "b" / "deep.md").read_text(encoding="utf-8") == "deep"
    assert not (content / "a" / "image.png").exists()


def test_copy_notes_returns_destinations_sorted(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "m").mkdir(parents=True)
    for name in ("z.md", "m/n.md", "a.md"):
        (vault / name).write_text(name, encoding="utf-8")
    content = tmp_path / "content"

    assert copy_notes(vault, content) == [
        content / "a.md",
        content / "m" / "n.md",
        content / "z.md",
    ]


def test_copy_notes_skips_a_directory_named_like_a_note(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "folder.md").mkdir(parents=True)

    assert copy_notes(vault, tmp_path / "content") == []


@pytest.mark.parametrize("make_file", [False, True])
def test_copy_notes_raises_when_vault_is_not_a_directory(
    tmp_path: Path, make_file: bool
) -> None:
    vault = tmp_path / "vault"
    if make_file:
        vault.write_text("", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        copy_notes(vault, tmp_path / "content")
