from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from manual_qa import CHECKS, Result, Verdict, ask_notes, parse_verdict, render_log


@pytest.mark.parametrize(
    ("answer", "verdict"),
    [
        ("p", Verdict.PASS),
        (" Pass ", Verdict.PASS),
        ("f", Verdict.FAIL),
        ("fail", Verdict.FAIL),
        ("s", Verdict.SKIP),
        ("", None),
        ("x", None),
        ("passed", None),
    ],
)
def test_verdict_is_read_from_a_prefix(answer: str, verdict: Verdict | None) -> None:
    assert parse_verdict(answer) is verdict


def test_log_records_each_verdict_with_its_notes_and_failure_details() -> None:
    passed = Result(CHECKS[0], ("mdblog", "serve"), Verdict.PASS, "", None, "")
    failed = Result(
        CHECKS[1], ("mdblog", "serve", "--port"), Verdict.FAIL, "a\nb", 1, "boom"
    )

    log = render_log(
        [passed, failed], datetime(2026, 11, 5, 9, tzinfo=UTC), "abc123 on task-008"
    )

    assert log == (
        "# Manual QA log\n"
        "\n"
        "- Started: 2026-11-05T09:00:00+00:00\n"
        "- Commit: abc123 on task-008\n"
        "\n"
        f"## {CHECKS[0].name}: PASS\n"
        "\n"
        "- Command: `mdblog serve`\n"
        "\n"
        "Notes:\n"
        "\n"
        "(none)\n"
        "\n"
        f"## {CHECKS[1].name}: FAIL\n"
        "\n"
        "- Command: `mdblog serve --port`\n"
        "- The command exited with status 1 before the verdict.\n"
        "\n"
        "Notes:\n"
        "\n"
        "a\n"
        "b\n"
        "\n"
        "Command output (last lines):\n"
        "\n"
        "```\n"
        "boom\n"
        "```\n"
    )


def _asker(answers: list[str]) -> Iterator[str]:
    yield from answers


@pytest.mark.parametrize("answer", ["", "n", " No "])
def test_declined_notes_are_empty_and_open_no_editor(
    tmp_path: Path, answer: str
) -> None:
    def edit(path: Path) -> None:
        raise AssertionError(path)

    assert ask_notes(lambda _: answer, edit, tmp_path / "notes.md") == ""


def test_accepted_notes_are_what_the_editor_saved(tmp_path: Path) -> None:
    answers = _asker(["maybe", "y"])

    def edit(path: Path) -> None:
        assert path.read_text(encoding="utf-8") == ""
        path.write_text("\nfirst line\nsecond line\n\n", encoding="utf-8")

    notes = ask_notes(lambda _: next(answers), edit, tmp_path / "notes.md")

    assert notes == "first line\nsecond line"


def test_notes_are_typed_when_the_editor_cannot_start(tmp_path: Path) -> None:
    answers = _asker(["yes", "typed note", ""])

    def edit(path: Path) -> None:
        raise FileNotFoundError(2, "No such file or directory", "no-such-editor")

    notes = ask_notes(lambda _: next(answers), edit, tmp_path / "notes.md")

    assert notes == "typed note"
