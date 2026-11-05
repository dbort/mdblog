---
id: task-004
title: "Convert Obsidian links, embeds and syntax"
blocked_by: [task-003]
---

# task-004: Convert Obsidian links, embeds and syntax

## Summary
Turns the Obsidian syntax in published notes into what Hugo renders: wikilinks, image embeds, comments, callouts, highlights and block IDs. A link or embed that can't resolve to something published fails the build, so readers never see a dead link, and draft text and images can't reach the site through one. With no vault to survey yet, this list comes from the author's choices, and anything else stays literal text.

## Must Have
- [x] These wikilink forms become Markdown links with root-relative URLs that start with `base_url`'s path: `[[note]]`, `[[note|alias]]`, `[[note#heading]]`, `[[note#heading|alias]]`, `[[#heading]]`, `[[note#^id]]`, `[[folder/note]]`, `[[../note]]` and `[[note.md]]`, including an alias escaped as `\|` inside a table.
- [x] Link text is the alias when present, and otherwise the target as written. Note matching ignores case. `[[note#a#b]]` targets heading `b`.
- [x] Heading anchors match Hugo's generated IDs. A test with real Hugo covers `Café & Über: 100%!` (`café--über-100`), a repeated heading `Same` (`same`, then `same-1`), and ``C++ and `code` stuff`` (`c-and-code-stuff`).
- [x] `[[note#^id]]` links to the top of the target note, and `[[#^id]]` links to the top of the current note.
- [x] `![[note]]` of a published note renders the same link as `[[note]]`.
- [x] Each of these fails the build, with a message naming the source note and the target: a link or embed that resolves to nothing, resolves to more than one note or image, resolves outside the vault, or targets a file under `_site/` or a dot-folder; a link or embed of an unpublished note; a missing heading or block ID; and a link or embed of a non-image file such as `paper.pdf` or `clip.mp4`.
- [x] An internal standard Markdown link or image fails the build, whether inline or reference-style. A destination with a URL scheme, or one that starts with `#`, passes through unchanged.
- [x] One run reports every failure across all published notes, along with task-003's failures, and leaves the output directory unchanged. These rules do not apply to the text of unpublished notes.
- [x] Tests confirm that a published note linking or embedding an unpublished note or image fails, and that the unpublished text and image appear nowhere in the output directory.
- [x] `![[a.png]]` renders an image, and `[[a.png]]` renders a link to the copied file. Supported extensions are `avif`, `bmp`, `gif`, `jpeg`, `jpg`, `png`, `svg` and `webp`, ignoring case.
- [x] `![[a.png|300]]` renders `width="300"`, `![[a.png|300x200]]` also renders `height="200"`, and `![[a.png|some text]]` renders that text as `alt`. A file name holding a space renders a working URL.
- [x] Only images used by published notes are copied: a test asserts that an unused image, and one used only by an unpublished note, are absent from the output. An image used by two notes appears under both pages.
- [x] Two different images with the same file name embedded in one note fail the build.
- [x] With `base_url` set to `https://example.test/blog/` or `https://example.test/blog`, `[[note]]` links to `/blog/posts/<slug>/` and `![[a.png]]` has the `src` `/blog/posts/<slug>/a.png`. With no path in `base_url`, they are `/posts/<slug>/` and `/posts/<slug>/a.png`. A real-Hugo test finds each target in the output once `/blog` is removed from its path.
- [x] `%%comments%%` are removed, inline and across lines. An unterminated `%%` removes the rest of the note. Text and links inside a comment do not reach the output and are not validated.
- [x] A trailing `^block-id`, on a line of its own or at the end of a line, is removed from the page.
- [x] Callouts render through a default `_markup/render-blockquote.html` layout: `> [!note]` and `> [!warning] Title` as a block with a title, `> [!faq]-` as a closed `<details>`, and `> [!tip]+` as an open one. A plain quote remains a `<blockquote>`.
- [x] `==text==` renders as `<mark>`.
- [x] Fenced code, indented code and inline code stay byte-identical: a test places each syntax above inside each kind of code, including a fence nested in a quote.
- [x] Inline `#tags` remain literal text and do not become site tags.
- [x] Raw HTML in a note does not render: the output has no `<img src="draft.png">` written directly in a note, so it cannot bypass these rules.
- [x] A site can override a default `_markup` layout from `_site/layouts/_markup/`.
- [x] `docs/vault-format.md` lists the supported syntax, the failure rules and the known limits: math, note transclusion, media players and hyphenated callout types are unsupported.
- [x] `tools/check` exits 0 on the finished branch.

