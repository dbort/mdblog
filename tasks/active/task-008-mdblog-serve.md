---
id: task-008
title: "Preview the site locally with mdblog serve"
---

# task-008: Preview the site locally with mdblog serve

## Summary
Adds `mdblog serve VAULT`, which runs Hugo's development server on the vault's site and rebuilds whenever the vault changes, so a page open in the browser reloads by itself while the author writes. Every link points at the local server, which a plain `mdblog build` served by `python3 -m http.server` cannot do. It also adds a short README covering installation and both commands.

## Must Have
- [ ] `mdblog serve VAULT` with no options, when port 1313 is free on 127.0.0.1, serves the site at `http://localhost:1313<base path>/` and renders it into `<system temp dir>/mdblog-serve-1313`.
- [ ] When port 1313 is busy and `--port` is not given, serve uses a free port P, renders into `<system temp dir>/mdblog-serve-P` and serves on P. A `--port N` that is busy exits 1 with a message naming N.
- [ ] `--output DIR` renders into DIR, which ends up holding the `.mdblog-output` marker. DIR is refused with exit 1 in every case where `mdblog build` refuses it, and it remains after serve exits.
- [ ] After SIGINT or SIGTERM, serve stops Hugo and exits 0, and neither the default `mdblog-serve-<port>` directory nor the assembled Hugo source directory exists afterward.
- [ ] With `base_url = "https://example.test/blog/"`, pages are served under `/blog/`, and no file in the rendered output, feeds included, contains `example.test`.
- [ ] While serve runs, editing a published note's text changes its served page within 10 seconds. Adding a published note adds its page, and deleting or unpublishing one makes its URL return 404 and removes its files from the output directory.
- [ ] While serve runs, changes to `_site/mdblog.toml`, `_site/bio.md` and a file under `_site/layouts/` each show up on the served site within 10 seconds.
- [ ] A change only under a hidden folder of the vault, such as `.obsidian/`, triggers no rebuild.
- [ ] If a change makes the vault fail validation (a note failure or a `ConfigError`), serve prints the same failure text `mdblog build` prints to stderr, keeps serving the last good site, keeps running, and rebuilds once a later change fixes it.
- [ ] If the vault fails validation at startup, serve prints the failures, starts no server, keeps watching, and starts the server after the first change that leaves the vault valid. A vault path that is not a directory exits 1 immediately.
- [ ] `--bind ADDRESS` passes ADDRESS to Hugo, and links on served pages use ADDRESS as their host with the base path kept. `--bind 0.0.0.0` or `--bind ::` exits 1 with a message asking for a specific address.
- [ ] `HUGO*` environment variables do not reach the Hugo server process.
- [ ] `watchfiles` is a dependency in `pixi.toml` and `pyproject.toml`, and `pixi.lock` resolves it for `linux-64`, `linux-aarch64` and `osx-arm64`.
- [ ] A `README.md` at the repo root of at most 60 lines covers installing with pixi, `mdblog build` and `mdblog serve` with each of serve's options, and links to `docs/vault-format.md` for everything about the vault.
- [ ] Every existing `mdblog build` test passes without changes to its assertions.
- [ ] Manual QA by the author: with `mdblog serve` running on the fixture vault and a page open in a browser, saving an edit to that page's note reloads the page without a manual refresh. A second device on the LAN loads the site through `--bind <LAN address>` and its links work.
- [ ] `tools/check` exits 0 on the finished branch.

