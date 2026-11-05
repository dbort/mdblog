# Roadmap

The v1 target is a personal site in the shape of [jacobian.org](https://jacobian.org): a short bio on the home page, one reverse-chronological stream mixing posts, TILs and links, a date and tags on every entry, and a full archive. Notes are written in Obsidian and reach the site without anyone editing generated files.

That site is a model for what readers see. [Its publishing setup](https://jacobian.org/til/hugo-obsidian/) keeps the vault inside the site repo and converts notes in a pre-commit hook, while mdblog keeps the vault in a separate checkout and converts at build time.

A note publishes only when its front matter has `publish: true`, and a note without that property stays off the site. This keeps unfinished notes from going live, and it is not access control: nothing in the vault is secret, and an unpublished note can be read wherever the vault itself can. Supporting secrets would need its own milestone. There is no existing site, so nothing needs migrating or redirecting.

M1 to M5 make up v1. M6 and M7 follow it. Each milestone's decisions are settled in the `/new-task` interview that plans it, and each recommendation below is a starting point for that interview.

Search, comments, series, scheduled publishing, and packaging mdblog for other people's sites are outside v1. Each site's settings live in its own vault, so in the long run this repo can host multiple independent sites.

## M2: Obsidian Markdown conversion

**Status:** Tasks task-003, task-004

- [ ] task-003: Write front matter from a fixed property list and place pages by slug (blocked on task-002)
- [ ] task-004: Convert Obsidian links, embeds and syntax (blocked on task-003)

Turn Obsidian's Markdown into what Hugo expects.

- Front matter: the converter writes each page's front matter from scratch, reading `title`, `date`, `tags`, `slug`, `type` and a link entry's `url`. A missing title comes from the file name. Every other property is dropped, because the same name can mean something else to Hugo, and `docs/vault-format.md` lists the collisions. A Hugo feature wanted later, such as a redirect after a rename, gets its own property and is never passed through by name.
- Page placement: every entry type lives at `/posts/<slug>/`, so a note's vault folder, file name and type have no effect on its URL. `slug` and `type` are required on published notes.
- `date` means the publish date, so a note started months ago does not land months back in the stream and the feed. Hugo dates a note with no `date` as year 0001 and lists it last in the feed, and it leaves out a future-dated note with no warning, so the converter validates dates itself.
- Tags: the `tags` property sets site tags, and nested tags keep Hugo's nested paths. Inline `#tags` stay literal text.
- Links: `[[note]]`, `[[note|alias]]`, `[[note#heading]]` and `![[note]]` become links to site URLs. Internal standard Markdown links are unsupported.
- Images: `![[image.png]]`, with an optional size, becomes an image, and only images used by published notes are copied. Other attachments are unsupported.
- Obsidian-only syntax: strip `%%comments%%` and block IDs, and render callouts and `==highlights==`.
- One validation pass that fails the build on any broken or ambiguous link or embed, any link or embed of an unpublished note, any invalid `date`, `slug` or `type`, any unsupported link, and any two notes with one URL. A note goes live only when everything it links to is published, so no draft text can reach the site that way.
- A reference in `docs/` listing each vault property, its meaning and the collisions above, so the mapping and its reasoning outlive this milestone's section.

**Done when:** a fixture vault using each supported syntax renders correctly in a Hugo build, a fixture note carrying colliding properties produces the same page and feed entry as one without them, generated front matter holds only the listed keys, a broken link, a missing date and a URL collision in the fixture each fail the build with a report naming the notes involved, and tests confirm that an unpublished note's text and images do not reach the output through a link or embed.

## M3: Site design and content types

**Status:** Planned

Build the reader-facing site from the default Hugo layouts in the `mdblog` package, using fixtures until real content arrives.

- Three entry types: posts, TILs and links, all at `/posts/<slug>/`. The converter records the type as `.Params.entry_type` and a link's target as `.Params.link_url`, so list pages filter on those. A link entry points to the external page and carries a short commentary and its own permalink.
- A home page with the bio from the vault's `_site/` and recent entries of every type, plus a full archive and tag pages.
- An RSS feed covering all entries, advertised from each page's `<head>`. Hugo generates this as `index.xml`, newest first, and M6 and M7 can read it too.
- A visual design of its own that works at phone width, plus a 404 page.
- h-entry microformats in entry templates, so M6 and M7 need no template retrofit.

**Done when:** a fixture build generates every page type, the tests assert each entry's date, tags, permalink and h-entry markup, and `index.xml` parses as RSS and lists entries of all three types.

**Decisions:**
- Styling. Recommended: plain CSS through Hugo, which keeps Node out of the build.
- Full text or summaries in the feed. Hugo's built-in template sends only each entry's summary, which cuts a post at its `<!--more-->` break or, with no break, after its first paragraphs. Recommended: full text through a small template override, so people can read in their feed reader. The converter's links are root-relative, so the override needs to make them absolute.
- Which other feeds to keep. Hugo also generates one per section and per tag. Recommended: keep the main feed and the tag feeds, and turn off the rest.
- How a link entry appears in the feed: pointing at the external page or at its permalink here.

## M4: Deploy to Cloudflare

**Status:** Planned

Serve the built site from a Cloudflare Worker as static assets, with no custom Worker code.

- Node from conda-forge, and wrangler from npm with a committed `package-lock.json`. No wrangler package turned up on conda-forge, so `CLAUDE.md`'s line about adding wrangler to the pixi environment needs correcting.
- `tools/check` installs from the npm lockfile itself, so callers need no setup step, and fails on a stale lockfile, which `pixi run --locked` does not detect. Under `--offline`, the install and any check that depends on it skip.
- A deploy command that runs a fresh production build of the current working directories, then uploads it without `mdblog build`'s output marker, so the site reflects their current state and local preview output cannot reach Cloudflare.
- A separate command that takes a deployed URL and fails if it does not serve the home page and feed, runnable at any time and independent of a deploy.
- A preview deployment separate from production, built with its own site URL because Hugo writes the URL into links and feeds, and kept out of search indexes.
- Worker configuration checked in `tools/check`: a `wrangler deploy --dry-run` if it works without network access or credentials, otherwise a test of the fields the deploy relies on.

**Done when:** one command publishes the fixture site to a preview URL, a separate command confirms that URL serves, and the gate validates the Worker configuration on a machine without Cloudflare credentials. `tools/check` never contacts a deployed site.

**Decisions:**
- Where the build runs. Recommended: locally or in CI through pixi, uploading the finished output, so Cloudflare never needs pixi and Hugo stays at the pinned version.
- Whether custom headers are needed at launch.
- Where each site's Worker name and routes live. Recommended: in the vault's `_site/`, because this repo holds nothing site-specific.

## M5: Authoring workflow and launch

**Status:** Planned

Make publishing part of writing, then go live.

- A local preview of the real vault with live reload, which can include unpublished notes and marks them as such. In that mode the converter passes them to Hugo with a generated `draft: true`, runs Hugo with `--buildDrafts`, writes to its own output directory, and renders links and embeds of unpublished notes normally. Validation failures that stop a production build only warn in this mode. Authors only write `publish`.
- A check command that runs the build's validation pass with nothing deployed, so problems surface before anything goes live.
- Note templates for each entry type, for use in Obsidian. They leave out `publish` and `date`, so a new note starts unpublished with or without a template, and the author sets the date when publishing it.
- A way to trigger a publish from the vault.
- The production domain, and the first real content.

**Done when:** a new note written in Obsidian, marked `publish: true` and given a `date` and `slug`, reaches the live site with no change to this repo.

**Decisions:**
- Publish trigger. Recommended: start with a manual command, then add CI on vault pushes once the check command has earned trust. The `publish` rule keeps new notes off the site, but an automatic trigger would still put a half-finished edit to an already published note live.

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
