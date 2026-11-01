#!/bin/sh
# SPDX-License-Identifier: MIT
# Update only the installed WARPSCOUT Entware package from the verified GitHub release.
set -eu

REPO='saymer-alt/entware-go'
API="https://api.github.com/repos/${REPO}/releases/tags/latest"
PREFIX="https://github.com/${REPO}/releases/download/latest/"

say() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

for tool in curl opkg awk sed grep sha256sum mktemp jq; do
    command -v "$tool" >/dev/null 2>&1 || die "missing required tool: $tool"
done

[ "$(uname -m)" = aarch64 ] || die 'only aarch64 routers are supported'
opkg print-architecture | grep -Eq '^arch aarch64-3\.10(_kn)?[[:space:]]' || die 'unsupported Entware architecture'
[ -d /opt ] || die '/opt is not available'

installed="$(opkg status warpscout | awk '$1 == "Version:" { print $2; exit }')"
[ -n "$installed" ] || die 'WARPSCOUT is not installed; use warpscout/install.sh first'
opkg compare-versions 1 '=' 1 >/dev/null 2>&1 || die 'opkg compare-versions is unavailable'

stage=''
cleanup() {
    if [ -n "$stage" ] && [ -d "$stage" ]; then rm -rf -- "$stage"; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

stage="$(umask 077; mktemp -d "${TMPDIR:-/tmp}/warpscout-update.XXXXXX")" || die 'cannot make private temporary directory'
chmod 700 "$stage" || die 'cannot secure temporary directory'

say "==> WARPSCOUT installed: $installed"
curl -fSsL --retry 3 --connect-timeout 15 -o "$stage/release.json" "$API" || die 'cannot read GitHub release metadata'

# GitHub release API uses quoted JSON fields; collect values from the *same*
# WARPSCOUT asset. Reject zero/multiple assets or incomplete metadata.
# Parse JSON structurally. GitHub REST normally returns compact one-line JSON;
# parsing it with awk/grep silently fails despite pretty-printed test fixtures.
jq -er '
    [ .assets[] | select(.name | type == "string" and test("^warpscout_[0-9]+[.][0-9]+[.][0-9]+-[0-9]+_aarch64-3[.]10[.]ipk$")) ] as $items
    | if ($items | length) != 1 then
          error("expected exactly one ARM64 WARPSCOUT IPK")
      else
          $items[0]
      end
    | .name, .digest, .browser_download_url
' "$stage/release.json" > "$stage/asset.fields" || die 'missing, ambiguous, or malformed WARPSCOUT GitHub release asset'

name="$(sed -n '1p' "$stage/asset.fields")"
digest="$(sed -n '2p' "$stage/asset.fields")"
url="$(sed -n '3p' "$stage/asset.fields")"

printf '%s\n' "$name" | grep -Eq '^warpscout_[0-9]+\.[0-9]+\.[0-9]+-[0-9]+_aarch64-3\.10\.ipk$' || die 'unexpected WARPSCOUT asset name'
printf '%s\n' "$digest" | grep -Eq '^sha256:[0-9a-f]{64}$' || die 'missing or invalid GitHub SHA-256 digest'
[ "$url" = "${PREFIX}${name}" ] || die 'unexpected WARPSCOUT asset download URL'

candidate="${name#warpscout_}"
candidate="${candidate%_aarch64-3.10.ipk}"
if opkg compare-versions "$installed" '=' "$candidate"; then
    say "==> Already up to date: $candidate"
    exit 0
fi
if opkg compare-versions "$installed" '>' "$candidate"; then
    say "==> Installed version $installed is newer than GitHub $candidate; no downgrade"
    exit 0
fi
opkg compare-versions "$installed" '<' "$candidate" || die 'cannot compare WARPSCOUT versions'

say "==> Updating WARPSCOUT $installed -> $candidate"
file="$stage/$name"
curl -fSsL --retry 3 --connect-timeout 15 -o "$file" "$url" || die 'cannot download WARPSCOUT IPK'
actual="$(sha256sum "$file" | awk '{ print $1 }')"
[ "$actual" = "${digest#sha256:}" ] || die 'WARPSCOUT IPK SHA-256 mismatch; existing package was not modified'

opkg install "$file" || die 'opkg installation failed'
after="$(opkg status warpscout | awk '$1 == "Version:" { print $2; exit }')"
[ "$after" = "$candidate" ] || die "installed package version does not match expected $candidate (got ${after:-missing})"
[ -x /opt/bin/warpscout ] || die 'WARPSCOUT executable missing after upgrade'
say "==> Update complete: $(/opt/bin/warpscout version)"
say '==> Existing /opt/etc/warpscout state was not modified by the updater'