## Advice
- User decisions (2026-11-05): use Hugo's server, not a Python HTTP server, for its live reload and because it rewrites URLs to the server's address. Serve the same notes as `mdblog build` with the same validation; M3.1's draft mode for unpublished notes is a separate task. The port defaults to 1313 and falls back to a free port only when `--port` was not given. The default output is `mdblog-serve-<port>` under `tempfile.gettempdir()`, deleted on exit; an `--output` directory is kept. A failing vault never stops serve: at startup it waits for a fix, and later it keeps the last good site, because the author is mid-edit. Failures go to the terminal only. `--bind` lets a phone on the LAN load the site.
- Hugo 0.169's server, tested: it keeps the base path (a `baseURL` of `https://example.test/blog/` serves at `http://localhost:PORT/blog/`, and `.Permalink` becomes `http://localhost:PORT/blog/`), it writes to disk under `--destination` by default, and it exits with `bind: address already in use` for a busy `--port` rather than choosing another. So mdblog chooses the port itself, probing it by binding a socket on the bind address and falling back to port 0, before naming the directory and starting Hugo.
- Keep `base_url` unchanged in the generated `hugo.toml` and in `convert_notes`. Hugo's server replaces only the scheme and host, so the root-relative links mdblog writes with the base path stay correct.
- For a non-loopback `--bind`, pass `--baseURL http://ADDRESS<base path>` so links use that host. Hugo's `--appendPort` default adds the port. Put an IPv6 address in brackets. Refuse a wildcard address, because links need one host to point at.
- Run Hugo as `hugo server --source SRC --destination OUT --cacheDir SRC/.cache --buildFuture --port P --bind B --disableFastRender`, with `HUGO*` variables stripped as `_run_hugo` does. `--disableFastRender` re-renders every page on each change, so the output directory matches what a build would produce. Fast render re-renders only visited pages, and a small personal site renders quickly anyway.
- Keep one assembled Hugo source in its own temporary directory for the whole session, separate from the output directory. On each good rebuild, assemble into a staging directory with the existing `_assemble_source`, then sync into the live source: write only files whose bytes differ and remove files and directories that no longer exist. Hugo watches its source and rebuilds per changed file, and replacing the whole tree at once can make it see a vanished `content/` directory.
- Restart the Hugo process when the generated `hugo.toml` changes, because a new `base_url` can change the path Hugo serves under. Keep the same port.
- A failed rebuild leaves the live source untouched. Recompute `now` on every rebuild, so a note dated today publishes at any local time.
- Before starting Hugo, empty the output directory and write the marker, since `check_output` has already established that mdblog owns it. Confirm Hugo leaves the marker in place while it serves. If it does not, rewrite the marker after each rebuild, and do not pass `--cleanDestinationDir`.
- Watch the vault with `watchfiles.watch`, filtering out every path with a hidden component relative to the vault. `select_notes` ignores hidden paths, and Obsidian rewrites `.obsidian/workspace.json` constantly. Keep `watchfiles`' default debounce, which batches Obsidian's frequent autosaves into one rebuild.
- Structure the loop so tests can drive it without watchfiles or a real server: a function that takes the vault, the live source, an iterable of change batches and a callable that (re)starts Hugo. Production passes `watchfiles.watch(...)` and a real process launcher.
- Stop on SIGINT and SIGTERM: terminate Hugo if it is still running, wait for it, then remove the temporary directories. If Hugo exits unexpectedly, serve exits 1 with a message naming Hugo's status.
- Pass Hugo's own output through to the terminal. It prints the server URL and its own template errors, which it also shows in the browser.
- Update `task-007`'s Advice to preview with `mdblog serve` on the fixture vault in place of `python3 -m http.server`.
- User decision (2026-11-05): build a reusable manual-QA walker in this task. `tools/manual_qa.py`, run through the `tools/manual-qa` pixi wrapper, holds every check as data (command, URL to wait for, steps), runs each on a scratch copy of the fixture vault, records a pass, fail or skip verdict and notes, and writes a Markdown log the author hands back. The steps live only in the script; there is no manual-QA doc. The author asked for it so manual QA needs no agent-made setup and can run at any time. `CLAUDE.md` tells future tasks to add their checks there.
- Implementation findings (2026-11-05), tested against Hugo 0.169: Hugo's server never deletes a removed page's files from `--destination` and keeps serving them with status 200, and `--cleanDestinationDir` deletes the marker without removing those files on a rebuild. So serve restarts Hugo into an emptied output directory, with the marker rewritten, whenever a sync removes a path or writes a top-level path (`hugo.toml`, or a new directory Hugo would not be watching). Hugo rejects a bracketed IPv6 `--baseURL` without a port, so an explicit `--bind` passes `--baseURL http://ADDRESS:PORT<base path>/ --appendPort=false` in place of relying on `--appendPort`. Hugo runs in its own process group so a terminal's Ctrl+C reaches only mdblog, which then stops Hugo; any other Hugo exit is a failure.
- Standing obligation, strict static checks: all new code is typed under pyrefly strict. `watchfiles` ships type hints; if any call still erases a type, comment why at that line.
- Standing obligation, scripts stay simple: no shell scripts. Port selection, syncing and the watch loop are importable Python functions.
- Standing obligation, test where the risk is: unit-test port selection, the directory name, the sync (changed, unchanged, removed and nested files), the hidden-path filter, the bind and base-URL rules, the Hugo argument list, the startup wait, keeping the last good source on failure, and the restart on a `hugo.toml` change, all with fakes. Run one real-Hugo, real-watchfiles end-to-end test: start serve on a copy of the fixture vault, fetch a page over HTTP, edit a note and see the change, break a note and see the old page stay, then send SIGTERM and confirm the directories are gone. Live reload in a browser and LAN access are manual QA, since no test here drives a browser or a second device.

## Plan
- [x] **Step 1** (`pixi.toml`, `pyproject.toml`, `pixi.lock`): add `watchfiles`.
- [x] **Step 2** (`src/mdblog/serve.py`, tests): port selection, bind and base-URL rules, output-directory choice and checks, source sync, the hidden-path filter, the watch-and-rebuild loop, and the Hugo server process with clean shutdown. Expose a `serve_site(vault, output, port, bind)` entry point. Factor any part of `build_site` that serve shares, such as the validation and conversion that produce pages or a `BuildError`, into a function both call, leaving `build_site`'s contract unchanged.
- [x] **Step 3** (`src/mdblog/cli.py`, tests): the `serve` subcommand with `VAULT`, `--output DIR`, `--port N` and `--bind ADDRESS`, reporting refusals as `mdblog: <error>` with exit 1.
- [x] **Step 4** (`tests/`): the real-Hugo end-to-end test.
- [x] **Step 5** (`README.md`): installation and usage, deferring to `docs/vault-format.md` for the vault.
- [x] **Step 6** (`tasks/active/task-007-visual-design.md`): replace the `python3 -m http.server` preview in its Advice with `mdblog serve`.
- [x] **Step 7** (`tools/manual_qa.py`, `tools/manual-qa`, `CLAUDE.md`, tests): the manual-QA walker, with serve's live-reload and LAN checks.
- [ ] **Step 8**: have the author run `tools/manual-qa` and record their approval from its log, dated, in `## Advice`.

## Review log
