#!/bin/sh
# TeleMT MIPSel 3.5.17 IPC + Panel Lite RC4: owner-opt-in beta installer.
# Installer consumes two *local*, SHA256-pinned research IPKs. Not a release feed.
set -eu
umask 077
R=/opt/etc/telemt-mipsel
BB=/opt/bin/busybox
CORE_BIN=/opt/bin/telemt-ipc-lab
PANEL_BIN=/opt/bin/telemt-panel
CORE_HASH=a83caf105dd77248de43c9e096f8248ce3851b322dfe6dd59a934801344d9506
PANEL_HASH=380cb5112b58538eafec9ae9fab27fb22c994fd36ce3130c541c5e11b29a40c8
CORE_IPK_HASH=fbf5ef4c2cad4a564483c29a584986623181574b798ec5b787cdc93c27e15daa
PANEL_IPK_HASH=0236dfb076b14b129a6392de49f287838a11aebe7681e092084d4ce87e771e68
SERVICE=/opt/etc/telemt-mipsel/service.sh
ICORE=/opt/etc/init.d/S98telemt-mipsel
IPANEL=/opt/etc/init.d/S99telemt-mipsel-panel
fail() { echo "MIPSEL_INSTALL_FAILED: $*" >&2; exit 1; }
ok() { echo "MIPSEL_INSTALL: $*"; }
hashmatch() {
  [ -f "$1" ] && [ ! -L "$1" ] || return 1
  h=$(sha256sum "$1" | "$BB" awk '{print $1}')
  [ "$h" = "$2" ]
}
available() {
  netstat -lnt 2>/dev/null | "$BB" grep -Eq ":$1[[:space:]]" && return 1
  return 0
}
ipcheck() {
  case "$1" in ''|*[!0-9.]*) return 1;; esac
  [ "$1" = 0.0.0.0 ] || [ "$1" = 127.0.0.1 ] ||
    ip -4 addr show | "$BB" grep -Fq "inet $1/"
}
[ "$#" -eq 5 ] || fail "Usage: sh install.sh CORE.ipk PANEL.ipk SOCKS5_IP:PORT PUBLIC_HOST PANEL_BIND_IP"
IPK1=$1
IPK2=$2
SOCKS=$3
PUBLIC_HOST=$4
PANEL_BIND=$5
PROXY_PORT=13443
PANEL_PORT=18082
[ "$(id -u)" = 0 ] || fail "run as Entware root"
[ -x /opt/bin/opkg ] && [ -x "$BB" ] || fail "Entware opkg/BusyBox missing"
/opt/bin/opkg print-architecture | "$BB" grep -q 'mipsel-3.4' ||
  fail "not Entware mipsel-3.4"
[ -d /proc ] && [ -d /opt/var ] || fail "/proc or /opt/var missing"
[ -d "$R" ] || [ ! -e "$R" ] || fail "install root is not a directory"
[ ! -L "$R" ] && [ ! -e "$R" ] || fail "existing install / symlink: no overwrite"
[ ! -e "$CORE_BIN" ] && [ ! -L "$CORE_BIN" ] ||
  fail "Core executable already exists; abort to avoid overwriting"
[ ! -e "$PANEL_BIN" ] && [ ! -L "$PANEL_BIN" ] ||
  fail "Panel executable already exists; abort to avoid overwriting"
[ ! -e "$ICORE" ] && [ ! -L "$ICORE" ] &&
  [ ! -e "$IPANEL" ] && [ ! -L "$IPANEL" ] ||
  fail "init script name already exists"
ipcheck "$PANEL_BIND" || fail "Panel bind IP is not assigned or invalid"
case "$SOCKS" in ''|*[!0-9.:]* ) fail "SOCKS5 must be an IPv4:PORT address";; esac
printf '%s\n' "$SOCKS" | "$BB" grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{1,5}$' ||
  fail "invalid SOCKS5 endpoint syntax"
case "$PUBLIC_HOST" in ''|*[!A-Za-z0-9.-]*) fail "invalid public/LAN host";; esac
[ "$PUBLIC_HOST" != "." ] || fail "invalid host"
[ "$PROXY_PORT" != "$PANEL_PORT" ] || fail "port collision"
available "$PROXY_PORT" || fail "MTProxy TCP port already used"
available "$PANEL_PORT" || fail "Panel TCP port already used"
available 19091 || fail "Core API port already used"

hashmatch "$IPK1" "$CORE_IPK_HASH" || fail "Core IPK SHA256 mismatch"
hashmatch "$IPK2" "$PANEL_IPK_HASH" || fail "Panel IPK SHA256 mismatch"
D=$("$BB" dirname "$0")
[ -f "$D/telemt-mipsel-service.sh" ] && [ ! -L "$D/telemt-mipsel-service.sh" ] ||
  fail "missing telemt-mipsel-service.sh alongside installer"

