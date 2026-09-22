#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="${1:-$ROOT_DIR/dist}"
PYINSTALLER="${PYINSTALLER:-pyinstaller}"
APPIMAGETOOL="${APPIMAGETOOL:-appimagetool}"

command -v "$PYINSTALLER" >/dev/null 2>&1 || {
    echo "pyinstaller is required" >&2
    exit 1
}
if [[ "$APPIMAGETOOL" != */* ]]; then
    command -v "$APPIMAGETOOL" >/dev/null 2>&1 || {
        echo "appimagetool is required" >&2
        exit 1
    }
elif [[ ! -x "$APPIMAGETOOL" ]]; then
    echo "appimagetool is not executable: $APPIMAGETOOL" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
temporary_dir="$(mktemp -d)"
trap 'rm -rf "$temporary_dir"' EXIT
app_dir="$temporary_dir/AppDir"

"$PYINSTALLER" \
    --noconfirm \
    --clean \
    --distpath "$temporary_dir/dist" \
    --workpath "$temporary_dir/build" \
    "$SCRIPT_DIR/TokenOrb.spec" >/dev/null

install -d \
    "$app_dir/usr/bin" \
    "$app_dir/usr/lib/tokenorb" \
    "$app_dir/usr/share/applications" \
    "$app_dir/usr/share/icons/hicolor/scalable/apps"
cp -a "$temporary_dir/dist/TokenOrb/." "$app_dir/usr/lib/tokenorb/"
install -m 0755 "$SCRIPT_DIR/tokenorb-appimage-launcher" "$app_dir/usr/bin/tokenorb"
install -m 0755 "$SCRIPT_DIR/tokenorb-appimage-run" "$app_dir/AppRun"
install -m 0644 "$SCRIPT_DIR/TokenOrb.desktop" "$app_dir/usr/share/applications/TokenOrb.desktop"
install -m 0644 "$SCRIPT_DIR/TokenOrb.desktop" "$app_dir/TokenOrb.desktop"
install -m 0644 "$ROOT_DIR/linux/assets/tokenorb.svg" \
    "$app_dir/usr/share/icons/hicolor/scalable/apps/tokenorb.svg"
install -m 0644 "$ROOT_DIR/linux/assets/tokenorb.svg" "$app_dir/tokenorb.svg"
install -m 0644 "$ROOT_DIR/LICENSE" "$app_dir/LICENSE"
install -m 0644 "$SCRIPT_DIR/INSTALL.md" "$app_dir/INSTALL.md"

if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "$app_dir/usr/share/applications/TokenOrb.desktop"
fi

output="$OUTPUT_DIR/TokenOrb-Linux-x86_64.AppImage"
rm -f "$output"
if [[ "$APPIMAGETOOL" == *.AppImage ]]; then
    ARCH=x86_64 "$APPIMAGETOOL" --appimage-extract-and-run "$app_dir" "$output" >/dev/null
else
    ARCH=x86_64 "$APPIMAGETOOL" "$app_dir" "$output" >/dev/null
fi
chmod 0755 "$output"
printf 'Built %s\n' "$output"
