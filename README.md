# mdblog

mdblog publishes the notes in an Obsidian vault as a static website built with Hugo. One vault is one site: its settings, bio, layouts and static files live in the vault's `_site/` folder. [docs/vault-format.md](docs/vault-format.md) covers everything about the vault, including which notes are published and how their links are converted.

## Install

mdblog runs on Linux and macOS. [pixi](https://pixi.sh) provides Python, Hugo and the other tools, so install pixi and then, from a checkout of this repository:

```sh
pixi install
```

Run the commands below through `pixi run`, for example `pixi run mdblog build ...`, or from a `pixi shell`.

## Build the site

```sh
mdblog build VAULT --output DIR
```

`build` renders the site into `DIR`, replacing what is there. It refuses a `DIR` that is inside the vault, contains the vault, or is a non-empty directory without the `.mdblog-output` marker file that mdblog writes into its output. If any published note fails validation, the build lists every failure and leaves `DIR` unchanged.

## Preview while writing

```sh
mdblog serve VAULT [--output DIR] [--port N] [--drafts]
```

`serve` runs Hugo's development server on the vault's site and rebuilds it whenever the vault changes, so a page open in the browser reloads by itself after each save. It listens on 127.0.0.1 only, so only this computer can load the site, and links point at `http://localhost:<port>` with the path from the site's `base_url` kept. Changes inside hidden folders such as `.obsidian/` are ignored.

If a change makes the vault fail validation, `serve` prints the failures and keeps serving the last good site until a later change fixes them. Stop it with Ctrl+C.

- `--output DIR` renders into `DIR` and keeps it afterward. `DIR` is checked as `build` checks it. By default `serve` renders into `mdblog-serve-<port>` in the system temporary directory and deletes it on exit.
- `--port N` serves on port `N` and fails if it is busy. By default `serve` uses port 1313, or a free port when 1313 is busy.
- `--drafts` also shows notes marked `publish: false`, labeled "Draft", and shows published notes that fail validation, labeled "Invalid", with a banner on every page saying it is a draft preview. Problems print as warnings after each rebuild instead of stopping the preview. See [Draft preview](docs/vault-format.md#draft-preview) for the rules.

## Development

```sh
tools/check
```

runs the formatter check, linter, type checker and tests. `tools/manual-qa` walks through the checks no test can make, such as live reload in a browser, and writes a log of the results.
