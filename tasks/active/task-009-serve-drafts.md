---
id: task-009
title: "Preview drafts with mdblog serve --drafts"
blocked_by: [task-007, task-008]
---

# task-009: Preview drafts with mdblog serve --drafts

## Summary
Adds `mdblog serve --drafts`, which also shows entries still being written: unpublished notes that have a `type`. Missing dates and slugs are filled in from the file. Problems that would stop a production build are printed as warnings, and the note still renders. The page shows a "Draft" or "Invalid" label so the author can tell drafts and broken notes from finished entries, and a banner on every page says the site is a draft preview.

## Must Have
- [ ] `mdblog serve --drafts` renders each unpublished note (no `publish: true`) with a non-null `type` property as an entry with a "Draft" label beside its type label, on its entry page and in every list that shows it.
- [ ] An unpublished note with no `type`, or a null one, is absent from the preview, whatever its other properties.
- [ ] A draft with no `date` gets the file's modification time, in the local zone with its offset. A draft with no `slug` gets one generated from its file name, valid under the slug rule. Neither prints a warning.
- [ ] A draft property that is present but invalid prints one warning naming the note and property. The note still renders: an invalid date falls back to the modification time, an invalid slug to the file-name slug, invalid tags to no tags, an invalid `type` to `post`, and a link entry without a valid `url` to `post`.
- [ ] A draft dated in the future renders with that date and no warning.
- [ ] A generated or fallback slug that collides with another note's slug gets the first free numeric suffix (`-2`, `-3`, ...). A note's own valid slug always wins over a generated one, and each suffixed slug prints a warning.
- [ ] A note with `publish: true` that fails validation in any way, link failures included, renders with the same fallbacks, an "Invalid" label in place of "Draft", and one warning per failure. A future date on such a note is kept.
- [ ] A failed wikilink, embed or internal Markdown link in any note or the bio stays on the page exactly as written and prints a warning. A wikilink to a draft converts into a link to the draft's page.
- [ ] A note whose front matter does not parse, has a non-boolean `publish`, or is not UTF-8 is absent and prints a warning.
- [ ] Every page carries a banner saying it is a draft preview and not the live site. The banner appears only under `--drafts`.
- [ ] Note failures never stop or delay `serve --drafts`: it starts on a vault with failing notes, and each rebuild prints the current warnings to stderr. A `ConfigError` still waits for a fix, as plain `serve` does.
- [ ] Without `--drafts`, `mdblog serve` output is identical to before this task. `mdblog build` accepts no `--drafts` option, never passes `--buildDrafts` to Hugo, and no build output contains a draft, the Draft or Invalid label, or the banner.
- [ ] The Draft label, Invalid label and banner are styled in light and dark palettes, with WCAG AA contrast, in the stylesheet task-007 adds.
- [ ] `docs/vault-format.md` documents draft mode's selection, fallbacks, labels and warnings, and `README.md` lists `--drafts`.
- [ ] Manual QA by the author: under `serve --drafts` on a vault holding a draft, an invalid published note and a valid published note, the labels and banner read clearly at phone and desktop widths in both palettes.
- [ ] `tools/check` exits 0 on the finished branch.

## Advice
- User decisions (2026-11-05): draft mode is a `--drafts` flag on `mdblog serve` only, so `mdblog build`, which feeds deploys, can never produce draft output. Drafts are unpublished notes with a `type`, because M5's entry templates set `type` and leave out `publish` and `date`, and the rest of the vault (journals, reference notes) stays off the preview. A missing date falls back to the file's modification time and a missing slug to the file name. A missing date or slug on a draft is expected, so only present-but-invalid values warn. An invalid published note renders labeled "Invalid". A failed link stays as written, which shows the author where it is. Every page carries a draft-preview banner. This task follows task-007 so its labels and banner fit the finished design.
- Generate `draft: true` in the Hugo front matter of each draft and run Hugo with `--buildDrafts`, so `.Draft` drives the Draft label and Hugo's own rules keep drafts out of any build without the flag. Mark an invalid published note with a generated param such as `params.mdblog_invalid`, and turn the banner on with a site param written into `hugo.toml` only in draft mode. Vault properties are never passed through to Hugo (`docs/vault-format.md` § Hugo collisions), so a vault's own `draft` property still has no effect.
- Keep production selection and validation unchanged, and add draft mode as an explicit parameter, such as `drafts: bool` on `select_notes` and `convert_notes`, defaulting to off. Production behavior must not depend on anything draft mode adds.
- In draft mode, conversion keeps a page whose links failed and turns its failures into warnings. Converted text already leaves a failed link as written. Drafts join the link index as published targets, so links and embeds of drafts render normally.
- Generate a slug from a file name by lowercasing it, mapping each run of characters other than ASCII letters and digits to one hyphen, and trimming hyphens. If nothing remains, as with a name in a non-Latin script, use `note`. Assign slugs in two passes: notes with a valid slug of their own keep it, then generated and fallback slugs take suffixes in path order. When two published notes share a slug, the first by path keeps it and the rest are invalid and suffixed.
- Print warnings in `mdblog build`'s failure format (`path: reason` lines) under a heading that says they are warnings, after each rebuild.
- Feeds under `--drafts` include drafts, which is Hugo's behavior under `--buildDrafts`. The preview's feeds are never published.
- Write draft-mode tests against temporary vaults built in the test, not the shared fixture vault. The fixture's unpublished notes carry `UNPUBLISHED-*` needles that production tests assert are absent, and new typed drafts there would also change what draft-mode tests see.
- Standing obligation, strict static checks: all new and changed code stays typed under pyrefly strict.
- Standing obligation, scripts stay simple: no shell scripts. Selection, fallbacks and slug assignment are importable functions.
- Standing obligation, test where the risk is: unit-test every selection rule, fallback, warning text, slug generation and collision case, and the invalid-published path, with no Hugo. Use real Hugo for the Draft label, Invalid label and banner under draft mode, and for the guarantee that a plain build of a vault with typed drafts contains none of them, since a break there would silently put drafts or labels on the live site. Leave the label and banner styling to manual QA.

## Plan
- [ ] **Step 1** (`src/mdblog/publish.py`, `src/mdblog/properties.py`, tests): draft-mode selection, with the typed-unpublished rule, modification-time and file-name fallbacks, slug assignment, an entry status of published, draft or invalid, and warnings.
- [ ] **Step 2** (`src/mdblog/links.py`, `src/mdblog/properties.py`, tests): draft-mode conversion that keeps pages whose links failed and reports warnings, and front matter carrying `draft: true` or the invalid param.
- [ ] **Step 3** (`src/mdblog/build.py`, `src/mdblog/serve.py`, `src/mdblog/cli.py`, tests): the `--drafts` flag on `serve`, `--buildDrafts` and the banner param in draft mode only, and warnings printed after each rebuild.
- [ ] **Step 4** (`src/mdblog/theme/layouts/`, `src/mdblog/theme/assets/css/main.css`, tests): the Draft and Invalid labels beside the type label in entry pages and lists, the banner in the base layout, and their styles in both palettes. Keep every class and element the existing site tests read.
- [ ] **Step 5** (`docs/vault-format.md`, `README.md`): document draft mode.
- [ ] **Step 6**: run the manual QA with the author and record their approval, dated, in `## Advice`.

## Review log
