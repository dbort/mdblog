---
id: task-018
title: "Work tasks in parallel git worktrees"
---

# task-018: Work tasks in parallel git worktrees

## Summary
Let several `/work` sessions run at once by giving every task its own git
worktree named after it, while the primary checkout stays on `main` and is
the only place that touches `main`. A small checker script tells agents
whether they are in the right tree, so they need not interpret the rules
themselves.

## Must Have
- [ ] `.gitignore` ignores `.claude/worktrees/`.
- [ ] `tools/task_tree.py` exists with modes `work task-XXX`, `ship task-XXX` and `main`. Each exits 0 when its preconditions hold and nonzero with a message naming the offending tree and branch otherwise.
- [ ] Every mode fails when `main` is checked out in any worktree other than the primary, or when any `task-NNN` branch is checked out anywhere other than `.claude/worktrees/task-NNN`.
- [ ] `work task-XXX` passes only when run from the primary checkout or from `.claude/worktrees/task-XXX`, and prints exactly one of `create <path>`, `enter <path>` or `here <path>` on success.
- [ ] `ship task-XXX` passes only when run from the primary checkout, on `main`, with a clean tree, no merge or rebase in progress, and a clean `.claude/worktrees/task-XXX`. It also passes when `task-XXX` is already merged into `main`, so `/ship`'s cleanup path can run.
- [ ] `main` passes only when run from the primary checkout on `main`.
- [ ] `tests/` cover each pass and fail rule above through an importable decision function fed fake `git worktree list --porcelain` output. One end-to-end test runs real git on a temp repo with one task worktree.
- [ ] `.claude/docs/pipeline.md` no longer contains "One task is in flight". It has a `## Worktrees` section stating the three rules in Advice, and it names `tools/task_tree.py` as the guard.
- [ ] `.claude/skills/work/SKILL.md`, `.claude/skills/ship/SKILL.md` and `.claude/skills/new-task/SKILL.md` run `tools/task_tree.py` in preflight and stop on a nonzero exit.
- [ ] `/ship` runs `git worktree remove` on the task's worktree before `git branch -d task-XXX`.
- [ ] `tools/check` passes.

## Advice
- **Rules (user decision):** (1) every `/work` happens in `.claude/worktrees/task-XXX`, a worktree named after the task; (2) only that task's session checks out `task-XXX`; (3) no worktree other than the primary checkout checks out or modifies `main`. The primary checkout stays on `main` permanently, so git's refusal to check out a branch in two trees enforces rule 3 for checkouts.
- **Guard (user decision):** enforce the rules through docs and skill preflight, with no git hooks. `tools/task_tree.py` exists so agents run a deterministic check instead of interpreting prose. The primary is the first entry of `git worktree list --porcelain`, never a hardcoded `/workspace`, because the repo holds no machine-specific paths. Put the decision logic in a pure function over parsed porcelain plus the current toplevel and status, so tests feed it fakes. Per CLAUDE.md's **Test where the risk is**, this tooling gets tests because a guard that passes wrongly silently lets a session touch the wrong branch.
- **Creating the worktree:** `/work` runs `git worktree add .claude/worktrees/task-XXX -b task-XXX main` (or omits `-b` when the branch already exists), then switches the session in with `EnterWorktree` using `path`. Never call `EnterWorktree` with `name`: it creates its own branch from `origin/<default>`, and this repo has no remote. The skill's instruction is what authorizes the tool, since the tool requires explicit worktree instructions. Worktrees live under `.claude/worktrees/` because `EnterWorktree` with `path` accepts only that location, and shell `cd` persists only inside the working directory. Ruff respects `.gitignore`, and pyrefly and pytest already limit themselves to `src`, `tests` and `tools`, so nested trees stay out of `tools/check`.
- **Where `/ship` runs (user decision):** one `/ship` from a session in the primary checkout. For hygiene and finalize, it switches into the task's worktree with `EnterWorktree` `path`, because `doc-hygiene` and `git mv` act on the cwd's tree. It returns with `ExitWorktree` `keep`, then merges and runs `tools/check` in the primary checkout. Committing in the task's worktree does not check out the branch, so rule 2 holds. The task session must be finished by then. The guard's clean-worktree check is the only enforcement.
- **Log and roadmap conflicts (user decision):** parallel branches both bump `next_id` in `.claude/docs/friction-log.md` and `.claude/docs/bug-log.md`, and they edit adjacent roadmap lines. Before the merge, `/ship` runs `git merge main` into `task-XXX` inside the worktree. It resolves conflicts confined to those two logs and `docs/roadmap.md` by keeping both sides, renumbering the task's entry ids above main's, and setting `next_id` to one past the highest. It commits the result (`task-XXX: sync with main`). Any other conflict, or a conflict mixed into other hunks, stops for the user. The sync touches only the task branch, so rule 3 holds. Update each log's own format text to say `/ship` renumbers on sync.
- **Reviewer:** `/work` runs the `reviewer` subagent after entering the worktree. Confirm during implementation that the subagent inherits the worktree as cwd. If it does not, name the worktree path in the prompt and have it `cd` there, because its `git diff main...HEAD` and `tools/check` must run against the task tree.
- **Environment:** each worktree gets its own `.pixi/` environment on its first `tools/check`, mostly hardlinked from the rattler cache. Accept that cost. Log friction only if it proves slow.
- **Manual QA:** the author runs `tools/manual-qa` from the task's worktree. `/work`'s report names that path.
- **Unaffected:** `tools/task_status.py` reads every local branch, and worktrees share branches. Run it from the primary checkout so its `tasks/` view is `main`'s.
- **Kit (user decision):** change this repo's pipeline docs and skills. `.claude/pipeline-kit-version` shows the pipeline is vendored from a shared kit, so the final report names the changed pipeline files for porting upstream later. This task does not edit the kit.
- **Manual QA opt-out:** `tools/manual_qa.py` exercises mdblog against a fixture vault, not the pipeline, so this task has no manual-QA Must Have. The first real parallel use (two tasks worked at once, both shipped) is the end-to-end proof. Log anything it reveals in the friction log.

