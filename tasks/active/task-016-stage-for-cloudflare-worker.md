---
id: task-016
title: "Stage the site for a Cloudflare Worker and serve it with wrangler dev"
---

# task-016: Stage the site for a Cloudflare Worker and serve it with wrangler dev

## Summary
`mdblog stage VAULT --output DIR` makes a fresh production build and lays it out as a self-contained bundle that a static-assets Worker can serve: a generated wrangler config, plus the site placed under its base path. `--serve` runs `wrangler dev` on that bundle, so the site can be checked locally exactly as Cloudflare will serve it. Node and wrangler join the toolchain, and the gate validates the Worker config without Cloudflare credentials.

## Must Have
- [ ] `_site/mdblog.toml` accepts an optional `[worker]` table whose only key is a required string `name`. `build`, `serve` and `check` work without the table. `load_config` raises `ConfigError` naming `mdblog.toml` for a `[worker]` that isn't a table, lacks `name`, has a non-string or invalid `name`, or has any other key. The existing errors for top-level keys keep their wording.
- [ ] `mdblog stage` on a vault without `[worker]` exits 1 with an error naming `mdblog.toml` and `[worker] name`, and writes nothing.
- [ ] `mdblog stage VAULT --output DIR`, on a vault whose `base_url` is `https://example.test/blog/`, leaves `DIR` holding a wrangler config and an assets directory. The config names the Worker, sets the assets directory, sets `not_found_handling` to `"404-page"`, sets a fixed `compatibility_date`, and has no `main` script. The assets directory holds the build output under `blog/` (including `blog/index.html`, `blog/404.html` and `blog/index.xml`) and nothing outside `blog/`.
- [ ] No file named `.mdblog-output`, or any other marker, exists anywhere under the assets directory. `DIR` itself carries a marker, and `stage` refuses `DIR` under the same rules `mdblog build` applies to its output.
- [ ] A failed `stage`, from bad notes, a bad config, a Hugo failure or a refused `DIR`, leaves `DIR` unchanged.
- [ ] `stage` always makes a production build. It has no drafts option, and it ignores any `--output` directory left by `mdblog build` or `mdblog serve`.
- [ ] `mdblog stage ... --serve` runs `wrangler dev` on the bundle, listening on 127.0.0.1 only. It uses port 8787, or a free port when 8787 is busy, and `--port N` fails naming the port when `N` is busy. It prints the site's local URL including the base path, and Ctrl+C stops it with exit 0.
- [ ] End to end with the real wrangler: the staged fixture, with a `/blog/` base, served by `wrangler dev` answers `/blog/` with 200 and the home page, and `/blog/no-such-page/` with 404 and the body of `blog/404.html`.
- [ ] The pixi environment provides Node from conda-forge. `package.json` and a committed `package-lock.json` pin wrangler, and `node_modules/` is git-ignored.
- [ ] `tools/check` installs from the npm lockfile and fails when `package.json` and `package-lock.json` disagree. When `node_modules/` already matches the lockfile, it doesn't reinstall. Under `--offline`, the install, the dry run and every wrangler-dependent test skip, and the gate reports the skip.
- [ ] `tools/check` validates the Worker config generated for a staged fixture bundle without Cloudflare credentials or network access: `wrangler deploy --dry-run` if that works offline, otherwise a test of the fields above. A gate test shows that a failing npm or dry-run step fails the gate.
- [ ] `README.md` documents `stage` and `--serve`, and its Development section points to the gate's contract instead of listing steps. `docs/vault-format.md` documents `[worker] name`. Comments in the code that writes the bundle give the reason for its layout and for each generated wrangler field. `.claude/docs/hugo-site.md` points to that code and copies none of it.
- [ ] `tools/check` exits 0 on the finished branch.

