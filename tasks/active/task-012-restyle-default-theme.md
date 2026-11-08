---
id: task-012
title: "Restyle the default theme with serif text, ivory and dark palettes, and a sidebar"
blocked_by: [task-009]
---

# task-012: Restyle the default theme with serif text, ivory and dark palettes, and a sidebar

## Summary
The default theme gets a new look modeled on two sites the author likes: serif body text and a dark palette from ludic.mataroa.blog, and an ivory light palette and a right-hand sidebar from wheresyoured.at. The bio moves from the top of the home page into the sidebar, alongside recent posts and top tags.

## Must Have
- [ ] Every page, the 404 page included, has an `<aside class="sidebar">` after `<main>` holding, in order: an About section with the bio (when `_site/bio.md` exists), Recent posts, and Tags (when any tag exists).
- [ ] The home page's `<main>` holds no bio. The bio renders in the sidebar on every page, and its embedded image's `src` resolves from an entry page and under a `base_url` with a path such as `https://example.test/blog/`.
- [ ] Recent posts lists the five newest entries other than the current page, newest first, each with its title and date, followed by a link to `/posts/`. With no other entries, the section is omitted.
- [ ] Tags lists at most ten tags, ordered by entry count with the highest first and ties by name, each with its count, followed by a link to `/tags/`.
- [ ] The header holds a brand link to the home page reading the site title, preceded by `« ` on every page except the home page, and a nav with the All posts and All tags links. The footer holds the copyright and an RSS link.
- [ ] The stylesheet still contains no `@font-face` or `@import`, and no page contains `<script` (task-007's tests stay green).
- [ ] Manual QA by the author: a fixture build under `mdblog serve` matches the decisions in `## Advice` at phone width (375px) and desktop width, in light and dark modes, on the home page, archive, tag index, a tag page, an entry page and the 404 page, plus task-009's draft labels and banner under `--drafts`, and no page scrolls sideways.
- [ ] `tools/check` exits 0 on the finished branch.

## Advice
- User decisions (2026-11-06). Visual reference: the mockup at https://claude.ai/artifact/5enBLueAcKroP13hxFv6me, variant "Blue in dark + red in light" (read it with the Artifact tool). The values below govern where the two differ.
  - Type: body and list text use `Charter, "Bitstream Charter", "Sitka Text", Cambria, serif` at 1.125rem, line-height 1.6, `max-width: 66ch`. Headings, the brand link, nav, dates, meta and the sidebar use the system sans stack. Headings are weight 500, and the page's `h1` gets a 2px bottom rule in the border color. No web fonts.
  - Light palette (wheresyoured.at "ivory"): background `#efe7dc`, text `#231b10`, muted about `#6b5a45`, border `#d6c2a8`, tinted surface `#e7dbcb`, links `#b00000`, ring markers `#dd0000`, code background `#f7f2ea`. The ring red is decoration only and never text, because `#dd0000` on ivory is 4.2:1.
  - Dark palette (Ludicity, text softened): background `#212529`, text `#e9ecef`, muted `#b1b6bb`, border `#353535`, surface and code background `#2b2b2b`, links and ring markers `#70b3ff`.
  - Links: a single thin underline (1px, offset about 0.2em) on links inside post, summary and bio text. Nav, list titles, dates, meta and sidebar links have no underline until hover. No double underlines.
  - Entry titles in lists (the `entry-item` partial on the home and tag pages) use the link color in both modes, red in light and blue in dark, and underline on hover. Plain text color left them hard to tell from summaries in dark mode. Archive and tag-index titles stay in the text color.
  - Layout: one grid with the sidebar on the right (about 16.5rem) from roughly 60rem up. Below that, one column with the sidebar after `<main>` and before the footer. The sidebar is not sticky.
  - Sidebar sections are boxes with a 1px border in the border color and 10px radius, each headed by a small uppercase sans label with a 10px ring marker in the accent color. The border is dashed in light mode and solid in dark mode, because a dashed `#353535` on `#212529` was too faint to see (user decision, 2026-11-07). The dark border color stays `#353535`.
  - Header: a brand link in the text color at weight 600, with a muted `« ` on non-home pages and no rule under the header. The header nav shows only below the sidebar breakpoint, hidden by CSS, because the sidebar's All posts and All tags links cover wide screens.
  - Footer: the existing `© author` line, muted, with a thin top rule.
  - Palettes follow `prefers-color-scheme` with no toggle or JavaScript, as task-007 decided.
- User decisions from the first manual QA run (2026-11-07, log at f12811f). These override the earlier bullets where they differ.
  - The About box's apparent blank line was the fixture headshot, an empty transparent 10x10 SVG. The fixture headshot draws a visible shape so the bio image shows in QA.
  - List summaries: every heading inside `.entry-summary` renders at body size in bold sans with no top margin, and list titles (`entry-item`) grow to 1.5rem, so a summary's headings never outrank its title.
  - The home page's "All entries" link is an outlined button: "All entries →" in sans weight 600 and the link color, inside a 1px rounded border in the link color, with a light tint on hover.
  - Draft and Invalid labels sit inline at the end of the entry title, inside the title heading, on list items and entry pages as well as the archive. They never render on the live site, so the preview-only change to the `p-name` text does not matter.
  - Archive titles match the sidebar's Recent posts titles: sans, weight 600, text color, link color and underline on hover. The tag index takes tag chips.
  - Every tag on the site is a chip: post meta, the tag index and the sidebar Tags box. Neutral chips: lowercase sans text in the text color on the tinted surface, a 1px border in the border color, a small corner radius (rounded rectangle, not a pill), the count inside the chip in muted text, and the link color on hover. They stay distinct from the uppercase colored Draft and Invalid labels.
  - Displayed dates abbreviate the month to three letters with no period ("Jan 4, 2026"). Machine dates (`datetime`, feeds) are unchanged.
  - List summaries are indented 1.25rem from their title and meta, so each entry's body reads as part of that entry and the divides between entries show (user decision, 2026-11-07, after the summary headings were demoted).
  - List items (home and tag pages) hide the author, because a site has one author; entry pages still show it. The list item keeps its `p-author h-card` with the `hidden` attribute, so task-006's h-entry markup is unchanged for M6 and M7 (user decision, 2026-11-07).
  - The year-grouped list at `/posts/` is "All posts" everywhere a reader sees it: its heading and `<title>` ("All posts | <site>"), the header nav, the sidebar's link under Recent posts and the home page's "All posts →" button. Tag feeds describe themselves as "Posts tagged ...". The URL stays `/posts/`. Earlier bullets that say Archive or All entries mean this page (user decision, 2026-11-07).
  - The tag index link reads "All tags" in the header nav, matching the Tags box. The sidebar has no Site box, since Recent posts and Tags end in All posts and All tags links and the home page has its button. RSS moves to the footer, after the copyright, on every page at every width; the header nav drops it as rarely used (user decision, 2026-11-07).
  - The home page shows Recent posts too, so its sidebar has an All posts link on wide screens like every other page, even though the box repeats the top of the home list (user decision, 2026-11-07).
  - `tools/manual-qa`: after each verdict it asks whether to add notes. Yes opens `$VISUAL`, else `$EDITOR`, else `vi`, on a scratch file whose text becomes the notes; no records none.
- Keep every text pair at WCAG AA (4.5:1), including links on the tinted surface, muted text, code tokens on the new code backgrounds, and callout titles on their tints. The GitHub light Chroma colors pass on `#f7f2ea` but not on `#e7dbcb`, which is why the code background differs from the surface. Re-derive any callout color that falls below AA on ivory, and update `main.css`'s header comment if the generated-palette edits change.
- Not blocked by task-011, which is deferred past v1 (user decision, 2026-11-07). The theme stays at `src/mdblog/theme/`; task-011 moves it later along with this task's layouts and CSS.
- Restyle task-009's Draft and Invalid labels and its banner in both palettes.
- The sidebar reads the bio from the home page's `.Content` (`content/_index.md`). Bio image URLs are root-relative with the base path (`tests/test_site.py` near line 238 asserts `/headshot.svg`), so they resolve from any page.
- Affected tests: `tests/test_site.py` home-page bio assertions near lines 230-240 and the description check near line 444, header assertions near lines 392 and 514; `tests/test_build.py` near line 652 (`class="bio"`). Keep every other class and element the site tests read.
- Before running the reviewer, replace the `design: phone and desktop, light and dark` check in `tools/manual_qa.py` with one covering this task's manual-QA Must Have. That check runs `mdblog serve --drafts` on the fixture vault so the labels are visible. Have the author run `tools/manual-qa` with its name, apply their feedback, and record the approval from the log in `## Advice` with the date and commit.
- Standing obligation, strict static checks: Python changes are limited to `tools/manual_qa.py` and tests, which stay fully typed.
- Standing obligation, scripts stay simple: no new scripts.
- Standing obligation, test where the risk is: test the sidebar contents, ordering, omissions, home-page exclusion, header brand text and bio placement with real Hugo, because each can silently show the wrong list. Do not test CSS values; the look is manual QA.

## Plan
- [x] **Step 1** (`src/mdblog/theme/layouts/`): the grid in `baseof.html`, a sidebar partial with its four sections, the header's brand link and phone nav, and the home page without the bio. Update the affected tests named in `## Advice` and add tests for the new markup Must Haves.
- [x] **Step 2** (`src/mdblog/theme/assets/css/main.css`): the palettes, type, link and title rules, sidebar boxes, header, footer, and task-009's labels, then the WCAG AA recheck including Chroma and callouts.
- [ ] **Step 3** (`tools/manual_qa.py`): the replacement manual-QA check, then the author's run and the recorded approval.

## Review log
