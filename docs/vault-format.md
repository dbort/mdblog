# Vault format

How mdblog reads an Obsidian vault: which notes it publishes, the properties and Obsidian syntax it reads, and the site files the vault holds.

mdblog reads every `.md` file outside `_site/`, skipping symbolic links and hidden paths, whose parts start with `.`. A note is published only when its front matter holds the boolean `publish: true`. Any note mdblog reads fails the build when its front matter is not UTF-8 or not a YAML mapping, including one with a duplicate key or an impossible date. Every other rule here applies only to published notes.

## Properties

mdblog reads only these properties. An empty property counts as missing, except an empty `publish`, which fails the build.

| Property | Required | Rule |
|---|---|---|
| `publish` | to publish | `true` or `false`. Anything else fails the build on any note. |
| `title` | no | A string. When missing, the title is the file name. |
| `date` | yes | A YAML date or datetime, not a quoted string, and not in the future, because nothing rebuilds the site when that date arrives. A datetime with no offset is the build machine's local time. |
| `slug` | yes | The page's URL, `/posts/<slug>/`. Lowercase ASCII letters and digits joined by single hyphens, unique across notes. |
| `tags` | no | A string or a list. `project/alpha` is its own tag, with no `project` tag implied. Each `/`-separated part uses letters, digits, `-`, `_`, `+` and `.`, with no spaces. Tags ignore case and display in lowercase. |

Every other property has no effect, including ones other site generators read, such as `aliases` or `draft`. A note's folder and file name never affect its URL.

## Obsidian syntax

mdblog converts this syntax outside code spans and code blocks, and publishes other Markdown as written.

| Syntax | Result |
|---|---|
| `[[note]]`, `[[note\|alias]]`, `![[note]]` | A link to the note's page. Notes are never transcluded. Inside a table, write `[[note\\|alias]]`. |
| `[[note#heading]]`, `[[#heading]]` | A link to the heading. |
| `[[note#^id]]`, `[[#^id]]` | A link to the top of the note. The block ID must exist. |
| `![[image.png]]` | The image. `\|300` sets its width, `\|300x200` its size, and any other alias its alt text. |
| `[[image.png]]` | A link to the image file. |
| `%%comment%%` | Removed. An unclosed `%%` removes the rest of the note. Comments hide text from the site, not from anyone who can read the vault. |
| `^block-id` | Removed at the end of a line. |
| `> [!type] Title` | A callout. `[!type]-` makes it collapsible and closed, `[!type]+` collapsible and open. |
| `==text==` | Highlighted text. |
| `#tag` in the body | Literal text. Only the `tags` property creates site tags. |

Raw HTML in a note renders as nothing. An image publishes only with a note or the bio that uses it.

A link target starting with `./` or `../` is a path from the note's folder, any other target holding `/` is a path from the vault root, and a bare name must be unique across the vault. Matching ignores case and the `.md` extension, and a note wins over another file with the same name. Heading matching ignores case and treats any run of punctuation and spaces as one space.

### Build failures

A published note fails the build when it holds:

- a link or embed that matches no file or several, or points outside the vault, into `_site/` or into a hidden folder
- a link or embed of a note that is unpublished or fails its own validation, or of a heading or block ID the note does not have
- a link or embed of a file that is neither a note nor an image (the image formats are `IMAGE_SUFFIXES` in [`src/mdblog/markdown.py`](../src/mdblog/markdown.py))
- two different images with the same file name
- a standard Markdown link or image whose destination has no URL scheme and does not start with `#`, such as `[text](note.md)`. Keep Obsidian's "Use [[Wikilinks]]" setting on.

Math, note transclusion, and audio, video and PDF players are unsupported. A callout type holding a hyphen, such as `[!custom-thing]`, renders as a plain quote. A link to a heading holding a numeric character reference, such as `&#42;`, can miss the heading without failing the build.

## Site folder

The `_site/` folder at the vault's root holds the site's own files. mdblog never publishes its notes or follows its symbolic links.

| Path | Required | Meaning |
|---|---|---|
| `_site/mdblog.toml` | yes | The site's `base_url`, `title` and `author`. A path in `base_url`, such as `https://example.test/blog/`, puts the whole site under that path. |
| `_site/bio.md` | no | The author's bio, shown on the site whatever its front matter says. Its links convert and fail like a note's. Keep its images outside `_site/`. |
| `_site/layouts/`, `_site/assets/` | no | Theme overrides. Each file replaces the packaged theme's file at the same path. |
| `_site/static/` | no | Files published at the site's root as they are. |
| `_site/Templates/` | no | Obsidian templates, such as the post template below. |

## Post template

To start new notes from [`templates/Post Template.md`](../templates/Post%20Template.md), copy it to `_site/Templates/` and set the folder of Obsidian's Templates core plugin to `_site/Templates`. The template has to live in `_site/`, because its unfilled placeholder is not valid YAML. Before publishing, fill in `title` unless the file name is the title you want.

## Draft preview

`mdblog serve --drafts` adds drafts, notes marked `publish: false`, labeled "Draft", and renders published notes that would fail the build, labeled "Invalid". A note with no `publish` property never appears. Instead of failing, a missing or invalid property falls back (`title` to the file name, `date` to the file's modification time, `slug` to one made from the file name, `tags` to none), a broken link stays as written, and a slug already taken gets a numeric suffix. Each problem other than a draft's missing property prints a warning. `mdblog build` never publishes a draft.
