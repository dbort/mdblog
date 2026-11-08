---
id: task-015
title: "Publish a recent-posts JSON file"
---

# task-015: Publish a recent-posts JSON file

## Summary
The build writes `recent.json` at the site's root, listing the five newest entries. A page elsewhere on the same domain, such as a home page at `/` served by another Worker, can then fetch it and show the blog's latest posts the way the sidebar does, staying current without being redeployed when a post goes live.

## Must Have
- [x] A build of the fixture vault writes `recent.json` at the site's root. Under a `base_url` with a path, such as `https://example.test/blog/`, it is at `blog/recent.json` in the output and nowhere else.
- [x] Its content is a JSON object with one key, `items`: an array of at most 5 objects, newest first, each with exactly the string keys `title`, `url` and `date`.
- [x] `title` is the entry's page title. `url` is the entry's absolute URL, equal to the `<link>` of the same entry in `/index.xml`. `date` is ISO 8601 with a UTC offset and is the same instant as that entry's `<pubDate>` in `/index.xml`.
- [x] The entries and their order match the first five links in the sidebar's Recent posts list on a page that isn't one of them.
- [x] A title holding `"`, `\`, `<` and a non-ASCII character comes back unchanged from `json.loads`.
- [x] A site with no published notes writes `{"items": []}`.
- [x] `.claude/docs/hugo-site.md` § Packaged theme documents the file's location, fields and limit as a contract for pages outside the blog.
- [x] `tools/check` exits 0 on the finished branch.

## Advice
- The shape is mdblog's own, not JSON Feed 1.1. JSON Feed requires content on every item, which would bring back the weight of the full-text RSS feed, and the point of this file is to be small.
- The limit is 5, matching the sidebar. Name the number once, so the sidebar and the file can't drift apart. A Hugo site param written by `hugo_config` beside `[services.rss] limit` works, and both templates read it.
- Use Hugo's JSON encoding (`jsonify` or `encoding.Jsonify` on a built dict), never hand-built string concatenation, so escaping is Hugo's job.
- Add the file as a custom output format on the home page in `hugo_config` (`[outputFormats]`, then `home = ["html", "rss", "<name>"]`), with the base name `recent` and the JSON media type.
- task-011 moves render hooks into a core layer that applies under any theme. This file is part of mdblog's contract, so its layout belongs in that layer too. task-011's plan names this, so put the layout in the packaged theme here and leave the move to task-011.
- A consuming page fetches the file with a script, which needs no CORS setup because both Workers serve one origin. The script belongs to the other site and is not part of this task.
- Standing obligations: strict static checks apply. No scripts. Tests: real-Hugo assertions go in `tests/test_site.py` beside the feed tests, reusing its built fixture, plus one build with a path `base_url` and one with no published notes. No test restates the generated `hugo.toml`.

## Plan
- [x] **Step 1** (`src/mdblog/build.py`): add the output format, the home output and the shared limit param to `hugo_config`.
- [x] **Step 2** (`src/mdblog/theme/layouts/home.recent.json` or Hugo's name for it, `src/mdblog/theme/layouts/_partials/sidebar.html`): render `recent.json`, and make the sidebar read the shared limit.
- [x] **Step 3** (`tests/test_site.py`, `tests/test_build.py`): cover each Must Have.
- [x] **Step 4** (`.claude/docs/hugo-site.md`): document the contract.

## Review log

### Round 1: APPROVED
- **N1: Must Have 1's wording doesn't match the output layout** (`tasks/active/task-015-recent-posts-json.md:12`): non-blocking. Hugo writes `recent.json` at the output's root under a `/blog/` `base_url`, served at `/blog/recent.json` like `index.xml`; the sub-path test confirms it is the only `recent.json`. "`blog/recent.json` in the output" is a planning slip.
- **N2: Roadmap bullet still reads as a recommendation** (`docs/roadmap.md:32`): non-blocking. It goes away when M4's section is deleted at ship time.
- **N3: The test helper hard-codes the limit** (`tests/test_site.py:130`): non-blocking. `Site.recent()` checks `len(items) <= 5` instead of `RECENT_LIMIT`; the main test already exercises the limit with six fixture entries.
