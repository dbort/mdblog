---
id: task-004
title: "Convert Obsidian links, embeds and syntax"
blocked_by: [task-003]
---

# task-004: Convert Obsidian links, embeds and syntax

## Summary
Turns the Obsidian syntax in published notes into what Hugo renders: wikilinks, image embeds, comments, callouts, highlights and block IDs. A link or embed that can't resolve to something published fails the build, so readers never see a dead link, and draft text and images can't reach the site through one. With no vault to survey yet, this list comes from the author's choices, and anything else stays literal text.

## Must Have
- [ ] These wikilink forms become Markdown links with root-relative URLs: `[[note]]`, `[[note|alias]]`, `[[note#heading]]`, `[[note#heading|alias]]`, `[[#heading]]`, `[[note#^id]]`, `[[folder/note]]`, `[[../note]]` and `[[note.md]]`, including an alias escaped as `\|` inside a table.
- [ ] Link text is the alias when present, and otherwise the target as written. Note matching ignores case. `[[note#a#b]]` targets heading `b`.
- [ ] Heading anchors match Hugo's generated IDs. A test with real Hugo covers `Café & Über: 100%!` (`café--über-100`), a repeated heading `Same` (`same`, then `same-1`), and ``C++ and `code` stuff`` (`c-and-code-stuff`).
- [ ] `[[note#^id]]` links to the top of the target note, and `[[#^id]]` links to the top of the current note.
- [ ] `![[note]]` of a published note renders the same link as `[[note]]`.
- [ ] Each of these fails the build, with a message naming the source note and the target: a link or embed that resolves to nothing, resolves to more than one note or image, resolves outside the vault, or targets a file under `_site/` or a dot-folder; a link or embed of an unpublished note; a missing heading or block ID; and a link or embed of a non-image file such as `paper.pdf` or `clip.mp4`.
- [ ] An internal standard Markdown link or image fails the build, whether inline or reference-style. A destination with a URL scheme, or one that starts with `#`, passes through unchanged.
- [ ] One run reports every failure across all published notes, along with task-003's failures, and leaves the output directory unchanged. These rules do not apply to the text of unpublished notes.
- [ ] Tests confirm that a published note linking or embedding an unpublished note or image fails, and that the unpublished text and image appear nowhere in the output directory.
- [ ] `![[a.png]]` renders an image, and `[[a.png]]` renders a link to the copied file. Supported extensions are `avif`, `bmp`, `gif`, `jpeg`, `jpg`, `png`, `svg` and `webp`, ignoring case.
- [ ] `![[a.png|300]]` renders `width="300"`, `![[a.png|300x200]]` also renders `height="200"`, and `![[a.png|some text]]` renders that text as `alt`. A file name holding a space renders a working URL.
- [ ] Only images used by published notes are copied: a test asserts that an unused image, and one used only by an unpublished note, are absent from the output. An image used by two notes appears under both pages.
- [ ] Two different images with the same file name embedded in one note fail the build.
- [ ] `%%comments%%` are removed, inline and across lines. An unterminated `%%` removes the rest of the note. Text and links inside a comment do not reach the output and are not validated.
- [ ] A trailing `^block-id`, on a line of its own or at the end of a line, is removed from the page.
- [ ] Callouts render through a default `_markup/render-blockquote.html` layout: `> [!note]` and `> [!warning] Title` as a block with a title, `> [!faq]-` as a closed `<details>`, and `> [!tip]+` as an open one. A plain quote remains a `<blockquote>`.
- [ ] `==text==` renders as `<mark>`.
- [ ] Fenced code, indented code and inline code stay byte-identical: a test places each syntax above inside each kind of code, including a fence nested in a quote.
- [ ] Inline `#tags` remain literal text and do not become site tags.
- [ ] Raw HTML in a note does not render: the output has no `<img src="draft.png">` written directly in a note, so it cannot bypass these rules.
- [ ] A site can override a default `_markup` layout from `_site/layouts/_markup/`.
- [ ] `docs/vault-format.md` lists the supported syntax, the failure rules and the known limits: math, note transclusion, media players and hyphenated callout types are unsupported.
- [ ] `tools/check` exits 0 on the finished branch.

