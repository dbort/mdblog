# Vault format

How `mdblog build` reads a vault's notes. A note reaches the site only when its front matter holds the boolean `publish: true`. The other rules on this page apply only to those notes, so a draft can hold any properties, as long as its front matter parses. Every selected note fails the build on invalid YAML, including an impossible date like `2026-13-45`, a duplicate key, a block that is not a mapping or text that is not UTF-8.

## Properties

The build reads these properties and ignores every other one. An empty property in Obsidian is null, and null counts as missing, except on `publish`, where it fails the build.

| Property | Required | Meaning | Validation |
|---|---|---|---|
| `publish` | to publish | Puts the note on the site. | `true` or `false`. Anything else, such as `yes` or `"true"`, fails the build, on any selected note. |
| `title` | no | The page title. | A string. When missing, the title is the file name without `.md`. |
| `date` | yes | The publish date. | A YAML date or datetime, not a quoted string. A date after the local date or a datetime after the current time fails. A datetime with no offset means the local time of the machine running the build, and is published with that offset. |
| `slug` | yes | Sets the page's URL, `/posts/<slug>/`. | Lowercase ASCII letters and digits joined by single hyphens, such as `first-note`. Two notes with one slug fail, and the message names both. |
| `tags` | no | Site tags. `project/alpha` builds a tag page at `/tags/project/alpha/`. | One string or a list of strings. Each `/`-separated part may use only letters, combining marks, digits, `-`, `_`, `+` and `.`, must hold a letter or digit, and when it holds a `.` must hold an ASCII letter or digit. Anything else fails, including spaces, because Hugo removes some characters from a tag's path, and what remains could write outside `/tags/`. |

A note's vault folder and file name have no effect on its URL, so moving or renaming a note never moves its page.

Hugo lowercases tag paths, so `Project/Alpha` builds at `/tags/project/alpha/` and shares a page with `project/alpha`. Tag text also displays in lowercase, so `Node.JS` shows as `node.js`. A nested tag builds a page only for itself: a note tagged only `project/alpha` builds no page at `/tags/project/`. A tag holding `page/<number>`, such as `a/page/2`, can replace a page of tag `a`'s listing if a site's layouts paginate tag pages. The packaged layouts do not.

A future date fails the build because nothing rebuilds the site when that date arrives. Hugo compares a date-only value as UTC midnight and would hide a note dated today at some local times, so the build runs Hugo with `--buildFuture` and applies the rule itself.

## Generated front matter

Each page's Hugo front matter is written from scratch, holding only `title`, `date` and, when there are any, `tags`. Under [draft preview](#draft-preview) only, a draft also gets Hugo's `draft: true` and an invalid published note gets the page param `mdblog_invalid`. The note's body after its front matter reaches Hugo byte for byte, apart from the conversions under [Obsidian syntax](#obsidian-syntax).

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

## Obsidian syntax

The build converts the Obsidian syntax below in each published note. Any other syntax reaches Hugo as written. None of it applies inside fenced code, indented code or inline code, which stay byte for byte, and none of it applies to unpublished notes.

| Syntax | Result |
|---|---|
| `[[note]]`, `[[note\|alias]]` | A link to the note's page. The link text is the alias, or otherwise the target as written. Inside a table, write the alias as `[[note\\|alias]]`. |
| `[[note#heading]]`, `[[#heading]]` | A link to that heading of the note, or of the current note. `[[note#a#b]]` targets heading `b`. |
| `[[note#^id]]`, `[[#^id]]` | A link to the top of the note, because Hugo gives a block nothing to link to. The block ID must exist. |
| `![[note]]` | The same link as `[[note]]`. Notes are never transcluded. |
| `![[image.png]]` | The image. `![[image.png\|300]]` sets its width, `![[image.png\|300x200]]` its width and height, and any other alias its alt text, which is otherwise the file name. |
| `[[image.png]]` | A link to the image file. |
| `%%comment%%` | Removed, inline or across lines, along with any links inside it. A `%%` with no closing `%%` removes the rest of the note, because leaking a private aside is worse than losing text. A comment hides text only on the site, since the vault itself is not secret. |
| `^block-id` | Removed when it ends a line or stands alone on one. |
| `> [!type] Title` | A callout with the type as its class and the title, or the capitalized type, as its heading. `[!type]-` renders a closed `<details>` and `[!type]+` an open one. A plain quote stays a `<blockquote>`. |
| `==text==` | `<mark>text</mark>`. |
| `#tag` in the body | Literal text. Only the `tags` property creates site tags. |

Every URL the build writes is root-relative and starts with the path of `base_url`, so with `base_url = "https://example.test/blog/"` a link reads `/blog/posts/<slug>/`. An image is copied next to the page of each note that uses it and served at `/blog/posts/<slug>/<file name>`. An image no published note uses is never copied.

A site can replace the default image and callout rendering with its own `_site/layouts/_markup/render-image.html` or `render-blockquote.html`. The default image layout reads an embed's size from `mdblog-width` and `mdblog-height` query parameters on the image's destination.

### Finding a link's target

The part of a target before the first `#` names a file, found in this order:

1. A target starting with `./` or `../` is a path from the note's folder.
2. Any other target holding `/` is a path from the vault root.
3. Anything else is a file name, which must be unique across the vault, ignoring folders.

Case never matters. A note matches with or without `.md`, and a note wins over any other file with the same name, so `[[v1.2 notes]]` finds `v1.2 notes.md`. A heading matches ignoring case and treating each run of punctuation and spaces as one space, so `[[note#Café Über]]` matches the heading `Café & Über:`. When two headings match, the link goes to the first. Files in `_site/`, in a folder or with a name starting with `.`, and symbolic links are never found.

