from datetime import UTC, datetime

import pytest

from manual_qa import CHECKS, Result, Verdict, parse_verdict, render_log


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
        CHECKS[1], ("mdblog", "serve", "--bind"), Verdict.FAIL, "a\nb", 1, "boom"
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
        "- Command: `mdblog serve --bind`\n"
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
