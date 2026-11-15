#!/bin/bash
# Build TeleMT Core 3.5.17 for Entware mipsel-3.4 (glibc 2.27, /opt/lib/ld.so.1,
# softfloat) and run the static Entware ABI gate. Designed for ubuntu-24.04 CI;
# also reproduces locally (see docs/research/telemt-mipsle-ipk-3517/README.md).
#
# Key facts driving this recipe (measured 2026-11-14, see README):
#  - Entware mipselsf-k3.4 runtime is glibc 2.27 soft-float; loader /opt/lib/ld.so.1
#  - glibc 2.34+ crt1.o references __libc_start_main@GLIBC_2.34 -> binary would fail
#    to load on 2.27; therefore crt/libc_nonshared come from glibc 2.24 cross dev
#  - Entware toolchain is not published prebuilt; sysroot is assembled from the
#    Entware runtime packages themselves (libc, libgcc, libpthread, librt)
#  - compile stage uses distro 2.39 headers; link stage resolves ONLY against the
#    Entware sysroot (gcc -B override), so any accidental >2.27 symbol use fails
#    the build or the version gate instead of reaching a device
set -euo pipefail

UPSTREAM_SHA=66708d2866f3f3a4541c4fa67984d408e71a8af4
# script is expected to be invoked from the repository root (CI default)
PATCH_FILE="$(pwd)/${PATCH_FILE:-docs/research/telemt-mipsle-ipk-3517/telemt-3.5.17-mipsle-atomic64-compat.patch}"
EB="${EB:-$HOME/entware-build}"
SR="$EB/sysroot"
L="$SR/usr/mipsel-linux-gnu/lib"
PREFLIGHT_FILE="$(pwd)/tools/telemt_mipsle_ipk_preflight.py"
TARGET=mipsel-unknown-linux-gnu

mkdir -p "$EB"; cd "$EB"

echo "===== 1) pinned artifacts (sha256-verified) ====="
cat > sha256.manifest <<'MANIFEST'
0fcec2bb0fb545ee427985950557fa5c5a6e811f4885d6821ad6af006abd2486  dev24.deb
45c7ef0bda2acb4475a75efee9734e83f69f54e128971b7a196d88c8b048a222  libc_2.27-12_mipsel-3.4.ipk
bbecc26b579470d52053b72e41dddb70415963eac9f74baf1747b9d2ecdcaaa3  libgcc_8.4.0-12_mipsel-3.4.ipk
8f50a9f331ad7b2bf6125c8826f71b643db62a113f09a93a3827ef3520bb3d34  libpthread_2.27-12_mipsel-3.4.ipk
49880f71e56b1f14738b3ff1412d41a632a3c679e802d06fafdabd227566ce85  librt_2.27-12_mipsel-3.4.ipk
MANIFEST
sha256sum -c sha256.manifest 2>/dev/null || {
  curl -fsSL --max-time 180 -o dev24.deb https://archive.debian.org/debian/pool/main/c/cross-toolchain-base/libc6-dev-mipsel-cross_2.24-10cross1_all.deb
  for p in libc_2.27-12_mipsel-3.4.ipk libgcc_8.4.0-12_mipsel-3.4.ipk libpthread_2.27-12_mipsel-3.4.ipk librt_2.27-12_mipsel-3.4.ipk; do
    curl -fsSL --max-time 120 "https://bin.entware.net/mipselsf-k3.4/$p" -o "$p"
  done
  sha256sum -c sha256.manifest
}

