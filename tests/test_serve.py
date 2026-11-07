import datetime as dt
import json
import os
import socket
import sys
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import pytest

from mdblog import serve
from mdblog.build import MARKER, BuildError
from mdblog.serve import (
    ServeError,
    SyncResult,
    choose_port,
    default_output,
    hugo_server_argv,
    is_hidden,
    needs_restart,
    reset_output,
    serve_site,
    start_hugo,
    sync_tree,
    watch_loop,
)
from notes import published_text

CONFIG = (
    'base_url = "https://example.test/blog/"\n'
    'title = "The Site Title"\n'
    'author = "The Site Author"\n'
)
NOW = dt.datetime(2026, 6, 1, 12, tzinfo=dt.UTC)


def _make_vault(root: Path) -> Path:
    vault = root / "vault"
    (vault / "_site").mkdir(parents=True)
    (vault / "_site" / "mdblog.toml").write_text(CONFIG, encoding="utf-8")
    (vault / "note.md").write_text(
        published_text("note", body="FIRST\n"), encoding="utf-8"
    )
    return vault


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): (
            path.read_bytes() if path.is_file() else None
        )
        for path in sorted(root.rglob("*"))
    }


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@pytest.fixture
def busy_port() -> Iterator[int]:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port: int = listener.getsockname()[1]
        yield port


def test_requested_free_port_is_used() -> None:
    port = _free_port()

    assert choose_port(port) == port


def test_requested_busy_port_is_refused_naming_it(busy_port: int) -> None:
    with pytest.raises(ServeError, match=f"port {busy_port}:"):
        choose_port(busy_port)


def test_requested_port_held_only_in_time_wait_is_used() -> None:
    with socket.socket() as listener:
        # As Hugo's listener does; Linux reuses a TIME_WAIT port only when the
        # listener that accepted the connection set this too.
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port: int = listener.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port)) as client:
            accepted, _ = listener.accept()
            # The server side closes first, so its end of the connection is left in
            # TIME_WAIT on the port, as after serve stops with a browser tab open.
            accepted.close()
            assert client.recv(1) == b""

    assert choose_port(port) == port


def test_default_port_is_used_when_free(monkeypatch: pytest.MonkeyPatch) -> None:
    port = _free_port()
    monkeypatch.setattr(serve, "DEFAULT_PORT", port)

    assert choose_port(None) == port


def test_busy_default_port_falls_back_to_a_free_one(
    busy_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serve, "DEFAULT_PORT", busy_port)

    port = choose_port(None)

    assert port != busy_port
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def test_default_output_is_named_for_the_port_in_the_temp_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    assert default_output(1313) == tmp_path / "mdblog-serve-1313"


@pytest.mark.parametrize(
    ("relative", "hidden"),
    [
        pytest.param(".obsidian/workspace.json", True, id="hidden-folder"),
        pytest.param("notes/.draft.md", True, id="hidden-file"),
        pytest.param("a/.trash/b/c.md", True, id="nested-hidden-folder"),
        pytest.param("notes/a.md", False, id="plain"),
        pytest.param("_site/mdblog.toml", False, id="site-folder"),
    ],
)
def test_hidden_paths_are_those_with_a_dotted_component(
    relative: str, hidden: bool
) -> None:
    vault = Path("/v/.vaults/mine")

    assert is_hidden(vault, vault / relative) is hidden


def test_path_outside_the_vault_is_not_hidden() -> None:
    assert not is_hidden(Path("/v"), Path("/.other/a.md"))


