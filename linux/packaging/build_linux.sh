#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="${1:-$ROOT_DIR/dist}"

mkdir -p "$OUTPUT_DIR"
bash "$SCRIPT_DIR/build_deb.sh" "$OUTPUT_DIR"
bash "$SCRIPT_DIR/build_rpm.sh" "$OUTPUT_DIR"
bash "$SCRIPT_DIR/build_appimage.sh" "$OUTPUT_DIR"
(
    cd "$OUTPUT_DIR"
    sha256sum \
        TokenOrb-Linux-x86_64.deb \
        TokenOrb-Linux-x86_64.rpm \
        TokenOrb-Linux-x86_64.AppImage \
        > TokenOrb-Linux-x86_64.sha256
)
printf 'Built %s\n' "$OUTPUT_DIR/TokenOrb-Linux-x86_64.sha256"
