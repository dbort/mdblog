# Roadmap

The v1 target is a personal site in the shape of [jacobian.org](https://jacobian.org): a short bio on the home page, one reverse-chronological stream of posts, a date and tags on every entry, and a full archive. Notes are written in Obsidian and reach the site without anyone editing generated files.

That site is a model for what readers see. [Its publishing setup](https://jacobian.org/til/hugo-obsidian/) keeps the vault inside the site repo and converts notes in a pre-commit hook, while mdblog keeps the vault in a separate checkout and converts at build time.

A note publishes only when its front matter has `publish: true`, and a note without that property stays off the site. This keeps unfinished notes from going live, and it is not access control: nothing in the vault is secret, and an unpublished note can be read wherever the vault itself can. Supporting secrets would need its own milestone. There is no existing site, so nothing needs migrating or redirecting.

M1 to M5 make up v1. M6 and M7 follow it. Each milestone's decisions are settled in the `/new-task` interview that plans it, and each recommendation below is a starting point for that interview.

Search, comments, series, scheduled publishing, and packaging mdblog for other people's sites are outside v1. Each site's settings live in its own vault, so in the long run this repo can host multiple independent sites.

## M4: Publish-ready output, locally

**Status:** Tasks task-014, task-015, task-016, task-017

- [x] task-014: Add mdblog check and a post template
- [ ] task-015: Publish a recent-posts JSON file
- [ ] task-016: Stage the site for a Cloudflare Worker and serve it with wrangler dev
- [ ] task-017: Verify that a URL serves the site (blocked on task-015, task-016)

Produce and check exactly what Cloudflare will serve, on a machine with no Cloudflare credentials.

- A check command that runs the build's validation pass with nothing deployed, so problems surface before anything goes live.
- A note template for use in Obsidian. It sets `publish: false`, which keeps the note off the site and shows it under `mdblog serve --drafts`, and leaves out `date`, which the author sets when publishing.
- Node from conda-forge, and wrangler from npm with a committed `package-lock.json`. No wrangler package turned up on conda-forge.
- `tools/check` installs from the npm lockfile itself, so callers need no setup step, and fails on a stale lockfile, which `pixi run --locked` does not detect. Under `--offline`, the install and any check that depends on it skip.
- A staging command that runs a fresh production build of the current working directories and lays it out for upload without `mdblog build`'s output marker, so local preview output cannot reach Cloudflare. Hugo writes files at the output's root, so a site whose `base_url` holds a path, such as `https://example.org/blog/`, is staged under that path, including `404.html`.
- Worker configuration for serving the staged output as static assets, with no custom Worker code. `wrangler dev` serves it locally, so local checks see the same asset handling as production, including which `404.html` answers a missing path.
- Worker configuration checked in `tools/check`: a `wrangler deploy --dry-run` if it works without network access or credentials, otherwise a test of the fields the deploy relies on.
- A separate command that takes a URL and fails unless it serves the home page, the feed and the recent-posts file, and answers a missing path under the site's path with status 404 and the site's 404 page. It is runnable at any time and independent of a deploy, against `wrangler dev` here and against deployed URLs in M5.
- Recent posts for pages outside the blog. A page elsewhere on the same domain, such as a home page at `/` served by another Worker, can show the blog's latest entries the way the sidebar's Recent posts box does, and keeps them current without redeploying when a post publishes. Recommended: the build writes a small `recent.json` at the site's root, such as `/blog/recent.json`, holding the title, URL and date of each of the latest entries, and the other page fetches it with a script. Both Workers serve one origin, so the fetch needs no CORS setup. The script belongs to the other site, and mdblog documents the file's fields as the contract between them.

**Done when:** the check command reports a broken fixture note with nothing built, and the fixture site, staged under a path and served by `wrangler dev`, passes the URL command, and the gate validates the Worker configuration, all on a machine without Cloudflare credentials.

**Decisions:**
- Where each site's Worker name and routes live. Recommended: in the vault's `_site/`, because this repo holds nothing site-specific.
- Whether custom headers are needed at launch.

## M5: Deploy and launch

**Status:** Planned

Upload the staged site to Cloudflare, make publishing part of writing, then go live.

- A deploy command that runs the staging command and uploads its output, so the site reflects the current state of the working directories.
- A preview deployment separate from production, built with its own site URL because Hugo writes the URL into links and feeds, and kept out of search indexes.
- A way to trigger a publish from the vault.
- The production domain, and the first real content.

**Done when:** one command publishes the fixture site to a preview URL, M4's separate URL command confirms that URL serves, and a new note written in Obsidian, marked `publish: true` and given a `date` and `slug`, reaches the live site with no change to this repo. `tools/check` never contacts a deployed site.

**Decisions:**
- Where the build runs. Recommended: locally or in CI through pixi, uploading the finished output, so Cloudflare never needs pixi and Hugo stays at the pinned version.
- Publish trigger. Recommended: start with a manual command, then add CI on vault pushes once the check command has earned trust. The `publish` rule keeps new notes off the site, but an automatic trigger would still put a half-finished edit to an already published note live.
- How a site under a path shares its domain with other content. Recommended: the blog's Worker claims a route such as `example.org/blog/*` and a separate Worker claims `example.org/*`. Cloudflare sends each request to the more specific route, so the other content deploys on its own and mdblog knows nothing about it. A request for `/blog` without the trailing slash matches only the other Worker's route, which then needs to redirect it.

## M6: POSSE

**Status:** Planned

Publish on the site first, then syndicate copies elsewhere. See [POSSE](https://indieweb.org/POSSE).

- Syndication of selected entries to chosen services, with a per-entry way to opt in.
- Idempotent runs, so rerunning never posts an entry twice. A crash between posting and recording the copy's URL is the hard case: the tool records its intent first, and reports an interrupted post for the author to resolve.
- Each copy's URL recorded and shown on the entry as a `u-syndication` link, which takes a rebuild and deploy after posting.

**Done when:** a new entry posts once to each chosen service, a repeat run posts nothing, a run interrupted after posting does not post again, and the entry page links to its copies. Tests run against fake service clients.

**Decisions:**
- Which services come first.
- Where syndication state lives. Writing to vault front matter makes the tool edit the author's notes, and a separate state file needs its own home and backup.
- What happens to copies when an entry is unpublished or deleted.

## M7: Backfeed

**Status:** Planned

Bring replies, likes and reposts back to the original entry. See [backfeed](https://indieweb.org/backfeed).

- Collection of responses from syndicated copies and from webmentions.
- Responses stored as data and rendered at build time, which keeps the site static.
- Moderation, so the author can hide a response.

**Done when:** a response on a syndicated copy appears on the entry after the next build, and a hidden response stays hidden across rebuilds.

**Decisions:**
- Hosted service or own collection. Recommended: start with a hosted webmention receiver and bridge, because receiving webmentions directly would need custom Worker code.
- Which response types to display, and how much of other people's content to store.
- Where response data lives, since it is neither framework code nor vault content.