echo "===== 2) assemble Entware link-sysroot ====="
rm -rf "$SR"; mkdir -p "$L"
[ -d root24 ] || dpkg-deb -x dev24.deb root24
for d in libc2 libgcc2 libpt librt; do rm -rf "$EB/$d"; mkdir -p "$EB/$d"; done
tar xzf libc_2.27-12_mipsel-3.4.ipk -C libc2 && tar xzf libc2/data.tar.gz -C libc2
tar xzf libgcc_8.4.0-12_mipsel-3.4.ipk -C libgcc2 && tar xzf libgcc2/data.tar.gz -C libgcc2
tar xzf libpthread_2.27-12_mipsel-3.4.ipk -C libpt && tar xzf libpt/data.tar.gz -C libpt
tar xzf librt_2.27-12_mipsel-3.4.ipk -C librt && tar xzf librt/data.tar.gz -C librt
for d in libc2 libgcc2 libpt librt; do cp -a "$d/opt/lib/." "$L/"; done
# glibc 2.24-era startup objects (2.39-era ones poison GLIBC_2.34 into .gnu.version_r)
# These old crt objects have zero COP1 instructions (verified separately), but
# their hardfloat attributes poison even a softfloat application. Fail closed
# if the underlying code changes; strip metadata ONLY on isolated copies.
for c in crt1.o Scrt1.o crti.o crtn.o libc_nonshared.a; do
  src="root24/usr/mipsel-linux-gnu/lib/$c"
  if mipsel-linux-gnu-objdump -dr "$src" |
      grep -iE '(^|[[:space:]])(mfc1|mtc1|lwc1|swc1|ldc1|sdc1|cvt\.[sd]|add\.[sd])([[:space:]]|$)'; then
    echo "::error::glibc startup object $c contains FPU instructions"; exit 1
  fi
  mipsel-linux-gnu-objcopy --remove-section .MIPS.abiflags \
    --remove-section .gnu.attributes "$src" "$L/$c"
done
printf 'GROUP ( libc.so.6 libc_nonshared.a AS_NEEDED ( ld.so.1 ) )\n' > "$L/libc.so"
ln -sf libm.so.6 "$L/libm.so"; ln -sf libpthread.so.0 "$L/libpthread.so"
ln -sf librt.so.1 "$L/librt.so"; ln -sf libdl.so.2 "$L/libdl.so"
ln -sf libutil.so.1 "$L/libutil.so"; ln -sf libresolv.so.2 "$L/libresolv.so"
# Debian GCC crtbegin/crtend files also have hardfloat attributes by default.
# Their no-FPU copies must be used by -B before the GCC built-in search path.
GCC=$(command -v mipsel-linux-gnu-gcc || command -v mipsel-linux-gnu-gcc-12)
GCC_LIBDIR=$(dirname "$("$GCC" -print-libgcc-file-name)")
for c in crtbegin.o crtbeginS.o crtbeginT.o crtend.o crtendS.o; do
  test -f "$GCC_LIBDIR/$c" || continue
  if mipsel-linux-gnu-objdump -dr "$GCC_LIBDIR/$c" |
      grep -iE '(^|[[:space:]])(mfc1|mtc1|lwc1|swc1|ldc1|sdc1|cvt\.[sd]|add\.[sd])([[:space:]]|$)'; then
    echo "::error::GCC startup object $c contains FPU instructions"; exit 1
  fi
  mipsel-linux-gnu-objcopy --remove-section .MIPS.abiflags \
    --remove-section .gnu.attributes "$GCC_LIBDIR/$c" "$L/$c"
done
echo "sysroot members: $(ls "$L" | wc -l)"

echo "===== 3) compiler/linker wrappers ====="
GCC=$(command -v mipsel-linux-gnu-gcc || command -v mipsel-linux-gnu-gcc-12)
[ -n "$GCC" ] || { echo "no mipsel cross gcc found"; exit 1; }
# Host Debian cross-glibc has only o32_hard availability stubs.
# This research-only alias supplies __stub_* feature macros, not libc ABI
# declarations, from the *same installed headers*. It is NOT a substitute
# for the genuine softfloat glibc development sysroot.
test -f /usr/mipsel-linux-gnu/include/gnu/stubs-o32_hard.h || {
  echo "::error::cross-glibc stub header missing"; exit 1;
}
mkdir -p "$EB/compat-headers/gnu"
cat > "$EB/compat-headers/gnu/stubs-o32_soft.h" <<'STUB'
/* Research-only selection of libc __stub_* availability macros. */
#include <gnu/stubs-o32_hard.h>
STUB
cat > "$EB/mipsel-entware-cc" <<EOF
#!/bin/sh
exec $GCC -msoft-float -I$EB/compat-headers "\$@"
EOF
cat > "$EB/mipsel-entware-link-gcc" <<EOF
#!/bin/sh
exec $GCC -B$L/ -msoft-float --sysroot=$SR \\
  -Wl,--dynamic-linker=/opt/lib/ld.so.1 \\
  -Wl,-rpath,/opt/lib \\
  "\$@"
