# mdblog

mdblog publishes the notes in an Obsidian vault as a static website built with Hugo. One vault is one site, and the site's own files live in the vault's `_site/` folder. [docs/vault-format.md](docs/vault-format.md) covers the vault: which notes publish and how their properties and links work.

## Install

mdblog runs on Linux and macOS. Install [pixi](https://pixi.sh), then run `pixi install` in a checkout of this repository. Run the commands below through `pixi run` or from a `pixi shell`. `mdblog <command> --help` lists each command's options.

## Commands

- `mdblog build VAULT --output DIR` renders the site into `DIR`, or lists every failing note and leaves `DIR` unchanged. It refuses a non-empty `DIR` that mdblog did not write, and any `DIR` inside or around the vault.
- `mdblog check VAULT` reports whether `build` would succeed, without keeping any output.
- `mdblog serve VAULT` previews the site on this computer and rebuilds it as the vault changes. `--drafts` adds notes still being written, as described in [Draft preview](docs/vault-format.md#draft-preview).

## Development

`tools/check` is the merge gate. Its contract is in [`.claude/docs/pipeline.md`](.claude/docs/pipeline.md#checks) and its steps are in `tools/check_runner.py`. `tools/manual-qa` walks through the checks no test can make and writes a log of the results.
