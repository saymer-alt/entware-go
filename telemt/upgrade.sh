#!/bin/sh
# Safe update staging for already installed TeleMT / Panel Lite packages.
# Does NOT run opkg install, change configuration or restart services.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "${1:-}" in
  core|panel) : ;;
  *) echo "Usage: sh upgrade.sh core|panel (prepare only)" >&2; exit 2 ;;
esac
[ "$#" -eq 1 ] || { echo 'No --apply option: upgrades are staged, not installed' >&2; exit 2; }
exec /bin/sh "$here/entware-manager.sh" stage "$1"
