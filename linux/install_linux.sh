#!/usr/bin/env bash

set -eu

APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APPLICATIONS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"

install -d "$APPLICATIONS_DIR"
install -d "$ICON_DIR"
install -d "$BIN_DIR"
install -m 644 "$APP_DIR/TokenOrb.desktop" "$APPLICATIONS_DIR/TokenOrb.desktop"
install -m 644 "$APP_DIR/assets/tokenorb.svg" "$ICON_DIR/tokenorb.svg"
sed "s|@APP_DIR@|$APP_DIR|g" \
    "$APP_DIR/packaging/tokenorb-user-launcher.in" > "$BIN_DIR/tokenorb"
chmod 0755 "$BIN_DIR/tokenorb"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

echo "已安装 TokenOrb 应用入口：$APPLICATIONS_DIR/TokenOrb.desktop"
echo "启动命令：$BIN_DIR/tokenorb"
