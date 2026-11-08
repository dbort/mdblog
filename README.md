# mdblog

mdblog publishes the notes in an Obsidian vault as a static website built with Hugo. One vault is one site, and the site's own files live in the vault's `_site/` folder. [docs/vault-format.md](docs/vault-format.md) covers the vault: which notes publish and how their properties and links work.

## Install

mdblog runs on Linux and macOS. Install [pixi](https://pixi.sh), then run `pixi install` in a checkout of this repository. Run the commands below through `pixi run` or from a `pixi shell`. `mdblog <command> --help` lists each command's options. `mdblog stage --serve` also needs wrangler, which `pixi run npm ci` installs into the checkout, as `tools/check` does.

## Commands

- `mdblog build VAULT --output DIR` renders the site into `DIR`, or lists every failing note and leaves `DIR` unchanged. It refuses a non-empty `DIR` that mdblog did not write, and any `DIR` inside or around the vault.
- `mdblog check VAULT` reports whether `build` would succeed, without keeping any output.
- `mdblog stage VAULT --output DIR` makes a production build laid out for a Cloudflare Worker that serves static assets: `DIR` gets a generated wrangler config and the site under its base path. It needs the `[worker]` table described in [Site folder](docs/vault-format.md#site-folder), refuses `DIR` as `build` does, and leaves `DIR` unchanged when it fails. With `--serve`, it then serves `DIR` on this computer with `wrangler dev`, the way Cloudflare will serve it, and prints the site's address. Ctrl+C stops it.
- `mdblog serve VAULT` previews the site on this computer and rebuilds it as the vault changes. `--drafts` adds notes still being written, as described in [Draft preview](docs/vault-format.md#draft-preview).

## Development

`tools/check` is the merge gate. Its contract is in [`.claude/docs/pipeline.md`](.claude/docs/pipeline.md#checks) and its steps are in `tools/check_runner.py`. `tools/manual-qa` walks through the checks no test can make and writes a log of the results.
