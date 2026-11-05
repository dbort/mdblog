---
id: task-006
title: "Build the site's pages, feeds and entry markup"
blocked_by: [task-004]
---

# task-006: Build the site's pages, feeds and entry markup

## Summary
Replaces the placeholder layouts with the site's real structure: a home page with the author's bio and latest entries, a year-grouped archive, tag pages, entry pages with h-entry markup, and full-text RSS feeds. The pages stay unstyled here, because task-007 adds the visual design. A vault also gains `_site/bio.md`, `_site/assets/` and `_site/static/`.

## Must Have
- [ ] The body of `_site/bio.md` renders on the home page above the entry list, and its front matter has no effect, including `publish: false`.
- [ ] A missing `_site/bio.md`, or one reached through a symbolic link, fails the build with a failure naming `_site/bio.md`, reported in the same run as every note failure, with the output directory unchanged. An empty file builds a home page with no bio.
- [ ] The bio goes through task-004's conversion: `[[note]]` becomes a link, `![[photo.jpg]]` renders an image whose file is in the output, and a broken link or a link to an unpublished note fails the build naming `_site/bio.md` and the target.
- [ ] The home page lists the latest 15 entries of all three types, newest first, then links to `/posts/`: a test with 16 entries finds the newest 15 and not the oldest. The 15 appears in one place in the code.
- [ ] In the home and tag lists, a post or TIL shows its title linking to its page, its Hugo summary, its date and its tags. A post cut with `<!--more-->` shows only the text before the marker.
- [ ] In those lists, a link entry's title links to `link_url` and the entry shows its full commentary, its date linking to its page, and its tags.
- [ ] Every list marks a TIL with the label `TIL` and a link entry with the label `Link`, and shows no label on a post.
- [ ] `/posts/` lists every entry under year headings, newest year first and newest first within a year, each line holding the type label, title and date. No per-entry summary or tags appear there.
- [ ] A tag page lists every entry with that tag in the home page's format, on one page. `/tags/` lists every tag alphabetically, with a link and its entry count.
- [ ] Tag text displays in lowercase on entries, tag pages and `/tags/`: a note tagged `Node.JS` shows `node.js`.
- [ ] No page is built for a nested tag's parent: a note tagged only `project/alpha` builds `/tags/project/alpha/` and no `/tags/project/index.html`.
- [ ] An entry page shows the type label, title, date, tags and body, and no previous, next or related links. A link entry's title links to `link_url`.
- [ ] Dates display as `January 2, 2026` in the date's own offset, in a `<time>` element whose `datetime` holds the full value: `2026-01-02T23:30:00-07:00` displays `January 2, 2026`, and so does the date-only `2026-01-02` under `TZ=Pacific/Kiritimati`.
- [ ] Every entry page and home or tag list item is an `h-entry` holding `p-name`, `u-url` set to its permalink, `dt-published`, `p-category` per tag and a `p-author h-card` naming the site's author. An entry page has `e-content`, and a list item has `p-summary` or, on a link entry, `e-content`. A link entry has `u-bookmark-of` set to `link_url`. The home and tag lists sit inside an `h-feed`.
- [ ] Every page has a header holding the site title linking home and links labeled `Archive` (`/posts/`), `Tags` (`/tags/`) and `RSS` (`/index.xml`), and a footer holding `© <author>`.
- [ ] Every page's `<head>` holds a `<title>`, the author meta tag, `<link rel="canonical">` with the page's absolute URL, `og:title`, `og:url`, `og:site_name` and `og:type`, which is `article` on an entry page and `website` elsewhere. An entry page and the home page with a non-empty bio also hold `meta name="description"` and `og:description`, in plain text from the summary, and a title or summary holding `&` is escaped once.
- [ ] Every page's `<head>` advertises `/index.xml` as `application/rss+xml`, and a tag page also advertises its own feed.
- [ ] `/index.xml` and `/tags/<tag>/index.xml` parse as RSS with channel `title`, `link` and `description`. `/posts/index.xml`, `/tags/index.xml` and `/categories/` are absent from the output.
- [ ] `/index.xml` lists entries of all three types, newest first. A feed holds at most its latest 50 entries: a test with 51 entries finds the newest 50 and not the oldest. The 50 appears in one place in the code.
- [ ] Each item's `<description>` holds the entry's full text, past any `<!--more-->`. Each `href` and `src` starting with `/` is absolute on the site's origin, and each one starting with `#` is absolute on the entry's permalink, while code text such as `` `href="/x"` `` stays unchanged. A body holding `]]>` and `&` still parses.
- [ ] Every item's `<link>` and `<guid>` are the entry's permalink. A link entry's `<description>` starts with a link to `link_url`.
- [ ] `_site/assets/` and `_site/static/` reach Hugo the way `_site/layouts/` does, skipping symbolic links and following neither directory if it is a symbolic link: a file at `_site/static/favicon.ico` is in the output at `/favicon.ico`.
- [ ] A vault's `_site/layouts/` can override each packaged layout and partial by name.
- [ ] `docs/vault-format.md` lists `_site/bio.md`, `_site/layouts/`, `_site/assets/` and `_site/static/`, and states that nested tag parents build no page. `CLAUDE.md`'s **Sites** line names them too.
- [ ] `tools/check` exits 0 on the finished branch.