def _tree(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_sync_writes_only_what_differs_and_removes_what_is_gone(
    tmp_path: Path,
) -> None:
    staging = _tree(
        tmp_path / "staging",
        {
            "same.txt": "same",
            "changed.txt": "new",
            "a/b/nested.txt": "nested",
            "a/b/new.txt": "new",
            "was-dir": "now a file",
        },
    )
    live = _tree(
        tmp_path / "live",
        {
            "same.txt": "same",
            "changed.txt": "old",
            "a/b/nested.txt": "nested",
            "a/gone.txt": "gone",
            "gone/deep/x.txt": "x",
            "was-dir/inner.txt": "inner",
            ".cache/hugo.bin": "cache",
            ".hugo_build.lock": "",
            "resources/_gen/img.png": "img",
        },
    )
    unchanged = live / "same.txt"
    os.utime(unchanged, (0, 0))

    result = sync_tree(staging, live)

    assert unchanged.stat().st_mtime == 0
    assert result == SyncResult(
        written=frozenset(
            PurePosixPath(p) for p in ("changed.txt", "a/b/new.txt", "was-dir")
        ),
        removed=frozenset(PurePosixPath(p) for p in ("a/gone.txt", "gone")),
    )
    hugo_owned = {".cache", ".cache/hugo.bin", ".hugo_build.lock", "resources"}
    assert {
        k: v
        for k, v in _snapshot(live).items()
        if k.split("/")[0] not in hugo_owned and k.split("/")[0] != "resources"
    } == _snapshot(staging)
    assert (live / ".cache" / "hugo.bin").is_file()
    assert (live / ".hugo_build.lock").is_file()
    assert (live / "resources" / "_gen" / "img.png").is_file()


def test_sync_replaces_a_file_with_a_directory(tmp_path: Path) -> None:
    staging = _tree(tmp_path / "staging", {"x/inner.txt": "inner"})
    live = _tree(tmp_path / "live", {"x": "file"})

    result = sync_tree(staging, live)

    assert (live / "x" / "inner.txt").read_text(encoding="utf-8") == "inner"
    assert result.written == {PurePosixPath("x"), PurePosixPath("x/inner.txt")}


def _sync(written: tuple[str, ...] = (), removed: tuple[str, ...] = ()) -> SyncResult:
    return SyncResult(
        written=frozenset(PurePosixPath(p) for p in written),
        removed=frozenset(PurePosixPath(p) for p in removed),
    )


@pytest.mark.parametrize(
    ("result", "restart"),
    [
        pytest.param(_sync(), False, id="nothing"),
        pytest.param(_sync(("content/posts/a/index.md",)), False, id="nested-file"),
        pytest.param(_sync(("content/posts/new",)), False, id="nested-dir"),
        pytest.param(_sync(("hugo.toml",)), True, id="config"),
        pytest.param(_sync(("layouts",)), True, id="new-top-level-dir"),
        pytest.param(_sync(removed=("content/posts/a",)), True, id="removal"),
    ],
)
def test_restart_follows_removals_and_top_level_changes(
    result: SyncResult, restart: bool
) -> None:
    assert needs_restart(result) is restart


def test_hugo_argv_listens_on_localhost_with_the_configured_base_url() -> None:
    argv = hugo_server_argv(("hugo",), Path("/src"), Path("/out"), 1400)

    assert argv[:2] == ["hugo", "server"]
    assert "--baseURL" not in argv
    assert "--appendPort=false" not in argv
    for flag, value in (
        ("--source", "/src"),
        ("--destination", "/out"),
        ("--cacheDir", "/src/.cache"),
        ("--port", "1400"),
        ("--bind", "127.0.0.1"),
    ):
        assert argv[argv.index(flag) + 1] == value
    assert "--buildFuture" in argv
    assert "--disableFastRender" in argv
    assert "--buildDrafts" not in argv


def test_hugo_argv_renders_drafts_only_in_draft_mode() -> None:
    argv = hugo_server_argv(("hugo",), Path("/src"), Path("/out"), 1400, drafts=True)

    assert argv == [
        *hugo_server_argv(("hugo",), Path("/src"), Path("/out"), 1400),
        "--buildDrafts",
    ]


def test_reset_output_empties_the_directory_and_writes_the_marker(
    tmp_path: Path,
) -> None:
    output = _tree(tmp_path / "out", {"old.html": "", "posts/a/index.html": ""})

    reset_output(output)

    assert [p.name for p in output.iterdir()] == [MARKER]


def test_reset_output_that_cannot_be_written_names_it(tmp_path: Path) -> None:
    output = tmp_path / "file" / "out"
    (tmp_path / "file").write_text("", encoding="utf-8")

    with pytest.raises(ServeError, match=f"cannot serve into {output}"):
        reset_output(output)


def test_hugo_starts_without_hugo_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUGO_BASEURL", "http://elsewhere.test/")
    monkeypatch.setenv("MDBLOG_TEST_KEPT", "1")
    seen = tmp_path / "env.json"
    script = f"import json, os; open({str(seen)!r}, 'w').write(json.dumps(sorted(os.environ)))"

    server = start_hugo([sys.executable, "-c", script], tmp_path)
    server.process.wait(timeout=30)

    names: list[str] = json.loads(seen.read_text(encoding="utf-8"))
    assert "MDBLOG_TEST_KEPT" in names
    assert not [name for name in names if name.startswith("HUGO")]


def test_hugo_that_cannot_start_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ServeError, match="cannot run"):
        start_hugo([str(tmp_path / "missing")], tmp_path)


