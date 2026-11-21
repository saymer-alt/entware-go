#!/bin/sh
# Foreground process only. No SSH, package manager, TUN/NAT/firewall/sysctl.
set -f
umask 077
case ${1-} in
    --plan)
        printf '%s\n' WDTT_RELAY_PLAN_V1 \
          'host=owner-approved-disposable-VM-only' \
          'identity=unprivileged-user' \
          'endpoint=pre-provisioned-loopback-WireGuard' \
          'secrets=private-config-file-only' \
          'API=disabled Telegram=disabled autostart=disabled' \
          'teardown=SIGTERM-own-foreground-process-no-interface-or-rule-deletion'
        exit 0;;
    --confirm-disposable-vm) [ "$#" -eq 4 ] || exit 78; shift;;
    *) printf '%s\n' WDTT_RELAY_EXPLICIT_DISPOSABLE_VM_REQUIRED >&2; exit 78;;
esac
[ "$(id -u)" != 0 ] || { printf '%s\n' WDTT_RELAY_NONROOT_REQUIRED >&2; exit 78; }
binary=$1; expected=$2; config=$3
case $binary:$config in /*:/*) ;; *) exit 78;; esac
case $expected in ''|*[!0-9a-f]*) exit 78;; esac
[ "${#expected}" -eq 64 ] && [ -f "$binary" ] && [ ! -L "$binary" ] || exit 78
[ "$(sha256sum "$binary" | awk '{print $1}')" = "$expected" ] || exit 78
ulimit -c 0 || exit 78
ulimit -n 256 || exit 78
# The binary verifies private files, caps lifetime at30min and handles SIGTERM.
# It creates no runtime files. Keep configs on a private volatile filesystem.
exec "$binary" -config-file "$config"
