#!/usr/bin/env bash
# Provision the userbot from the checkout in /opt/toad-userbot. Idempotent; run as root.
#
# First install:
#   git clone https://github.com/I-Den-I/toad-userbot-complete.git /opt/toad-userbot
#   /opt/toad-userbot/deploy/install.sh
# Later updates: /opt/toad-userbot/deploy/update.sh
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy/lib.sh
. "$here/lib.sh"
require_root
[ "$(cd "$here/.." && pwd)" = "$APP_DIR" ] || die "expected the checkout at $APP_DIR"

log "system user $APP_USER"
if ! id -u "$APP_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "$DATA_DIR" --no-create-home --shell /usr/sbin/nologin "$APP_USER"
fi

log "directories"
install -d -m 0750 -o root -g "$APP_USER" "$CONFIG_DIR"
install -d -m 0700 -o "$APP_USER" -g "$APP_USER" "$DATA_DIR"
install -d -m 0755 "$(dirname "$UV_CACHE_DIR")"

log "uv $UV_VERSION (isolated in $TOOLS_DIR)"
if [ ! -x "$UV" ] || [ "$("$UV" --version | awk '{print $2}')" != "$UV_VERSION" ]; then
    python3 -m venv "$TOOLS_DIR"
    "$TOOLS_DIR/bin/pip" install --quiet --disable-pip-version-check "uv==$UV_VERSION"
fi

log "Python $PYTHON_VERSION and locked dependencies"
"$UV" python install --quiet "$PYTHON_VERSION"
(cd "$APP_DIR" && "$UV" sync --quiet --locked --no-dev --no-editable --python "$PYTHON_VERSION")

log "configuration in $CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/env" ]; then
    install -m 0640 -o root -g "$APP_USER" /dev/null "$CONFIG_DIR/env"
    cat >"$CONFIG_DIR/env" <<'EOF'
# Secrets of the userbot. Filled in by deploy/login.sh. Never share or commit.
TG_API_ID=
TG_API_HASH=
LOG_LEVEL=INFO
EOF
fi
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    install -m 0640 -o root -g "$APP_USER" "$APP_DIR/config.example.yaml" "$CONFIG_DIR/config.yaml"
fi
printf 'GIT_COMMIT=%s\n' "$(git -C "$APP_DIR" rev-parse --short HEAD)" >"$CONFIG_DIR/build.env"
chmod 0644 "$CONFIG_DIR/build.env"

log "systemd unit $SERVICE"
install -m 0644 "$APP_DIR/deploy/systemd/$SERVICE" "/etc/systemd/system/$SERVICE"
systemctl daemon-reload

if [ -f "$DATA_DIR/userbot.session" ]; then
    systemctl enable --quiet "$SERVICE"
    systemctl restart "$SERVICE"
    log "restarted $SERVICE"
    systemctl --no-pager --lines=5 status "$SERVICE" || true
else
    log "no Telegram session yet. Log in interactively:"
    echo "    ssh -t root@<server> $APP_DIR/deploy/login.sh"
fi
