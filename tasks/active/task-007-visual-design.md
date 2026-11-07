---
id: task-007
title: "Give the site its visual design and 404 page"
blocked_by: [task-006, task-008, task-010]
---

# task-007: Give the site its visual design and 404 page

## Summary
Gives the site a look of its own with one plain CSS file: a single readable column in system fonts, light and dark palettes that follow the reader's system, and syntax-highlighted code in both. It also adds the 404 page. The author reviews the result in a browser, since no test can judge a design.

## Must Have
- [ ] Every page links one stylesheet built from the theme's `assets/css/main.css` through Hugo's asset pipeline, with a fingerprinted file name, and that file is in the output.
- [ ] A vault's `_site/assets/css/main.css` replaces the packaged stylesheet: a test finds the site's text in the published file and not the packaged text.
- [ ] Every page's `<head>` has a `viewport` meta tag with `width=device-width`.
- [ ] No page in a fixture build contains `<script`, and the stylesheet contains no `@font-face` or `@import`.
- [ ] `pixi.toml` gains no Node dependency.
- [ ] The stylesheet sets light colors by default and dark colors under `@media (prefers-color-scheme: dark)`, with no toggle.
- [ ] Fenced code with a language renders with Hugo's `chroma` classes and no inline `style` attribute, and the stylesheet colors those classes in both palettes.
- [ ] `/404.html` is in the output with the site's header and footer, a message saying the page was not found, and a link home.
- [ ] With `base_url` set to `https://example.test/blog/`, the stylesheet link and each internal link on the 404 page start with `/blog/`.
- [ ] Each of these is styled: entry lists, year headings, tag lists, tables, inline and fenced code, `<mark>`, images, and task-004's callouts in each form, including closed and open `<details>`.
- [ ] Manual QA by the author: a fixture build looks right at phone width (375px) and desktop width, in light and dark modes, on the home page, archive, tag index, a tag page, an entry page and the 404 page, and no page scrolls sideways.
- [ ] `tools/check` exits 0 on the finished branch.

## Advice
- User decisions (2026-11-04): plain CSS through Hugo with no Node; system fonts in a single column about 65 characters wide; palettes follow `prefers-color-scheme` with no toggle or JavaScript; syntax highlighting through CSS classes in both modes; a vault can replace the stylesheet from `_site/assets/`.
- Before running the reviewer, add the manual-QA Must Have as a check in `tools/manual_qa.py` that runs `mdblog serve` on the fixture vault, have the author run `tools/manual-qa` with that check's name, and apply their feedback. Serve reloads the page after each change to a layout or note, and a `file://` view would break root-relative links. Record the author's approval from the log in `## Advice`, with the date, so the reviewer can confirm the manual QA.
- Set `markup.highlight.noClasses = false` in `hugo_config`. Hugo's default writes inline styles from a dark theme, which cannot follow the reader's mode. Generate each palette once with `hugo gen chromastyles`, check the result into `main.css`, and scope the dark one inside the media query. Tested on Hugo 0.169: fenced code renders `class="chroma"` with this setting, and a fingerprinted resource's `.RelPermalink` keeps a base path.
- Keep text at WCAG AA contrast (4.5:1 for body text) in both palettes, including code tokens, labels and links.
- Long URLs, wide tables and wide code blocks must not widen the page at 375px: let code and tables scroll inside their own boxes, wrap long words in text, and cap images at the column width.
- Change markup only where the design needs it, and keep every class and element task-006's and task-010's tests read.
- Standing obligation, strict static checks: the only Python change is one `hugo_config` line, which stays typed.
- Standing obligation, scripts stay simple: no new scripts.
- Standing obligation, test where the risk is: test the stylesheet link, site override, 404 and highlight classes with real Hugo, because each can break silently. Do not test CSS values or restate the stylesheet in tests, which leaves the design itself to manual QA.

## Plan
- [ ] **Step 1** (`src/mdblog/build.py`, `src/mdblog/theme/assets/css/main.css`, `src/mdblog/theme/layouts/`, tests): add the highlight setting, the stylesheet with both palettes, the head link and viewport tag.
- [ ] **Step 2** (`src/mdblog/theme/layouts/404.html`, tests): the 404 page. `test_build_supplies_the_packaged_theme_and_vault_layouts` pins the theme's file list, so update it.
- [ ] **Step 3** (`tests/fixtures/vault/`): add any fixture content the review needs, such as a wide table, a long URL and a fenced code block, adding no text that matches the `UNPUBLISHED-*` needles.
- [ ] **Step 4** (`docs/vault-format.md`): state that `_site/assets/css/main.css` replaces the packaged stylesheet.
- [ ] **Step 5**: the author's browser review and any changes it asks for.

## Review log