## Advice
- mdblog generates the wrangler config, and the vault supplies only the Worker name (routes come in M5). The assets directory, 404 handling and compatibility date are what the staging layout depends on, so mdblog owns them, and a vault cannot break them. Pin `compatibility_date` as a constant in code.
- Validate `name` against Cloudflare's rule for Worker names. Check the rule in Cloudflare's docs during `/work` instead of trusting memory (roughly lowercase letters, digits and hyphens, at most 63 characters). Then a bad name fails at load time rather than at deploy.
- Wrangler comes from npm because conda-forge has no wrangler package. The gate checks the npm lockfile itself because `pixi run --locked` does not detect a stale `package-lock.json`. (Moved from the roadmap, 2026-11-07.)
- Keep the marker outside the assets directory, for example `DIR/.mdblog-output` beside `DIR/wrangler.json` and `DIR/public/`. Wrangler uploads everything under the assets directory, and local output must never reach Cloudflare. Strip the marker `build_site` writes into its own output.
- Hugo writes files at the output's root even when `base_url` holds a path, so staging moves the whole output under the path. With a root `base_url`, the output goes at the assets root.
- `--serve` overlaps with `mdblog serve` only in port choice and output protection. Reuse `choose_port`, with the default port as a parameter, and `check_output`, rather than duplicating them. Leave `mdblog serve` alone. Its value is Hugo's live reload, incremental rebuilds and drafts, none of which `wrangler dev` offers, and routing authoring preview through wrangler would add Node to the writing loop for no gain.
- Pass `--ip 127.0.0.1` explicitly to `wrangler dev`, matching task-013's localhost-only rule for `serve`. Set `WRANGLER_SEND_METRICS=false` and anything else needed so wrangler never phones home or prompts in tests or the gate.
- Find wrangler at the repo's `node_modules/.bin/wrangler` (mdblog runs from a checkout through pixi). A missing wrangler is an error naming the path and saying how to install it, never a silent skip outside `--offline`.
- Verify early in `/work` whether `wrangler dev` and `wrangler deploy --dry-run` run with no network and no credentials. The gate design depends on it. Record any workaround in the friction log.
- `tools/check` passes `--offline` down to pytest (an environment variable or a marker), so wrangler tests skip only then. A missing `node_modules/` in a default run is a failure (pipeline § Checks: a missing tool is a failure).
- Tests that stage write their own vault config with a `/blog/` `base_url` and a `[worker]` table, as `tests/test_build.py` does. Don't edit the shared fixture's `mdblog.toml`, which seven test modules and `tools/manual_qa.py` read.
- A preview build with its own site URL is M5's job. Leave a seam (the staging function takes the `SiteConfig` it builds with) without adding a flag now.
- `tests/test_serve_hugo.py` shows how a test drives a real server subprocess on a chosen port. Follow it for the wrangler end-to-end test.
- Standing obligations: strict static checks apply. All logic is in Python. The npm steps in `check_runner.py` are plain argv entries in `Commands`, and any lockfile comparison is an importable function. Tests: fakes for argv construction and port handling, one real-wrangler happy path that includes the 404 body (a wrong 404 is silent), and a gate test that a failing npm step fails the gate. No test that restates the generated config's literal values beyond the Must Have fields.

## Plan
- [x] **Step 1** (`pixi.toml`, `pixi.lock`, `package.json`, `package-lock.json`, `.gitignore`): add Node and wrangler.
- [x] **Step 2** (`tools/check_runner.py`, `tests/test_check_runner.py`): add the npm install and stale-lock check, the offline skips and the dry run. The dry run runs as a `wrangler`-marked test in `tests/test_stage.py`, since it needs a bundle staged by step 4's code; pytest is a gate step, and `--offline` skips that marker.
- [x] **Step 3** (`src/mdblog/config.py`, `tests/test_config.py`): add the `[worker]` table.
- [x] **Step 4** (new `src/mdblog/stage.py`, `src/mdblog/serve.py` for the shared helpers, `src/mdblog/cli.py`): staging into a protected bundle, the generated wrangler config, and `--serve` via `wrangler dev`.
- [x] **Step 5** (new `tests/test_stage.py`, `tests/test_cli.py`): unit tests with fakes, plus the one real-wrangler end-to-end test.
- [x] **Step 6** (`README.md`, `docs/vault-format.md`, code comments, a pointer in `.claude/docs/hugo-site.md`, `CLAUDE.md` § Toolchain only if every session needs to know about the npm lockfile): document the work.

## Review log

### Round 1: REJECTED
- **F1: Test of pathological input to repo tooling** (`tests/test_check_runner.py:99-121`): `test_lock_problems_reports_an_unusable_file` feeds `lock_problems` a missing lockfile, invalid JSON, a JSON array and a lockfile with no root package. Each fails loudly and leaves output intact, and `check_runner` is repo tooling, so CLAUDE.md's **Test where the risk is** excludes the test. Delete it; keep the stale-lock, stamp and offline-variable tests.
- **N1: Install-script opt-out has no recorded reason** (`package.json:8`): `allowScripts` turns off `esbuild`'s and `workerd`'s install scripts with no reason recorded anywhere. Record one line near the npm step or in a commit message.
- **N2: Wrangler's leftover processes after it exits on its own** (`src/mdblog/serve.py:309-310`): `ServerProcess.stop` returns early when the leader has exited and never signals the group, so orphaned `workerd` grandchildren keep running. Signal the group regardless, ignoring `ProcessLookupError`.
- **N3: `choose_port` default** (`src/mdblog/serve.py:58`): `default: int = DEFAULT_PORT` would replace the `None` branch.

### Round 2: REJECTED
- **F1: The new group-signal branch in `ServerProcess.stop` has no test** (`src/mdblog/serve.py:305-312`): the round 1 N2 fix signals the group after the leader has already exited, but no test reaches that path: the exit-on-its-own fake starts no child, and the SIGINT test stops a running leader. A regression would leave `workerd` running with every test green. Have the exit-on-its-own fake start a grandchild, record its pid and exit 3, then assert the grandchild is gone after the `ServeError`.

### Round 3: APPROVED
- Round 2's F1 is fixed: `test_serve_bundle_reports_wrangler_exiting_on_its_own` (`tests/test_stage.py:336-358`) now leaves a grandchild in the exited leader's process group and asserts it is gone. In a throwaway copy, a mutation that returns early from `ServerProcess.stop` for an exited leader fails it. Round 1's fixes are still in place, and `tools/check` exits 0 on HEAD (678 passed).
