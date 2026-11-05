---
id: task-003
title: "Write front matter from a fixed property list and place pages by slug"
blocked_by: [task-002, task-005]
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
- [ ] `docs/vault-format.md` lists each property the converter reads, its meaning and validation, and each tested Hugo collision.
- [ ] `tools/check` exits 0 on the finished branch.

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
- Standing obligation, test where the risk is: the property rules and page placement are novel code, so unit tests cover each rule and message. Real Hugo runs in the end-to-end fixture build and in the time-zone Must Have, because Hugo hides that page silently. The byte-identical output trees may use real Hugo or the fake, whichever proves it.
- 2026-11-04: generated front matter is JSON, which Hugo reads natively when a page starts with `{`. JSON has one reading of each string, where a YAML reader could take a title of `yes` for a boolean, and needs no serializer settings. Tested on Hugo 0.169 with quotes, braces, `yes` and `123`.
- 2026-11-04, user request: this task also closes task-005's review note N2, by asserting the rendered value in the `publish` error (`not 'yes'`).

## Plan
- [x] **Step 1** (`src/mdblog/properties.py`, tests): a function taking a note's parsed front matter, its file name and the clock, returning a validated value or every failure for that note. Cover each Must Have rule directly.
- [x] **Step 2** (`src/mdblog/publish.py`, `src/mdblog/build.py`, tests): write validated pages to `content/posts/<slug>/index.md` with generated front matter and the original body. Detect slug collisions across notes, report all failures in one run, and pass `--buildFuture` to Hugo.
- [x] **Step 3** (`tests/fixtures/vault/`): add `type`, `slug` and `date` to `projects/first-note.md` and every other published fixture note, and add a `type: link` note.
- [x] **Step 4** (tests from task-002): grep task-002's tests for `projects/first-note`, relative-path placement assertions, and notes holding only `publish: true`, and update each: published test notes need the required properties, so add a shared helper that writes them.
- [x] **Step 5** (`docs/vault-format.md`): the property reference. Move the collision evidence there from the roadmap's M2 section.

## Review log

### Round 1: REJECTED
- **F1: A naive datetime is validated as local time but published as UTC** (`src/mdblog/properties.py:170`): `_is_future` treats a datetime with no offset as local, as the Advice and `docs/vault-format.md:13` both state. `front_matter` then writes `page.date.isoformat()` with no offset, and Hugo reads that as UTC, so the published instant is silently wrong by the local offset. Reproduced with `TZ=America/New_York` and real Hugo: `date: 2026-06-15T10:00:00` (14:00 UTC) rendered `<pubDate>Mon, 15 Jun 2026 10:00:00 +0000</pubDate>` and listed below a note dated `2026-06-15T11:00:00Z`, the earlier instant. Write the resolved local offset into the front matter, using the offset for that date, because `now.tzinfo` is a fixed offset and would be wrong across a DST change. Add a naive case to `test_front_matter_keeps_a_datetime_and_its_offset`.
- **F2: The production local clock has no test** (`src/mdblog/build.py:169`): the default `now or datetime.now().astimezone()` implements the "local date" rule and the "in any time zone" Must Have, and no test exercises it against a time zone. A scratch-copy mutation to `datetime.now(UTC)` passed all 211 tests. Add a test that calls `build_site` with no `now` under a zone set through `TZ` and `time.tzset`. A fake Hugo can prove this.
- **N1: Redundant flag test** (`tests/test_build.py:326`): `test_build_asks_hugo_to_keep_dates_validation_accepted` only asserts that a literal stays in the argv list. The real-Hugo test at `tests/test_build.py:602` already proves the behavior. Delete it.
- **N2: A tag string can escape `/tags/`** (`src/mdblog/properties.py:88`): `tags: "../../evil"` passes validation and real Hugo writes `/evil/index.html` at the site root. `tags: ""` and `tags: [""]` also pass, and Hugo produces no page for them. The Must Have only requires strings, so this does not block, but it cuts against the task's aim that properties should not change the site by accident. Consider a follow-up rule on tag segments.
- **N3: A lone surrogate in a title escapes failure reporting** (`src/mdblog/properties.py:176`): `title: "\ud83d"` loads from YAML and passes validation. `.encode("utf-8")` then raises `UnicodeEncodeError` as an uncaught traceback that names no note. It fails loudly, so under the test entry it needs no test.

### Round 2: APPROVED
- **N1: `astimezone()` can crash validation or produce an offset Hugo cannot parse** (`src/mdblog/properties.py:53`): it raises `ValueError` on the boundary dates `0001-01-01` and `9999-12-31` (for example `date: 9999-12-31T23:59:59`), so `mdblog build` ends in a traceback that names no note and hides the other notes' failures, with the output unchanged and exit status 1. A naive datetime from a zone's local-mean-time era resolves to an offset with seconds, such as `1880-01-01T00:00:00-04:56:02` in America/New_York, which Hugo rejects naming only a temporary path. Both are pathological input that fails loudly with the output intact, so `CLAUDE.md` § Test where the risk is requires no test. The first is still a narrow gap in "One run reports every failure". Catching `ValueError` around the conversion and reporting it through `_date` would close it.
- **N2: Round 1's N2 and N3 remain open** (`src/mdblog/properties.py:101`, `src/mdblog/properties.py:186`): both were non-blocking. `tags: ../../evil` still passes validation, and real Hugo still writes `/evil/` at the site root. This deserves a follow-up rule on tag segments or a decision to accept it. The title-encoding code is unchanged, so the lone-surrogate traceback should remain; not re-run.

Round 1 findings: F1 is fixed, confirmed with `TZ=America/New_York` and real Hugo, and mutations to no offset and to a fixed offset each fail a test. F2 is fixed: a `datetime.now(UTC)` mutation fails `test_build_judges_dates_by_the_local_clock`. Round 1's N1 is closed. `tools/check` exits 0 with 213 tests passing.
