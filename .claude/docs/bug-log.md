---
next_id: bug-002
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

- `bug-001` - **One glyph can build two tag pages**: a note tagged `café`
  with precomposed `é` (U+00E9) and a note tagged `café` with decomposed
  `é` (`e` + U+0301) both pass validation and build separate directories
  under `tags/`, so a reader sees the same tag twice with each page listing
  only some of its notes. Obsidian or an editor can write either form, and
  the two look identical in the note. Found while probing tags against real
  Hugo during task-003, and reproduced on Linux. macOS is untested, where
  the filesystem may treat the two paths as one. Root cause:
  `_is_safe_tag_segment` and `_tags` in `src/mdblog/properties.py` pass the
  tag text through unchanged and Hugo keeps the bytes it receives, while
  case variants merge because Hugo lowercases tag paths. Canonicalize tags
  so each glyph emits one tag however it is composed, for example with
  Unicode NFC before front matter is written. Fix: a task, not yet planned,
  because choosing the normalization form and where it applies is a design
  decision on the rule every tag passes through.
