---
id: task-017
title: "Verify that a URL serves the site"
blocked_by: [task-015, task-016]
---

# task-017: Verify that a URL serves the site

## Summary
`mdblog verify URL` checks that a site answers at a URL: home page, feed, recent-posts file, and its own 404 page for a missing path. It runs against `wrangler dev` now and against deployed preview and production URLs in M5, as a separate command independent of any deploy.

## Must Have
- [x] `mdblog verify URL` takes the site's URL including its base path, such as `http://127.0.0.1:8787/blog/`. A missing trailing slash makes no difference.
- [x] It checks four things, each with one request:
  - The URL answers 200 with an HTML content type.
  - `index.xml` under it answers 200 and parses as RSS 2.0 with a `<channel>`.
  - `recent.json` under it answers 200 and parses as task-015's shape.
  - A path under it that no site holds (a fixed name with a random suffix) answers 404, with a body containing the 404 marker string.
- [x] Every check runs even after another fails. Each prints one line naming the check and `ok` or the reason it failed (status, content type, parse error or missing marker). The command exits 0 only when all four pass, and 1 otherwise.
- [x] A connection error, DNS failure or timeout fails the check it hit, naming the URL and the error, without a traceback. The timeout applies per request.
- [x] The packaged 404 layout carries the marker where readers don't see it, such as in a `<meta>` element. A test of the real build finds it in `404.html` and in no other page.
- [x] Unit tests drive the command against a local fake HTTP server, one case for each check's failure: wrong status, wrong content type, unparsable body, 404 without the marker, and connection refused.
- [x] End to end: the staged `/blog/` fixture served by `wrangler dev` passes `mdblog verify`. This replaces task-016's direct HTTP assertions, so the suite still runs wrangler once.
- [x] `README.md` documents `verify`. `docs/vault-format.md` says that a `_site/layouts/404.html` override must keep the marker or `mdblog verify` fails.
- [x] `tools/check` never runs `mdblog verify` against anything but a local server.
- [x] `tools/check` exits 0 on the finished branch.

## Advice
- The marker shows that the response is this site's own 404 page and not Cloudflare's empty 404 or another site's. The author asked for a unique-enough string hidden in the page. A fixed string containing `mdblog`, defined once in Python and written into the layout, is enough. Don't build it from the site title: the verifier knows only the URL, and titles need HTML escaping. A test of the real build ties the layout to the constant, so neither can drift without failing.
- One attempt per check, no retries. If M5 finds that deploys need time to propagate, waiting belongs in deploy.
- Use `urllib.request` from the standard library, with a fixed User-Agent naming mdblog and no contact address. Don't follow redirects on the 404 check, because a redirect there means the 404 handling is wrong.
- Parse RSS with `xml.etree.ElementTree`. The input is a site the author controls, and the check only needs well-formedness and a `<channel>`. Parse JSON with `json` and check the shape with a small typed function, the only place the external data's type is narrowed.
- Under a third-party theme (task-011), the 404 marker and possibly the feed belong to the default theme. Don't design around that here: task-011's doc Must Have already lists what holds only for the default theme, and its plan names this command.
- Under `--offline`, the end-to-end test skips with the other wrangler tests (task-016). The fake-server tests always run.
- Standing obligations: strict static checks apply. The HTTP and parsing logic is importable and typed, not a script. Tests: a fake server for every failure branch, one real-wrangler run, and no test of a remote site.

## Plan
- [x] **Step 1** (new `src/mdblog/verify.py`, `src/mdblog/cli.py`): the four checks, reporting and exit status.
- [x] **Step 2** (`src/mdblog/theme/layouts/404.html`, `.claude/docs/hugo-site.md`): add the marker with a comment saying why, and point to it from `hugo-site.md` without copying its value.
- [x] **Step 3** (new `tests/test_verify.py`, `tests/test_site.py`, `tests/test_stage.py`): fake-server branch tests, the marker test, and the end-to-end test replacing task-016's direct assertions.
- [x] **Step 4** (`README.md`, `docs/vault-format.md`): document the command and the override rule.

## Review log

### Round 1: APPROVED
- **N1: Unwrapped docstring line** (`src/mdblog/build.py:113`): the edited `hugo_config` docstring line runs to 108 characters where its neighbors wrap near 88. Ruff ignores E501, so the gate passes; rewrap it.
- **N2: Timeout is per socket operation** (`src/mdblog/verify.py`, `fetch`): urllib applies `timeout` to each connect and read, so a server trickling its response can hold one request past `TIMEOUT`. The Must Have still holds, but the `TIMEOUT` comment ("connecting and reading included") claims slightly more than urllib guarantees.

### Round 2: APPROVED
- The doc-hygiene pass (9127d55) fixed round 1's N1 and N2. Its verifier found that a timeout while reading an error response's body escaped `fetch` as a bare `TimeoutError`, breaking the Must Have that a timeout fails only its own check. 391a7ee nests the `try` so the outer handlers cover that read, and adds a `404 page` case to `test_a_timeout_fails_only_the_slow_request` that stalls after the headers. The case costs about 0.33 s because the fake server's handler threads are daemons. `tools/check` exits 0 (707 passed).
