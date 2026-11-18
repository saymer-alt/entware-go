#!/bin/sh
# Research beta: isolated TeleMT IPC and Panel Lite MIPSel service kit.
# Only the KN-1010 lab instance. Never replaces normal TeleMT or S99telemt.
set -eu
ROOT=/opt/etc/telemt-ipc-pilot
SELF=$ROOT/service.sh
CORE=/opt/bin/telemt-ipc-lab
PANEL=/opt/bin/telemt-panel
CONF=/opt/etc/telemt-ipc-kn1010-socks5.toml
CPID=/opt/var/run/telemt-ipc-kn1010.pid
SDIR=/opt/var/run/telemt-ipc-kn1010
SOCK=$SDIR/ctl.sock
CLOG=/opt/var/log/telemt-ipc-kn1010.log
PCONF=$ROOT/panel.toml
PPID=/opt/var/run/telemt-panel-ipc-pilot.pid
PLOG=/opt/var/log/telemt-panel-ipc-pilot.log
ICORE=/opt/etc/init.d/S98telemt-ipc-pilot
IPANEL=/opt/etc/init.d/S99telemt-panel-ipc-pilot
BB=/opt/bin/busybox
die() { echo "FAIL: $*" >&2; exit 1; }
msg() { echo "PILOT: $*"; }
pid_read() { [ -r "$1" ] && cat "$1" || :; }
valid_pid() { case "$1" in ''|*[!0-9]*) return 1;; *) [ "$1" -gt 1 ];; esac; }
exe() { [ -r "/proc/$1/exe" ] && readlink "/proc/$1/exe" 2>/dev/null || :; }
core_live() {
  p=$(pid_read "$CPID")
  valid_pid "$p" && [ "$(exe "$p")" = "$CORE" ]
}
panel_live() {
  p=$(pid_read "$PPID")
  valid_pid "$p" && [ "$(exe "$p")" = "$PANEL" ] &&
  "$BB" tr '\000' '\n' < "/proc/$p/cmdline" |
    "$BB" grep -Fxq "$PCONF"
}
port_busy() { netstat -lnt 2>/dev/null | "$BB" grep -Eq ':18082[[:space:]]'; }
core_start() {
  [ -f "$CONF" ] || die "Core lab SOCKS5 config missing"
  [ ! -L "$SDIR" ] || die "socket directory is a symlink"
  mkdir -p "$SDIR" /opt/var/log
  chmod 700 "$SDIR"
  if core_live; then
    [ -S "$SOCK" ] || die "running Core without control socket"
    msg "CORE_READY (already running)"; return 0
  fi
  [ ! -e "$CPID" ] && [ ! -e "$SOCK" ] ||
    die "stale Core PID/socket: diagnose manually, no unsafe cleanup"
  HOME=/opt TMPDIR=/opt/tmp "$CORE" start --log-file "$CLOG" \
    --pid-file "$CPID" --control-socket "$SOCK" "$CONF"
  n=0
  while [ "$n" -lt 90 ]; do
    if core_live && [ -S "$SOCK" ]; then msg CORE_READY; return 0; fi
    sleep 1; n=$((n+1))
  done
  die "Core not ready after 90 seconds; inspect Core log"
}
core_stop() {
  if ! core_live; then
    [ ! -e "$SOCK" ] || die "unknown owner of existing IPC socket"
    msg "CORE_STOPPED (already stopped)"; return 0
  fi
  [ -S "$SOCK" ] || die "Core alive but IPC socket missing"
  old=$(pid_read "$CPID")
  HOME=/opt "$CORE" stop --control-socket "$SOCK"
  n=0
  while [ "$n" -lt 30 ]; do
    if [ "$(exe "$old")" != "$CORE" ] && [ ! -e "$SOCK" ]; then
      msg CORE_STOPPED; return 0
    fi
    sleep 1; n=$((n+1))
  done
  die "Core shutdown not confirmed; not signalling numeric PID"
}
panel_start() {
  [ -f "$PCONF" ] || die "managed Panel config missing"
  if panel_live; then msg "PANEL_READY (already running)"; return 0; fi
  [ ! -e "$PPID" ] || die "stale Panel PID; refusing overwrite"
  port_busy && die "port 18082 occupied; stop foreground Panel first"
  mkdir -p /opt/var/log
  HOME=/opt TMPDIR=/opt/tmp "$PANEL" -config "$PCONF" \
    </dev/null >>"$PLOG" 2>&1 &
  id=$!
  printf '%s\n' "$id" > "$PPID"
  n=0
  while [ "$n" -lt 15 ]; do
    if panel_live && port_busy; then msg "PANEL_READY pid=$id"; return 0; fi
    sleep 1; n=$((n+1))
  done
  die "Panel not ready; inspect Panel log"
}
panel_stop() {
  if [ ! -e "$PPID" ]; then msg "PANEL_STOPPED (already stopped)"; return 0; fi
  panel_live || die "Panel identity mismatch; refusing signal"
  old=$(pid_read "$PPID")
  # Unlike Core this process has no IPC stop: verify exe and exact config.
  kill -TERM "$old" || die "Panel signal failed"
  n=0
  while [ "$n" -lt 15 ]; do
    if [ "$(exe "$old")" != "$PANEL" ]; then
      rm -f "$PPID"
      msg PANEL_STOPPED; return 0
    fi
    sleep 1; n=$((n+1))
  done
  die "Panel did not terminate; no SIGKILL fallback"
}
install() {
  [ "$(id -u)" = 0 ] || die "requires Entware root"
  /opt/bin/opkg print-architecture | "$BB" grep -q 'mipsel-3.4' ||
    die "incompatible architecture"
  [ -f "$CONF" ] && [ -f /opt/etc/telemt-ipc-kn1010.secret ] ||
    die "lab Core SOCKS5 config/secret absent"
  [ -x "$CORE" ] && [ -x "$PANEL" ] || die "lab IPKs not installed"
  [ "$(sha256sum "$CORE" | "$BB" awk '{print $1}')" = \
    a83caf105dd77248de43c9e096f8248ce3851b322dfe6dd59a934801344d9506 ] ||
    die "Core SHA256 mismatch"
  [ "$(sha256sum "$PANEL" | "$BB" awk '{print $1}')" = \
    380cb5112b58538eafec9ae9fab27fb22c994fd36ce3130c541c5e11b29a40c8 ] ||
    die "Panel SHA256 mismatch"
  [ ! -e "$PCONF" ] && [ ! -e "$SELF" ] && [ ! -L "$ROOT" ] ||
    die "managed installation already exists, no overwrite"
  [ -f "$0" ] || die "installer must be a file"
  port_busy && die "port 18082 occupied, stop Panel first"
  bind_ip=127.0.0.1
  if [ "$#" -gt 0 ]; then bind_ip=$1; fi
  case "$bind_ip" in *[!0-9.]*|'') die "invalid numeric IPv4";; esac
  if [ "$bind_ip" != 127.0.0.1 ]; then
    ip -4 addr show | "$BB" grep -Fq "inet $bind_ip/" ||
      die "bind IP is not configured on router"
    msg "WARNING: HTTP on $bind_ip may be accessible via LAN, not just SSTP"
  fi
  umask 077
  pass=$("$BB" head -c 24 /dev/urandom | "$BB" base64 | "$BB" tr -d '\n')
  hash=$(printf '%s\n' "$pass" | "$PANEL" hash-password)
  [ -n "$hash" ] || die "password hash failed"
  mkdir -p "$ROOT" /opt/var/lib/telemt-panel-ipc-kn1010
  chmod 700 "$ROOT"
  cp "$0" "$SELF"
  chmod 700 "$SELF"
  cat > "$PCONF" <<TOML
