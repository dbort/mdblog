---
id: task-014
title: "Add mdblog check and a post template"
---

# task-014: Add mdblog check and a post template

## Summary
`mdblog check VAULT` runs a full production build into a throwaway directory and reports anything that would stop the site from publishing, with no output directory to manage. The repo also gains an Obsidian post template that starts each note as a draft. The docs say where to keep it so its unfilled placeholder never breaks a build.

## Must Have
- [ ] `mdblog check VAULT` on the fixture vault exits 0 and prints one line to stdout giving the number of notes that would publish.
- [ ] `mdblog check` writes nothing under the vault or the current directory, and leaves no temporary directory behind after a success, a note failure or a Hugo failure.
- [ ] On a vault with failing notes, `mdblog check` exits 1 and prints to stderr the same failure text `mdblog build` prints for that vault.
- [ ] On an unusable `_site/mdblog.toml`, `mdblog check` exits 1 with the same `ConfigError` message `mdblog build` prints.
- [ ] When Hugo fails, for example on a `_site/layouts/` override with a template syntax error, `mdblog check` exits 1 with the same message `mdblog build` gives for that failure.
- [ ] `templates/Post Template.md` holds exactly the front matter in `## Advice` and no body.
- [ ] A test replaces `{{date:YYYY-MM-DDTHH:mm:ssZ}}` in the template with a timestamp in that format, such as `2026-11-07T14:03:22-08:00`, and reads the result through mdblog's front-matter and draft-property code. It finds `publish` false, `created` a timezone-aware datetime, no warnings, and the file-name title and slug and the modification-time date as fallbacks.
- [ ] `README.md` documents `mdblog check`. `docs/vault-format.md` documents the template: copy it to `_site/Templates/Post Template.md` and set the folder of Obsidian's Templates core plugin to `_site/Templates`. It explains why the template lives in `_site/`, and the `_site/` table gains a `_site/Templates/` row.
- [ ] `tools/check` exits 0 on the finished branch.

## Advice
- The template's front matter, as the author specified it:
  ```
  ---
  publish: false
  slug:
  title:
  tags: []
  date:
  created: {{date:YYYY-MM-DDTHH:mm:ssZ}}
  ---
  ```
  Keep the placeholder unquoted. After Obsidian fills it in, `created` is a YAML datetime with an offset, which mdblog ignores. Before that, `{{...}}` is a YAML flow mapping with a mapping as its key, which ruamel rejects. Any `.md` outside `_site/` fails `mdblog build` on invalid YAML and warns under `serve --drafts`, so the template has to sit under `_site/`, which mdblog never reads as notes.
- Empty `slug`, `title` and `date` are null, which counts as missing. A draft falls back for each. On publish, an empty `date` or `slug` fails the build, but an empty `title` silently becomes the file name. Say so in the doc.
- `check` runs the real build: call `build_site` into a `tempfile.TemporaryDirectory`. A broken `_site/layouts/` override then fails `check` as it fails `build`, and the publish trigger in M5 relies on that. Reusing `build_site` keeps the two commands' errors identical without a second code path.
- `check` takes no `--output` and no `--drafts`. It answers one question: would `mdblog build` succeed now.
- Put the template parse test in the test module for draft properties. Run it through the same functions `select_notes` uses, rather than a bare YAML load, so it breaks if the draft rules change.
- Standing obligations: strict static checks apply. No shell scripts. Tests: one CLI test per Must Have exit path, using a fake `hugo` (see `tests/test_cli.py`) for the Hugo-failure case, and no new real-Hugo test, since `check` reuses `build_site`.
- No manual QA. Obsidian's fill-in of `{{date:...}}` is outside mdblog, and the author sees the result the first time they use the template.

## Plan
- [ ] **Step 1** (`src/mdblog/cli.py`, `src/mdblog/build.py` if a count needs exposing): add `check VAULT`. It runs `build_site` into a temporary directory, prints the published-note count on success and maps errors exactly as `build` does.
- [ ] **Step 2** (`tests/test_cli.py`): cover success, note failure, config failure and Hugo failure. Check that no files remain in the vault, the current directory or the temp directory.
- [ ] **Step 3** (`templates/Post Template.md`, the draft-properties test module): add the template and its parse test.
- [ ] **Step 4** (`README.md`, `docs/vault-format.md`): document `check` and the template setup.

## Review log
