---
id: task-011
title: "Let a vault use any Hugo theme"
blocked_by: [task-009]
---

# task-011: Let a vault use any Hugo theme

## Summary
mdblog's look is already a Hugo theme, but the theme also holds the callout and image-size rendering that mdblog's converter depends on. This task moves those two render hooks into a small core layer that sits under any theme. A vault can then name a different Hugo theme in `mdblog.toml` and give it its own settings in `_site/hugo.toml`, while callouts and sized embeds keep working.

## Must Have
- [ ] A vault with no `theme` key builds exactly as before: every existing site test passes, with only the edits that path and constant renames require.
- [ ] `theme` in `_site/mdblog.toml` is an optional string path. A relative path resolves against the vault root, an absolute path is used as given, and a build with either renders pages from that theme's layouts and from none of the packaged default theme's (for example, no `site-header` and no link to the packaged stylesheet).
- [ ] `load_config` raises `ConfigError` naming `mdblog.toml` and the resolved path when `theme` is not a string, the path does not exist, the path is not a directory, or the directory has no `layouts/` subdirectory.
- [ ] Under a theme with no render hooks, a `> [!tip]- Title` callout renders with the core layer's `callout callout-tip` `<details>` markup, and `![[image.svg|300]]` renders an `<img>` with `width="300"` and no `mdblog-width` in its `src`.
- [ ] A theme's own `_markup/render-image.html` wins over the core layer's: a build with a fixture theme that has one shows that theme's image markup.
- [ ] The packaged core layer holds only `layouts/_markup/render-blockquote.html` and `layouts/_markup/render-image.html`. Feeds, page layouts and CSS stay in the default theme, so under another theme that theme (or Hugo's embedded template) renders the feeds.
- [ ] A param set in `_site/hugo.toml` (for example `[params] greeting = "hi"`) reaches templates as `site.Params.greeting`, under the default theme and under a third-party theme, and `params.author` from `mdblog.toml` survives alongside it.
- [ ] Every key mdblog generates wins over `_site/hugo.toml`. A test sets `baseURL`, `title`, `params.author`, `outputs` and `markup.goldmark.renderer.unsafe = true` in the overlay and finds the generated values in the output: the configured base URL in absolute links, the configured title, only mdblog's outputs, and a raw `<b>` in a note not passed through as HTML.
- [ ] A `_site/hugo.toml` that is a symbolic link fails the build with an error naming it.
- [ ] Symbolic links and any `.git` entry inside the theme directory are not copied into the Hugo source.
- [ ] `mdblog serve` on a vault whose `theme` path lies outside the vault rebuilds after a file under that theme changes, shown with a fake watcher. A theme inside the vault reloads through the existing vault watch.
- [ ] `docs/vault-format.md` documents the `theme` key, `_site/hugo.toml` and which of its keys mdblog overrides, the core hooks that apply under every theme, and that the feed contract, the 404 page and task-009's draft labels hold only for the default theme. `CLAUDE.md` § Sites lists `_site/hugo.toml` and the `theme` key.
- [ ] `tools/check` exits 0 on the finished branch.

## Advice
- User decisions (2026-11-06): a vault picks a theme by a path in `mdblog.toml`, relative to the vault root or absolute, with `_site/themes/<name>/` as the documented home. No Hugo Modules, because those need Go in pixi and network access on every build. A missing key means the packaged default theme. Theme settings come from an optional `_site/hugo.toml` overlay that Hugo merges under mdblog's generated config, with mdblog's keys always winning. Under a third-party theme mdblog supplies only the callout and image render hooks; the theme owns feeds, layouts and CSS.
- Deferred past v1 (user decision, 2026-11-07): v1 has one site, so picking a theme can wait, and task-012 lands first. Before `/work`, re-check the Plan's file paths and test line numbers against task-012's restyled layouts, sidebar partial and tests, and move its files with the rest of the default theme.
- Sequenced after task-009 at the user's request; both touch `serve.py` and the theme's layouts. Task-009's draft labels and banner live in the default theme's layouts, so they do not appear under a third-party theme. Document that and do not move them into the core layer.
- Stack themes with Hugo's theme list, `theme = ["<site theme>", "mdblog-core"]`, so a project layout beats the site theme and the site theme beats the core layer, file by file. Copy the chosen theme into the Hugo source under a fixed directory name, not its own basename, so no theme name can collide with `mdblog-core`.
- Require a `layouts/` directory in the configured theme. Without one, Hugo warns "found no layout file" and writes blank pages with exit status 0, which is silently wrong output.
- Pass `_site/hugo.toml` through Hugo's comma-separated `--config` list in both `build` and `serve`, ordered so mdblog's generated file wins. Confirm the precedence direction with real Hugo before relying on it; the Must Have test above is the guard. Set `markup.goldmark.renderer.unsafe = false` explicitly in the generated config, because raw HTML must stay off so a note cannot bypass the link rules, and an omitted key would let the overlay turn it on. Serve must restart Hugo when the overlay changes, as it does for other config changes (`needs_restart`).
- A theme inside the vault but outside `_site/` would make its files link targets and puts its Markdown through note scanning. Recommend `_site/themes/` in the docs; do not add a new exclusion rule.
- Serve watches the theme directory configured when it started, ignoring hidden paths inside it as it does in the vault. A change to the `theme` key itself takes effect after restarting serve; say so in the docs.
- Keep `_site/layouts/`, `_site/assets/` and `_site/static/` working under every theme: they are project directories and outrank any theme.
- Standing obligation, strict static checks: the new `SiteConfig.theme` field is `Path | None`, resolved in `load_config`. Keep all new code fully typed under pyrefly strict.
- Standing obligation, scripts stay simple: no new scripts.
- Standing obligation, test where the risk is: theme stacking order, overlay precedence and the `layouts/` requirement each fail silently, so each gets a real-Hugo test with a minimal fixture theme under `tests/fixtures/themes/`, outside the fixture vault so the absolute-path case is covered too. Config errors and path resolution are unit tests. Serve's extra watch path uses the existing fake-watcher style in `tests/test_serve.py`. No test of a real third-party theme from the internet, and no manual QA: every Must Have is machine-checked.

## Plan
- [ ] **Step 1** (`src/mdblog/config.py`, `tests/test_config.py`): optional `theme` key resolved to an absolute `Path` against the vault root, with the four `ConfigError` cases. The unknown-key check keeps rejecting everything else.
- [ ] **Step 2** (`src/mdblog/theme/` → `src/mdblog/themes/mdblog/` and `src/mdblog/themes/mdblog-core/`, `src/mdblog/build.py`): split the packaged files, moving the two `_markup/` hooks into the core layer, and replace `PACKAGED_THEME` with constants for both. `hugo_config` writes the theme list and `unsafe = false`. `assemble_source` copies the core layer plus either the default theme or the configured one, skipping symbolic links and `.git`. Update every user of the old path: `tests/test_build.py` (the `_seen` theme listing near line 49, `test_build_supplies_the_packaged_theme` near line 176, the `table["theme"]` assertion near line 604) and `tests/test_site.py` (the `PACKAGED_THEME` import and its uses near lines 476 and 680).
- [ ] **Step 3** (`src/mdblog/build.py`, `src/mdblog/serve.py`, tests): the `_site/hugo.toml` overlay in build and serve, its symlink refusal, and the precedence test.
- [ ] **Step 4** (`tests/fixtures/themes/`, `tests/test_site.py` or a new test module): a minimal third-party fixture theme with home, list and single layouts that print a param, plus a variant with its own `render-image.html`. Cover the theme-selection, core-hook and hook-precedence Must Haves.
- [ ] **Step 5** (`src/mdblog/serve.py`, `tests/test_serve.py`): watch an outside-vault theme directory as well as the vault.
- [ ] **Step 6** (`docs/vault-format.md`, `CLAUDE.md`): document the `theme` key, the overlay and its overridden keys, the core hooks, and the default-theme-only features listed in the Must Haves.

## Review log