## Advice
- User decisions (2026-11-04): latest 15 on the home page, kept easy to change; title, excerpt and metadata in lists; a text label for types; a missing bio fails the build; full-text feeds of the latest 50, with a tag feed per tag and nothing else; a link entry's feed `<link>` is the permalink on this site, with the external link first in the body; lowercase tag text; no parent pages for nested tags; no type-specific lists or standalone pages in v1; Open Graph without an image; two tasks, with all visual work in task-007.
- An empty bio stays allowed so a vault can opt out on purpose. The failure exists to catch a renamed or moved file, which would otherwise go live with no warning.
- Report bio failures through the same list as note failures, using the path `_site/bio.md`, so one run names everything. `select_notes` skips `_site/`, so read the bio separately. Refuse a symbolic link for the reason `load_config` does: `_site/` content must come from the vault.
- Write the bio to `content/_index.md`, which Hugo renders as the home page's `.Content`. Copy its images beside that file and pass the converter the home URL as the page prefix, since task-004's image URLs assume `/posts/<slug>/`. Confirm the published path with the test on real Hugo. task-004 rejects targets under `_site/`, so a headshot lives elsewhere in the vault.
- Do not paginate. `docs/vault-format.md` records that a tag such as `a/page/2` can replace a page of tag `a`'s listing only under a paginating layout, and the packaged layouts promise not to.
- Put the 15 in a variable at the top of `home.html`. Put the 50 in `hugo.toml` as `services.rss.limit` from a named constant in `build.py`, and read it in the feed template as `site.Config.Services.RSS.Limit`. A site that overrides a layout then still gets the config, and neither number needs a `mdblog.toml` key.
- In `hugo_config`, set `[taxonomies] tag = "tags"`, which drops `categories`, and `[outputs]` as `home = ["html", "rss"]`, `section = ["html"]`, `taxonomy = ["html"]`, `term = ["html", "rss"]`, `page = ["html"]`. Tested on Hugo 0.169: this produces exactly the Must Have's feed set. Keep Hugo's `sitemap.xml`.
- Override the feed with a theme `layouts/rss.xml`. Tested on Hugo 0.169: on the home page `.Pages` holds sections, so range `site.RegularPages` there and `.Pages` on a term. `replaceRE` over `.Content` with `transform.XMLEscape` keeps code text intact, because Goldmark escapes the quotes in it. `absURL "/"` returns the origin even under a base URL with a path, so a replacement must keep the slash it matched, or `/posts/a/` becomes `https://example.orgposts/a/`. Resolving against the origin matches what a browser does with task-004's root-relative links on the page. Fragment-only `href` values also appear in footnotes, so cover those.
- Omit RSS `<author>`, because RSS requires an email there and `mdblog.toml` holds none. Name the author in the channel `title` or a `dc:creator` if needed.
- Hugo title-cases term titles, so `node.js` arrives as `Node.js` and `.Data.Term` keeps the note's case. Apply `lower` at display. Sort `/tags/` on the lowercased text.
- Format dates with `.Date.Format`. Tested on Hugo 0.169: it keeps a value's own offset, and date-only values are UTC, so the displayed day matches what the author wrote. Do not call `.Local` or set `timeZone`.
- A link entry's date links to its permalink, because its title leaves the site. Use the same date link on every entry, so one partial covers all types and `u-url` has one home.
- Keep `<html lang>` at Hugo's default language, and add a `mdblog.toml` key on first need.
- Leave out the stylesheet link, the viewport tag and the 404 page, which task-007 adds. Use semantic elements (`header`, `nav`, `main`, `article`, `footer`, `time`) and plain class names that task-007 can style without changing markup.
- Standing obligation, strict static checks: new Python is fully typed, with no escape hatch expected.
- Standing obligation, scripts stay simple: all logic is Python in importable functions and Hugo templates, with no new shell.
- Standing obligation, test where the risk is: these layouts are novel code that only Hugo can execute, and a break silently produces wrong pages, so real-Hugo tests cover each Must Have about output. Copying site files, bio failures and `hugo_config` use fake Hugo or direct calls. Parse output with `html.parser` and `xml.etree`, and add no microformats dependency. Share one fixture build across read-only assertions, and write no tests of the parsing helper.

## Plan
- [ ] **Step 1** (`src/mdblog/build.py`, `src/mdblog/publish.py`, `tests/test_build.py`, `tests/test_publish.py`): read and convert `_site/bio.md`, merge its failures with the notes', write `content/_index.md` and its images, and copy `_site/assets/` and `_site/static/` beside `_site/layouts/`.
- [ ] **Step 2** (`src/mdblog/build.py`, `tests/test_build.py`): add the taxonomies, outputs and feed limit to `hugo_config`. `test_hugo_config_round_trips_any_string` keeps asserting its three strings.
- [ ] **Step 3** (`tests/fixtures/vault/_site/bio.md`, `tests/fixtures/vault/`, `tests/test_build.py`, `tests/test_cli.py`): add the fixture bio and enough fixture notes for every page type and entry type. `_make_vault` in `tests/test_build.py` writes a bio. Check each vault built in `tests/test_cli.py` and `tests/test_build.py`, because a vault with no bio now fails. Fixture notes must add no text matching the `UNPUBLISHED-*` needles.
- [ ] **Step 4** (`src/mdblog/theme/layouts/`, `tests/test_build.py`): add `baseof.html`, partials for the head, header, footer, entry list item, date and tags, plus `home.html`, `section.html`, `taxonomy.html`, `term.html` and `page.html`. Remove `list.html` if nothing still resolves to it. Update `test_build_supplies_the_packaged_theme_and_vault_layouts`, which pins the theme's file list, plus `test_generated_site_uses_the_configuration` and `test_vault_layout_replaces_only_the_page_default`.
- [ ] **Step 5** (`src/mdblog/theme/layouts/rss.xml`, tests): the full-text feed, with `<head>` advertising.
- [ ] **Step 6** (`docs/vault-format.md`, `CLAUDE.md`): the `_site/` files and the nested tag limit.

## Review log
