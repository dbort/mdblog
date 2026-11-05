---
id: task-005
title: "Refocus the test suite on novel code"
blocked_by: [task-002]
---

# task-005: Refocus the test suite on novel code

## Summary
Removes tests of the gate, of config files and of third-party tools that a loud failure with a good error message already covers, which takes `tools/check` from about 80 seconds to a few seconds. The new rule, recorded for future planning and review, is that unit tests go on novel code and anything else needs a failure that would otherwise be silent. It also removes code from task-002 that only handled pathological input, and updates the task-003 and task-004 plans to match.

## Must Have
- [ ] `tests/test_check_wrapper.py` and `tests/test_project_config.py` do not exist, and no file under `tests/` starts `tools/check` or `pixi` as a subprocess.
- [ ] `tools/check` runs exactly `ruff format`, `ruff check`, `pyrefly` and `pytest`, in that order, and works from any working directory.
- [ ] `tools/check --smoke` and `tools/check --offline` exit 0 and run the same four steps. An unknown flag exits nonzero.
- [ ] `git grep -E 'FIXTURE_NOTE_TEXT|FIXTURE_PAGE|HUGO_STEP|hugo_fixture_build|pytest_argv|--nested|mark\.hugo|mark\.wrapper'` on the finished branch matches only `tasks/completed/` and this task's own file. `pyproject.toml` declares no `hugo` or `wrapper` marker.
- [ ] `tests/test_check_runner.py` holds only tests that, using fake commands, show the gate exits 0 when every step passes, nonzero when any one step fails, and nonzero when any one tool is missing.
- [ ] Exactly three test functions run real Hugo: an end-to-end build of the fixture vault showing the published note's page holds its text and each unpublished note's text is in no output file, a build showing `base_url`, `title` and `author` reach the site, and a build showing `VAULT/_site/layouts/page.html` replaces the page default while the home page keeps its own.
- [ ] Tests using a fake Hugo show: a note that loses `publish: true` and a deleted note each leave no file in the output on the next build, a failed Hugo run leaves the previous output byte-for-byte unchanged, a build changes no path or content under the vault, and `HUGO*` variables do not reach Hugo.
- [ ] `src/mdblog/publish.py` has no `_describe` function and no YAML directive check, and `is_published` formats a bad `publish` value with `{value!r}`. `src/mdblog/config.py` catches `UnicodeDecodeError` and `tomllib.TOMLDecodeError` for invalid TOML and no longer catches `RecursionError`. No test covers a huge integer, deep nesting, a `!!bool` tag or a `%YAML` directive.
- [ ] A typo in `publish` and broken YAML each still name the note and its reason on stderr, and invalid YAML still cannot stop the run from naming other bad notes.
- [ ] `CLAUDE.md` § Standing task-planning obligations holds the test-scope entry from `## Advice`, and its Gate line names the four steps and no Hugo build.
- [ ] `.claude/agents/reviewer.md` applies the review rule from `## Advice`.
- [ ] `tasks/active/task-003-*.md` has `blocked_by: [task-002, task-005]`, and neither it nor `tasks/active/task-004-*.md` mentions `FIXTURE_PAGE`, `FIXTURE_NOTE_TEXT`, `tools/check_runner.py`, the `hugo` mark or the gate's Hugo step.
- [ ] `tools/check` exits 0 on the finished branch in under 15 seconds on the development machine, and `git status --short` is empty afterward.

