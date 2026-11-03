---
next_id: bug-001
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
