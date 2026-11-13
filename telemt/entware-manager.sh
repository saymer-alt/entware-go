#!/bin/sh
# Safe ARM64 Entware TeleMT package manager.
# Generic public code only: never records router IP, SNI, users or secrets.
# Install: opt-in binary-only initial install. Upgrade: stage only until
# package-aware rollback and runtime health checks are independently accepted.
set -eu
umask 077
LC_ALL=C
export LC_ALL

REPO='saymer-alt/entware-go'
API="https://api.github.com/repos/$REPO/releases/tags/latest"
OUT_DIR="${TELEMT_STAGE_DIR:-/opt/tmp/telemt-ipk}"
CACHE_DIR="${TELEMT_CACHE_DIR:-/opt/var/backups/telemt-ipks}"
manifest=''
scratch=''
partial=''
cleanup() {
  [ -z "$manifest" ] || rm -f "$manifest"
  [ -z "$partial" ] || rm -f "$partial"
  [ -z "$scratch" ] || rm -rf "$scratch"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
log() { printf '%s\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"; }
usage() {
  cat <<'HELP'
TeleMT / Panel Lite, unofficial Entware aarch64-3.10 IPK
  update.sh status                 Installed opkg versions
  update.sh check                  Compare with GitHub Release latest
  update.sh fetch core|panel       Download and verify IPK (no install)
  update.sh inspect core|panel     Verify downloaded IPK control metadata
  update.sh cache core|panel       Save CURRENT installed IPK for future rollback
  update.sh stage core|panel       Prepare a NEWER IPK, requires cached old IPK
  update.sh install core|panel     Dry-run a clean binary-only install
  update.sh install core|panel --apply  Explicitly install on a CLEAN device

"stage" deliberately DOES NOT install, restart or overwrite binaries.
The package doesn't contain configuration, users, init scripts or autostart.
Prepare private settings and the service separately; don't commit them.
HELP
}
platform() {
  need opkg; need grep; need awk; need uname
  case "$(uname -m)" in aarch64|arm64) : ;; *) fail 'Only aarch64 Linux is supported' ;; esac
  opkg print-architecture | grep -Eq '(^|[[:space:]])aarch64-3[.]10(_kn)?([[:space:]]|$)' ||
    fail 'No compatible Entware aarch64-3.10 architecture'
}
secure_dir() {
  path="$1"
  case "$path" in /opt/*) : ;; *) fail "Unsafe directory outside /opt: $path" ;; esac
  [ ! -L "$path" ] || fail "Symlinked directory refused: $path"
  mkdir -p "$path" || fail "Cannot create $path"
  [ -d "$path" ] && [ ! -L "$path" ] || fail "Not a regular directory: $path"
  chmod 0700 "$path" || fail "Cannot protect directory: $path"
}
setup() {
  platform
  for cmd in curl jq sha256sum mktemp tar gzip sed; do need "$cmd"; done
  secure_dir "$OUT_DIR"
}
installed_version() {
  opkg status "$1" 2>/dev/null | awk '/^Version:[[:space:]]/ {print $2; exit}' || true
}
family() {
  case "$1" in
    core) pkg='telemt'; binary='/opt/bin/telemt'
      prefix='telemt_'; suffix='_aarch64-3.10.ipk'
      pattern='^telemt_[0-9]+[.][0-9]+[.][0-9]+-1_aarch64-3[.]10[.]ipk$' ;;
    panel) pkg='telemt-panel-lite'; binary='/opt/bin/telemt-panel'
      prefix='telemt-panel-lite_'; suffix='_aarch64-3.10.ipk'
      pattern='^telemt-panel-lite_1[.][0-9]+[.][0-9]+([.]rc[.][0-9]+)?-1_aarch64-3[.]10[.]ipk$' ;;
    *) fail "Unknown package family: $1 (expected core or panel)" ;;
  esac
}
manifest_get() {
  [ -n "$manifest" ] && return 0
  manifest="$(mktemp "$OUT_DIR/.release.XXXXXX")" || fail 'Cannot allocate release manifest'
  curl -q -fsSL --connect-timeout 12 --max-time 45 --retry 2 \
    --proto '=https' --proto-redir '=https' \
    -H 'Accept: application/vnd.github+json' "$API" -o "$manifest" ||
    fail 'GitHub Release API unavailable'
  jq -e '.tag_name == "latest" and (.assets | type == "array")' "$manifest" >/dev/null ||
    fail 'Unexpected GitHub Release JSON'
}
asset() {
  family "$1"
  manifest_get
  # Entware jq can lack ONIGURUMA; only plain-string functions are allowed.
  filt='.assets[] | select((.name|type) == "string" and (.name|startswith($p)) and (.name|endswith($s)))'
  count="$(jq -r --arg p "$prefix" --arg s "$suffix" "[$filt]|length" "$manifest")" ||
    fail 'Cannot count release assets'
  [ "$count" = 1 ] || fail "Expected exactly one $pkg ARM64 IPK, found $count"
  name="$(jq -r --arg p "$prefix" --arg s "$suffix" "$filt|.name" "$manifest")"
  printf '%s\n' "$name" | grep -Eq "$pattern" || fail "Invalid release asset name: $name"
  hash_field="$(jq -r --arg p "$prefix" --arg s "$suffix" "$filt|.digest // empty" "$manifest")"
  case "$hash_field" in sha256:*) hash="${hash_field#sha256:}" ;; *) fail "Missing SHA-256 digest for $name" ;; esac
  printf '%s\n' "$hash" | grep -Eq '^[0-9a-f]{64}$' || fail "Bad SHA-256 for $name"
  url="$(jq -r --arg p "$prefix" --arg s "$suffix" "$filt|.browser_download_url // empty" "$manifest")"
  [ "$url" = "https://github.com/$REPO/releases/download/latest/$name" ] ||
    fail "Unexpected asset URL: $name"
  version="${name#${pkg}_}"
  version="${version%_aarch64-3.10.ipk}"
  [ "$1" != panel ] || version="$(printf '%s\n' "$version" | sed 's/\.rc\./~rc./')"
  file="$OUT_DIR/$name"
}
verify_hash() {
  [ -f "$1" ] && [ ! -L "$1" ] || fail "Missing or symlinked IPK: $1"
  actual="$(sha256sum "$1" | awk '{print $1}')"
  [ "$actual" = "$2" ] || fail "SHA-256 mismatch: $1"
}
download() {
  if [ -e "$file" ] || [ -L "$file" ]; then
    verify_hash "$file" "$hash"
    log "Already verified: $file"
    return 0
  fi
  partial="$(mktemp "$OUT_DIR/.ipk.XXXXXX")" || fail 'Cannot allocate temporary IPK'
  curl -q -fsSL --retry 2 --connect-timeout 12 --max-time 180 \
    --proto '=https' --proto-redir '=https' --max-filesize 104857600 \
    "$url" -o "$partial" || fail "Download failed: $name"
  verify_hash "$partial" "$hash"
  mv "$partial" "$file" || fail "Cannot save IPK: $file"
  partial=''
  chmod 0600 "$file"
  verify_hash "$file" "$hash"
  log "PASS: GitHub SHA-256: $hash"
  log "Saved: $file"
}
control_field() {
  awk -F ': ' -v key="$1" '$1 == key {n++; value=$2} END {if (n==1) print value}' "$2"
}
inspect() {
  # Entware IPK outer container is gzip-compressed TAR, not plain TAR or ar.
  # Extract only control metadata into a root-private temp directory.
  scratch="$(mktemp -d "$OUT_DIR/.inspect.XXXXXX")" || fail 'Cannot allocate inspection folder'
  tar -xzOf "$file" ./control.tar.gz > "$scratch/control.tar.gz" ||
    fail "Malformed IPK outer gzip/tar: $file"
  tar -xzOf "$scratch/control.tar.gz" ./control > "$scratch/control" ||
    fail 'Malformed control.tar.gz'
  for field in Package Version Architecture; do
    [ "$(grep -c "^$field: " "$scratch/control")" = 1 ] ||
      fail "Missing or repeated control field $field"
  done
  [ "$(control_field Package "$scratch/control")" = "$pkg" ] ||
    fail "Unexpected embedded Package in $name"
  [ "$(control_field Version "$scratch/control")" = "$version" ] ||
    fail "Unexpected embedded Version in $name"
  [ "$(control_field Architecture "$scratch/control")" = 'aarch64-3.10' ] ||
    fail "Unexpected embedded Architecture in $name"
  if tar -tzf "$scratch/control.tar.gz" | grep -Eq '(^|/)(preinst|postinst|prerm|postrm)$'; then
    fail 'Unexpected executable maintainer scripts in the IPK'
  fi
  tar -xzOf "$file" ./data.tar.gz > "$scratch/data.tar.gz" ||
    fail 'Malformed IPK data archive'
  if tar -tzf "$scratch/data.tar.gz" | grep -Eq '^\./(opt/)?(etc|var)/'; then
    fail 'IPK unexpectedly contains configuration or state paths'
  fi
  rm -rf "$scratch"
  scratch=''
  log "PASS: control Package=$pkg Version=$version Architecture=aarch64-3.10"
}
check_root() {
  need id
  [ "$(id -u)" = 0 ] || fail 'Use root for installation and local package cache'
}
cache_current() {
  current="$(installed_version "$pkg")"
  [ -n "$current" ] || fail "$pkg is not installed via opkg"
  [ "$current" = "$version" ] ||
    fail "Only currently published identical version can be cached safely (installed $current; GitHub $version)"
  download
  inspect
  check_root
  secure_dir "$CACHE_DIR"
  cache="$CACHE_DIR/$name"
  if [ -e "$cache" ] || [ -L "$cache" ]; then
    verify_hash "$cache" "$hash"
  else
    cp "$file" "$cache" || fail 'Cannot preserve current IPK'
    chmod 0600 "$cache"
    verify_hash "$cache" "$hash"
  fi
  printf '%s\n' "$hash" > "$cache.sha256"
  chmod 0600 "$cache.sha256"
  log "Rollback IPK cached: $cache"
  log 'Protect this directory: latest release will remove older package assets.'
}
stage_upgrade() {
  current="$(installed_version "$pkg")"
  [ -n "$current" ] || fail "$pkg is not installed through opkg; use install on a clean device"
  [ -e "$binary" ] && [ ! -L "$binary" ] || fail "Installed binary is missing or a symlink: $binary"
  if [ "$current" = "$version" ]; then
    log "$pkg already current ($version); no update needed"
    return 0
  fi
  opkg compare-versions "$current" '<<' "$version" ||
    fail "Refusing downgrade or unsupported version comparison: $current -> $version"
  download
  inspect
  secure_dir "$CACHE_DIR"
  # For opkg-consistent rollback, a separately verified exact PREVIOUS IPK is mandatory.
  old_prefix="${pkg}_${current}"
  found=0
  for candidate in "$CACHE_DIR/$old_prefix"_aarch64-3.10.ipk "$CACHE_DIR/${pkg}_$(printf '%s' "$current" | sed 's/~rc\./.rc./')_aarch64-3.10.ipk"; do
    [ -f "$candidate" ] || continue
    [ ! -L "$candidate" ] || fail "Unsafe cached symlink: $candidate"
    [ -f "$candidate.sha256" ] || fail "Cached previous IPK lacks checksum: $candidate"
    old_hash="$(cat "$candidate.sha256")"
    printf '%s\n' "$old_hash" | grep -Eq '^[0-9a-f]{64}$' || fail 'Invalid cached SHA-256'
    verify_hash "$candidate" "$old_hash"
    found=1
    break
  done
  [ "$found" = 1 ] ||
    fail "No verified previous IPK for $current in $CACHE_DIR; do not risk in-place upgrade"
  log "Prepared new $pkg: $current -> $version"
  log "Verified previous IPK: $candidate"
  log "Verified new IPK: $file"
  log 'STAGED ONLY. No opkg install, service restart or configuration change.'
  log 'To update production, first make an offline config/state backup,'
  log 'review upstream compatibility, then use the documented manual procedure.'
}
clean_install() {
  current="$(installed_version "$pkg")"
  [ -z "$current" ] || fail "Already managed by opkg ($pkg $current). Use upgrade staging."
  [ ! -e "$binary" ] && [ ! -L "$binary" ] ||
    fail "Binary exists without matching opkg ownership: $binary"
  download
  inspect
  log "Clean binary-only package: $pkg $version"
  log 'No users/config/init scripts are provided; no service will start.'
  if [ "${2:-}" = '--apply' ]; then
    check_root
    [ ! -e "$binary" ] && [ -z "$(installed_version "$pkg")" ] ||
      fail 'The installation state changed during preflight'
    opkg install "$file" || fail 'opkg install failed; inspect its state before retry'
    [ "$(installed_version "$pkg")" = "$version" ] ||
      fail 'opkg installed version does not match verified IPK'
    [ -x "$binary" ] || fail "Installed binary missing after opkg: $binary"
    log "PASS: package installed ($pkg $version). Service NOT configured or started."
  else
    log "DRY RUN: use 'sh install.sh $1 --apply' to install this single package."
  fi
}
main() {
  cmd="${1:-help}"
  case "$cmd" in
    -h|--help|help) usage; return ;;
    status)
      [ "$#" -eq 1 ] || fail 'status takes no arguments'
      platform
      for p in telemt telemt-panel-lite; do
        v="$(installed_version "$p")"
        log "$p: ${v:-not installed}"
      done
      return ;;
  esac
  [ "$#" -ge 2 ] && [ "$#" -le 3 ] || fail 'Expected command and family (core|panel)'
  setup
  asset "$2"
  case "$cmd" in
    check)
      [ "$#" -eq 2 ] || fail 'check takes one package family'
      log "$pkg: installed=$(installed_version "$pkg") GitHub=$version" ;;
    fetch)
      [ "$#" -eq 2 ] || fail 'fetch takes one package family'
      download; inspect ;;
    inspect)
      [ "$#" -eq 2 ] || fail 'inspect takes one package family'
      verify_hash "$file" "$hash"; inspect ;;
    cache)
      [ "$#" -eq 2 ] || fail 'cache takes one package family'
      cache_current ;;
    stage)
      [ "$#" -eq 2 ] || fail 'stage takes one package family'
      stage_upgrade ;;
    install)
      [ "$#" -eq 2 ] || [ "${3:-}" = '--apply' ] || fail 'Only --apply is accepted'
      clean_install "$2" "${3:-}" ;;
    *) fail "Unknown command: $cmd" ;;
  esac
}
main "$@"
