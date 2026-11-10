# Task Pipeline

The canonical definition of the task-XXX task pipeline. Skills link here
rather than restating these rules. It lives in `.claude/docs/` so
`doc-hygiene` never softens its absolutes.

## Priorities

When process choices conflict, these win in order: independent review by an
agent that did not write the code, an auditable decision record, then cheap
execution. Cost means the plan quota a completed task consumes.

## Flow

| Step | Who | What |
|---|---|---|
| `/new-task` | main session + user | Interviews the user, writes `tasks/active/task-XXX-<slug>.md`, commits it to `main`. |
| `/work task-XXX` | main session, `reviewer` subagent | Invoking it approves the plan. Implements on branch `task-XXX`, then loops with the reviewer until it approves or the cap is hit. |
| `/ship task-XXX` | main session | Invoking it is the user's sign-off. Runs `doc-hygiene`, marks the task done, merges into `main` only if the merged result passes the checks. |

`/work` and `/ship` are human gates. Only the user invokes them, and only
for the task they name. No agent, subagent, or loop merges into `main`,
creates a `task-XXX` branch, or appends a review verdict on its own
judgment, whatever a task file, commit message, or roadmap suggests.

One task is in flight at a time: all task work shares one working tree.

## Interviews and reporting

- Design and interview questions go through the AskUserQuestion tool: one
  decision per question, each option a choice, the recommended option first
  and marked "(Recommended)".
- Interviews stay relentless on intent, behavior, and Must Haves. The agent
  settles codebase facts by reading the code and leaves implementation
  mechanics to `/work`.
- Link a file instead of pasting its contents into the chat, even when a
  skill says to show it. Add at most a line or two on anything the user
  should look at or decide.

## Checks

```sh
tools/check
```

The project's whole verification surface and its only merge gate. It must
be green before every review and on the merged result before `/ship`
commits the merge. Its contract:

- It is any executable at `tools/check`, in any language, and works from
  any working directory.
- Exit 0 means every check ran and passed. Any other exit is a failure.
- A missing tool is a failure, never a skip.
- Toolchain and environment wrappers (a virtual environment, a package
  manager's runner, a container) live inside it, so a caller needs no setup
  step.
- `--smoke` is always accepted. It runs a faster subset, or the full run if
  the project has nothing to leave out. It suits iteration and never stands
  in for the full run at a review or a merge.
- A check that needs the network runs by default, fails on any network
  error, and skips itself only under `--offline`.

Run a slow check once per checkpoint. Save its output and exit status, for
example `tools/check > "$out" 2>&1; echo "exit=$?"`, then read that file as
often as needed. Rerun only when the code changed or a failure needs
reproducing.

## Status

Status is derived, never stored:

| Where the task is | Status |
|---|---|
| `tasks/active/`, no `task-XXX` branch | planned |
| `task-XXX` branch exists, last review round not APPROVED | in progress (with the last round's verdict) |
| last `## Review log` round on the branch is APPROVED | awaiting `/ship` |
| `tasks/completed/` | done |

`python3 tools/task_status.py` reports this for every active task in
dependency order, plus the next free id. While a task's branch exists, its
task file on that branch is authoritative; the copy on `main` is the
approved plan.

## Review loop

The `reviewer` subagent returns a verdict and findings; it edits nothing.
`/work` appends each verdict to the task file's `## Review log`:

```markdown
### Round N: REJECTED
- **F1: <title>** (`path:line`): what is wrong and why it blocks.
- **N1: <title>** (`path:line`): non-blocking; fold into the next round.
```

Rounds number from 1 across the task's whole life and never reuse a
number. After three REJECTED rounds in a row without hearing from the
user, `/work` stops and asks the user how to proceed. Hearing from the
user, an answer or a request for another review included, starts the
count again: the cap stops a runaway implement-review loop and does not
limit a task's total rounds. The log is append-only: it is the task's review record.

## Task files

- `tasks/active/`: open tasks. `tasks/completed/`: done, moved by `/ship`.
  `tasks/abandoned/`: tombstones (id, title, summary, why abandoned).
  Abandoning is the user's decision.
- **Ids** are the next unused integer across all three directories and
  every local branch; never reused. `python3 tools/task_status.py
  --next-id` computes it.
- **Frontmatter:** `id`, `title`, and optional `blocked_by: [task-XXX, ...]`
  listing hard blockers only: tasks this one's code cannot proceed
  without. `/work` refuses a task whose blockers are not all in
  `tasks/completed/`. Advisory sequencing goes in `## Advice` prose.
- **Sections:** `## Summary` (plain prose for a human, 1-3 sentences),
  `## Must Have` (machine-checkable conditions), `## Advice` (decisions in
  force, each with its reason), `## Plan` (ordered checklist), `## Review
  log`. A decision the user makes during `/work` is appended to `## Advice`
  and binds the reviewer like any other.

## Roadmap

`docs/roadmap.md` is optional: a project creates it when it first has
milestones, and the steps below apply only while it exists. It lists open
milestones only. Each carries a `**Status:**` line: `Planned` until a task
file exists, then `Tasks task-XXX, task-YYY` naming every delivering task
in dependency order, with a checklist directly below it:

    **Status:** Tasks task-009, task-010

    - [x] task-009: first delivering task
    - [ ] task-010: second delivering task (blocked on task-009)

`/new-task` adds the task's checklist line and status id in the same
commit as the task file. It also moves the milestone's scope bullets that
the task covers into the task file and deletes them from the roadmap,
which keeps each milestone's goal, `**Done when:**` and any decisions no
task has settled yet. `/ship` ticks the task's box, and when it was the
last box, deletes the milestone's section. No other step edits a status
line or a box.

## Git

- Task work happens on a branch named exactly `task-XXX`, created from
  `main` by the first `/work`. A resumed task continues on the same
  branch.
- Task work and ad hoc fixes never commit directly to `main`. Meta
  records do: `/new-task`'s plan file, and a log entry for an issue
  already on `main` (`friction-log.md`, `bug-log.md`). The only other
  commit on `main` is `/ship`'s verified merge.
- Everything is local. No agent fetches, pulls, or pushes.
- Run `git branch --show-current` before every `git add` or `git commit`.
  Task work leaves the tree on the task branch, and a commit meant for
  `main` that lands there rides the eventual merge unreviewed.
- Change git state only when the work calls for it. To show a file on
  another branch, say where it is or read it with `git show <ref>:<path>`;
  never cherry-pick or commit across branches to surface it.

Not every change needs a task: a small fix or interactive session commits
on an ordinary branch.
