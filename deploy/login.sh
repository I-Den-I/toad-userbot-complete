#!/usr/bin/env bash
# Interactive login by the account owner, then start the service. Needs a terminal:
#   ssh -t root@<server> /opt/toad-userbot/deploy/login.sh          # QR code (default)
#   ssh -t root@<server> /opt/toad-userbot/deploy/login.sh --code   # login code instead
#
# Asks for the API credentials (https://my.telegram.org) if they are not configured yet,
# then shows a QR code to scan from the Telegram app (or asks for the phone number and the
# login code), and finally the 2FA password if the account has one.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy/lib.sh
. "$here/lib.sh"
require_root
[ -t 0 ] || die "an interactive terminal is required: connect with ssh -t"

env_file="$CONFIG_DIR/env"
[ -f "$env_file" ] || die "$env_file is missing, run deploy/install.sh first"

configured() { grep -Eq "^$1=.+" "$env_file"; }

if ! configured TG_API_ID || ! configured TG_API_HASH; then
    echo "API-ключі акаунта: https://my.telegram.org → API development tools"
    read -r -p "api_id: " api_id
    read -r -s -p "api_hash (не відображається): " api_hash
    echo
    [[ "$api_id" =~ ^[0-9]+$ ]] || die "api_id must be a number"
    [[ "$api_hash" =~ ^[0-9a-f]{32}$ ]] || die "api_hash must be 32 hexadecimal characters"
    sed -i -e "s/^TG_API_ID=.*/TG_API_ID=$api_id/" -e "s/^TG_API_HASH=.*/TG_API_HASH=$api_hash/" "$env_file"
    chown root:"$APP_USER" "$env_file"
    chmod 0640 "$env_file"
fi

# A session file must never be used by two clients at once.
systemctl stop "$SERVICE" 2>/dev/null || true

set -a
# shellcheck source=/dev/null
. "$env_file"
set +a
cd "$DATA_DIR"
runuser -u "$APP_USER" -- env \
    DATA_DIR="$DATA_DIR" \
    CONFIG_PATH="$CONFIG_DIR/config.yaml" \
    "$APP_DIR/.venv/bin/toad-userbot" login "$@"

systemctl enable --now --quiet "$SERVICE"
log "$SERVICE started. Next, in Saved Messages: .ping → .chats <name> → .chat set <id> → .status"
systemctl --no-pager --lines=10 status "$SERVICE" || true
