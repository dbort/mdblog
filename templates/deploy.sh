#!/bin/sh
# Copy to the vault's _site/deploy.sh. Cloudflare Workers Builds runs it from the
# vault's root as the deploy command `sh _site/deploy.sh`; mdblog's
# docs/deploy-under-a-path.md describes the setup.
set -eu

# The mdblog commit to build with, as a full SHA. Changing it and pushing republishes
# the site with that version.
MDBLOG_COMMIT=REPLACE_WITH_A_COMMIT_SHA
MDBLOG_REPO=https://github.com/dbort/mdblog.git

vault=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
# Outside the vault, because mdblog reads every note in it, and fresh on each run.
mdblog=$(mktemp -d)
git clone --quiet "$MDBLOG_REPO" "$mdblog"
git -C "$mdblog" checkout --quiet "$MDBLOG_COMMIT"
exec "$mdblog/tools/workers-build" "$vault"
