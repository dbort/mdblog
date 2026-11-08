# Hugo site

How mdblog maps the vault format in `docs/vault-format.md` onto Hugo and the packaged theme. The user doc states the contract with no Hugo terms, so it could describe a vault built by another generator; the Hugo-specific reasons and mechanics live here.

## Generated front matter

Each page's Hugo front matter is written from scratch, holding only `title`, `date` and, when there are any, `tags`. Under draft preview only, a draft also gets Hugo's `draft: true` and an invalid published note gets the page param `mdblog_invalid`. The note's body after its front matter reaches Hugo byte for byte, apart from the Obsidian conversions. Syntax mdblog does not convert reaches Hugo as written.

## Hugo collisions

A vault property that shares a name with a Hugo front matter key would change the site by accident, so none is passed through. A test builds a note carrying each of these and asserts the output matches the same note without them.

| Property | What Hugo would do with it |
|---|---|
| `aliases` | Generates redirect pages. |
| `url` | Moves the page. |
| `weight` | Reorders the feed. |
| `published` | Sets the publish date, which can hide the page or fail the build. |
| `expiryDate` | Can hide the page or fail the build. |
| `headless` | Publishes no page for the note. |
| `build` | Can stop the page rendering or listing. |
| `layout` | Selects a different layout. |
| `type` | Selects a different layout type. |
| `draft` | Hides the page. |
| `cascade` | Applies front matter to other pages. |
| `outputs` | Changes which formats the page renders to. |

A Hugo feature wanted later, such as a redirect after a rename, gets its own property and is never passed through by name.

## Dates

Hugo compares a date-only value as UTC midnight and would hide a note dated today at some local times, so the build runs Hugo with `--buildFuture` and applies the future-date rule itself.

## Tags

The tag character rule exists because Hugo removes some characters from a tag's path, and what remains could write outside `/tags/`: `!..` would become `..`. Requiring each segment to hold a letter or digit Hugo keeps closes that; a blocklist would not.

Hugo lowercases tag paths, so `Project/Alpha` builds at `/tags/project/alpha/` and shares a page with `project/alpha`. A nested tag builds a page only for itself: a note tagged only `project/alpha` builds no page at `/tags/project/`.

A tag holding `page/<number>`, such as `a/page/2`, can replace a page of tag `a`'s listing if a site's layouts paginate tag pages. The packaged layouts do not (user decision, 2026-11-04, task-003).

## Conversions

- A block link goes to the top of the note because Hugo gives a block nothing to link to.
- A callout renders with its type as its class. `[!type]-` renders a closed `<details>` and `[!type]+` an open one; a plain quote stays a `<blockquote>`.
- `==text==` renders as `<mark>text</mark>`.
- Every URL the build writes is root-relative and starts with the path of `base_url`, so with `base_url = "https://example.test/blog/"` a link reads `/blog/posts/<slug>/`. Each note is a leaf bundle, so an image is copied next to the page of each note that uses it and served at `/blog/posts/<slug>/<file name>`.
- A site can replace the default image and callout rendering with its own `_site/layouts/_markup/render-image.html` or `render-blockquote.html`. The default image layout reads an embed's size from `mdblog-width` and `mdblog-height` query parameters on the image's destination.
- Heading links follow Hugo's heading IDs, which the build computes on its own. A heading whose ID Hugo builds from a numeric character reference, such as `&#42;`, can get a different ID than the build expects, and its link then fails silently.

## Site folder

- The bio is written to `content/_index.md`, so Hugo renders it as the home page's `.Content`. An image it embeds is served at the home page's URL.
- `_site/layouts/` and `_site/assets/` are copied into the Hugo project, which Hugo prefers to the packaged theme's files with the same name. `_site/assets/` feeds Hugo's asset pipeline, and every page links `css/main.css`.
- `_site/static/` is Hugo's static directory.

## Packaged theme

- The home page lists the latest 15 entries and ends with an "All posts" button. `/posts/` lists all posts by year, each tag has a page listing its entries, and `/tags/` indexes the tags. No list is paginated.
- Every page has a sidebar, to the right on wide screens and after the content on narrow ones. It holds an About box with the bio, a Recent posts box with the five newest other entries and a link to `/posts/`, and a Tags box with the ten most used tags and a link to `/tags/`. A box with nothing to show is left out. The footer links the site's RSS feed.
- Each feed is RSS holding the full text of its latest 50 entries: `/index.xml` for the whole site and `/tags/<tag>/index.xml` for each tag.
- `recent.json` at the site's root, such as `/blog/recent.json` under `base_url = "https://example.test/blog/"`, lists the newest entries for pages outside the blog, such as a home page on the same domain that fetches it with a script. Its shape is a contract those pages rely on:
  - The file is a JSON object whose only key, `items`, holds an array of at most 5 objects, newest first. With no published entries the array is empty.
  - Each item has exactly the string keys `title`, `url` and `date`. `title` is the entry's page title. `url` is its absolute URL, the same as its `<link>` in `/index.xml`. `date` is ISO 8601 with a UTC offset, such as `2026-01-02T23:30:00-07:00`, and is the same instant as its `<pubDate>` in `/index.xml`.
  - The items are the entries the sidebar's Recent posts box lists on a page that is none of them, in the same order. The site param `mdblog_recent_limit` holds the limit both layouts read.
  - The shape is mdblog's own rather than JSON Feed 1.1, which requires content on every item and would make the file as heavy as the full-text feed.
  - The file is a Hugo output format named `recent` on the home page, with `notAlternative` set so a layout listing the page's alternative formats does not advertise it.

## Draft preview

The packaged partials `entry-status.html` and `preview-banner.html` draw the labels and the banner, and a site's `_site/layouts/` can replace them. They read Hugo's `.Draft` for the Draft label, the page param `mdblog_invalid` for the Invalid label, and the site param `mdblog_preview` for the banner.

The labels appear on an entry's page and in the home page, All posts and tag page lists. The sidebar's Recent posts box lists drafts and invalid entries without a label.