## Advice
- User decisions: links and embeds of unpublished notes fail the build, so a production build has no plain-text or render-nothing path, and a note goes live only when its targets are published. Non-image attachments fail, and support gets added on first need. Internal standard Markdown links fail, so keep Obsidian's "Use [[Wikilinks]]" setting on. Note embeds render as links, which avoids recursion and duplicate-content rules.
- Use a Python converter, not `obsidian-export`. It would need an ignore file generated from the `publish` rule, it unlinks excluded targets silently where these rules need a failure, its links would need rewriting for `/posts/<slug>/`, and it is not on conda-forge, so pixi could not pin it.
- Add `markdown-it-py` from conda-forge (tested with 4.2.0, which ships `py.typed`). Use its tokens to find `link_open` and `image` destinations, which covers reference-style links and skips code, and to find `fence` and `code_block` line ranges, including inside quotes. Scan for backtick code spans on the remaining lines. Do not regex the whole document for links, because code and reference definitions defeat it.
- Process each note in order: remove comments, remove block IDs, then convert links and embeds. Collect headings and block IDs from comment-free text, so a heading inside a comment is not a valid target. A comment marker inside code is literal.
- An unterminated `%%` removes to the end of the note, because leaking a private aside is worse than losing text. The `%%` hides text only on the site: nothing in the vault is secret.
- Resolve a target in order: path from the note's folder when it starts with `./` or `../`; path from the vault root when it holds `/`; otherwise, unique file name across selected files. Check notes before images, so `[[v1.2 notes]]` is a note. A file that exists but has an unsupported extension gets its own failure message, because "not found" would mislead.
- User decision (2026-11-04): a site can live under a sub-path of its domain. Generate root-relative URLs that start with the path of `SiteConfig.base_url` (`/blog/posts/<slug>/`), not relative or absolute ones, because Hugo passes Markdown destinations through unchanged (tested on Hugo 0.169). Read the path with `urllib.parse.urlsplit` and accept it with or without a trailing slash, as Hugo does. M4's preview build has its own site URL, so its links come out right, and a full-text feed in M3 can make them absolute. Percent-encode file names and anchors. Escape `[` and `]` in generated link text.
- Copy images into the note's leaf bundle at `content/posts/<slug>/`. Tested on Hugo 0.169: bundle files publish next to the page, including names with spaces. Bundles avoid a global attachment namespace, at the cost of duplicate copies across notes.
- Carry an image's size in a query parameter on its destination (`?mdblog-width=300`), and read it in a default `_markup/render-image.html` hook that strips it from `src`. Tested on Hugo 0.169. Do not set `markup.goldmark.renderer.unsafe`: keeping raw HTML off is what stops a note from bypassing these rules.
- Hugo's blockquote hook handles callouts with no converter code, and exposes `.AlertType`, `.AlertTitle` and `.AlertSign`. It leaves a hyphenated type such as `[!custom-thing]` as a plain quote with literal text, which is a documented limit. M3 owns callout styling.
- Enable `markup.goldmark.extensions.extras.mark` in the generated `hugo.toml` for highlights. Tested on Hugo 0.169.
- Compute heading anchors with Hugo's algorithm and pin it with the real-Hugo test, since a mismatch produces a link that silently goes nowhere.
- Standing obligation, strict static checks: `markdown-it-py` is typed, so it needs no escape hatch. Keep each syntax step a pure function from text to text plus failures.
- Standing obligation, scripts stay simple: all logic is Python in importable functions, tested directly.
- Standing obligation, test where the risk is: conversion and validation are novel code, so unit tests cover each rule and message. Real Hugo runs in the end-to-end fixture build, for heading anchors and for the render hooks, because a break there silently produces wrong pages.

