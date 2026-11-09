# Roadmap

The v1 target is a personal site in the shape of [jacobian.org](https://jacobian.org): a short bio on the home page, one reverse-chronological stream of posts, a date and tags on every entry, and a full archive, written in Obsidian with no hand-edited generated files.

`publish: true` keeps unfinished notes off the site. It is not access control: an unpublished note can be read wherever the vault can, and supporting secrets would need its own milestone. There is no existing site to migrate.

M4 and M5 complete v1, and M6 and M7 follow it. Search, comments, series, scheduled publishing and packaging for other people are outside v1. Each milestone's decisions are settled in the `/new-task` interview that plans it, and each recommendation below is a starting point for that interview.

## M5: Deploy and launch

**Status:** Planned

Upload the staged site to Cloudflare, make publishing part of writing, then go live.

- A deploy command that stages the current working directories and uploads the result.
- A preview deployment separate from production, built with its own site URL because Hugo writes the URL into links and feeds, and kept out of search indexes.
- A way to trigger a publish from the vault.
- The production domain, and the first real content.

**Done when:** one command publishes the fixture site to a preview URL that M4's URL command accepts, and a new note written in Obsidian and marked `publish: true` reaches the live site with no change to this repo. `tools/check` never contacts a deployed site.

**Decisions:**
- Where the build runs. Recommended: locally or in CI through pixi, uploading the finished output, so Cloudflare never needs pixi and Hugo stays at the pinned version.
- Publish trigger. Recommended: a manual command first, then CI on vault pushes once the check command has earned trust, because an automatic trigger would put a half-finished edit to a published note live.
- Whether custom headers are needed at launch.
- Where each site's Worker routes live. Recommended: the vault's `_site/`, beside the Worker name, since this repo holds nothing site-specific.
- How a site under a path shares its domain. Recommended: the blog's Worker claims a route such as `example.org/blog/*` and a separate Worker claims `example.org/*`. Cloudflare sends each request to the more specific route, so the other content deploys on its own. A request for `/blog` without the trailing slash reaches only the other Worker, which then has to redirect it.

## M6: POSSE

**Status:** Planned

Publish on the site first, then syndicate copies elsewhere ([POSSE](https://indieweb.org/POSSE)).

- Syndication of entries that opt in, to chosen services.
- Idempotent runs. For a crash between posting and recording the copy's URL, the tool records its intent first and reports the interrupted post for the author to resolve.
- Each copy's URL shown on the entry as a `u-syndication` link, which takes a rebuild and deploy after posting.

**Done when:** a new entry posts once to each chosen service, neither a repeat run nor a run interrupted after posting posts again, and the entry links to its copies. Tests use fake service clients.

**Decisions:**
- Which services come first.
- Where syndication state lives: vault front matter makes the tool edit the author's notes, and a separate state file needs its own home and backup.
- What happens to copies when an entry is unpublished or deleted.
- Whether a copy's text starts from the entry's lede, the `[!summary]` callout that task-019 adds.

## M7: Backfeed

**Status:** Planned

Bring replies, likes and reposts back to the original entry ([backfeed](https://indieweb.org/backfeed)).

- Responses collected from syndicated copies and webmentions, stored as data and rendered at build time, so the site stays static.
- Moderation, so the author can hide a response.

**Done when:** a response on a syndicated copy appears on the entry after the next build, and a hidden response stays hidden across rebuilds.

**Decisions:**
- Hosted service or own collection. Recommended: a hosted webmention receiver and bridge first, because receiving webmentions directly needs custom Worker code.
- Which response types to display, and how much of other people's content to store.
- Where response data lives, since it is neither framework code nor vault content.
