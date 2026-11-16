#!/bin/bash
# Assemble checksum-verified getrandom forks with the ENOSYS-only MIPS
# /dev/urandom fallback delta and wire [patch.crates-io] into the pinned
# upstream tree. Fail-closed: any checksum, patch or lock mismatch aborts.
#
# Usage: assemble-forks.sh <entware-build-dir>
# Expects <dir>/upstream to be the pinned telemt checkout (with the atomic64
# compat patch already applied) and crates.io checksums to match the committed
# Cargo.lock (single source of truth for the crate provenance).
set -euo pipefail

EB="${1:?usage: assemble-forks.sh <entware-build-dir>}"
RESEARCH_DIR="$(cd "$(dirname "$0")" && pwd)"
UP="$EB/upstream"
COMPAT="$EB/compat"

# cargo is required for the lock consistency check; rustup's default location
# plus a sourceable env fallback keeps this independent of runner setup order.
command -v cargo >/dev/null 2>&1 || export PATH="$HOME/.cargo/bin:$PATH"
command -v cargo >/dev/null 2>&1 || { test -f "$HOME/.cargo/env" && . "$HOME/.cargo/env"; }
command -v cargo >/dev/null 2>&1 || { echo "::error::cargo not found for the lock check"; exit 1; }

test -e "$UP/.git" || { echo "::error::upstream tree missing at $UP"; exit 1; }
test -f "$RESEARCH_DIR/Cargo.lock" || { echo "::error::committed Cargo.lock missing"; exit 1; }
test -f "$RESEARCH_DIR/checksums.txt" || { echo "::error::committed checksums.txt missing"; exit 1; }
test -f "$RESEARCH_DIR/patch-section.toml.snippet" || { echo "::error::patch section snippet missing"; exit 1; }

echo "===== 4.5a) download + checksum-verify the three crate sources ====="
# checksums.txt is an independent record extracted from the pinned upstream
# Cargo.lock BEFORE [patch.crates-io] wiring (patched entries drop checksums).
mkdir -p "$COMPAT/dl"
cd "$COMPAT/dl"
if sha256sum -c "$RESEARCH_DIR/checksums.txt" 2>/dev/null; then
  echo "GETRANDOM_CRATE_CACHE: PASS"
else
  for v in 0.4.3 0.3.4 0.2.17; do
    curl -fsSL --max-time 120 -o "getrandom-$v.crate" \
      "https://static.crates.io/crates/getrandom/getrandom-$v.crate"
  done
  sha256sum -c "$RESEARCH_DIR/checksums.txt"
fi

echo "===== 4.5c) extract forks and apply the reviewed delta patches ====="
cd "$UP"
for v in 0.4.3 0.3.4 0.2.17; do
  DIR="$COMPAT/getrandom-$v-entware"
  rm -rf "$DIR"; mkdir -p "$DIR"
  tar xzf "$COMPAT/dl/getrandom-$v.crate" -C "$DIR" --strip-components=1
  patch -s -p1 --fuzz=0 -d "$DIR" < "$RESEARCH_DIR/patches/getrandom-$v-mips-fallback.patch"
  # fail-closed structural assertions on the forked source
  MODULE="$DIR/src/backends/linux_mips_with_fallback.rs"
  [ "$v" = "0.2.17" ] && MODULE="$DIR/src/linux_mips_with_fallback.rs"
  test -f "$MODULE" || { echo "::error::mips fallback module missing for $v"; exit 1; }
  if grep -q 'EPERM => NOT_AVAILABLE\|EPERM) => false' "$MODULE"; then
    echo "::error::$v module still falls back on EPERM (assignment requires ENOSYS only)"
    exit 1
  fi
  ROUTING="$DIR/src/backends.rs"
  [ "$v" = "0.2.17" ] && ROUTING="$DIR/src/lib.rs"
  N=$(grep -c 'target_arch = "mips",' "$ROUTING")
  [ "$N" = "1" ] || { echo "::error::$v mips routing count=$N (expected exactly 1)"; exit 1; }
  echo "FORK_ASSEMBLED_OK getrandom-$v"
done

echo "===== 4.5d) wire [patch.crates-io] and install the patched lock ====="
python3 - "$UP/Cargo.toml" "$RESEARCH_DIR/patch-section.toml.snippet" <<'PYEOF'
import sys
p, snippet = sys.argv[1], sys.argv[2]
txt = open(p).read()
if "[patch.crates-io]" in txt:
    print("PATCH_SECTION_ALREADY_PRESENT")
else:
    open(p, "w").write(txt.rstrip() + "\n" + open(snippet).read())
    print("PATCH_SECTION_INSERTED")
PYEOF
cp "$RESEARCH_DIR/Cargo.lock" "$UP/Cargo.lock"
(cd "$UP" && cargo metadata --format-version 1 --locked >/dev/null) || {
  echo "::error::Cargo.lock inconsistent with manifests after patch wiring"
  exit 1
}
echo "FORKS_ASSEMBLED_OK (lock consistent, path patches active)"