listen = "$bind_ip:18082"
data_dir = "/opt/var/lib/telemt-panel-ipc-kn1010"
[tls]
mode = "http"
[telemt]
url = "http://127.0.0.1:19091"
auth_header = ""
[auth]
username = "labadmin"
password_hash = "$hash"
[store]
driver = "memory"
[privileges]
mode = "direct"
[host]
service_manager = "custom"
log_source = "file"
log_file = "$CLOG"
[host.commands.telemt]
start = ["$SELF", "core-start"]
stop = ["$SELF", "core-stop"]
restart = ["$SELF", "core-restart"]
[host.commands.panel]
restart = ["$SELF", "panel-restart"]
TOML
  chmod 600 "$PCONF"
  msg "INSTALLED (no autostart)"
  msg "LOGIN=labadmin"
  msg "NEW_PASSWORD=$pass"
  msg "Save password locally, DO NOT send it to chat."
  msg "Next: $SELF start"
}
enable_autostart() {
  [ -x "$SELF" ] && [ -f "$PCONF" ] || die "install first"
  [ ! -e "$ICORE" ] && [ ! -e "$IPANEL" ] ||
    die "init conflict; refusing overwrite"
  mkdir -p /opt/etc/init.d
  cat > "$ICORE" <<'INIT'
#!/bin/sh
# managed-by: telemt-ipc-pilot beta
case "$1" in
 start) exec /opt/etc/telemt-ipc-pilot/service.sh core-start;;
 stop) exec /opt/etc/telemt-ipc-pilot/service.sh core-stop;;
 restart) exec /opt/etc/telemt-ipc-pilot/service.sh core-restart;;
 *) exit 2;;
