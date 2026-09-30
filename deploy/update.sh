#!/usr/bin/env bash
# Deploy a git ref (default: origin/main) and re-provision. Run as root.
#   /opt/toad-userbot/deploy/update.sh                # latest main
#   /opt/toad-userbot/deploy/update.sh origin/feature # a branch, e.g. to try a PR
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy/lib.sh
. "$here/lib.sh"
require_root

ref="${1:-origin/main}"
git -C "$APP_DIR" fetch --prune --quiet origin
git -C "$APP_DIR" checkout --quiet --force --detach "$ref"
log "checked out $(git -C "$APP_DIR" log -1 --format='%h %s')"

# Run the install script of the new revision.
exec "$APP_DIR/deploy/install.sh"
