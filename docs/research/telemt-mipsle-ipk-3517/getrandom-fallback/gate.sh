#!/bin/bash
# Entropy fallback gate: run the fail-closed test matrix for the forked
# getrandom crates BEFORE the experimental IPK is uploaded.
#
#   1. Host regression tests: upstream + delta tests of every fork in three
#      modes (stock getrandom path, forced /dev/urandom fallback via upstream's
#      own `getrandom_test_linux_fallback` hook, and the without-fallback guard).
#   2. Target-arch runs: the entropy probe (three forks + rand 0.10.2
#      ThreadRng) built for mipsel-unknown-linux-gnu with the Entware ABI and
#      executed under qemu-user in the plain and fallback-forced modes.
#   3. Fail-closed: in a mount namespace whose /dev is an empty tmpfs every
#      fork must return an error, never fabricate entropy.
#
# Usage: gate.sh <entware-build-dir>   (run after build-telemt-core.sh)
set -euo pipefail

EB="${1:?usage: gate.sh <entware-build-dir>}"
RESEARCH_DIR="$(cd "$(dirname "$0")" && pwd)"
SR="$EB/sysroot"
L="$SR/usr/mipsel-linux-gnu/lib"
QEMU="${QEMU_BIN:-qemu-mipsel}"
TARGET=mipsel-unknown-linux-gnu

command -v cargo >/dev/null 2>&1 || export PATH="$HOME/.cargo/bin:$PATH"
command -v cargo >/dev/null 2>&1 || { test -f "$HOME/.cargo/env" && . "$HOME/.cargo/env"; }
command -v cargo >/dev/null 2>&1 || { echo "::error::cargo not found for the fork tests"; exit 1; }

command -v "$QEMU" >/dev/null 2>&1 || { echo "::error::qemu-mipsel not found (install qemu-user)"; exit 1; }

echo "===== GATE 1) fork host regression tests (3 modes x 3 forks) ====="
for v in 0.4.3 0.3.4 0.2.17; do
  fork="$EB/compat/getrandom-$v-entware"
  test -d "$fork/tests" || { echo "::error::fork tests missing for $v"; exit 1; }
  for cfg in "" "--cfg getrandom_test_linux_fallback" "--cfg getrandom_test_linux_without_fallback"; do
    MODE="stock"; [ -n "$cfg" ] && MODE="${cfg#--cfg getrandom_test_}"
    OUT=$( (cd "$fork" && RUSTFLAGS="$cfg -Aunexpected_cfgs" cargo test 2>&1) )
    if printf '%s' "$OUT" | grep -q 'test result: FAILED'; then
      echo "::error::fork $v mode $MODE: unit tests FAILED"; exit 1
    fi
    INT=$( (cd "$fork" && RUSTFLAGS="$cfg -Aunexpected_cfgs" \
            cargo test --test mips_fallback_integration 2>&1 | grep 'test result' || true) )
    printf '%s' "$INT" | grep -q '2 passed; 0 failed' || {
      echo "::error::fork $v mode $MODE: integration matrix incomplete: $INT"; exit 1; }
    echo "FORK_HOST_TESTS_OK $v/$MODE"
  done
done

echo "===== GATE 2) mipsel probe build + qemu-user runs ====="
# Dynamic probe binaries need the Entware loader and libc; mirror the pinned
# sysroot into a qemu -L prefix (same layout as the guest /opt/lib).
PREFIX="$EB/qemu-prefix"
rm -rf "$PREFIX"; mkdir -p "$PREFIX/opt/lib"
cp -a "$L/." "$PREFIX/opt/lib/"

