---
id: task-019
title: "Post summaries from a summary callout"
---

# task-019: Post summaries from a summary callout

## Summary
A post can open with an Obsidian `> [!summary]` callout holding a short lede. That text becomes the post's summary on the home page, tag pages, archive, `recent.json` and link-preview descriptions, and is left off the post's own page. A post without one gets a shortened plain-text excerpt in all the same places, so every listing agrees, and M6 POSSE can later reuse the lede as a copy's intro.

## Must Have
- [ ] A published note whose body's first block, after `%%` comments are removed, is a callout of type `summary` (any case, any title, with or without a `-`/`+` fold marker) has that callout removed from its post page, and the callout's content is the note's lede.
- [ ] A `[!summary]` callout that is not the body's first block renders as an ordinary callout and sets no lede, and so does a first-block callout of any other type, `[!abstract]` and `[!tldr]` included.
- [ ] A lede callout with no content is removed from the post page, and the note falls back to the excerpt.
- [ ] For a note with a lede, the `p-summary` element on the home page, on each tag page listing it and on the archive page holds the lede as HTML: inline formatting kept, and each wikilink converted to its root-relative URL as in the body. The post page's `<meta name="description">` and `og:description`, and its `recent.json` item's `summary`, hold the same text as plain text, with each whitespace run collapsed to one space.
- [ ] A note with both a lede and a `<!--more-->` divider shows the lede in all five places above.
- [ ] For a note without a lede, all five places hold one identical plain-text excerpt: the plain text of Hugo's summary (the text before `<!--more-->` when present), cut at a word boundary to at most `EXCERPT_LENGTH` characters plus a trailing `…` only when cut. A list's `p-summary` excerpt holds no HTML element, so footnote links no longer reach list pages.
- [ ] `EXCERPT_LENGTH` is a constant in `src/mdblog/build.py` that reaches the layouts as site config the way the `*_LIMIT` constants do, and the excerpt test derives its expectations from the constant.
- [ ] The build fails, naming the note, when a lede holds anything other than paragraphs of inline Markdown (a list, heading, code block, table, thematic break, quote or nested callout, or an image or `![[...]]` embed), a footnote reference, or a standard Markdown link whose destination starts with `#`. A wikilink in a lede follows the body's rules, so a broken one fails the build as it would in the body.
- [ ] Under `mdblog serve --drafts`, a lede that would fail the build prints a warning, stays on the post page as an ordinary callout, and the note uses the excerpt.
- [ ] Each `recent.json` item has exactly the string keys `date`, `summary`, `title` and `url`, and `home.recent.json`'s contract comment states the `summary` key.
- [ ] A vault `summary` or `description` property has no effect on the site: `test_properties_hugo_would_read_do_not_change_the_site` includes both.
- [ ] Feeds keep full content in `<description>`, and the home page's own meta description still comes from the bio, as before.
- [ ] `docs/vault-format.md` documents the summary callout: its syntax, first-block rule, allowed content, the empty case and the build failures. `.claude/docs/hugo-site.md` records how the lede reaches the layouts and names `EXCERPT_LENGTH`.
- [ ] `bug-003` is deleted from `.claude/docs/bug-log.md` in the commit that makes list excerpts plain text.
- [ ] The manual-QA check `summaries` in `tools/manual_qa.py` passes in a log from the author.
- [ ] `tools/check` exits 0 on the finished branch.

## Advice
- User decisions (2026-11-09): the lede lives in the body as a first-block `> [!summary]` callout, not a property. Obsidian Publish and Quartz read `description` only as SEO metadata, and the author wants visible text. Only type `summary` counts, and only as the first block, so a closing recap callout further down stays put. The lede is paragraphs of inline Markdown with wikilinks, and the callout's title and fold marker are ignored. The post page does not show it. Home and tag lists, the archive, `recent.json` and meta/og descriptions always agree. Each shows the lede, or for a post without one, a plain-text excerpt truncated at a word boundary and shorter than Hugo's 70-word default. The excerpt length is one theme-wide constant, not a site key. `recent.json` has no outside consumers yet, so changing its contract is fine.
- Hugo 0.169 facts, verified in a scratch site: `<!--more-->` beats front matter `summary` for `.Summary`; front matter `summary` renders as Markdown; `summaryLength` keeps whole paragraphs, so it cannot cut below a post's first paragraph. So do not hand the lede to Hugo's `summary` key, and do not shorten excerpts with `summaryLength`. Put the converted lede Markdown in a page param under `params` (the `mdblog_` prefix, as `INVALID_PARAM` uses), and have one partial decide lede-or-excerpt and produce both its HTML and its plain text, so the five places cannot drift apart. Truncate with Hugo's `truncate` on the plain text, and check its word-boundary and ellipsis behavior against the Must Have with real Hugo.
- `front_matter` builds Hugo's front matter from scratch (`.claude/docs/hugo-site.md`, No pass-through), so a vault `summary` or `description` property stays inert. The colliding-keys test guards that.
- The converter in Python finds and removes the lede, because Hugo draws callouts in `render-blockquote.html` and Python never parsed them. Find the first block with the markdown-it parser `markdown.py` already uses, so a `> [!summary]` inside a code block or after other content never matches. Convert the lede's wikilinks with the same converter and note path as the body, so relative targets and failures match. A lede link with a `#` destination or a footnote reference would point at the list page it is shown on (bug-003's class), which is why those fail.
- Keep the extracted lede Markdown as a typed field on the converted note, so M6 can read it without parsing the body again.
- Starting value `EXCERPT_LENGTH = 160` characters, about a search snippet's length. The author tunes it through the manual-QA check. A changed value needs no doc edit, because docs name the constant.
- Plain-text excerpts in lists drop links and footnote references, which fixes bug-003's list symptom. Entry pages and feeds were already correct. The fixing commit deletes the entry, per the bug log's rules.
- Standing obligation, strict static checks: new Python is fully typed under pyrefly strict. Where markdown-it's token API forces it, narrow token attributes at that boundary with a comment.
- Standing obligation, scripts stay simple: no new scripts.
- Standing obligation, docs point to code: `docs/vault-format.md` gains the author rules (syntax, first-block rule, allowed content, empty case, failures) with no Hugo or theme terms. `.claude/docs/hugo-site.md` gains one bullet on the param, the partial and `EXCERPT_LENGTH`. `home.recent.json`'s comment owns the JSON contract. No doc copies the length's value.
- Standing obligation, test where the risk is: unit tests cover each extraction rule and failure message (first block, case, title and fold ignored, other types, later callout, empty, a comment before the callout, a code block that looks like a callout, each disallowed block, footnote reference, `#` link, broken wikilink) and the draft-mode fallback. Real-Hugo site tests on the fixture vault cover agreement across the five places, lede-beats-divider and truncation, because each fails silently. No test of Hugo's own Markdown rendering.
- Manual QA approved by the author on 2026-11-09 at 2d90ebd: they ran `tools/manual-qa summaries` and reported in conversation that it looks good, keeping `EXCERPT_LENGTH` at 160. No log path was handed back.

