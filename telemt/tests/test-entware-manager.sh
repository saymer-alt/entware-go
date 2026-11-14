#!/bin/sh
# Offline GitHub API and opkg acceptance tests; never operates a real router.
set -eu
base="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
root="/opt/tmp/telemt-ipk-test-$$"
[ "$(id -u)" = 0 ] || { echo 'Run on a disposable CI runner with sudo' >&2; exit 2; }
[ ! -e "$root" ] || exit 2
[ ! -e /opt/bin/telemt ] || { echo 'CI test requires a disposable host without installed TeleMT' >&2; exit 2; }
mkdir -p /opt/bin "$root/bin" "$root/control" "$root/data/opt/bin"
cleanup() {
  rm -rf "$root"
  rm -f /opt/bin/telemt-ipk-ci-test /opt/bin/telemt
}
trap cleanup EXIT
printf '#!/bin/sh\nexit 0\n' > "$root/data/opt/bin/telemt"
printf 'Package: telemt\nVersion: 3.5.17-1\nArchitecture: aarch64-3.10\n' > "$root/control/control"
# Real Entware SDK IPKs always carry opkg's standard hook boilerplate; the
# fixture mirrors that so every check below exercises the same whitelist.
printf '%s\n' '#!/bin/sh' '[ "${IPKG_NO_SCRIPT}" = "1" ] && exit 0' \
  '[ -s /opt/lib/functions.sh ] || exit 0' '. /opt/lib/functions.sh' \
  'default_postinst $0 $@' > "$root/control/postinst"
printf '%s\n' '#!/bin/sh' '[ -s /opt/lib/functions.sh ] || exit 0' \
  '. /opt/lib/functions.sh' 'default_prerm $0 $@' > "$root/control/prerm"
tar -czf "$root/control.tar.gz" -C "$root/control" .
tar -czf "$root/data.tar.gz" -C "$root/data" .
printf '2.0\n' > "$root/debian-binary"
tar -czf "$root/test.ipk" -C "$root" ./control.tar.gz ./data.tar.gz ./debian-binary
hash="$(sha256sum "$root/test.ipk" | awk '{print $1}')"
name=telemt_3.5.17-1_aarch64-3.10.ipk
url="https://github.com/saymer-alt/entware-go/releases/download/latest/$name"
jq -n --arg name "$name" --arg url "$url" --arg digest "sha256:$hash" \
  '{tag_name:"latest", assets:[{name:$name,browser_download_url:$url,digest:$digest}]}' > "$root/manifest.json"
cat > "$root/bin/uname" <<'SH'
#!/bin/sh
printf 'aarch64\n'
SH
cat > "$root/bin/curl" <<'SH'
#!/bin/sh
out=''
url=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    *) url="$1"; shift ;;
  esac
done
case "$url" in
  https://api.github.com/repos/saymer-alt/entware-go/releases/tags/latest)
    cp "$IPK_TEST_ROOT/manifest.json" "$out" ;;
  https://github.com/saymer-alt/entware-go/releases/download/latest/*)
    cp "$IPK_TEST_ROOT/test.ipk" "$out" ;;
  *) exit 42 ;;
esac
SH
cat > "$root/bin/opkg" <<'SH'
#!/bin/sh
case "$1" in
  print-architecture) printf 'arch aarch64-3.10 10\n' ;;
  status)
    if [ "$2" = telemt ] && [ -f "$IPK_TEST_ROOT/installed" ]; then
      printf 'Package: telemt\nVersion: %s\n' "$(cat "$IPK_TEST_ROOT/installed")"
    fi ;;
  compare-versions)
    [ "$2" = '3.5.16-1' ] && [ "$3" = '<<' ] && [ "$4" = '3.5.17-1' ] ;;
  install)
    printf '%s\n' "$2" > "$IPK_TEST_ROOT/opkg-install-called"
    printf '3.5.17-1\n' > "$IPK_TEST_ROOT/installed"
    printf '#!/bin/sh\nexit 0\n' > /opt/bin/telemt-ipk-ci-test
    cp /opt/bin/telemt-ipk-ci-test /opt/bin/telemt
    chmod 755 /opt/bin/telemt ;;
  *) exit 3 ;;
