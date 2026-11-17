#!/bin/sh
# Clean ARM64 Entware TeleMT / Panel Lite package installation only.
# No default configuration, secrets, init scripts or autostart.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec /bin/sh "$here/entware-manager.sh" install "$@"
