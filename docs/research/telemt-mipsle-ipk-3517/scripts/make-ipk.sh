#!/bin/bash
# Build a minimal, reproducible Entware .ipk (opkg tar.gz outer format).
#
# Usage: make-ipk.sh <control-file> <data-root-dir> <out.ipk> [source-date-epoch]
#   control-file : plain control (Package/Version/Architecture/... fields)
#   data-root-dir: directory whose contents become the payload (e.g. a root/opt tree)
#
# Guarantees:
#  - outer archive: gzipped tar with ./debian-binary, ./data.tar.gz, ./control.tar.gz
#    (same member order as Entware feed packages)
#  - all tar members root:root 0, normalized mtime (reproducible builds)
#  - binaries keep their executable bit; nothing is executed during packaging
set -euo pipefail

CONTROL_FILE=$1
DATA_ROOT=$2
OUT_IPK=$3
SDE=${4:-1760380800}  # fixed epoch for reproducibility (2025-10-14T00:00:00Z default, caller may override)

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

TARFLAGS=(--sort=name --owner=0 --group=0 --numeric-owner --mtime="@$SDE")

# --- payload ---
mkdir "$WORK/data-root"
cp -a "$DATA_ROOT/." "$WORK/data-root/"
# normalize payload metadata without changing file modes
find "$WORK/data-root" -mindepth 0 -exec chown 0:0 {} + 2>/dev/null || true
tar "${TARFLAGS[@]}" -C "$WORK/data-root" -czf "$WORK/data.tar.gz" .

# --- control ---
mkdir "$WORK/control-root"
cp "$CONTROL_FILE" "$WORK/control-root/control"
chmod 0644 "$WORK/control-root/control"
tar "${TARFLAGS[@]}" -C "$WORK/control-root" -czf "$WORK/control.tar.gz" .

# --- outer ---
printf '2.0\n' > "$WORK/debian-binary"
tar "${TARFLAGS[@]}" -C "$WORK" -czf "$OUT_IPK" \
  ./debian-binary ./control.tar.gz ./data.tar.gz

echo "wrote $OUT_IPK ($(stat -c%s "$OUT_IPK") bytes)"
tar tzf "$OUT_IPK"
