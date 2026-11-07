"""manual_qa: walks the author through the checks no automated test can make.

Each check runs its command on a scratch copy of the fixture vault, prints the steps,
and records the author's verdict and notes. The log written at the end is what the
author hands back to the agent running `/work`.
"""

import argparse
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_VAULT = REPO_ROOT / "tests" / "fixtures" / "vault"
# Seconds a check's server gets to answer before the steps are shown anyway.
READY_TIMEOUT = 30
# Lines of a failed check's command output copied into the log.
OUTPUT_TAIL = 40


@dataclass(frozen=True)
class Places:
    """The values a check's command, URL and steps refer to by `{name}`."""

    # The scratch copy of the fixture vault.
    vault: Path
    port: int
    # This machine's address on the local network.
    lan: str

    def fill(self, text: str) -> str:
        """`text` with every `{name}` replaced; the sites end in a slash."""
        return text.format(
            vault=self.vault,
            port=self.port,
            lan=self.lan,
            site=f"http://localhost:{self.port}/",
            lan_site=f"http://{self.lan}:{self.port}/",
        )


@dataclass(frozen=True)
class Check:
    """One manual check."""

    name: str
    # Runs for the whole check and is stopped with SIGTERM after the verdict.
    command: tuple[str, ...]
    # Polled until it answers, so the steps appear once the server is up.
    url: str
    steps: tuple[str, ...]


CHECKS = (
    Check(
        name="serve: live reload",
        command=("mdblog", "serve", "{vault}", "--port", "{port}"),
        url="{site}",
        steps=(
            "Open {site}posts/first-note/ in a browser.",
            "Edit {vault}/projects/first-note.md: change a word of its body and save.",
            "Pass if the open page shows the change without a manual refresh.",
        ),
    ),
    Check(
        name="serve: LAN access",
        command=("mdblog", "serve", "{vault}", "--port", "{port}", "--bind", "{lan}"),
        url="{lan_site}",
        steps=(
            "On a second device on the same network, open {lan_site}.",
            "Follow a post link, a tag link and the RSS feed link.",
            "Pass if each loads on that device and stays under {lan_site}.",
        ),
    ),
    Check(
        name="design: phone and desktop, light and dark",
        command=("mdblog", "serve", "{vault}", "--port", "{port}"),
        url="{site}",
        steps=(
            "With the system in light mode, open {site} in a desktop-width window.",
            "Visit the home page, Archive, Tags, {site}tags/node.js/, "
            "{site}posts/syntax/ and {site}404.html.",
            "Repeat at phone width: the browser's device toolbar set to 375px wide, "
            "or a phone on the same network.",
            "Switch the system to dark mode and repeat both widths.",
            "On posts/syntax/, open and close each callout and scroll the code block "
            "and the table sideways.",
            "Pass if every page reads well and looks right in both modes at both "
            "widths, and no page scrolls sideways as a whole. Note anything to change.",
        ),
    ),
)


class Verdict(StrEnum):
    """The author's verdict on one check."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


def parse_verdict(answer: str) -> Verdict | None:
    """The verdict `answer` names by its first letter or in full, or None if none."""
    word = answer.strip().lower()
    for verdict in Verdict:
        if word and verdict.value.startswith(word):
            return verdict
    return None


@dataclass(frozen=True)
class Result:
    """What one check recorded."""

    check: Check
    # The command as run, with places filled in.
    command: tuple[str, ...]
    verdict: Verdict
    notes: str
    # The command's exit status when it stopped before the verdict, else None.
    early_exit: int | None
    # The end of the command's output, kept only for a failed check.
    output_tail: str


def render_log(results: Sequence[Result], started: datetime, commit: str) -> str:
    """The Markdown log of `results`, in order, with every verdict and note."""
    lines = [
        "# Manual QA log",
        "",
        f"- Started: {started.isoformat(timespec='seconds')}",
        f"- Commit: {commit}",
        "",
    ]
    for result in results:
        lines += [
            f"## {result.check.name}: {result.verdict.value.upper()}",
            "",
            f"- Command: `{' '.join(result.command)}`",
        ]
        if result.early_exit is not None:
            lines.append(
                f"- The command exited with status {result.early_exit} before the verdict."
            )
        lines += ["", "Notes:", "", result.notes or "(none)", ""]
        if result.output_tail:
            lines += [
                "Command output (last lines):",
                "",
                "```",
                result.output_tail,
                "```",
                "",
            ]
    return "\n".join(lines)


def lan_address() -> str:
    """This machine's address on the network that holds its default route."""
    # Connecting a UDP socket sends nothing; it only picks the outgoing interface.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))
        except OSError:
            return "127.0.0.1"
        address: str = probe.getsockname()[0]
        return address


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("", 0))
        port: int = probe.getsockname()[1]
        return port


