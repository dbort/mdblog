---
id: task-002
title: "Add the mdblog build command and the publish rule"
---

# task-002: Add the mdblog build command and the publish rule

## Summary
Adds `mdblog build VAULT --output DIR`, which builds a site from one vault and publishes only notes marked `publish: true`. Each site keeps its settings in its own vault, so this repo holds no site-specific information and can serve several independent sites later. Published notes still reach Hugo with their Markdown and front matter unchanged, because converting them is M2's job.

## Must Have
- [x] `pixi run --locked mdblog build VAULT --output DIR` works from any working directory. Omitting `VAULT` or `--output` exits nonzero with a usage message.
- [x] `pixi.toml` declares `ruamel.yaml`, and `pixi.lock` resolves it for all three platforms.
- [x] The site configuration is read from `VAULT/_site/mdblog.toml`, with required string keys `base_url`, `title` and `author`. A missing file, invalid TOML, a missing key, a non-string value or an unknown key exits nonzero with a message naming the file, and leaves the output directory unchanged.
- [x] The generated Hugo site uses those values: `base_url` appears in `index.xml` links, `title` is the site title, and `author` is available to layouts as `.Site.Params.author`.
- [x] A note publishes only when its front matter has the boolean `publish: true`. A note with `publish: false`, no `publish` property, no front matter, or an opening `---` with no closing `---` builds no page and causes no error.
- [x] A note whose `publish` is a non-boolean (`"true"`, `yes`, `1`), or whose front matter is invalid YAML, has a duplicate key, is not a mapping, or is not UTF-8, makes the build exit nonzero and leaves the output directory unchanged. One run names every such note on stderr, with the reason for each.
- [x] Only `*.md` files reach Hugo's content directory, at their relative vault paths. A file under `_site/`, or under any path component starting with `.`, is never selected and never validated, even with `publish: true`. Tests cover `.obsidian/` and `.trash/`.
- [x] A symbolic link in the vault is not followed or published.
- [x] A test builds a fixture vault with published and unpublished notes and asserts that each unpublished note's text appears in no file under the output directory.
- [x] A test builds, removes `publish: true` from a note, builds again, and asserts that no file for that note remains in the output directory. A second test does the same by deleting the note.
- [x] A successful build leaves a `.mdblog-output` marker file at the root of the output directory.
- [x] The build refuses, exits nonzero, and changes nothing when the output path is a file, is a non-empty directory with no marker, is the vault or inside it, or contains the vault. A missing or empty output directory is accepted.
- [x] When Hugo exits nonzero, the build exits nonzero and the previous output directory is byte-for-byte unchanged.
- [x] A build writes nothing under the vault: a test compares the vault's paths and contents before and after.
- [x] Default layouts ship inside the `mdblog` package, and a vault with no `_site/layouts/` builds with them. A layout at `VAULT/_site/layouts/page.html` replaces the default for pages while the home page keeps its default.
- [x] A `HUGO_BASEURL` variable in the caller's environment does not change the generated site's URLs.
- [x] With `hugo` absent from `PATH`, the build exits nonzero with a message naming `hugo`.
- [x] `copy_notes` no longer exists, and a full `tools/check` builds the fixture vault through the build command's importable function and asserts the published note's page exists and holds its text.
- [x] `tests/fixtures/site/` no longer exists. `tests/fixtures/vault/` holds `_site/mdblog.toml`, at least one published note in a subdirectory and at least one unpublished note.
- [x] `tools/check` exits 0 on the finished branch, and `git status --short` is empty afterward. Tests that run real Hugo carry the `hugo` mark, so `--smoke` still omits them.

## Advice
- One vault is one site. Do not add site names, a multi-site config or a per-site `publish` rule. Several sites means running the command once per vault.
- Keep all site-specific information out of this repo: site URL, title, author, bio and any overriding layouts belong in the vault's `_site/`. The repo's only configs are test fixtures. Do not commit a real site config, because the long-term goal is hosting multiple independent sites from these tools.
- The vault path comes only from the required argument, and the output path only from the required `--output`. Do not add an environment variable, a default, or a local config file. Paths in `mdblog.toml` are not needed, because the file is inside the vault it describes.
- Reject unknown configuration keys, because a misspelled optional key added later must not be ignored silently.
- Use `ruamel.yaml` in its YAML 1.2 safe mode (`YAML(typ="safe", pure=True)`). Tested with 0.19.1: `publish: yes` loads as the string `"yes"`, `publish: true` as a boolean, and a duplicate key raises. PyYAML reads `yes` as true and keeps the last duplicate, which breaks the boolean-only rule.
- Check `publish` with `value is True`, since `1 == True` in Python.
- Front matter starts only with `---` alone on the note's first line and ends at the next line holding only `---`, matching how Obsidian treats properties. Accept CRLF line endings. A note with no closing line has no front matter, so a leading horizontal rule is not an error.
- A bad note fails the build even if it was probably never meant to publish, by user decision: a typo in `publish` must not go unnoticed. Validate every selected note before running Hugo, and report all failures in one run so the author fixes them together.
- Copy published notes verbatim, including front matter. A colliding property such as `url: https://...` can fail Hugo or hide a page until M2 writes front matter from scratch. Do not add a key allowlist, Obsidian syntax handling or attachment copying here, because M2 owns them with the vault survey as evidence. Nothing deploys before M2.
- Generate the Hugo site in a temporary working directory: `hugo.toml` from the configuration, `content/` from published notes, `themes/mdblog/` from the packaged defaults, and `layouts/` copied from `VAULT/_site/layouts/` if present. Tested on Hugo 0.169: a project `layouts/page.html` overrides the theme's and the theme's `home.html` still applies. Building there keeps `.hugo_build.lock` and `resources/` out of the vault and the repo.
- Strip `HUGO*` variables from Hugo's environment, because they override site configuration: `HUGO_BASEURL` replaced the configured URL in testing. Point `--cacheDir` into the temporary directory, as `tools/check_runner.py` does. Keep Hugo's default outputs. M3 owns feed and output choices.
- Build into a temporary directory beside the output path, on the same filesystem, write the marker, then swap it in with renames, so a failed build or a crash never leaves a partial site. Hugo's `--cleanDestinationDir` is not enough: it offers no protection against a wrong path and exposes a partial site on failure.
- M4's upload must exclude `.mdblog-output`. The roadmap records this.
- Standing obligation, strict static checks: all new code passes pyrefly strict. `ruamel.yaml` output is an untyped boundary, so narrow it to `object` at the load call and validate from there. Any suppression at that boundary carries a comment saying why.
- Standing obligation, scripts stay simple: all logic is Python under `src/mdblog/`, in importable functions tested directly. Add no shell scripts.

