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

command -v rpmbuild >/dev/null 2>&1 || {
    echo "rpmbuild is required" >&2
    exit 1
}

mkdir -p "$OUTPUT_DIR"
temporary_dir="$(mktemp -d)"
trap 'rm -rf "$temporary_dir"' EXIT
top_dir="$temporary_dir/rpm"
source_dir="$top_dir/SOURCES/tokenorb-source"
mkdir -p "$top_dir/SOURCES" "$top_dir/SPECS" "$source_dir/assets"

install -m 0644 "$ROOT_DIR/linux/tokenorb_app.py" "$ROOT_DIR/linux/tokenorb_core.py" \
    "$source_dir/"
install -m 0644 "$ROOT_DIR/linux/assets/tokenorb.svg" "$source_dir/assets/tokenorb.svg"
install -m 0644 "$SCRIPT_DIR/TokenOrb.desktop" "$source_dir/TokenOrb.desktop"
install -m 0644 "$SCRIPT_DIR/INSTALL.md" "$source_dir/INSTALL.md"
install -m 0644 "$ROOT_DIR/LICENSE" "$source_dir/LICENSE"
install -m 0755 "$SCRIPT_DIR/tokenorb-launcher" "$source_dir/tokenorb-launcher"
tar -C "$top_dir/SOURCES" -czf "$top_dir/SOURCES/tokenorb-source.tar.gz" tokenorb-source
sed "s/@VERSION@/$VERSION/g" "$SCRIPT_DIR/tokenorb.spec.in" > "$top_dir/SPECS/tokenorb.spec"

rpmbuild --define "_topdir $top_dir" -bb "$top_dir/SPECS/tokenorb.spec" >/dev/null
rpm_path="$(find "$top_dir/RPMS" -type f -name 'tokenorb-*.rpm' -print -quit)"
if [[ -z "$rpm_path" ]]; then
    echo "RPM build did not produce an artifact" >&2
    exit 1
fi

output="$OUTPUT_DIR/TokenOrb-Linux-x86_64.rpm"
rm -f "$output"
install -m 0644 "$rpm_path" "$output"
rpm -qp "$output" >/dev/null
printf 'Built %s\n' "$output"
