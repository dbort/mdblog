---
id: task-003
title: "Write front matter from a fixed property list and place pages by slug"
blocked_by: [task-002]
---

# task-003: Write front matter from a fixed property list and place pages by slug

## Summary
Stops vault properties from changing the site by accident: the converter writes each page's Hugo front matter from scratch using a short list of properties, and drops everything else. Every published note lands at `/posts/<slug>/` whatever its vault folder, and a published note with a missing or invalid `date`, `slug` or `type` fails the build. Note bodies still pass through unchanged until task-004 converts Obsidian syntax.

## Must Have
- [ ] A published note builds at `/posts/<slug>/`. A test moves a note to another vault folder and renames its file, and asserts the output tree is byte-identical.
- [ ] Generated front matter parses to a mapping holding only `title`, `date`, `tags` (only when non-empty) and `params`, and `params` holds only `entry_type` plus, on a link entry, `link_url`.
- [ ] A test builds one vault with a note carrying `aliases`, a clipped `url`, `weight`, `published`, `expiryDate`, `headless`, `build`, `layout`, `draft`, `cascade` and `outputs`, and a second vault with the same note without them, and asserts the two output trees are byte-identical.
- [ ] `title` comes from the `title` string. A missing or null `title` comes from the file name without `.md`, and any other type fails the build.
- [ ] `date` must be a YAML date or datetime. A missing, null or other value fails the build, and so does a date after the local date or a datetime after the current time.
- [ ] A note dated with today's local date builds and is present in the output in any time zone: a test with real Hugo uses a date that is already today locally and still in the future in UTC.
- [ ] `slug` is required and matches `^[a-z0-9]+(-[a-z0-9]+)*$`. Anything else fails the build.
- [ ] `type` is required and is exactly `post`, `til` or `link`. It reaches layouts as `.Params.entry_type`. A missing or other value fails the build. Hugo's own `type` key is never written.
- [ ] A `type: link` note requires `url`, an `http` or `https` URL string, which reaches layouts as `.Params.link_url`. Any other value fails the build. On `post` and `til` notes, `url` has no effect, whatever its value.
- [ ] `tags` may be missing, null, one string or a list of strings. Any other value fails the build. `project/alpha` builds a tag page at `/tags/project/alpha/`.
- [ ] Two published notes with the same `slug` fail the build, and the message names both notes.
- [ ] These rules apply only to published notes: an unpublished note with no `date`, `slug` or `type` causes no failure. A bad `publish` value still fails for any selected note.
- [ ] One run reports every failure across all published notes, naming the note and reason for each, and leaves the output directory unchanged.
- [ ] A published note's body after its front matter reaches Hugo byte-for-byte.
- [ ] `docs/vault-format.md` lists each property the converter reads, its meaning and validation, and each tested Hugo collision. A test asserts the file names every property the converter reads.
- [ ] `tools/check` exits 0 on the finished branch, with real Hugo tests carrying the `hugo` mark.

## Advice
- User decisions: every entry type lives at `/posts/<slug>/`, so slugs are unique across the site and changing a note's type never moves it. `type` and `slug` are required on published notes. Slugs are lowercase ASCII, so URLs copy cleanly and two slugs cannot collide on a case-insensitive filesystem.
- Nested tags keep Hugo's nested paths, by user decision. A parent such as `/tags/project/` may have no page of its own, and this task does not change that.
- Write a page as `content/posts/<slug>/index.md`. A leaf bundle gives task-004 a place for attachments, and Hugo copies a bundle's files next to the page. Do not write Hugo's `slug` or `url`: the folder sets the URL, and a generated `url` adds a second source for it.
- Build the front matter as a data structure and serialize it, so a title holding `: ` or quotes stays valid. Never concatenate strings into YAML.
- The list of read properties is the extension point. Do not add a key allowlist or pass any property through by name, because `aliases`, `url` and `weight` are valid Hugo keys that change the site (`docs/roadmap.md` § M2 records the evidence, and this task moves it to `docs/vault-format.md`).
- Run Hugo with `--buildFuture`. The converter owns the future-date rule because Hugo compares date-only values as UTC midnight, so a note dated today can be hidden with no warning at some local times. A future-dated note fails the build because nothing rebuilds the site when the date arrives, and scheduled publishing is outside v1.
- A date is compared at date precision when the property holds a date, and at instant precision when it holds a datetime. A naive datetime means local time. Take the clock as a parameter in the validation function, so tests are deterministic.
- `ruamel.yaml` returns `datetime.date` or `datetime.datetime`. A quoted `"2026-01-01"` is a string and fails, since Obsidian's date property writes it unquoted.
- A null property means missing, because Obsidian writes an empty property as null.
- Standing obligation, strict static checks: the validated note is a frozen dataclass with precise field types. Narrow from `object` with `isinstance` checks instead of casts.
- Standing obligation, scripts stay simple: all logic is Python in importable functions, tested directly.

## Plan
- [ ] **Step 1** (`src/mdblog/properties.py`, tests): a function taking a note's parsed front matter, its file name and the clock, returning a validated value or every failure for that note. Cover each Must Have rule directly.
- [ ] **Step 2** (`src/mdblog/publish.py`, `src/mdblog/build.py`, tests): write validated pages to `content/posts/<slug>/index.md` with generated front matter and the original body. Detect slug collisions across notes, report all failures in one run, and pass `--buildFuture` to Hugo.
- [ ] **Step 3** (`tests/fixtures/vault/`): add `type`, `slug` and `date` to `projects/first-note.md` and every other published fixture note, and add a `type: link` note.
- [ ] **Step 4** (`tools/check_runner.py`, `tests/test_check_runner.py`, tests from task-002): `FIXTURE_PAGE` becomes `posts/first-note/index.html`. `test_hugo_build_fails_when_the_note_text_is_missing` writes a note with full valid properties, so it fails for the intended reason. `test_hugo_build_fails_when_the_page_is_not_generated` renames the note today, which no longer changes the URL, so it changes the note's `slug` instead. Grep task-002's tests for `projects/first-note`, relative-path placement assertions, and notes holding only `publish: true`, and update each: published test notes need the required properties, so add a shared helper that writes them.
- [ ] **Step 5** (`docs/vault-format.md`): the property reference. Move the collision evidence there from the roadmap's M2 section.

## Review log