## Plan
- [x] **Step 1** (`pixi.toml`, `pixi.lock`, `pyproject.toml`): add `markdown-it-py`.
- [x] **Step 2** (`src/mdblog/markdown.py`, tests): locate code regions, remove comments and block IDs, and collect headings, block IDs and internal Markdown link destinations.
- [x] **Step 3** (`src/mdblog/links.py`, tests): an index of selected notes and images with the resolution order, then wikilink and embed conversion taking the site's base path and returning new text, images to copy and every failure.
- [x] **Step 4** (`src/mdblog/publish.py`, `src/mdblog/build.py`, tests): wire conversion into page writing, copy images into leaf bundles, merge failures with task-003's report, and add `extras.mark` to the generated `hugo.toml`.
- [x] **Step 5** (`src/mdblog/theme/layouts/_markup/`, tests): default `render-blockquote.html` and `render-image.html` hooks, tested with real Hugo along with the site override.
- [x] **Step 6** (`tests/fixtures/vault/`, `tests/test_build.py`): add fixture notes and images using each supported syntax, with the end-to-end test building them.
- [x] **Step 7** (`docs/vault-format.md`): the syntax, failure rules and known limits.

## Review log

### Round 1: REJECTED
- **F1: Hugo's heading-ID rules beyond the three Must Have cases are pinned only by hand-verified unit expectations** (`tests/test_markdown.py:784`, `tests/test_build.py:75`): `headings()` and `_plain_text()` copy many Hugo behaviors: an explicit `{#id}` is used as written, `{.class}` attributes are stripped, other braces stay as text, image alt text counts, autolinks and raw HTML add nothing, a setext heading's ID comes from its last line, an empty heading gets no ID, and an all-punctuation heading falls back to `heading`. `test_headings_follow_hugos_ids` asserts IDs that were checked against Hugo by hand. The real-Hugo test (`ANCHOR_TARGET`) covers only `Café & Über: 100%!`, `Same`/`Same` and ``C++ and `code` stuff``. If any copied branch differs from Hugo, a link silently goes nowhere. Advice calls for pinning the algorithm with real Hugo for exactly that reason, and **Test where the risk is** allows a second real-tool test where a break is silent. Fix: in the real-Hugo build, add the `test_headings_follow_hugos_ids` headings to a target note, then assert that the `id`s Hugo emits equal `[h.anchor for h in headings(body)]` in order.
- **N1: Generated link text is still parsed as Markdown** (`src/mdblog/links.py:150`): `_link_text` escapes only `\`, `[` and `]`, so `[[_draft notes_]]` renders in italics, and an alias with backticks or `<b>` renders as code or as omitted HTML. The Must Have says the text should be "the target as written". Backslash-escape all ASCII punctuation in link text.
- **N2: An image embed inside a heading gets a different anchor than Hugo gives it** (`src/mdblog/markdown.py:683`): `_wikilink_display` uses the alias or the target, but Hugo uses the alt text the converter writes. `## Diagram ![[a.png|300]]` computes `diagram-300` where Hugo produces `diagram-apng`, and `## Diagram ![[images/a.png]]` computes `diagram-imagesapng`. Either compute the display text the way `convert` builds alt text, or list it under Known limits.

### Round 2: REJECTED
- **F1: Escaping link text puts heading IDs out of step with Hugo again** (`src/mdblog/markdown.py:262`, `src/mdblog/links.py:151`): the converter now backslash-escapes link text, so Hugo reads it literally, but `headings()` still parses the unconverted wikilink with markdown-it, which reads the alias or target as Markdown before `wikilink_text` sees it: `_x_` becomes emphasis, `<b>` dropped raw HTML and `&amp;` an `&`. Real Hugo: `## See [[_draft notes_]]` gives `see-_draft-notes_` against our `see-draft-notes`; `## Alias [[_draft notes_|<b>x</b> &amp; y]]` gives `alias-bxb-amp-y` against `alias-x--y`; `## Under [[_draft notes_|_lead and trail_]]` gives `under-_lead-and-trail_` against `under-lead-and-trail`. A link to such a heading silently goes nowhere. Fix: before parsing, replace each wikilink outside code with its escaped display text, sharing the escaping function between both modules, and add a heading with `_`, inline HTML and an entity in its wikilink text to `HEADINGS`.
