---
id: task-013
title: "Serve only on localhost"
---

# task-013: Serve only on localhost

## Summary
`mdblog serve` drops its `--bind` option and always listens on 127.0.0.1 with Hugo's own `http://localhost:<port>` links. That removes the wildcard refusal, IPv6 bracketing and base-URL rewriting that existed only so a second device on the LAN could load the preview, along with the manual-QA LAN check and its `--lan` plumbing.

## Must Have
- [ ] `mdblog serve --help` does not mention `--bind`, and `mdblog serve VAULT --bind 127.0.0.1` exits 2 with argparse's unrecognized-arguments error.
- [ ] `src/mdblog/serve.py` defines no `check_bind` or `server_base_url`, and `serve_site` takes no `bind` parameter.
- [ ] The argv from `hugo_server_argv` holds `--bind 127.0.0.1` and never `--baseURL` or `--appendPort=false`; a unit test asserts both.
- [ ] `choose_port` probes 127.0.0.1 only and takes no address argument; its existing unit tests (requested, busy, default, fallback, TIME_WAIT) pass against the new signature.
- [ ] `tools/manual_qa.py` has no `serve: LAN access` check, no `--lan` option, no `lan_address`, and `Places` has no LAN field; no check's steps mention a second device or a phone on the network.
- [ ] `README.md` does not mention `--bind` or loading the site from another device.
- [ ] `tools/check` passes.

## Advice
- User decisions (2026-11-07): serve is localhost-only. Previewing on a real phone before deployment is given up: phone-width manual QA uses the browser's device toolbar at 375px, and checks on a real phone wait for the deployment milestone's preview URL. Do not add a replacement such as a documented SSH or Tailscale forward.
- Keep passing `--bind 127.0.0.1` to Hugo explicitly even though it is Hugo's default, so the address Hugo listens on is the one `choose_port` probed. Keep the probe's `SO_REUSEADDR` and its comment (task-008 review F1). The probe is IPv4-only, so the `AF_INET6` family choice goes.
- No deprecation shim or friendly message for a passed `--bind`: argparse's exit-2 error is clear enough for a personal tool, and a test of it would only restate argparse. The Must Have is checked by running the command, not by a new test.
- `mdblog.links.base_path` stays: `links.py` and `tests/test_links.py` use it. Only serve's import of it goes.
- `tasks/completed/task-008-mdblog-serve.md` keeps its LAN decisions and QA record as history; do not edit it.
- Sequencing: no other active task depends on `--bind` (task-009, task-011 and task-012 do not mention it), so this task can land before or after them. Landing it before task-009 gives task-009 the smaller `serve.py`. task-012's Advice replaces the design check in `tools/manual_qa.py`; whichever task lands second keeps that check free of the phone-on-the-network wording.
- No manual QA: removing an option and its plumbing is fully covered by unit tests and the existing real-Hugo end-to-end test in `tests/test_serve_hugo.py`, which already serves on localhost.
- Standing obligation, strict static checks: the changed signatures stay fully typed under pyrefly strict; nothing new needs an escape hatch.
- Standing obligation, scripts stay simple: no shell is touched.
- Standing obligation, test where the risk is: delete the tests of removed code rather than adapting them; update the argv test to assert the fixed bind and the absent base URL. `tools/manual_qa.py` tests change only where they reference the removed check.

## Plan
- [ ] **Step 1** (`src/mdblog/serve.py`, `tests/test_serve.py`): delete `check_bind`, `server_base_url` and the `ipaddress` and `base_path` imports. Rename `DEFAULT_BIND` to a fixed listen-address constant (for example `HOST = "127.0.0.1"`). `choose_port(requested: int | None) -> int` and `_bound_port(port)` probe that address over IPv4; error messages keep naming the address and port. `hugo_server_argv(hugo, source, destination, port)` always passes `--bind HOST` and no base-URL flags. `serve_site(vault, output=None, port=None, hugo=("hugo",))` drops `bind`. The configured base URL reaches Hugo only through the generated `hugo.toml`, so remove its plumbing: `Rebuilt` loses `base_url` (and goes entirely, with `rebuild` returning `SyncResult | None`, if `sync` is its only field), and `watch_loop`'s `start` becomes `Callable[[], Server]`. Update the docstrings: links point at `http://localhost:<port>` with the base path kept. In `tests/test_serve.py` delete the wildcard and specific-bind tests and the `server_base_url` table test, update the `choose_port` calls, replace the two argv tests with one asserting `--bind 127.0.0.1` and no `--baseURL` or `--appendPort=false`. The fake server factory drops its `base_url`; `test_loop_restarts_with_the_new_base_url_on_a_config_change` keeps proving a `mdblog.toml` change restarts Hugo, asserting the restart count and the new `baseURL` in the synced `hugo.toml` in place of the started servers' base URLs, and is renamed to match. Every other test reading `server.base_url` changes the same way.
- [ ] **Step 2** (`src/mdblog/cli.py`, `tests/test_cli.py`): remove the `--bind` argument and pass `serve_site(args.vault, args.output, args.port)`. Delete the `--bind 0.0.0.0` refusal test.
- [ ] **Step 3** (`tools/manual_qa.py`, `tests/test_manual_qa.py`): remove the `serve: LAN access` check, `Places.lan` and the `lan`/`lan_site` fill keys, `lan_address`, the `--lan` option and the "LAN address" startup line. In the design check, drop "or a phone on the same network" from the phone-width step. In `tests/test_manual_qa.py`, the `render_log` test builds a `Result` from `CHECKS[1]` with a `--bind` command string; keep it valid against the shortened `CHECKS` and give it a command without `--bind`.
- [ ] **Step 4** (`README.md`): drop `[--bind ADDRESS]` from the usage line and the `--bind` bullet; state that serve listens on 127.0.0.1 only.

## Review log
