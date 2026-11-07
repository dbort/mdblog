---
id: task-010
title: "Make every entry a plain post"
---

# task-010: Make every entry a plain post

## Summary
Removes the TIL and link entry types, so every published note is the same kind of post. The `type` property is no longer required and has no effect, and neither does `url`. The site loses its per-type feeds, the TIL and Link labels and the link-entry markup, and the code and docs that supported them go too.

## Must Have
- [ ] A published note with no `type` property builds. A note carrying `type: til`, `type: nonsense`, `url: not a url` or a null `type` builds output byte-identical to the same note without those lines.
- [ ] `validate_properties` reads only `title`, `date`, `slug` and `tags`, and its failures never mention `type` or `url`.
- [ ] Generated Hugo front matter holds only `title`, `date` and `tags` when there are any. It holds no `params` key.
- [ ] `type` appears in the Hugo-collision test's colliding note and in the `docs/vault-format.md` § Hugo collisions table, with what Hugo would do with it (select a different layout type).
- [ ] A fixture build contains exactly two kinds of feed: `/index.xml` and `/tags/<tag>/index.xml`. No path under `types/` exists in the output, and `hugo_config` lists only `html` and `rss` as home outputs and defines no custom output format.
- [ ] No page in a fixture build contains `entry-label`, `u-bookmark-of` or `e-content entry-content` inside a list item. Every list item holds a `p-summary`, and every feed item's description starts with the entry's own content.
- [ ] Each page's `<head>` advertises `/index.xml`, and a tag page also advertises its own tag feed. No other feed is advertised.
- [ ] `src/mdblog/theme/layouts/home.postfeed.xml`, `home.tilfeed.xml`, `home.linkfeed.xml` and `_partials/entry-label.html` no longer exist.
- [ ] `git grep -nE 'entry_type|link_url|ENTRY_TYPES|LINK_ENTRY|tilfeed|linkfeed|postfeed|u-bookmark-of' -- src tests docs README.md` prints nothing.
- [ ] `docs/vault-format.md` lists no `type` or `url` property row, describes no per-type feed or link entry, and says only folder and file name have no effect on a page's URL.
- [ ] `tools/check` exits 0 on the finished branch.

## Advice
- User decisions (2026-11-06): one entry type. `type` is ignored on every note like any other unread property, with no failure for old values, since there is no real content yet. The roadmap and task-007 and task-009 are already rewritten for this; leave them alone.
- `url` stays in the Hugo-collisions table because a vault property named `url` must still never reach Hugo. `type` joins that table for the same reason: Hugo reads front matter `type` to pick layouts. Front matter is written from scratch, so both stay out with no special code.
- Every page stays at `/posts/<slug>/`, and h-entry markup on entry pages and lists is otherwise unchanged (`h-entry`, `p-name`, `u-url`, `dt-published`, `p-category`, `p-author`, `p-summary` in lists, `e-content` on the entry page). M6 and M7 read it.
- Inline `_partials/entry-title.html` into its callers or keep it as a plain permalink, whichever leaves fewer files; either way no title links off the site.
- Fixture notes `tests/fixtures/vault/projects/til-one.md`, `old-til.md` and `a-link.md` stay published posts with their slugs, dates and tags, so ordering, timezone and tag tests keep their meaning. Drop their `type` and `url` lines and every other fixture note's `type` line. Renaming them or their `FIXTURE-TIL-*` needles is optional; `tests/test_serve_hugo.py` names `til-one` and `FIXTURE-TIL-BODY`, so a rename must update it too. Add no text matching the `UNPUBLISHED-*` needles.
- Affected tests, each of which changes: `tests/notes.py` (`published_text` loses `entry_type` and writes no `type` line), `tests/test_properties.py` (type and link-url rules and front-matter params), `tests/test_publish.py` (type failure messages near lines 160-180 and 242-249), `tests/test_build.py` (theme file list near line 186, the collision test near line 375 gains `type` and loses the `entry_type` cascade, the layout-override test near line 660 stops reading params), `tests/test_site.py` (type feeds in the expected file list, labels, link-entry and bookmark assertions, the feeds-only test, the 51-entry feed test).
- User decision (2026-11-06, during `/work`): fixtures that existed only for the TIL and link cases are removed or renamed. None was removable, since each still covers something else, so all three are renamed: `til-one` to `offset-time` (offset datetime, ordering, tag), `old-til` to `last-year` (second archive year), `a-link` to `link-target` (heading and block wikilink target), with their needles and titles to match. `tests/test_serve_hugo.py` loses its rewrite of the link note's `example.test` URL, which the fixture no longer holds.
- No manual QA: the change removes markup and feeds that tests assert directly, and task-007 reviews the design in a browser afterward.
- Standing obligation, strict static checks: changed code in `properties.py` and `build.py` stays typed under pyrefly strict; removing `link_url` and `entry_type` from `PageProperties` must leave no `Optional` or `object` behind.
- Standing obligation, scripts stay simple: no scripts are added or changed.
- Standing obligation, test where the risk is: delete tests of the removed rules rather than inverting each one. Add one properties unit test that `type` and `url` values, including invalid ones, leave the result unchanged, and extend the collision test with `type`. Keep the real-Hugo site tests that pin the feed list and list markup, because a stray type feed or label would ship silently.

## Plan
- [x] **Step 1** (`src/mdblog/properties.py`, `tests/notes.py`, `tests/test_properties.py`, `tests/test_publish.py`): drop `ENTRY_TYPES`, `LINK_ENTRY`, `URL_SCHEMES`, `_entry_type`, `_link_url`, `_is_web_url` and the `entry_type` and `link_url` fields; front matter writes no `params`; update docstrings to the new contract.
- [x] **Step 2** (`src/mdblog/build.py`, `src/mdblog/theme/layouts/`, `tests/test_build.py`): `hugo_config` renders only the site feed on the home page plus tag feeds; delete the three per-type feed layouts and `entry-label.html`; list items, entry titles and feed items render every entry as a post.
- [x] **Step 3** (`tests/fixtures/vault/`, `tests/test_site.py`, `tests/test_serve_hugo.py` if renamed): fixtures without `type` or `url`; site tests assert the single-type output and the exact feed list.
- [x] **Step 4** (`docs/vault-format.md`): remove the `type` and `url` rows, link-entry and per-type feed text, the `params` description under § Generated front matter, and the retyping sentence; add `type` to § Hugo collisions.

## Review log

### Round 1: APPROVED
- **N1: Test variable named after removed concept** (`tests/test_site.py:258`, `tests/test_site.py:323`): the `a-link` entry is bound to `unlabeled`, a name that only means something to a reader who remembers labels; `entry` or `a_link` describes it as the code stands. Cosmetic.
- **N2: Redundant trailing assertion** (`tests/test_site.py:533-534`): the loop already checks every site-feed item's first block against its page's `e-content`, so the extra `a-link` `startswith` check adds little. Harmless.