EOF
chmod +x "$EB/mipsel-entware-cc" "$EB/mipsel-entware-link-gcc"

echo "===== 4) upstream tree + reviewed compat patch ====="
cd "$EB"
if [ ! -d upstream/.git ]; then
  git clone -q https://github.com/telemt/telemt upstream
fi
cd upstream
git fetch -q origin "$UPSTREAM_SHA" 2>/dev/null || true
git checkout -q -f "$UPSTREAM_SHA"
git clean -qfd -e target
test "$(git rev-parse HEAD)" = "$UPSTREAM_SHA" || { echo "SHA_MISMATCH"; exit 1; }
git apply --check --whitespace=nowarn "$PATCH_FILE"
git apply --whitespace=nowarn "$PATCH_FILE"
test -f src/compat.rs && grep -q portable-atomic Cargo.toml || { echo "PATCH_APPLY_INCOMPLETE"; exit 1; }
echo "patch applied on $UPSTREAM_SHA"

echo "===== 5) bounded TeleMT MIPSLE build (Entware ABI) ====="
# glibc-2.34+ symbol backport shim: the C sources compile against distro 2.39
# headers where _GNU_SOURCE redirects clock_gettime/nanosleep/fcntl/ioctl/stat
# to __*_time64/__isoc23_* names, and rust 1.102 std weak!-refers
# __clock_gettime64 (strong after fat-LTO inlining). glibc 2.27 has none of
# them; the shim provides faithful implementations (time64 structs -> 2.27
# syscalls; Y2038-unsafe truncation acceptable for a research build).
mkdir -p "$EB/shim"
cat > "$EB/shim/shim.c" <<'EOF'
#include <time.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>

/* The BUILD headers (glibc 2.39) may use a 16-byte 64-bit timespec even
 * though the LEGACY Entware glibc 2.27 clock_gettime/nanosleep symbols on
 * MIPS O32 take an EIGHT-byte { int32 sec, int32 nsec } timespec.
 * NEVER pass the build header's struct timespec to Entware's time32 libc.
 * Rust std __clock_gettime64 uses a distinct 16-byte result structure.
 */
struct entware_timespec32 { int32_t tv_sec; int32_t tv_nsec; };
struct ts64 { int64_t tv_sec; int32_t tv_nsec; int32_t _padding; };
_Static_assert(sizeof(struct entware_timespec32) == 8, "MIPS O32 legacy timespec32 size");
_Static_assert(offsetof(struct entware_timespec32, tv_nsec) == 4, "MIPS O32 legacy nsec offset");
_Static_assert(sizeof(struct ts64) == 16, "Rust __timespec64 size");
_Static_assert(offsetof(struct ts64, tv_nsec) == 8, "Rust __timespec64 nsec offset");

/* CRITICAL: the distro headers may redirect clock_gettime/nanosleep/fcntl
 * into our own __*_time64 definitions. That creates silent infinite recursion
 * (confirmed in production ELF disassembly and QEMU stack overflow).
 * Explicit assembler aliases force real Entware glibc-2.27 time32 symbols.
 * Unlike changing ELF bytes, this preserves the generated machine-code ABI.
 */
extern int entware_clock_gettime32(clockid_t, struct entware_timespec32 *) __asm__("clock_gettime");
extern int entware_nanosleep32(const struct entware_timespec32 *, struct entware_timespec32 *) __asm__("nanosleep");
extern int entware_fcntl32(int, int, ...) __asm__("fcntl");
extern int entware_ioctl32(int, unsigned long, ...) __asm__("ioctl");
extern int entware_stat32(const char *, struct stat *) __asm__("stat");
extern long entware_strtol32(const char *, char **, int) __asm__("strtol");

