#!/bin/sh
# Opt-in KN-1010: convert an installed synthetic TeleMT IPC pilot into a
# functional secure MTProxy profile, preserving its rollback path.
# Research-only until physical client and boot acceptance are recorded.
set -eu
umask 077
KIT=/opt/etc/telemt-ipc-pilot
SERVICE=$KIT/service.sh
CFG=/opt/etc/telemt-ipc-kn1010-socks5.toml
BACKUP=$KIT/previous-synthetic-telemt.toml
LINK=$KIT/private-telegram-link.txt
ADMIN=$KIT/private-new-panel-password.txt
PCONF=$KIT/panel.toml
PANEL=/opt/bin/telemt-panel
BB=/opt/bin/busybox
fail() { echo "LIVE_SETUP_FAIL: $*" >&2; exit 1; }
[ "$#" -eq 5 ] || fail "Usage: sh script BIND_IP PORT SOCKS5_IP:PORT PUBLIC_HOST USERNAME"
BIND_IP=$1
PORT=$2
UPSTREAM=$3
PUBLIC_HOST=$4
USERNAME=$5
case "$BIND_IP" in ''|*[!0-9.]* ) fail "BIND_IP must be numeric IPv4";; esac
case "$PORT" in ''|*[!0-9]* ) fail "PORT must be decimal";; esac
[ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ] || fail "PORT out of range"
case "$UPSTREAM" in ''|*[!0-9.:]* ) fail "SOCKS5 endpoint must be IPv4:PORT";; esac
case "$UPSTREAM" in *:*) :;; *) fail "SOCKS5 missing port";; esac
case "$PUBLIC_HOST" in ''|*[!A-Za-z0-9.-]* ) fail "PUBLIC_HOST contains unsafe characters";; esac
case "$USERNAME" in ''|*[!A-Za-z0-9_-]* ) fail "USERNAME contains unsafe characters";; esac
[ -x "$SERVICE" ] || fail "managed service kit not installed"
[ -f "$CFG" ] && [ ! -L "$CFG" ] || fail "existing Core config absent or symlink"
[ -f "$KIT/panel.toml" ] || fail "managed Panel config absent"
[ ! -e "$BACKUP" ] && [ ! -L "$BACKUP" ] || fail "backup exists: run only once"
[ ! -e "$LINK" ] && [ ! -L "$LINK" ] || fail "link file already exists"
[ ! -e "$ADMIN" ] && [ ! -L "$ADMIN" ] || fail "admin file already exists"
"$BB" grep -q 'lab = "00000000000000000000000000000000"' "$CFG" ||
  fail "not the expected synthetic lab profile, refuse to overwrite"
[ "$BIND_IP" = 0.0.0.0 ] ||
  ip -4 addr show | "$BB" grep -Fq "inet $BIND_IP/" ||
  fail "bind address not configured on this router"
HEX=$("$BB" head -c 16 /dev/urandom | "$BB" hexdump -v -e '1/1 "%02x"')
[ "$(printf '%s' "$HEX" | "$BB" wc -c)" -eq 32 ] ||
  fail "could not generate 128-bit random secret"
printf '%s\n' "$HEX" | "$BB" grep -Eq '^[0-9a-f]{32}$' ||
  fail "generated invalid hex secret"
TMP=$CFG.new.$$
trap 'rm -f "$TMP"' 0
trap 'exit 2' 1 2 3 15
cat > "$TMP" <<TOML
[general]
use_middle_proxy = false
log_level = "normal"
quota_state_path = "/opt/etc/telemt-ipc-kn1010.limit.json"

[general.modes]
classic = false
secure = true
tls = false

[server]
port = $PORT
max_connections = 256

[[server.listeners]]
ip = "$BIND_IP"

[server.api]
enabled = true
listen = "127.0.0.1:19091"
whitelist = ["127.0.0.1/32"]

[access.users]
$USERNAME = "$HEX"

[censorship]
mask = false

[[upstreams]]
type = "socks5"
address = "$UPSTREAM"
weight = 1
enabled = true
ipv4 = true
ipv6 = false
TOML
chmod 600 "$TMP"
cp -p "$CFG" "$BACKUP"
mv "$TMP" "$CFG"
echo "LIVE_SETUP: real secure user created; restarting only experimental IPC Core"
if "$SERVICE" core-restart; then
  printf 'tg://proxy?server=%s&port=%s&secret=dd%s\n' \
    "$PUBLIC_HOST" "$PORT" "$HEX" > "$LINK"
  chmod 600 "$LINK"
  # The previous panel password was pasted into chat. Rotate it immediately,
  # store the new value in an owner-only one-time handoff file.
  PW=$("$BB" head -c 24 /dev/urandom | "$BB" base64 | "$BB" tr -d '\n')
  PHASH=$(printf '%s\n' "$PW" | "$PANEL" hash-password)
  [ -n "$PHASH" ] || fail "live Core ready, Panel password hash failed"
  printf '%s\n' "$PW" > "$ADMIN"
  chmod 600 "$ADMIN"
  "$BB" sed -i "s|^password_hash = .*|password_hash = \"$PHASH\"|" "$PCONF"
  chmod 600 "$PCONF"
  "$SERVICE" panel-restart || fail "live Core ready; Panel restart requires diagnosis"
  echo "PANEL_PASSWORD_ROTATED"
  echo "PRIVATE_PANEL_PASSWORD_FILE=$ADMIN"
  echo "LIVE_CORE_READY"
  echo "PRIVATE_LINK_FILE=$LINK"
  echo "Read link LOCALLY, do not paste into chats/logs."
  if [ "$BIND_IP" = 0.0.0.0 ]; then
    echo "NOTICE: proxy listens on all IPv4 interfaces; protect the API/Panel separately"
  fi
  echo "NOTICE: a private WAN address needs upstream port forwarding or VPS relay for mobile Internet clients"
  exit 0
fi
echo "LIVE_SETUP: Core restart failed, restoring prior synthetic config" >&2
cp -p "$BACKUP" "$CFG"
if "$SERVICE" core-start; then
  echo "ROLLBACK_CORE_READY" >&2
else
  echo "ROLLBACK_REQUIRES_MANUAL_DIAGNOSIS" >&2
fi
exit 1