HEX=$("$BB" head -c 16 /dev/urandom | "$BB" hexdump -v -e '1/1 "%02x"')
PW=$("$BB" head -c 24 /dev/urandom | "$BB" base64 | "$BB" tr -d '\n')
[ "$(printf '%s' "$HEX" | "$BB" wc -c)" -eq 32 ] || fail "secret RNG failed"
[ -n "$PW" ] || fail "password RNG failed"

# Packages are explicitly pinned and never installed via opkg upgrade/feed.
# A fresh router is required to prevent overwriting an existing Panel install.
ok "installing verified local IPKs (no opkg update)"
/opt/bin/opkg install "$IPK1" || fail "Core package install failed"
/opt/bin/opkg install "$IPK2" || fail "Panel package install failed"
hashmatch "$CORE_BIN" "$CORE_HASH" || fail "installed Core ELF differs from pin"
hashmatch "$PANEL_BIN" "$PANEL_HASH" || fail "installed Panel ELF differs from pin"

HASH=$(printf '%s\n' "$PW" | "$PANEL_BIN" hash-password)
[ -n "$HASH" ] || fail "bcrypt password generation failed"
mkdir -p "$R" "$R/ctl" /opt/var/log /opt/var/run
chmod 700 "$R" "$R/ctl"
cp "$D/telemt-mipsel-service.sh" "$SERVICE"
chmod 700 "$SERVICE"
cat > "$R/core.toml" <<TOML
[general]
use_middle_proxy = false
log_level = "normal"
quota_state_path = "$R/quotas.json"

[general.modes]
classic = false
secure = true
tls = false

[server]
port = $PROXY_PORT
max_connections = 256

[[server.listeners]]
ip = "0.0.0.0"

[server.api]
enabled = true
listen = "127.0.0.1:19091"
whitelist = ["127.0.0.1/32"]

[access.users]
home = "$HEX"

[censorship]
mask = false

[[upstreams]]
type = "socks5"
address = "$SOCKS"
weight = 1
enabled = true
ipv4 = true
ipv6 = false
TOML
cat > "$R/panel.toml" <<TOML
listen = "$PANEL_BIND:$PANEL_PORT"
data_dir = "/opt/var/lib/telemt-mipsel-panel"

[tls]
mode = "http"

[telemt]
url = "http://127.0.0.1:19091"
auth_header = ""

[auth]
username = "admin"
password_hash = "$HASH"

[store]
driver = "memory"

[privileges]
mode = "direct"

[host]
service_manager = "custom"
log_source = "file"
log_file = "/opt/var/log/telemt-mipsel-core.log"

[host.commands.telemt]
start = ["$SERVICE", "core-start"]
stop = ["$SERVICE", "core-stop"]
restart = ["$SERVICE", "core-restart"]

[host.commands.panel]
restart = ["$SERVICE", "panel-restart"]

[updates]
telemt_binary_path = "$CORE_BIN"
panel_binary_path = "$PANEL_BIN"
TOML
printf 'tg://proxy?server=%s&port=%s&secret=dd%s\n' \
  "$PUBLIC_HOST" "$PROXY_PORT" "$HEX" > "$R/private-telegram-link.txt"
printf '%s\n' "$PW" > "$R/private-panel-password.txt"
chmod 600 "$R/core.toml" "$R/panel.toml" \
  "$R/private-telegram-link.txt" "$R/private-panel-password.txt"
mkdir -p /opt/var/lib/telemt-mipsel-panel
chmod 700 /opt/var/lib/telemt-mipsel-panel

ok "config created; starting both services"
"$SERVICE" start || fail "start failed; files retained for diagnosis; boot not enabled"
ok "STATUS_BEGIN"
"$SERVICE" status
ok "STATUS_END"

if [ "$PANEL_BIND" != 127.0.0.1 ]; then
  ok "WARNING: Panel HTTP on $PANEL_BIND accessible to any permitted LAN/VPN clients; never port-forward"
fi
ok "NOTICE: MTProxy on 0.0.0.0:$PROXY_PORT. WAN ingress requires router firewall/NAT setup."
ok "PRIVATE_LINK_FILE=$R/private-telegram-link.txt"
ok "PRIVATE_PANEL_PASSWORD_FILE=$R/private-panel-password.txt"
ok "DO NOT SEND CREDENTIALS TO CHATS OR LOGS"
ok "After client test, enable autostart: $SERVICE enable-boot"
ok "Generic upstream updater is NOT qualified for these patched experimental binaries"