int __clock_gettime64(clockid_t clk, struct ts64 *tp) {
    struct entware_timespec32 ts = {0, 0};
    int r = entware_clock_gettime32(clk, &ts);
    if (r == 0) {
        tp->tv_sec = (int64_t)ts.tv_sec;
        tp->tv_nsec = ts.tv_nsec;
        tp->_padding = 0;
    }
    return r;
}

int __nanosleep64(const struct ts64 *req, struct ts64 *rem) {
    if (req->tv_sec < INT32_MIN || req->tv_sec > INT32_MAX) {
        errno = EOVERFLOW; /* Entware 2.27 time_t cannot encode it. */
        return -1;
    }
    struct entware_timespec32 rq = {(int32_t)req->tv_sec, req->tv_nsec};
    struct entware_timespec32 rm = {0, 0};
    int r = entware_nanosleep32(&rq, rem != 0 ? &rm : 0);
    if (rem != 0 && r != 0) {
        rem->tv_sec = (int64_t)rm.tv_sec;
        rem->tv_nsec = rm.tv_nsec;
        rem->_padding = 0;
    }
    return r;
}

int __fcntl_time64(int fd, int cmd, long arg) {
    return entware_fcntl32(fd, cmd, arg);
}

int __ioctl_time64(int fd, unsigned long req, long arg) {
    return entware_ioctl32(fd, req, arg);
}

/* aws-lc vm_ube_detect.c: caller checks only the return value */
int __stat64_time64(const char *path, void *buf) {
    struct stat st;
    return entware_stat32(path, &st);
}

long __isoc23_strtol(const char *nptr, char **endptr, int base) {
    return entware_strtol32(nptr, endptr, base);
}
EOF
"$EB/mipsel-entware-cc" -fPIC -c "$EB/shim/shim.c" -o "$EB/shim/shim.o"
mipsel-linux-gnu-readelf -A "$EB/shim/shim.o" | grep -qF 'FP ABI: Soft float' || {
  echo "::error::glibc-compat shim is not softfloat"; exit 1;
}
# Fail early if a future header/toolchain change accidentally redirects
# time32 libc calls into our own shim symbols again.
SHIM_RELOCS=$(mipsel-linux-gnu-readelf -r "$EB/shim/shim.o")
for external in clock_gettime nanosleep fcntl ioctl stat strtol; do
  if ! grep -Eq "[[:space:]]${external}([[:space:]]|$)" <<<"$SHIM_RELOCS"; then
    echo "::error::shim missing external time32/libc relocation: $external"; exit 1
  fi
done
echo "SHIM_TIME32_RELOCATIONS: PASS (all six external glibc functions)"
# NOTE: link shim.o as an OBJECT, not an archive — archives positioned before
# the referencing objects are not pulled, leaving the refs unresolved.
export RUST_LIBC_UNSTABLE_GNU_TIME_BITS=32
# Rust inserts its first -lc before the explicit link-arg shim.o. The
# Entware libc.so GROUP also references libc_nonshared.a (static archive):
# stat() is pulled only if another -lc follows the late shim object.
# Reproduced: -lc shim.o => undefined stat; -lc shim.o -lc => QEMU exit 0
# (including --as-needed). Keep the shim as an object, never a patched ELF.
export CARGO_TARGET_MIPSEL_UNKNOWN_LINUX_GNU_RUSTFLAGS="-C target-cpu=mips32r2 -C target-feature=+soft-float -Aunexpected_cfgs -C link-arg=$EB/shim/shim.o -C link-arg=-lc"
export CARGO_TARGET_MIPSEL_UNKNOWN_LINUX_GNU_LINKER="$EB/mipsel-entware-link-gcc"
export CC_mipsel_unknown_linux_gnu="$EB/mipsel-entware-cc"
export CFLAGS_mipsel_unknown_linux_gnu="-msoft-float -I$EB/compat-headers"
export CARGO_BUILD_JOBS=2
# libc's build script does not declare rerun-if-env-changed for the time-bits
# env var; force a rerun so time32 ABI actually takes effect.
cargo clean -p libc
if ! timeout 1700 cargo +nightly -Z build-std=std,panic_abort \
    build --release --locked --target "$TARGET" --bin telemt; then
  echo "::error::TELEMT_3517_ENTWARE_BUILD_BLOCKED (record first error, stop)"
  exit 1