esac
INIT
  cat > "$IPANEL" <<'INIT'
#!/bin/sh
# managed-by: telemt-ipc-pilot beta
case "$1" in
 start) exec /opt/etc/telemt-ipc-pilot/service.sh panel-start;;
 stop) exec /opt/etc/telemt-ipc-pilot/service.sh panel-stop;;
 restart) exec /opt/etc/telemt-ipc-pilot/service.sh panel-restart;;
 *) exit 2;;
esac
INIT
  chmod 700 "$ICORE" "$IPANEL"
  msg "AUTOSTART_ENABLED (requires working rc.unslung boot hook)"
}
disable_autostart() {
  for f in "$ICORE" "$IPANEL"; do
    if [ -e "$f" ]; then
      [ ! -L "$f" ] && "$BB" grep -q '^# managed-by: telemt-ipc-pilot beta$' "$f" ||
        die "foreign init script; refusing to remove"
      rm -f "$f"
    fi
  done
  msg AUTOSTART_DISABLED
}
status() {
  if core_live && [ -S "$SOCK" ]; then msg CORE_READY; else msg CORE_NOT_READY; fi
  if panel_live && port_busy; then msg PANEL_READY; else msg PANEL_NOT_READY; fi
  [ ! -e "$ICORE" ] || msg CORE_AUTOSTART_CONFIGURED
  [ ! -e "$IPANEL" ] || msg PANEL_AUTOSTART_CONFIGURED
}
[ "$#" -gt 0 ] || die "missing action"
action=$1
shift
case "$action" in
 install) install "$@";;
 start) core_start; panel_start;;
 stop) panel_stop; core_stop;;
 restart) panel_stop; core_stop; core_start; panel_start;;
 core-start) core_start;;
 core-stop) core_stop;;
 core-reload) HOME=/opt "$CORE" reload --control-socket "$SOCK";;
 core-restart) core_stop; core_start;;
 panel-start) panel_start;;
 panel-stop) panel_stop;;
 panel-restart) panel_stop; panel_start;;
 status) status;;
 enable-autostart) enable_autostart;;
 disable-autostart) disable_autostart;;
 *) die "unknown action: $action";;
esac
