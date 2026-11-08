# Vault format

How mdblog reads an Obsidian vault: which notes it publishes, the properties it reads, the Obsidian syntax it converts and the site files the vault holds.

A note is published only when its front matter holds the boolean `publish: true`. The other rules on this page apply only to those notes, so a draft can hold any properties, as long as its front matter parses. Every selected note fails the build on invalid YAML, including an impossible date like `2026-13-45`, a duplicate key, a block that is not a mapping or text that is not UTF-8.

## Properties

mdblog reads these properties and ignores every other one. An empty property in Obsidian is null, and null counts as missing, except on `publish`, where it fails the build.

| Property | Required | Meaning | Validation |
|---|---|---|---|
| `publish` | to publish | Puts the note on the site. | `true` or `false`. Anything else, such as `yes` or `"true"`, fails the build, on any selected note. |
| `title` | no | The page title. | A string. When missing, the title is the file name without `.md`. |
| `date` | yes | The publish date. | A YAML date or datetime, not a quoted string. A date after the local date or a datetime after the current time fails. A datetime with no offset means the local time of the machine running the build, and is published with that offset. |
| `slug` | yes | Sets the page's URL, `/posts/<slug>/`. | Lowercase ASCII letters and digits joined by single hyphens, such as `first-note`. Two notes with one slug fail, and the message names both. |
| `tags` | no | Site tags. `project/alpha` has its page at `/tags/project/alpha/`. | One string or a list of strings. Each `/`-separated part may use only letters, combining marks, digits, `-`, `_`, `+` and `.`, must hold a letter or digit, and when it holds a `.` must hold an ASCII letter or digit. Anything else fails, including spaces, because each part becomes part of a URL. |

A note's vault folder and file name have no effect on its URL, so moving or renaming a note never moves its page.

Tags ignore case. `Project/Alpha` and `project/alpha` are one tag, and tags display in lowercase, so `Node.JS` shows as `node.js`. A nested tag stands alone: a note tagged only `project/alpha` creates no `project` tag.

A future date fails the build, because nothing rebuilds the site when that date arrives.

Properties that site generators often read, such as `aliases`, `url`, `draft`, `weight` or `layout`, have no effect, like any other property not listed above.

## Obsidian syntax

mdblog converts the Obsidian syntax below in each published note, and publishes any other Markdown as written. None of it applies inside fenced code, indented code or inline code, which stay byte for byte, and none of it applies to unpublished notes.

| Syntax | Result |
|---|---|
| `[[note]]`, `[[note\|alias]]` | A link to the note's page. The link text is the alias, or otherwise the target as written. Inside a table, write the alias as `[[note\\|alias]]`. |
| `[[note#heading]]`, `[[#heading]]` | A link to that heading of the note, or of the current note. `[[note#a#b]]` targets heading `b`. |
| `[[note#^id]]`, `[[#^id]]` | A link to the top of the note, because a block has no anchor on the site. The block ID must exist. |
| `![[note]]` | The same link as `[[note]]`. Notes are never transcluded. |
| `![[image.png]]` | The image. `![[image.png\|300]]` sets its width, `![[image.png\|300x200]]` its width and height, and any other alias its alt text, which is otherwise the file name. |
| `[[image.png]]` | A link to the image file. |
| `%%comment%%` | Removed, inline or across lines, along with any links inside it. A `%%` with no closing `%%` removes the rest of the note, because leaking a private aside is worse than losing text. A comment hides text only on the site, since the vault itself is not secret. |
| `^block-id` | Removed when it ends a line or stands alone on one. |
| `> [!type] Title` | A callout headed by its title, or by its type capitalized. `[!type]-` makes it collapsible and closed, and `[!type]+` collapsible and open. A plain quote stays a quote. |
| `==text==` | Highlighted text. |
| `#tag` in the body | Literal text. Only the `tags` property creates site tags. |

An image is published with each note that embeds it. An image no published note uses is never published.

Raw HTML in a note renders as nothing, so an `<img>` or `<a>` written in a note cannot bypass these rules.

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

### Known limits

- Math, note transclusion and audio, video and PDF players are unsupported.
- A callout type holding a hyphen, such as `[!custom-thing]`, renders as a plain quote with its marker as literal text.
- A link to a heading holding a numeric character reference, such as `&#42;`, can miss the heading without failing the build.

## Site folder

The `_site/` folder at the vault's root holds the site's own files. Its notes are never published, and a link into it fails the build. The build never follows a symbolic link inside it.

| Path | Required | Meaning |
|---|---|---|
| `_site/mdblog.toml` | yes | The site's `base_url`, `title` and `author`. `base_url` may hold a path, such as `https://example.test/blog/`, and every page, link and feed then lives under `/blog/`. A trailing slash makes no difference. |
| `_site/bio.md` | no | The author's bio, which the theme shows on the site. Its front matter has no effect, including `publish: false`. Its wikilinks and embeds convert as a note's do and fail the build the same way, with failures naming `_site/bio.md`. Because no link may target `_site/`, keep the bio's images elsewhere in the vault. A symbolic link at this path fails the build. |
| `_site/layouts/`, `_site/assets/` | no | Theme overrides: each file replaces the packaged theme's layout or asset at the same path, so `_site/assets/css/main.css` replaces the stylesheet. |
| `_site/static/` | no | Files published at the site's root as they are, so `_site/static/favicon.ico` is served at `/favicon.ico`. |

## Draft preview

`mdblog serve --drafts` previews the site with the notes still being written. `mdblog build` has no such option, so a built site never holds a draft.

The preview holds every note `mdblog build` would publish, and every draft: a note whose front matter holds the boolean `publish: false`. A note with no `publish` property stays off the preview, whatever its other properties, so journals and reference notes never appear. A note whose front matter does not parse, whose `publish` is not a boolean, or whose text is not UTF-8 is left out with a warning.

A draft needs no properties beyond `publish: false`:

- With no `date`, it takes the file's modification time in the local zone, with its offset. A future date stays as written.
- With no `slug`, it takes one made from its file name: lowercased, each run of characters other than ASCII letters and digits turned into one hyphen, and hyphens trimmed from the ends, so `My Draft Note.md` gets `my-draft-note`. A name with no ASCII letter or digit, such as one in a non-Latin script, gets `note`.
- A property that is present but invalid prints a warning naming the note and the property, and the note still renders: an invalid `title` falls back to the file name, an invalid `date` to the modification time, an invalid `slug` to the file-name slug and invalid `tags` to no tags.

A published note that would fail the build renders anyway with the same fallbacks, and prints one warning per failure, link failures included. A future date on it is kept.

Every slug stays unique. A note's own valid slug wins over a generated one, a published note's own slug wins over a draft's, and between two drafts or two published notes, the first by vault path keeps it. Every other note, in path order, adds the first free numeric suffix, such as `my-draft-2`, and prints a warning naming the note holding the slug. A published note whose own slug was taken counts as failing.

A link or embed that would fail the build stays on the page exactly as written, which shows where it is, and prints a warning. This applies to the bio too. A link to a draft goes to the draft's page.

The preview labels each draft "Draft" and each published note that fails "Invalid", and every page carries a banner saying it is a draft preview and not the live site. The preview's feeds include drafts but are never published.

After each rebuild, `serve --drafts` prints the current warnings to stderr as `path: reason` lines, in the format of `mdblog build`'s failures, under a heading that says they are warnings. A failing note never stops or delays the preview. An unusable `_site/mdblog.toml` still stops it until a change fixes the file, as with plain `serve`.