fi
BIN="target/$TARGET/release/telemt"
test -f "$BIN" || { echo "TELEMT_ENTWARE_BUILD: FAIL (no binary)"; exit 1; }
echo "TELEMT_3517_CORE_BUILD: PASS"

echo "===== 6) Entware ABI gate (readelf -l/-d/-V/-h, FP census, abiflags) ====="
file "$BIN" | head -1
readelf -h "$BIN" | grep -E 'Flags:|Type:'
INTERP=$(readelf -l "$BIN" | grep -oE '/opt/lib/ld\.so\.1' | head -1)
[ "$INTERP" = "/opt/lib/ld.so.1" ] || { echo "ABI_GATE: FAIL interpreter=$(readelf -l "$BIN" | grep -oE 'interpreter: .*' | head -1)"; exit 1; }
readelf -d "$BIN" | grep -E 'NEEDED|RUNPATH'
GLIBC_MAX=$(readelf -V "$BIN" | grep -oE 'GLIBC_[0-9.]+' | sort -uV | tail -1)
echo "max GLIBC symbol version: $GLIBC_MAX"
case "$GLIBC_MAX" in
  GLIBC_2.27|GLIBC_2.2[0-6]|GLIBC_2.1[0-9]|GLIBC_2.[0-9]) echo "GLIBC_GATE: PASS";;
  *) echo "::error::GLIBC_GATE: FAIL (max $GLIBC_MAX > 2.27)"; exit 1;;
esac
FP='\bmfc1\b|\bmtc1\b|\bldc1\b|\bsdc1\b|\blwc1\b|\bswc1\b|\bcvt\.[sd]\.|\bdiv\.[sd]\b|\bmul\.[sd]\b|\badd\.[sd]\b|\bsub\.[sd]\b|\bmadd\.[sd]\b|\bmsub\.[sd]\b|\bmov\.[sd]\b'
FP_COUNT=$(mipsel-linux-gnu-objdump -d "$BIN" | grep -icE "$FP" || true)
echo "FPU instructions: $FP_COUNT"
[ "${FP_COUNT:-0}" -eq 0 ] || { echo "::error::FP_GATE: FAIL (FPU instructions on FPU-less MT7621)"; exit 1; }
# Earlier readelf -n incorrectly reported 0 flags, although QEMU rejects
# PT_MIPS_ABIFLAGS.fp_abi=5. Check both real executable ABI and GNU attrs.
ABIDUMP=$(mipsel-linux-gnu-readelf -A "$BIN")
for required in 'Tag_GNU_MIPS_ABI_FP: Soft float' 'FP ABI: Soft float' 'CPR1 size: 0'; do
  if ! grep -qF "$required" <<<"$ABIDUMP"; then
    echo "::error::FP_ABI_GATE: FAIL missing $required"; exit 1
  fi
done
python3 "$PREFLIGHT_FILE" --kind core --file "$BIN" > "$EB/core-elf-preflight.json"
echo "FP_ABI_GATE: PASS (real PT_MIPS_ABIFLAGS=3 + GNU softfloat)"
# Prove no shim wrapper directly branches to itself. This caught the genuine
# Core stack overflow even though all previous static ABI checks passed.
for sym in __clock_gettime64 __nanosleep64 __fcntl_time64 __ioctl_time64 __stat64_time64; do
  if mipsel-linux-gnu-objdump -d --disassemble="$sym" "$BIN" |
       grep -Eq "[[:space:]]bal[[:space:]].*<$sym>"; then
    echo "::error::SHIM_RECURSION_GATE: FAIL self-call in $sym"; exit 1
  fi
done
echo "SHIM_RECURSION_GATE: PASS (no direct self-branches)"
readelf -V "$BIN" | grep -q 'GLIBC_2.34' && { echo "::error::stale GLIBC_2.34 ref"; exit 1; } || true
echo -n "binary sha256: "; sha256sum "$BIN"
echo "CORE_ENTWARE_ABI: PASS (static gates; QEMU_RUNTIME=NOT_TESTED)"