esac
SH
chmod +x "$root/bin/"*
export IPK_TEST_ROOT="$root"
export TELEMT_STAGE_DIR="$root/stage"
export TELEMT_CACHE_DIR="$root/cache"
export PATH="$root/bin:$PATH"
# Trust the release fixture; this is not a network or a production install.
sh "$base/telemt/entware-manager.sh" check core | grep -q '3.5.17-1'
sh "$base/telemt/entware-manager.sh" fetch core | grep -q 'PASS: control'
test ! -e "$root/opkg-install-called"
# Verify checksum and metadata for the cached copy.
sh "$base/telemt/entware-manager.sh" inspect core | grep -q 'PASS: control'
# Deliberately wrong metadata SHA is rejected.
cp "$root/manifest.json" "$root/good.json"
jq '.assets[0].digest="sha256:0000000000000000000000000000000000000000000000000000000000000000"' "$root/good.json" > "$root/manifest.json"
if sh "$base/telemt/entware-manager.sh" inspect core > "$root/bad.out" 2>&1; then
  echo 'FAIL: accepted tampered digest' >&2
  exit 1
fi
test ! -e "$root/opkg-install-called"
mv "$root/good.json" "$root/manifest.json"
# Existing package cannot be installed via the clean installer.
printf '3.5.17-1\n' > "$root/installed"
if sh "$base/telemt/install.sh" core > "$root/already.out" 2>&1; then
  echo 'FAIL: accepted install over opkg package' >&2
  exit 1
fi
test ! -e "$root/opkg-install-called"
# Current package can be cached for opkg-consistent future rollback.
sh "$base/telemt/entware-manager.sh" cache core | grep -q 'Rollback IPK cached'
test -f "$root/cache/$name"
test -f "$root/cache/$name.sha256"
# A newer release without prior cache must fail closed.
# Mock an existing program owned by the older installed package.
cp "$root/data/opt/bin/telemt" /opt/bin/telemt
chmod 0755 /opt/bin/telemt
printf '3.5.16-1\n' > "$root/installed"
if sh "$base/telemt/upgrade.sh" core > "$root/no-rollback.out" 2>&1; then
  echo 'FAIL: accepted upgrade without previous IPK' >&2
  exit 1
fi
# Dirty old binary prevents unowned clean installs; no destructive change.
rm -f "$root/installed"
if sh "$base/telemt/install.sh" core --apply > "$root/unowned.out" 2>&1; then
  echo 'FAIL: accepted an existing unowned binary' >&2
  exit 1
fi
test ! -e "$root/opkg-install-called"
# Positive clean install must use ONLY the mocked opkg and preserve metadata.
rm -f /opt/bin/telemt
sh "$base/telemt/install.sh" core --apply | grep -q 'PASS: package installed'
test -s "$root/opkg-install-called"
test "$(cat "$root/installed")" = '3.5.17-1'
# A custom maintainer script could mutate config/state or add autostart.
# Rebuild the fixture with a rogue postinst; the dry run must fail closed.
rebuild_fixture() {
  rm -f "$root/stage/$name"
  tar -czf "$root/control.tar.gz" -C "$root/control" .
  tar -czf "$root/test.ipk" -C "$root" ./control.tar.gz ./data.tar.gz ./debian-binary
  hash="$(sha256sum "$root/test.ipk" | awk '{print $1}')"
  jq -n --arg name "$name" --arg url "$url" --arg digest "sha256:$hash" \
    '{tag_name:"latest", assets:[{name:$name,browser_download_url:$url,digest:$digest}]}' > "$root/manifest.json"
}
rm -f "$root/installed" /opt/bin/telemt "$root/opkg-install-called"
printf '#!/bin/sh\n. /opt/lib/functions.sh\nstart_service telemt\n' > "$root/control/postinst"
rebuild_fixture
if sh "$base/telemt/install.sh" core > "$root/custom.out" 2>&1; then
  echo 'FAIL: accepted a custom maintainer script' >&2
  exit 1
fi
test ! -e "$root/opkg-install-called"
# A foreign preinst is rejected even with otherwise standard hooks.
printf '#!/bin/sh\nexit 0\n' > "$root/control/preinst"
printf '%s\n' '#!/bin/sh' '[ "${IPKG_NO_SCRIPT}" = "1" ] && exit 0' \
  '[ -s /opt/lib/functions.sh ] || exit 0' '. /opt/lib/functions.sh' \
  'default_postinst $0 $@' > "$root/control/postinst"
rebuild_fixture
if sh "$base/telemt/install.sh" core > "$root/preinst.out" 2>&1; then
  echo 'FAIL: accepted a foreign preinst' >&2
  exit 1
fi
test ! -e "$root/opkg-install-called"
# The exact standard SDK hook bytes are accepted again.
rm -f "$root/control/preinst"
rebuild_fixture
sh "$base/telemt/install.sh" core | grep -q 'DRY RUN'
test ! -e "$root/opkg-install-called"
echo 'PASS: offline manifest, digest, metadata, maintainer-script, cache, downgrade, clean install gates'
