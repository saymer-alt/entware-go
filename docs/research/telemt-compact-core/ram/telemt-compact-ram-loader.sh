#!/bin/sh
# Compressed ELF stays in /opt; a checksum-verified ELF runs from /tmp tmpfs.
set -eu
umask 077
BB=/opt/bin/busybox
XZ=/opt/bin/xz
SRC=/opt/share/telemt-compact-ram/telemt.xz
EXPECTED_FILE=/opt/share/telemt-compact-ram/telemt.sha256
RUN=/tmp/telemt-ipc-compact-ram
EXE=$RUN/telemt-ipc-compact-ram
fail() { echo "TELEMT_COMPACT_RAM_FAILED: $*" >&2; exit 1; }
[ -x "$XZ" ] && [ -f "$SRC" ] && [ -f "$EXPECTED_FILE" ] ||
  fail "XZ dependency / payload missing"
EXPECTED=$("$BB" cat "$EXPECTED_FILE")
[ "$(printf '%s' "$EXPECTED" | "$BB" wc -c)" -eq 64 ] ||
  fail "invalid embedded ELF digest"
if [ -f "$EXE" ] && [ ! -L "$EXE" ]; then
  HAVE=$("$BB" sha256sum "$EXE" | "$BB" awk '{print $1}')
  [ "$HAVE" = "$EXPECTED" ] ||
    fail "cached runtime ELF digest mismatch: refusing to overwrite"
  exec "$EXE" "$@"
fi
[ ! -L "$RUN" ] && [ ! -L "$EXE" ] || fail "symlink in runtime path"
"$BB" mkdir -p "$RUN"
"$BB" chmod 700 "$RUN"
ELF_KIB=ELF_KIB_PLACEHOLDER
TMP_FREE=$(df -k /tmp | "$BB" awk 'END {print $4}')
AVAIL_RAM=$("$BB" awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
case "$TMP_FREE:$AVAIL_RAM" in
  *[!0-9:]*|:*|*:) fail "cannot measure /tmp space / available RAM";;
esac
[ "$TMP_FREE" -ge $((ELF_KIB + 4096)) ] ||
  fail "insufficient /tmp tmpfs space"
[ "$AVAIL_RAM" -ge $((ELF_KIB + 12288)) ] ||
  fail "insufficient available RAM for tmpfs binary and service reserve"
PROBE=$RUN/.exec-test.$$
printf '#!/bin/sh\nexit 0\n' > "$PROBE"
"$BB" chmod 700 "$PROBE"
if ! "$PROBE"; then
  "$BB" rm -f "$PROBE"
  fail "/tmp is noexec or runtime execution disabled"
fi
"$BB" rm -f "$PROBE"
TMP=$RUN/.unpack.$$
trap '"$BB" rm -f "$TMP"' 0
"$XZ" -dc "$SRC" > "$TMP" || fail "XZ extraction failed"
GOT=$("$BB" sha256sum "$TMP" | "$BB" awk '{print $1}')
[ "$GOT" = "$EXPECTED" ] || fail "decompressed ELF SHA256 mismatch"
"$BB" chmod 700 "$TMP"
"$BB" mv -n "$TMP" "$EXE" || fail "cannot finalize RAM executable"
[ -x "$EXE" ] || fail "RAM executable not available"
exec "$EXE" "$@"