## Advice
- User decisions: links and embeds of unpublished notes fail the build, so a production build has no plain-text or render-nothing path, and a note goes live only when its targets are published. Non-image attachments fail, and support gets added on first need. Internal standard Markdown links fail, so keep Obsidian's "Use [[Wikilinks]]" setting on. Note embeds render as links, which avoids recursion and duplicate-content rules.
- Use a Python converter, not `obsidian-export`. It would need an ignore file generated from the `publish` rule, it unlinks excluded targets silently where these rules need a failure, its links would need rewriting for `/posts/<slug>/`, and it is not on conda-forge, so pixi could not pin it.
- Add `markdown-it-py` from conda-forge (tested with 4.2.0, which ships `py.typed`). Use its tokens to find `link_open` and `image` destinations, which covers reference-style links and skips code, and to find `fence` and `code_block` line ranges, including inside quotes. Scan for backtick code spans on the remaining lines. Do not regex the whole document for links, because code and reference definitions defeat it.
- Process each note in order: remove comments, remove block IDs, then convert links and embeds. Collect headings and block IDs from comment-free text, so a heading inside a comment is not a valid target. A comment marker inside code is literal.
- An unterminated `%%` removes to the end of the note, because leaking a private aside is worse than losing text. The `%%` hides text only on the site: nothing in the vault is secret.
- Resolve a target in order: path from the note's folder when it starts with `./` or `../`; path from the vault root when it holds `/`; otherwise, unique file name across selected files. Check notes before images, so `[[v1.2 notes]]` is a note. A file that exists but has an unsupported extension gets its own failure message, because "not found" would mislead.
- Generate root-relative URLs (`/posts/<slug>/`), not relative or absolute ones. They survive M4's preview URL override, and a full-text feed in M3 can make them absolute. Percent-encode file names and anchors. Escape `[` and `]` in generated link text.
- Copy images into the note's leaf bundle at `content/posts/<slug>/`. Tested on Hugo 0.169: bundle files publish next to the page, including names with spaces. Bundles avoid a global attachment namespace, at the cost of duplicate copies across notes.
- Carry an image's size in a query parameter on its destination (`?mdblog-width=300`), and read it in a default `_markup/render-image.html` hook that strips it from `src`. Tested on Hugo 0.169. Do not set `markup.goldmark.renderer.unsafe`: keeping raw HTML off is what stops a note from bypassing these rules.
- Hugo's blockquote hook handles callouts with no converter code, and exposes `.AlertType`, `.AlertTitle` and `.AlertSign`. It leaves a hyphenated type such as `[!custom-thing]` as a plain quote with literal text, which is a documented limit. M3 owns callout styling.
- Enable `markup.goldmark.extensions.extras.mark` in the generated `hugo.toml` for highlights. Tested on Hugo 0.169.
- Compute heading anchors with Hugo's algorithm and pin it with the real-Hugo test, since a mismatch produces a link that silently goes nowhere.
- Standing obligation, strict static checks: `markdown-it-py` is typed, so it needs no escape hatch. Keep each syntax step a pure function from text to text plus failures.
- Standing obligation, scripts stay simple: all logic is Python in importable functions, tested directly.
- Standing obligation, test where the risk is: conversion and validation are novel code, so unit tests cover each rule and message. Real Hugo runs in the end-to-end fixture build, for heading anchors and for the render hooks, because a break there silently produces wrong pages.

## Plan
- [ ] **Step 1** (`pixi.toml`, `pixi.lock`, `pyproject.toml`): add `markdown-it-py`.
- [ ] **Step 2** (`src/mdblog/markdown.py`, tests): locate code regions, remove comments and block IDs, and collect headings, block IDs and internal Markdown link destinations.
- [ ] **Step 3** (`src/mdblog/links.py`, tests): an index of selected notes and images with the resolution order, then wikilink and embed conversion returning new text, images to copy and every failure.
- [ ] **Step 4** (`src/mdblog/publish.py`, `src/mdblog/build.py`, tests): wire conversion into page writing, copy images into leaf bundles, merge failures with task-003's report, and add `extras.mark` to the generated `hugo.toml`.
- [ ] **Step 5** (`src/mdblog/theme/layouts/_markup/`, tests): default `render-blockquote.html` and `render-image.html` hooks, tested with real Hugo along with the site override.
- [ ] **Step 6** (`tests/fixtures/vault/`, `tests/test_build.py`): add fixture notes and images using each supported syntax, with the end-to-end test building them.
- [ ] **Step 7** (`docs/vault-format.md`): the syntax, failure rules and known limits.

## Review log