## Plan
- [x] **Step 1** (`pixi.toml`, `pixi.lock`, `pyproject.toml`): add `ruamel.yaml` and a `mdblog` console script that calls `mdblog.cli:main`.
- [x] **Step 2** (`src/mdblog/config.py`, tests): load and validate `_site/mdblog.toml` into a typed value. Raise an error naming the file for each Must Have failure.
- [x] **Step 3** (`src/mdblog/publish.py`, `tests/test_publish.py`): delete `copy_notes` and rewrite its tests. Add note selection, front matter parsing and the `publish` decision, returning published notes plus every failure with its reason.
- [x] **Step 4** (`src/mdblog/theme/layouts/`, `src/mdblog/build.py`, tests): minimal `home.html`, `page.html` and `section.html` defaults inside the package. A build function that takes the vault, output path and Hugo argv, assembles the working directory, generates `hugo.toml`, runs Hugo with a filtered environment, and applies the marker, refusal and swap rules.
- [x] **Step 5** (`src/mdblog/cli.py`, tests): the `build` subcommand with required arguments, reporting failures on stderr and mapping them to a nonzero exit. A subcommand leaves room for later commands.
- [x] **Step 6** (`tests/fixtures/`): move the fixture to the new shape. Delete `tests/fixtures/site/`, add `vault/_site/mdblog.toml`, add `publish: true` to `vault/projects/first-note.md`, and add unpublished notes plus `.obsidian/` and `.trash/` content.
- [x] **Step 7** (`tools/check_runner.py`, `tests/test_check_runner.py`, `tests/test_check_wrapper.py`): `hugo_fixture_build` calls the build function in place of `copy_notes` and its own Hugo invocation. In `tests/test_check_runner.py`, the missing-text test writes its replacement note with `publish: true` so it fails for the intended reason, the broken-layout test writes `fixtures/vault/_site/layouts/page.html`, the renamed-note test and the fixture text test stay valid, and `test_hugo_build_points_every_path_at_its_temporary_directory` is updated to the build function's invocation. In `tests/test_check_wrapper.py`, the broken layout at line 107 moves to `tests/fixtures/vault/_site/layouts/page.html`, creating its parents. Its copied repo keeps importing the installed `mdblog`, so confirm the test still shows `--smoke` skips Hugo.
- [x] **Step 8** (`CLAUDE.md`): under Project conventions, state that one vault is one site and that its settings and overriding layouts live in the vault's `_site/`. Update the opening paragraph's "keeps site-specific settings in configuration" to match.

## Review log

### Round 1: REJECTED
- **F1: Some bad front matter crashes the build instead of being reported** (`src/mdblog/publish.py:98`): the Must Have says one run names every bad note on stderr with its reason, but two inputs escape as raw Python tracebacks. `publish: !!bool maybe` raises `KeyError` from ruamel's `construct_yaml_bool`, and the `except` catches only `YAMLError`, `ValueError` and `RecursionError`. `publish: 0xfff...` with 5000 hex digits loads, then `{value!r}` at line 125 raises `ValueError` outside any handler. In the `KeyError` run, a second bad note was never named. Any exception from the load call should become a `FrontMatterError`, and formatting the value must not be able to raise. Add cases for both inputs, plus a test showing other bad notes are still named.
- **N1: Same gap in the config loader** (`src/mdblog/config.py:43`): a `mdblog.toml` with a 5000-digit integer raises `ValueError`, and one with 5000 nested `[` raises `RecursionError`. Both escape `load_config` with no message naming the file. Fold in with F1 and add matching test cases.
- **N2: A YAML directive can opt a note out of the 1.2 boolean rule** (`src/mdblog/publish.py:92`): a block holding `%YAML 1.1`, then `--- ` with a trailing space, then `publish: yes` loads as `True`, so the note publishes. The fix could reject directives in front matter.
- **N3: Absent-Hugo assertion can pass for the wrong reason** (`tests/test_cli.py:47`): `tmp_path` contains `hugo` because pytest derives it from the test name. Asserting `"cannot run hugo"` closes this.