## Advice
- Add this entry to `CLAUDE.md` § Standing task-planning obligations, in this wording: "**Test where the risk is:** unit tests cover novel code: every documented rule, branch and error message, including realistic bad input. A real third-party tool runs in one end-to-end happy path, and in another test only where a break would silently produce wrong output. Anything a fake can prove uses a fake. Repo tooling gets a test only where a bug would silently give a wrong answer that matters, such as the gate passing after a failure, so `tools/task_status.py` stays untested. Write no tests of tests (breaking a fixture to show a check notices), no tests that restate config, and no tests of pathological input that fails loudly and leaves output intact. A clear error message covers those, and they get debugged when someone hits them."
- Reason for that rule: integration points here change slowly, and a loud failure is cheap to debug when running the real tools. A silent one reaches readers of the site.
- Review rule for `.claude/agents/reviewer.md`: a missing test for novel code blocks. A missing third-party or tooling test blocks only when the failure would be silent. A new test the `CLAUDE.md` entry excludes is a blocking finding. "Behavior you had to verify by hand is a missing test" applies to novel code only. Keep the rest of the reviewer's judging list.
- Keep the gate's false-green guard, because a gate that exits 0 after a failure is the one silent failure in the tooling, and every later task trusts that result.
- Accept these losses: nothing fails if `--locked` is dropped from `tools/check` or if pyrefly is weakened from strict, and review of that diff is the only protection. A broken `[project.scripts]` entry fails loudly when the command runs.
- `--smoke` stays accepted because `.claude/docs/pipeline.md` § Checks requires it, and that contract already allows it to run everything when nothing is worth leaving out. Add a distinction back when a slow check arrives, such as M4's npm install. Do not edit `pipeline.md`.
- `--offline` stays accepted for the same contract and selects the same steps.
- Remove the pathological-input handling as well as its tests, because untested code still has to be reasoned about, and the directive check wrongly rejects an unindented `%` continuation line in a quoted string. Keep the broad `except Exception` around the YAML load, with its comment narrowed to what remains true: any loader error becomes a named report. A realistic case still reaches it, `date: 2026-13-45`, which raises a plain `ValueError`. Accepted outcomes: a 5000-digit `publish` value gives a traceback with a nonzero exit and untouched output, and a deliberate `%YAML 1.1` with `publish: yes` passes mdblog's check.
- This closes task-002's round 2 notes N2, N3 and N4. N4's `!!bool yes` publishing is accepted, because the tag states the author's intent.
- Leave novel-code tests alone unless they pin third-party behavior, restate config or cover pathological input. Keep the Hugo-absent test, since it checks mdblog's own message, and tighten nothing else here.
- Keep real-Hugo requirements in task-003 and task-004 that guard silent failures: today's date in any time zone, and heading anchors. Task-003's byte-identical output trees may use real Hugo or a fake, whichever proves it.
- Standing obligation, strict static checks: changed code passes pyrefly strict.
- Standing obligation, scripts stay simple: `tools/check` is unchanged, and no shell is added.
- Standing obligation, test where the risk is: this task creates it, and its own changes follow it.
- No roadmap edit: this task delivers no milestone. The order 002, 005, 003, 004 comes from the `blocked_by` entries.

## Plan
- [x] **Step 1** (`tools/check_runner.py`): reduce the gate to the four tool steps. Remove `hugo_fixture_build`, `pytest_argv`, `FIXTURE_NOTE_TEXT`, `FIXTURE_PAGE`, `HUGO_STEP`, the `hugo` command in `Commands`, `--nested`, and the `mdblog` imports. `--smoke` and `--offline` stay accepted and change nothing, with help text saying so.
- [x] **Step 2** (`tests/test_check_runner.py`, `tests/test_check_wrapper.py`, `tests/test_project_config.py`, `pyproject.toml`): delete the wrapper and project-config test files, and the `hugo` and `wrapper` markers. Reduce the runner tests to the three false-green cases in the Must Have.
- [x] **Step 3** (`tests/test_build.py`, `tests/test_cli.py`): keep exactly the three real-Hugo tests in the Must Have, moving the fixture happy-path text assertion into the end-to-end test. Convert the stop-publishing and vault-unchanged tests to the fake Hugo. Delete the real-Hugo escape, environment, Hugo-failure and no-warning tests, `test_build_keeps_package_layouts_inside_the_package`, and both console-script tests in `tests/test_cli.py`. Drop every `pytest.mark.hugo`.
- [x] **Step 4** (`src/mdblog/publish.py`, `src/mdblog/config.py`, `tests/test_publish.py`, `tests/test_config.py`, `tests/test_cli.py`): remove `_describe`, the directive check and the config `RecursionError` catch, per Advice. Delete the deep-nesting, huge-integer, bad-bool and directive cases, `test_select_notes_names_other_notes_after_a_loader_crash` and `test_a_loader_crash_still_names_every_bad_note`. Keep the bad-date case and add a `select_notes` test showing a note with `date: 2026-13-45` and a note with `publish: yes` are both named.
- [x] **Step 5** (`CLAUDE.md`, `.claude/agents/reviewer.md`): add the standing obligation, update the Gate line, and apply the review rule.
- [x] **Step 6** (`tasks/active/task-003-front-matter-and-placement.md`): add `task-005` to `blocked_by`. Drop the `hugo` mark clause from the `tools/check` Must Have. Remove the sentence requiring a test that `docs/vault-format.md` names every property. Rewrite Step 4 to keep only updating task-002's tests and adding the shared helper for notes with the required properties, and remove its `tools/check_runner.py` and `tests/test_check_runner.py` references. Add the `Test where the risk is` obligation to its `## Advice`.
- [x] **Step 7** (`tasks/active/task-004-obsidian-syntax.md`): drop the `hugo` mark clause from the `tools/check` Must Have. In the Must Have on linking an unpublished note or image, replace "Tests with real Hugo" with "Tests", since validation fails before Hugo runs. Rewrite Step 6 to add fixture notes and images using each supported syntax, with the end-to-end test building them, and remove its `tools/check_runner.py` and `FIXTURE_NOTE_TEXT` references. Add the `Test where the risk is` obligation to its `## Advice`.

## Review log
