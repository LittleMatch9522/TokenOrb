#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="${1:-$ROOT_DIR/dist}"
VERSION="${TOKENORB_VERSION:-}"

if [[ -z "$VERSION" && "${GITHUB_REF_NAME:-}" =~ ^v(.+)$ ]]; then
    VERSION="${BASH_REMATCH[1]}"
fi
if [[ -z "$VERSION" ]]; then
    VERSION="$(tr -d '[:space:]' < "$ROOT_DIR/linux/VERSION")"
fi
if [[ ! "$VERSION" =~ ^[0-9][0-9A-Za-z.+:~_-]*$ ]]; then
    echo "Invalid package version: $VERSION" >&2
    exit 2
fi

command -v dpkg-deb >/dev/null 2>&1 || {
    echo "dpkg-deb is required" >&2
    exit 1
}

mkdir -p "$OUTPUT_DIR"
temporary_dir="$(mktemp -d)"
trap 'rm -rf "$temporary_dir"' EXIT
staging="$temporary_dir/root"

install -d \
    "$staging/DEBIAN" \
    "$staging/usr/bin" \
    "$staging/usr/lib/tokenorb/assets" \
    "$staging/usr/share/applications" \
    "$staging/usr/share/icons/hicolor/scalable/apps" \
    "$staging/usr/share/doc/tokenorb"
install -m 0755 "$SCRIPT_DIR/tokenorb-launcher" "$staging/usr/bin/tokenorb"
install -m 0644 "$ROOT_DIR/linux/tokenorb_app.py" "$ROOT_DIR/linux/tokenorb_core.py" \
    "$staging/usr/lib/tokenorb/"
install -m 0644 "$ROOT_DIR/linux/assets/tokenorb.svg" "$staging/usr/lib/tokenorb/assets/tokenorb.svg"
install -m 0644 "$SCRIPT_DIR/TokenOrb.desktop" "$staging/usr/share/applications/TokenOrb.desktop"
install -m 0644 "$ROOT_DIR/linux/assets/tokenorb.svg" \
    "$staging/usr/share/icons/hicolor/scalable/apps/tokenorb.svg"
install -m 0644 "$ROOT_DIR/LICENSE" "$staging/usr/share/doc/tokenorb/copyright"
install -m 0644 "$SCRIPT_DIR/INSTALL.md" "$staging/usr/share/doc/tokenorb/INSTALL.md"
sed "s/@VERSION@/$VERSION/g" "$SCRIPT_DIR/debian/control.in" > "$staging/DEBIAN/control"

if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "$staging/usr/share/applications/TokenOrb.desktop"
fi

output="$OUTPUT_DIR/TokenOrb-Linux-x86_64.deb"
rm -f "$output"
dpkg-deb --build --root-owner-group "$staging" "$output" >/dev/null
dpkg-deb --info "$output" >/dev/null
printf 'Built %s\n' "$output"
