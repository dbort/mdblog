---
name: init-pipeline
description: One-shot setup of a freshly installed pipeline. Records what the project is and its stack in CLAUDE.md, plans task-001 to scaffold the project and make tools/check real, then deletes itself. Run only when the user invokes /init-pipeline.
disable-model-invocation: true
---

# Initialize the pipeline

Pipeline rules: `.claude/docs/pipeline.md`. This skill runs once, right
after `install.py`, and nothing here depends on a particular language or
mix of languages.

1. **Preflight.** Require branch `main`, a clean tree, an empty
   `tasks/active/`, and both `/init-pipeline` comments still in `CLAUDE.md`.
   Stop if any is untrue.
2. **Interview** the user (`pipeline.md` § Interviews and reporting) until
   these are settled. Recommend an answer for each, drawing on what you know
   of the stack in question.
   - **Brief:** one paragraph on what the project is and who it is for.
   - **Stack:** every language and major framework or platform, and how the
     toolchain is provided. If the stack is undecided, keep asking: task-001
     cannot be planned around a guess.
   - **Gate:** what `tools/check` must cover for each language, such as
     formatting, linting, the static checker and its strictest practical
     setting, tests, and build. Note anything slow enough to leave out of
     `--smoke`, and anything that needs the network.

   Do not design the product here; milestones and `docs/` come later through
   `/new-task`. Do not suggest further rules or conventions. Record one only
   when the user names it.
3. **Fill in `CLAUDE.md`.** Replace the first `/init-pipeline` comment with
   the brief. Replace the second with the stack, each language's static
   checker and setting, and any convention the user named.
4. **Plan task-001.** Write `tasks/active/task-001-<slug>.md` from the
   template in `.claude/skills/new-task/SKILL.md`. Its work is to scaffold
   the project and replace the `tools/check` stub. Its Must Haves include:
   - Each language in the stack has a minimal project that builds, with at
     least one real test that `tools/check` runs.
   - `tools/check` runs everything the Gate answer named and meets the
     contract in `pipeline.md` § Checks.
   - `.gitignore` covers each toolchain's build output.

   Check `CLAUDE.md` § Standing task-planning obligations as `/new-task`
   does.
5. **Remove this skill and commit.** `git rm -r .claude/skills/init-pipeline`,
   stage the rest, and commit to `main` (`Configure pipeline and plan
   task-001`).
6. **Report.** Link the task file without pasting it, note that `LICENSE` is
   MIT under the name from the user's git config and can be changed, and
   tell the user to start with `/work task-001`.