### Build failures

A published note fails the build when it holds any of these, and the message names the note and the link as written:

- a link or embed that matches no file, matches more than one, resolves outside the vault, or targets a path under `_site/` or a hidden folder
- a link or embed of a note that is not published, or that fails its own validation
- a heading or block ID the target note does not have, outside its comments
- a link or embed of a file other than a note or an `avif`, `bmp`, `gif`, `jpeg`, `jpg`, `png`, `svg` or `webp` image (in any case), such as `paper.pdf` or `clip.mp4`
- two different images with the same file name, because they would share one URL on the page
- a standard Markdown link or image, inline or reference-style, whose destination has no URL scheme and does not start with `#`, such as `[text](note.md)`; keep Obsidian's "Use [[Wikilinks]]" setting on

One build reports every failure in every note, together with the property failures above, and leaves the output directory unchanged. A note goes live only when everything it links to is published.

Raw HTML in a note renders as nothing, so an `<img>` or `<a>` written in a note cannot bypass these rules.

### Known limits

- Math, note transclusion and audio, video and PDF players are unsupported.
- A callout type holding a hyphen, such as `[!custom-thing]`, renders as a plain quote with its marker as literal text.
- Heading links follow Hugo's heading IDs, which the build computes on its own. A heading whose ID Hugo builds from a numeric character reference, such as `&#42;`, can get a different ID than the build expects, and its link then fails silently.

## Site folder

The `_site/` folder at the vault's root holds the site's own files. Its notes are never published, and a link into it fails the build. The build never follows a symbolic link inside it.

| Path | Required | Meaning |
|---|---|---|
| `_site/mdblog.toml` | yes | The site's `base_url`, `title` and `author`. `base_url` may hold a path, such as `https://example.test/blog/`, and every page, link and feed then lives under `/blog/`. A trailing slash makes no difference. |
| `_site/bio.md` | no | The author's bio, rendered on the home page above the latest entries. Without it the home page has no bio. Its front matter has no effect, including `publish: false`. Its wikilinks and embeds convert as a note's do and fail the build the same way, with failures naming `_site/bio.md`. An image it embeds is served at the home page's URL. Because no link may target `_site/`, keep the bio's images elsewhere in the vault. A symbolic link at this path fails the build. |
| `_site/layouts/` | no | Hugo layouts that replace the packaged ones with the same name, such as `page.html`, `_partials/footer.html` or `_markup/render-image.html`. |
| `_site/assets/` | no | Files for Hugo's asset pipeline, replacing packaged assets with the same path. `_site/assets/css/main.css` replaces the packaged stylesheet, which every page links. |
| `_site/static/` | no | Files copied to the site's root as they are, so `_site/static/favicon.ico` is served at `/favicon.ico`. |

## Pages and feeds

The packaged layouts build the home page with the latest 15 entries, an archive of every entry by year at `/posts/`, a page per tag listing its entries, an index of tags at `/tags/`, and a page per entry. No list is paginated.

Each feed is RSS holding the full text of its latest 50 entries: `/index.xml` for the whole site and `/tags/<tag>/index.xml` for each tag.

## Draft preview

`mdblog serve --drafts` previews the site with the notes still being written. `mdblog build` has no such option, so a built site never holds a draft, a label or the banner.

The preview holds every note `mdblog build` would publish, and every draft: a note whose front matter holds the boolean `publish: false`. A note with no `publish` property stays off the preview, whatever its other properties, so journals and reference notes never appear. A note whose front matter does not parse, whose `publish` is not a boolean, or whose text is not UTF-8 is left out with a warning.

A draft needs no properties beyond `publish: false`:

- With no `date`, it takes the file's modification time in the local zone, with its offset. A future date stays as written.
- With no `slug`, it takes one made from its file name: lowercased, each run of characters other than ASCII letters and digits turned into one hyphen, and hyphens trimmed from the ends, so `My Draft Note.md` gets `my-draft-note`. A name with no ASCII letter or digit, such as one in a non-Latin script, gets `note`.
- A property that is present but invalid prints a warning naming the note and the property, and the note still renders: an invalid `title` falls back to the file name, an invalid `date` to the modification time, an invalid `slug` to the file-name slug and invalid `tags` to no tags.

A published note that would fail the build renders anyway with the same fallbacks, and prints one warning per failure, link failures included. A future date on it is kept.

Every slug stays unique. A note's own valid slug wins over a generated one, a published note's own slug wins over a draft's, and between two drafts or two published notes, the first by vault path keeps it. Every other note, in path order, adds the first free numeric suffix, such as `my-draft-2`, and prints a warning naming the note holding the slug. A published note whose own slug was taken counts as failing.

A link or embed that would fail the build stays on the page exactly as written, which shows where it is, and prints a warning. This applies to the bio too. A link to a draft goes to the draft's page.

Pages show what each entry is:

- A draft carries a "Draft" label on its page and in every list that shows it: the home page, the archive and the tag pages.
- A published note that fails in any way carries an "Invalid" label in the same places.
- Every page carries a banner at the top saying it is a draft preview and not the live site.

The feeds include drafts, but the preview's feeds are never published.

After each rebuild, `serve --drafts` prints the current warnings to stderr as `path: reason` lines, in the format of `mdblog build`'s failures, under a heading that says they are warnings. A failing note never stops or delays the preview. An unusable `_site/mdblog.toml` still stops it until a change fixes the file, as with plain `serve`.

The packaged partials `entry-status.html` and `preview-banner.html` draw the labels and the banner, and a site's `_site/layouts/` can replace them. They read Hugo's `.Draft` for the Draft label, the page param `mdblog_invalid` for the Invalid label, and the site param `mdblog_preview` for the banner.