## Plan
- [ ] **Step 1** (`.gitignore`): ignore `.claude/worktrees/`.
- [ ] **Step 2** (`tools/task_tree.py`, `tests/test_task_tree.py`): typed CLI with modes `work task-XXX`, `ship task-XXX`, `main`. Parse `git worktree list --porcelain` into (path, branch-or-detached) records. A pure `decide(mode, task_id, worktrees, toplevel, state) -> Verdict` holds every rule in Must Have. Thin git-calling wrappers gather the inputs. Unit tests cover each rule and message. One end-to-end test builds a temp repo with `git worktree add`.
- [ ] **Step 3** (`.claude/docs/pipeline.md`): replace the single-tree sentence in § Flow with a pointer to a new `## Worktrees` section. That section holds the three rules, the worktree path, the guard, the reviewer cwd note, the per-worktree pixi note, and the manual-QA path. Update § Git: the first `/work` creates the branch together with its worktree, resumed work continues in the same worktree, and `/ship` removes the worktree before deleting the branch.
- [ ] **Step 4** (`.claude/skills/work/SKILL.md`): preflight runs `tools/task_tree.py work task-XXX` and acts on `create`/`enter`/`here`. Step 2 creates or enters the worktree as in Advice. The report names the worktree path.
- [ ] **Step 5** (`.claude/skills/ship/SKILL.md`): preflight runs `tools/task_tree.py ship task-XXX`. Hygiene and finalize run inside the task worktree via `EnterWorktree` `path`. Add the sync-with-main step and its narrow conflict rule. `ExitWorktree` `keep`, then merge in the primary as today, minus `git checkout main` since the primary is always on `main`. On green, `git worktree remove .claude/worktrees/task-XXX`, then `git branch -d task-XXX`. The step-1 already-merged path also removes the worktree first.
- [ ] **Step 6** (`.claude/skills/new-task/SKILL.md`): before committing, run `tools/task_tree.py main`, because the plan commit lands on `main`.
- [ ] **Step 7** (`.claude/docs/friction-log.md`, `.claude/docs/bug-log.md`): add one sentence to each format section saying `/ship` renumbers a task branch's entries when syncing with `main`.
- [ ] **Step 8** (`CLAUDE.md` § Invariants): add one line saying task work happens only in `.claude/worktrees/task-XXX`, and that only the primary checkout touches `main`, pointing to `pipeline.md` § Worktrees.

## Review log
