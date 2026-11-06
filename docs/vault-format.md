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
| `type` | yes | The entry type, which layouts read as `.Params.entry_type`. | Exactly `post`, `til` or `link`. |
| `tags` | no | Site tags. `project/alpha` builds a tag page at `/tags/project/alpha/`. | One string or a list of strings. Each `/`-separated part may use only letters, combining marks, digits, `-`, `_`, `+` and `.`, must hold a letter or digit, and when it holds a `.` must hold an ASCII letter or digit. Anything else fails, including spaces, because Hugo removes some characters from a tag's path, and what remains could write outside `/tags/`. |
| `url` | on `type: link` | The linked page, which layouts read as `.Params.link_url`. | An `http` or `https` URL. On `post` and `til` notes `url` has no effect, whatever its value. |

A note's vault folder, file name and type have no effect on its URL, so moving or retyping a note never moves its page.

Hugo lowercases tag paths, so `Project/Alpha` builds at `/tags/project/alpha/` and shares a page with `project/alpha`. A tag holding `page/<number>`, such as `a/page/2`, can replace a page of tag `a`'s listing if a site's layouts paginate tag pages. The packaged layouts do not.

A future date fails the build because nothing rebuilds the site when that date arrives. Hugo compares a date-only value as UTC midnight and would hide a note dated today at some local times, so the build runs Hugo with `--buildFuture` and applies the rule itself.

## Generated front matter

Each page's Hugo front matter is written from scratch, holding only `title`, `date`, `tags` when there are any, and `params`. `params` holds `entry_type` and, on a link entry, `link_url`. The note's body after its front matter reaches Hugo byte for byte, apart from the conversions under [Obsidian syntax](#obsidian-syntax).

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