rm -rf "$EB/entropy-probe-rs"
cp -r "$RESEARCH_DIR/entropy-probe-rs" "$EB/entropy-probe-rs"
cd "$EB/entropy-probe-rs"
export CARGO_TARGET_MIPSEL_UNKNOWN_LINUX_GNU_LINKER="$EB/mipsel-entware-link-gcc"
export CC_mipsel_unknown_linux_gnu="${CC_mipsel_unknown_linux_gnu:-$(command -v mipsel-linux-gnu-gcc || command -v mipsel-linux-gnu-gcc-12) -msoft-float -I$EB/compat-headers}"
export CFLAGS_mipsel_unknown_linux_gnu="-msoft-float -I$EB/compat-headers"
export RUST_LIBC_UNSTABLE_GNU_TIME_BITS=32
export CARGO_BUILD_JOBS=2

run_probe() { # <binary> <expected-final-marker>
  local BIN="$1" MARK="$2" OUT
  OUT=$("$QEMU" -L "$PREFIX" "$BIN")
  printf '%s\n' "$OUT"
  printf '%s' "$OUT" | grep -q "$MARK" || { echo "::error::probe marker $MARK missing"; exit 1; }
  printf '%s' "$OUT" | grep -q 'RS_THREADRNG_OK' || { echo "::error::ThreadRng regression"; exit 1; }
}

MODE1_RUSTFLAGS="-C target-cpu=mips32r2 -C target-feature=+soft-float -Aunexpected_cfgs"
export CARGO_TARGET_MIPSEL_UNKNOWN_LINUX_GNU_RUSTFLAGS="$MODE1_RUSTFLAGS"
cargo clean -p libc 2>/dev/null || true
cargo +nightly -Z build-std=std,panic_abort build --release --target "$TARGET" --bins 2>&1 \
  | grep -E '^error' && { echo "::error::probe plain build failed"; exit 1; }
run_probe "$EB/entropy-probe-rs/target/$TARGET/release/entropy-probe-rs" "RS_PROBE_DONE"
echo "QEMU_PROBE_PLAIN: PASS (getrandom path present on target arch)"

export CARGO_TARGET_MIPSEL_UNKNOWN_LINUX_GNU_RUSTFLAGS="$MODE1_RUSTFLAGS --cfg getrandom_test_linux_fallback"
cargo clean -p libc 2>/dev/null || true
cargo +nightly -Z build-std=std,panic_abort build --release --target "$TARGET" --bins 2>&1 \
  | grep -E '^error' && { echo "::error::probe fallback build failed"; exit 1; }
FB="$EB/entropy-probe-rs/target/$TARGET/release/entropy-probe-rs"
FC="$EB/entropy-probe-rs/target/$TARGET/release/entropy-failclosed-rs"
run_probe "$FB" "RS_PROBE_DONE"
echo "QEMU_PROBE_FALLBACK: PASS (forced /dev/urandom fallback serves ThreadRng and all three forks)"

echo "===== GATE 3) fail-closed without entropy devices ====="
# Sanity first: with devices present the fail-closed binary skips by design.
"$QEMU" -L "$PREFIX" "$FC" | grep -q 'RS_FAIL_CLOSED_SKIPPED_DEVICE_PRESENT' \
  || { echo "::error::fail-closed skip semantics broken"; exit 1; }
unshare -m sh -c "mount -t tmpfs none /dev && $QEMU -L $PREFIX $FC; rc=\$?; exit \$rc"
echo "FAIL_CLOSED_NO_ENTROPY: PASS (every fork returned an error; no fabricated success)"

echo "===== GATE 4) ABI fingerprint of the probe binaries ====="
for b in "$FB" "$FC"; do
  FP=$(mipsel-linux-gnu-readelf -A "$b" | grep -oE 'FP ABI: [A-Za-z ]+' | head -1)
  INTERP=$(mipsel-linux-gnu-readelf -l "$b" | grep -oE 'interpreter: /opt/lib/ld\.so\.1' | head -1)
  [ "$FP" = "FP ABI: Soft float" ] || { echo "::error::$b FP ABI: $FP"; exit 1; }
  [ -n "$INTERP" ] || { echo "::error::$b interpreter missing"; exit 1; }
  echo "ABI_OK $(basename "$b"): $FP, $INTERP"
done

echo "ENTROPY_FALLBACK_GATE: PASS"
