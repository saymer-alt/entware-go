#!/bin/sh
set -eu

REPO="saymer-alt/entware-go"
RELEASE_TAG="latest"
STATE_DIR="/opt/etc/warpscout"
BIN="/opt/bin/warpscout"
ACCOUNT_FILE="${STATE_DIR}/warpscout-account.json"

say() {
    printf '%s\n' "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

cleanup_file=""
cleanup() {
    if [ -n "${cleanup_file}" ] && [ -f "${cleanup_file}" ]; then
        rm -f "${cleanup_file}"
    fi
}
trap cleanup EXIT INT TERM HUP

command -v opkg >/dev/null 2>&1 || die "opkg not found; Entware is required"
command -v curl >/dev/null 2>&1 || die "curl not found; install it first: opkg update && opkg install curl ca-bundle"

arch="$(uname -m 2>/dev/null || true)"
[ "${arch}" = "aarch64" ] || die "unsupported CPU architecture: ${arch:-unknown}; WARPSCOUT package is aarch64-only"

if ! opkg print-architecture 2>/dev/null | grep -Eq '^arch aarch64-3\.10(_kn)?[[:space:]]'; then
    die "Entware aarch64-3.10 architecture was not found"
fi

[ -d /opt ] || die "/opt is not available"
mkdir -p "${STATE_DIR}"
chmod 700 "${STATE_DIR}"

say "==> Installing WARPSCOUT for ARM64 Entware"

if opkg update && opkg install warpscout; then
    say "==> Installed/updated WARPSCOUT from Entware feed"
else
    say "==> WARPSCOUT is not available from the configured feed yet; falling back to GitHub latest release"

    api="https://api.github.com/repos/${REPO}/releases/tags/${RELEASE_TAG}"
    asset_url="$(
        curl -fSsL "${api}" |
        grep -o 'https://[^"]*warpscout_[^"]*_aarch64-3\.10\.ipk' |
        head -n 1 || true
    )"

    [ -n "${asset_url}" ] || die "could not resolve the latest WARPSCOUT aarch64 IPK from GitHub release ${RELEASE_TAG}"

    cleanup_file="/tmp/$(basename "${asset_url}")"
    say "==> Downloading $(basename "${cleanup_file}")"
    curl -fSL --retry 3 --connect-timeout 15 -o "${cleanup_file}" "${asset_url}"

    say "==> Installing ${cleanup_file}"
    opkg install "${cleanup_file}"
fi

[ -x "${BIN}" ] || die "WARPSCOUT binary was not installed at ${BIN}"

version="$("${BIN}" version 2>/dev/null || true)"
[ -n "${version}" ] || die "WARPSCOUT was installed but version check failed"
say "==> WARPSCOUT ${version} is ready"

if [ -s "${ACCOUNT_FILE}" ]; then
    chmod 600 "${ACCOUNT_FILE}" 2>/dev/null || true
    say "==> Existing WARP account found; registration skipped"
else
    say "==> Registering a fresh WARP account"
    if (
        umask 077
        cd "${STATE_DIR}"
        "${BIN}" register
    ); then
        [ -f "${ACCOUNT_FILE}" ] && chmod 600 "${ACCOUNT_FILE}" 2>/dev/null || true
        say "==> WARP account registered"
    else
        die "WARPSCOUT is installed, but WARP account registration failed; retry with: cd ${STATE_DIR} && warpscout register"
    fi
fi

say ""
say "WARPSCOUT installation complete."
say "State directory: ${STATE_DIR}"
say "Account file: ${ACCOUNT_FILE} (keep it private)"
say ""
say "Run scans from the state directory:"
say "  cd ${STATE_DIR}"
say "  warpscout scan -p wg -P -jt 4"
say "  warpscout scan -p awg -P -jt 4 -gen-i1 quic"
say "  warpscout scan -p masque -P -jt 4 -masque-sni 4pda.to"
say "  warpscout scan -p masque-h2 -P -jt 4 -masque-sni 4pda.to"
say ""
say "On a tested KN-1812 with 1 GB RAM, -jt 16 also ran comfortably."
