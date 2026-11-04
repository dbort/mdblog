---
id: task-001
title: "Scaffold mdblog and the check gate"
---

# task-001: Scaffold mdblog and the check gate

## Summary
Sets up the pixi environment, a minimal `mdblog` Python package, and a real `tools/check` to replace the failing stub, so later tasks have a working merge gate. The package does only enough to prove the path from a vault of notes to a Hugo-built page; Obsidian syntax handling, configuration, deployment, POSSE and backfeed all wait for their own tasks.

## Must Have
- [x] `pixi.toml` declares exactly the platforms `linux-64`, `linux-aarch64` and `osx-arm64`, the `conda-forge` channel, and `python`, `hugo`, `ruff`, `pyrefly` and `pytest`, with Python constrained to `3.14.*`. `pixi.lock` is committed and resolves for all three platforms.
- [x] `pixi.toml` and `pixi.lock` contain no `nodejs` or `wrangler` dependency.
- [x] `src/mdblog/` is a package installed editable into the pixi environment: from any working directory, `pixi run --manifest-path <repo>/pixi.toml python -c "import mdblog"` exits 0.
- [x] `mdblog.publish.copy_notes(vault: Path, content_dir: Path)` copies each `*.md` file under `vault` to the same relative path under `content_dir`, returns the destination paths sorted, and raises `FileNotFoundError` when `vault` does not exist. A pytest test asserts all three behaviors.
- [x] `tests/fixtures/vault/` holds at least one note in a subdirectory, and a Hugo site fixture holds the minimal config and layouts Hugo needs to render it.
- [x] A full `tools/check` runs `copy_notes` on the fixture vault, runs a real `hugo` build into a temporary directory, and asserts the note's text appears in the generated HTML. It reads no path outside the repository and its temporary directories.
- [x] A full `tools/check` runs `ruff format --check`, `ruff check`, `pyrefly check` and `pytest` over `src/`, `tests/` and `tools/`, and the Hugo build above. It exits 0 on the finished branch.
- [x] `pyproject.toml` sets `[tool.pyrefly] preset = "strict"`.
- [x] Tests demonstrate that a failing format check, lint, type check, test, or Hugo build makes the runner exit nonzero, by injecting a failing command into the runner's importable functions.
- [x] `tools/check --smoke` exits 0 and omits only the Hugo build. `tools/check --offline` is accepted and exits 0 with the environment already installed.
- [x] `tools/check` exits 0 when invoked from `/` by its absolute path.
- [x] With `pixi` absent from `PATH`, `tools/check` prints an error naming `pixi` and exits nonzero.
- [x] `tools/check` fails when `pixi.lock` is out of date with `pixi.toml`.
- [x] `.gitignore` covers `.pixi/`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/`, `.ruff_cache/`, `dist/`, `build/`, and Hugo's `public/`, `resources/` and `.hugo_build.lock`; `git status --short` is empty after a full `tools/check` on a clean tree.

## Advice
- `pixi` is the only prerequisite. It is not installed in the dev environment until the user installs it; if it is still missing when `/work` starts, stop and ask rather than installing it or working around it.
- Keep the worktree free of any vault: the vault lives in a parallel checkout, and the gate must pass on a machine without one, so all gate inputs are fixtures.
- Keep `copy_notes` deliberately plain. No wikilink or frontmatter transforms, CLI, or configuration format: the product's shape is undecided and later `/new-task` interviews settle it.
- Leave Node and wrangler out: nothing in this task deploys, and the deploy task adds them.
- Standing obligation, strict static checks: use `preset = "strict"`, and promote to errors any preset warning that catches a real defect, because a warning does not fail the gate. Follow `shelving-workbench`'s setup: `redundant-cast` and `unnecessary-type-conversion` as errors, and `enabled-ignores = ["pyrefly"]` so a suppression aimed at another checker cannot hide a pyrefly error. Confirm these option names against the installed pyrefly version. `tools/task_status.py` falls under the gate, so fix whatever it trips.
- Standing obligation, scripts stay simple: `tools/check` remains a thin shell wrapper that locates the repo, fails if `pixi` is missing, and hands off through `pixi run --locked`. Argument handling and step sequencing live in a Python module under `tools/` with importable functions, tested directly.
- Keep the wrapper compatible with macOS's bash 3.2, since macOS is a supported platform.
- Pin Hugo's minor version in `pixi.toml` because its output can change between releases; the lockfile pins everything else exactly.
- All checks are local, so `--offline` has no effect on which checks run. Only environment installation needs the network, and that happens before any check starts.

## Plan
- [x] **Step 1** (`pixi.toml`, `pixi.lock`, `pyproject.toml`, `.gitignore`): pixi workspace for the three platforms, editable `mdblog` install from a `src/` layout, ruff and pyrefly configuration, ignores for each toolchain's output.
- [x] **Step 2** (`src/mdblog/publish.py`, `tests/test_publish.py`): `copy_notes` with its contract tests.
- [x] **Step 3** (`tests/fixtures/`): fixture vault and minimal Hugo site.
- [x] **Step 4** (`tools/`, `tests/`): check runner with importable step definitions covering `--smoke`, `--offline`, the Hugo fixture build, and nonzero exit on any failing step, with direct tests.
- [x] **Step 5** (`tools/check`): replace the stub with the thin wrapper; verify from another working directory, with `pixi` hidden from `PATH`, and with a stale lockfile.
- [x] **Step 6** (`tools/task_status.py`): bring it through ruff and pyrefly strict without changing its behavior.

## Review log

### Round 1: REJECTED
- **F1: `--smoke` still runs real Hugo builds through pytest** (`tests/test_check_runner.py:25`): the Must Have says `--smoke` omits only the Hugo build, but only the named step is dropped. The pytest step still builds with real Hugo and starts nested full gates, so a broken layout fails `--smoke` and smoke is no faster than the full gate. `test_smoke_exit_status_ignores_a_failing_hugo` only injects a failure into the skipped step.
- **F2: Nothing tests that pyrefly covers `src/`, `tests/` and `tools/`** (`tests/test_project_config.py:51`): the scope depends entirely on `project-includes`, and with `project-includes = ["src"]` the tests still pass and `pyrefly check` reports 0 errors. The default `typecheck` argv is also unasserted.
- **N1: An exported `CDPATH` breaks the wrapper's repo lookup** (`tools/check:7`): with `CDPATH` set and a relative `tools/check` call, `cd` also prints the directory, so `repo` holds two lines and pixi fails.
