---
next_id: bug-004
---

# Bug log

Functional defects in the project on `main`: wrong output, a refusal that
should succeed, a crash, behavior that contradicts the design docs or a
task's Must Haves. Log one in the same session when it will outlive that
session. A defect fixed at once gets no entry; its fixing commit describes
it. Friction in building the project goes in `friction-log.md`.

Format, oldest first:

- `bug-NNN` - **<what's wrong>**: what a user sees, how it was found, and
  the root cause once known. Fix: `ad hoc` or `task-XXX task`, with the
  reason for that call.

Ad hoc suits a small, localized fix whose correct behavior is not in
question. A task suits a fix to shared logic or one that needs a design
decision.

The id is `next_id` from the front matter; increment it in the same
commit. It only moves forward, even when entries are deleted. An entry
written during task work commits on the task's branch. A commit that
fixes the entry, or removes the code it concerns, deletes it. Sweeping the
log happens only when the user asks.

## Entries

- `bug-001` - **One glyph can build two tag pages**: tags `café` with precomposed `é` (U+00E9) and with decomposed `é` (`e` + U+0301) both validate and build separate directories under `tags/`, so readers see one tag twice, each page listing only some notes. Editors can write either form, and they look identical. Found probing tags against real Hugo in task-003, reproduced on Linux, untested on macOS. Root cause: `_tags` in `src/mdblog/properties.py` passes tag text through unchanged, and Hugo keeps the bytes it receives. Canonicalize tags, for example with Unicode NFC, before writing front matter. Fix: a task, not yet planned, because choosing the normalization form and where it applies is a design decision.

- `bug-002` - **A footnote whose text is one word fails the build**: `text[^1]` with `[^1]: Word.` fails with "Markdown link to 'Word.' is internal; use a wikilink", though Hugo renders a footnote. Found in task-006. Root cause: `internal_destinations` in `src/mdblog/markdown.py` parses plain CommonMark, which reads `[^1]: Word.` as a link reference definition. A definition holding a space is not one, so most footnotes pass. Fix: `ad hoc`, with a footnote plugin or by skipping `[^...]` labels, since the correct behavior is not in question.

- `bug-003` - **Footnote links in the home and tag lists point at the list page**: list summaries keep Goldmark's page-relative footnote hrefs (`#fn:1`), so two entries on one list share ids, and a reference before `<!--more-->` points at a target the list lacks. Entry pages and feeds are correct. Found by task-006's review. Hugo 0.169 has no footnote id prefix, so a fix rewrites the hrefs in the list layouts, as the feed item partial does, or prefixes the ids per entry. Fix: `task-XXX task`, because choosing between those needs a design decision.
