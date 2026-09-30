# Shared settings for the deploy scripts. Sourced, never executed directly.
# shellcheck shell=bash
# The variables below are used by the scripts that source this file.
# shellcheck disable=SC2034

APP_NAME=toad-userbot
APP_USER=toad-userbot
APP_DIR=/opt/toad-userbot
CONFIG_DIR=/etc/toad-userbot
DATA_DIR=/var/lib/toad-userbot
PYTHON_VERSION=3.12
UV_VERSION=0.12.21

TOOLS_DIR="$APP_DIR/.tools"
UV="$TOOLS_DIR/bin/uv"
SERVICE="$APP_NAME.service"

# Python is installed by uv inside the app directory: the system Python and other
# services on the host are never touched.
export UV_PYTHON_INSTALL_DIR="$APP_DIR/.python"
export UV_PYTHON_PREFERENCE=only-managed
export UV_CACHE_DIR=/var/cache/toad-userbot/uv

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() {
    printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2
    exit 1
}
require_root() { [ "$(id -u)" -eq 0 ] || die "run as root"; }
