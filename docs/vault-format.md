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

Each page's Hugo front matter is written from scratch, holding only `title`, `date`, `tags` when there are any, and `params`. `params` holds `entry_type` and, on a link entry, `link_url`. The note's body after its front matter reaches Hugo byte for byte.

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