## Plan
- [x] **Step 1** (`src/mdblog/markdown.py` or a new `src/mdblog/summary.py`, `src/mdblog/links.py`, `src/mdblog/publish.py`): typed lede extraction that returns the body without the lede callout plus the lede Markdown or None, or failure reasons. Wire it after comment removal and before wikilink conversion, convert the lede's wikilinks with the body's converter, and carry the lede on the converted note. Under draft mode, failures become warnings and the callout stays in the body.
- [x] **Step 2** (`src/mdblog/properties.py` `front_matter`, `src/mdblog/build.py`): write the converted lede into a `params` key. Add `EXCERPT_LENGTH` to the site config the layouts read, beside `LIMIT_PARAMS`.
- [x] **Step 3** (`src/mdblog/theme/layouts/_partials/`, `entry-item.html`, `section.html`, `head.html`, `home.recent.json`, `assets/css/main.css`): one summary partial returning lede HTML or excerpt text plus its plain text. Lists and the archive render it in `p-summary`, `head.html` uses the plain text for post pages only, `recent.json` adds `summary` and its contract comment, and CSS styles the archive's summary line.
- [x] **Step 4** (`tests/fixtures/vault/projects/last-year.md`, `tests/fixtures/vault/projects/link-target.md`): give `last-year.md` a lede with emphasis and a wikilink, and a `<!--more-->` divider after its body text. Lengthen `link-target.md`'s first paragraph well past any plausible `EXCERPT_LENGTH` without touching its `## Details` heading or block ID. Update the tests these change: `Site.recent()`'s key check (`tests/test_site.py` ~142), the list-summary test (~412), the archive text assertions (~445-460), the description tests (~590-610), and any assertion on link-target's or last-year's page or list text found by grep.
- [x] **Step 5** (`tests/test_markdown.py` or `tests/test_summary.py`, `tests/test_build.py`, `tests/test_publish.py`, `tests/test_site.py`): unit and site tests per Advice; add `summary` and `description` to the colliding-keys test.
- [x] **Step 6** (`tools/manual_qa.py`): check `summaries` serving the scratch fixture vault. The author reviews the home page, the archive and a tag page, confirms `last-year` shows its lede and its post page has no summary callout, judges whether excerpts at `EXCERPT_LENGTH` read well, and notes a preferred length.
- [x] **Step 7** (`docs/vault-format.md`, `.claude/docs/hugo-site.md`, `templates/Post Template.md`, `.claude/docs/bug-log.md`): document per Advice. Add an empty `> [!summary]` callout as the template's body, since an empty one counts as none. Delete `bug-003`.

## Review log

### Round 1: REJECTED
- **F1: Excerpts pick up footnote markers and footnote text** (`src/mdblog/theme/layouts/_partials/summary.html:13`): `.Summary | plainify` turns a footnote inside Hugo's summary into plain text, so a short post with a footnote shows `A claim1 that ... The note. ↩︎` in all five places, and footnote content still reaches list pages after bug-003's deletion. Strip Goldmark's footnote reference `<sup>` and footnotes section before `plainify`, and add a site test with a footnote inside the excerpt.
- **N1: The template's empty callout can swallow the first paragraph** (`templates/Post Template.md:9`): text typed on the line after `> [!summary]` lazily continues the callout and becomes the lede; end the template with a blank line.
- **N2: The user doc's failure list leaves out HTML blocks** (`docs/vault-format.md:69`).
- **N3: One very long word is cut mid-word** (`src/mdblog/theme/layouts/_partials/summary.html:15`): Hugo's `truncate` cuts a single word longer than `EXCERPT_LENGTH`; rare, non-blocking.
- **N4: Two fields share one comment** (`src/mdblog/markdown.py:374`): `LedeCallout.start` and `end`.
- **N5: Manual QA approved without a log** (`tasks/active/task-019-post-summaries.md`): accepted, since Advice records the author's decision.