def _answers(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


def _wait_until_ready(url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + READY_TIMEOUT
    while process.poll() is None and time.monotonic() < deadline:
        if _answers(url):
            return
        time.sleep(0.3)
    print(f"  (nothing answered at {url}; see the command output)")


def _ask_verdict(ask: Callable[[str], str]) -> Verdict:
    while True:
        verdict = parse_verdict(ask("Verdict [p]ass, [f]ail or [s]kip: "))
        if verdict is not None:
            return verdict


def _ask_notes(ask: Callable[[str], str]) -> str:
    print("Notes, ending with an empty line:")
    lines: list[str] = []
    while line := ask("> "):
        lines.append(line)
    return "\n".join(lines)


def _tail(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return "\n".join(text.splitlines()[-OUTPUT_TAIL:])


def run_check(
    check: Check, places: Places, work: Path, ask: Callable[[str], str]
) -> Result:
    """Runs `check` with `places`, writing its command output under `work`."""
    command = tuple(places.fill(part) for part in check.command)
    output = work / f"{check.name.replace(':', '').replace(' ', '-')}.log"
    print(f"\n== {check.name}\n$ {' '.join(command)}\n  (output: {output})")
    with output.open("wb") as sink:
        process = subprocess.Popen(command, stdout=sink, stderr=subprocess.STDOUT)
    try:
        _wait_until_ready(places.fill(check.url), process)
        for number, step in enumerate(check.steps, start=1):
            print(f"{number}. {places.fill(step)}")
        verdict = _ask_verdict(ask)
        notes = _ask_notes(ask)
        early_exit = process.poll()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
    return Result(
        check=check,
        command=command,
        verdict=verdict,
        notes=notes,
        early_exit=early_exit,
        output_tail=_tail(output) if verdict is Verdict.FAIL else "",
    )


def _commit() -> str:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
        ).stdout.strip()

    dirty = " (uncommitted changes)" if git("status", "--porcelain") else ""
    return f"{git('rev-parse', '--short', 'HEAD')} on {git('branch', '--show-current')}{dirty}"


def main(argv: Sequence[str] | None = None) -> int:
    """Runs the selected checks interactively; returns 0 once the log is written."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "names",
        nargs="*",
        metavar="TEXT",
        help="run only checks whose name contains TEXT (default: every check)",
    )
    parser.add_argument(
        "--lan",
        metavar="ADDRESS",
        help="this machine's LAN address (default: detected)",
    )
    parser.add_argument(
        "--log", type=Path, metavar="PATH", help="where to write the log"
    )
    parser.add_argument("--list", action="store_true", help="list the checks and exit")
    args = parser.parse_args(argv)
    names: list[str] = args.names
    checks = [c for c in CHECKS if not names or any(n in c.name for n in names)]
    if args.list or not checks:
        for check in checks or CHECKS:
            print(check.name)
        return 0 if checks else 2
    started = datetime.now().astimezone()
    log: Path = args.log or Path(tempfile.gettempdir()) / (
        f"mdblog-qa-{started:%Y%m%d-%H%M%S}.md"
    )
    results: list[Result] = []
    with tempfile.TemporaryDirectory(prefix="mdblog-qa-") as work_name:
        work = Path(work_name)
        vault = work / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        places = Places(vault=vault, port=_free_port(), lan=args.lan or lan_address())
        print(
            f"Scratch vault: {vault}\nLAN address: {places.lan} (override with --lan)"
        )
        try:
            for check in checks:
                results.append(run_check(check, places, work, input))
        except KeyboardInterrupt, EOFError:
            print("\nStopped; the log holds the checks finished so far.")
        finally:
            log.write_text(render_log(results, started, _commit()), encoding="utf-8")
    print(f"\nLog written to {log}\nGive that path to Claude.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
