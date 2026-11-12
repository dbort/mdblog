---
name: new-task
description: Interview the user about a new unit of work and write its tasks/active/task-XXX task file. Use when the user starts a new task or asks to plan one.
---

# New task

Pipeline rules: `.claude/docs/pipeline.md`.

1. **Interview** the user the way `/grill-me` does (`pipeline.md`
   § Interviews and reporting): branch by branch until shared
   understanding, a recommended answer with every question, and the
   codebase explored instead of asked wherever it can answer. Spend
   questions on what only the user decides: behavior, edge cases, Must
   Haves, tradeoffs. Leave file-level mechanics to `/work`.
2. **Check** `CLAUDE.md` § Standing task-planning obligations. Each one
   shapes the plan, and the task file names it only where that section
   says to.
3. **Write** `tasks/active/task-XXX-<slug>.md` with the id from
   `python3 tools/task_status.py --next-id`, using the template below.
4. **Roadmap:** if the task delivers a `docs/roadmap.md` milestone, add it
   to that milestone's status and checklist (`pipeline.md` § Roadmap).
5. **Commit** the task file and any roadmap edit to `main` (`task-XXX: plan
   <title>`), link the file for the user without pasting it, and stop. The
   user starts the work with `/work task-XXX`.

Writing rules: `## Summary` is plain prose for a human skimmer and adds
information beyond the title. `## Decisions` and `## Notes` are dense and
imperative, for an agent: each item with its reason, current decisions
only, no history. Must Haves state observable behavior that a machine can
check ("returns HTTP 429 on rate limit", not "handles errors well"), and
name a test design only when the design is the requirement, such as a
real-tool test where a failure would be silent. A manual-QA case only for
what no test can assert. Write no file-level steps; `/work` writes the
Checklist. Notes hold only what `/work` cannot cheaply rediscover. Before
planning a change that deletes or renames a name, or changes what a test
fixture produces, grep code, comments and docs for every user of it and
name each affected file in Notes: a missed dependent surfaces only as an
unplanned failure late in `/work`.

```markdown
---
id: task-XXX
title: "Short title"
# blocked_by: [task-YYY]   # hard blockers only; omit otherwise
---

# task-XXX: Short title

## Summary
1-3 sentences: what the task does and why.

## Must Have
- [ ] Observable, machine-checkable behavior.

## Decisions
- User decisions and verified facts about outside tools, each with its reason.

## Notes
- Code pointers, suggested approaches, early checks, known dependents, ordering constraints.

## Checklist

## Review log
```