@dataclass
class FakeServer:
    """A server whose exit status a test sets."""

    source: dict[str, bytes | None]
    status: int | None = None
    stopped: bool = False

    def poll(self) -> int | None:
        return self.status

    def stop(self) -> None:
        self.stopped = True


@dataclass
class Starts:
    """Records each server start along with the live source it started on."""

    source: Path
    servers: list[FakeServer] = field(default_factory=list[FakeServer])

    def __call__(self) -> FakeServer:
        server = FakeServer(_snapshot(self.source))
        self.servers.append(server)
        return server


def _run_loop(
    vault: Path,
    source: Path,
    *steps: Callable[[], object],
    clock: Callable[[], dt.datetime] = lambda: NOW,
) -> Starts:
    starts = Starts(source)

    def batches() -> Iterator[set[str]]:
        for step in steps:
            step()
            yield {"changed"}

    watch_loop(vault, source, batches(), starts, clock)
    return starts


def _write(path: Path, text: str) -> Callable[[], object]:
    return lambda: path.write_text(text, encoding="utf-8")


def _page(source: Path) -> str:
    return (source / "content/posts/note/index.md").read_text(encoding="utf-8")


def _hugo_toml(server: FakeServer) -> bytes:
    return server.source.get("hugo.toml") or b""


def test_loop_starts_once_and_syncs_an_edit_without_restarting(
    tmp_path: Path,
) -> None:
    vault = _make_vault(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    pages: list[str] = []

    starts = _run_loop(
        vault,
        source,
        _write(vault / "note.md", published_text("note", body="SECOND\n")),
        lambda: pages.append(_page(source)),
    )

    assert len(starts.servers) == 1
    server = starts.servers[0]
    assert b"https://example.test/blog/" in _hugo_toml(server)
    assert "content/posts/note/index.md" in server.source
    assert "SECOND" in pages[0]
    assert server.stopped


def test_loop_waits_for_a_valid_vault_before_starting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = _make_vault(tmp_path)
    (vault / "bad.md").write_text("---\npublish: yes\n---\n", encoding="utf-8")
    source = tmp_path / "source"
    source.mkdir()
    started: list[int] = []
    starts = Starts(source)

    def batches() -> Iterator[set[str]]:
        (vault / "other.md").write_text("still broken", encoding="utf-8")
        yield {"changed"}
        started.append(len(starts.servers))
        (vault / "bad.md").unlink()
        yield {"changed"}

    watch_loop(vault, source, batches(), starts, lambda: NOW)

    assert started == [0]
    assert len(starts.servers) == 1
    err = capsys.readouterr().err
    assert (
        "mdblog: cannot build from these notes:\n"
        "  bad.md: publish must be true or false, not 'yes'\n"
        "mdblog: waiting for a change that fixes the vault\n"
    ) in err


def test_loop_keeps_the_last_good_source_after_a_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = _make_vault(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    before: list[dict[str, bytes | None]] = []
    after: list[dict[str, bytes | None]] = []

    starts = _run_loop(
        vault,
        source,
        lambda: before.append(_snapshot(source)),
        _write(vault / "_site" / "mdblog.toml", "title = 3\n"),
        lambda: after.append(_snapshot(source)),
        _write(vault / "_site" / "mdblog.toml", CONFIG),
        _write(vault / "note.md", published_text("note", body="FIXED\n")),
    )

    assert before == after
    assert len(starts.servers) == 1
    assert "FIXED" in _page(source)
    assert "mdblog.toml: missing key 'base_url'" in capsys.readouterr().err


def test_loop_prints_config_failures_as_build_does(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = _make_vault(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    config = vault / "_site" / "mdblog.toml"

    _run_loop(vault, source, _write(config, CONFIG + "extra = 'x'\n"))

    assert f"mdblog: {config}: unknown key 'extra'\n" in capsys.readouterr().err


def test_loop_restarts_on_a_base_url_change_with_the_new_config(
    tmp_path: Path,
) -> None:
    vault = _make_vault(tmp_path)
    source = tmp_path / "source"
    source.mkdir()

    starts = _run_loop(
        vault,
        source,
        _write(
            vault / "_site" / "mdblog.toml",
            CONFIG.replace("/blog/", "/journal/"),
        ),
    )

    assert [b"/blog/" in _hugo_toml(s) for s in starts.servers] == [True, False]
    assert [b"/journal/" in _hugo_toml(s) for s in starts.servers] == [False, True]
    assert all(s.stopped for s in starts.servers)


def test_loop_restarts_after_a_page_is_removed(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    (vault / "other.md").write_text(published_text("other"), encoding="utf-8")
    source = tmp_path / "source"
    source.mkdir()

    starts = _run_loop(vault, source, lambda: (vault / "other.md").unlink())

    assert len(starts.servers) == 2
    assert "content/posts/other" not in starts.servers[1].source


def test_loop_rebuilds_with_the_time_of_each_change(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    (vault / "tomorrow.md").write_text(
        published_text("tomorrow", date="2026-06-02"), encoding="utf-8"
    )
    source = tmp_path / "source"
    source.mkdir()
    times = iter((NOW, NOW + dt.timedelta(days=1)))

    starts = _run_loop(vault, source, lambda: None, clock=lambda: next(times))

    assert len(starts.servers) == 1
    assert "content/posts/tomorrow/index.md" in starts.servers[0].source


def test_loop_only_checks_the_server_on_an_empty_batch(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    starts = Starts(source)

    def batches() -> Iterator[set[str]]:
        yield set()
        starts.servers[0].status = 2
        yield set()

    with pytest.raises(ServeError, match="hugo exited with status 2"):
        watch_loop(vault, source, batches(), starts, lambda: NOW)

    assert len(starts.servers) == 1


def test_serve_refuses_a_vault_that_is_not_a_directory(tmp_path: Path) -> None:
    with pytest.raises(BuildError, match="is not a directory"):
        serve_site(tmp_path / "missing", port=_free_port())


def test_serve_refuses_outputs_as_build_does(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)
    taken = _tree(tmp_path / "taken", {"keep.txt": "keep"})

    with pytest.raises(BuildError, match="non-empty directory"):
        serve_site(vault, taken, port=_free_port())
    with pytest.raises(BuildError, match="inside it"):
        serve_site(vault, vault / "out", port=_free_port())

    assert (taken / "keep.txt").is_file()


def _serve_with_failing_hugo(tmp_path: Path, output: Path | None) -> Path:
    vault = _make_vault(tmp_path)
    temp = tmp_path / "temp"
    temp.mkdir()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tempfile, "tempdir", str(temp))
        with pytest.raises(ServeError, match="hugo exited with status 3"):
            serve_site(
                vault,
                output,
                port=_free_port(),
                hugo=(sys.executable, "-c", "raise SystemExit(3)"),
            )
    return temp


def test_serve_removes_its_temporary_directories_on_exit(tmp_path: Path) -> None:
    temp = _serve_with_failing_hugo(tmp_path, None)

    assert list(temp.iterdir()) == []


def test_serve_keeps_a_given_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "out"

    temp = _serve_with_failing_hugo(tmp_path, output)

    assert (output / MARKER).is_file()
    assert list(temp.iterdir()) == []


def test_draft_loop_starts_on_failing_notes_and_warns_after_each_rebuild(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = _make_vault(tmp_path)
    (vault / "bad.md").write_text("---\npublish: true\n---\n", encoding="utf-8")
    (vault / "draft.md").write_text("---\npublish: false\n---\n", encoding="utf-8")
    source = tmp_path / "source"
    source.mkdir()
    starts = Starts(source)

    def batches() -> Iterator[set[str]]:
        (vault / "bad.md").write_text(published_text("bad"), encoding="utf-8")
        yield {"changed"}

    watch_loop(vault, source, batches(), starts, lambda: NOW, drafts=True)

    assert len(starts.servers) == 1
    first = starts.servers[0].source
    assert "content/posts/bad/index.md" in first
    assert "content/posts/draft/index.md" in first
    assert b"mdblog_preview = true" in _hugo_toml(starts.servers[0])
    assert capsys.readouterr().err == (
        "mdblog: warnings from these notes, shown in the draft preview anyway:\n"
        "  bad.md: date is required\n"
        "  bad.md: slug is required\n"
    )


def test_draft_loop_still_waits_for_a_config_fix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = _make_vault(tmp_path)
    config = vault / "_site" / "mdblog.toml"
    config.write_text("title = 3\n", encoding="utf-8")
    source = tmp_path / "source"
    source.mkdir()
    started: list[int] = []
    starts = Starts(source)

    def batches() -> Iterator[set[str]]:
        started.append(len(starts.servers))
        config.write_text(CONFIG, encoding="utf-8")
        yield {"changed"}

    watch_loop(vault, source, batches(), starts, lambda: NOW, drafts=True)

    assert started == [0]
    assert len(starts.servers) == 1
    err = capsys.readouterr().err
    assert "mdblog.toml: missing key 'base_url'" in err
    assert "mdblog: waiting for a change that fixes the vault\n" in err
