#!/bin/sh
# TeleMT IPC MIPSel beta service: only /opt/etc/telemt-mipsel.
# No unsafe pid-file signalling for Core. Uses in-daemon AF_UNIX.
set -eu
R=/opt/etc/telemt-mipsel
CORE=/opt/bin/telemt-ipc-lab
PANEL=/opt/bin/telemt-panel
CCFG=$R/core.toml
PCFG=$R/panel.toml
PID=$R/core.pid
SOCKET=$R/ctl/ctl.sock
PPID=$R/panel.pid
CLOG=/opt/var/log/telemt-mipsel-core.log
PLOG=/opt/var/log/telemt-mipsel-panel.log
CBOOT=$R/core-boot-id
PBOOT=$R/panel-boot-id
BB=/opt/bin/busybox
I1=/opt/etc/init.d/S98telemt-mipsel
I2=/opt/etc/init.d/S99telemt-mipsel-panel

err() { echo "telemt-mipsel: $*" >&2; exit 1; }
say() { echo "telemt-mipsel: $*"; }
readpid() { [ -r "$1" ] && cat "$1" || :; }
pidok() { case "$1" in ''|*[!0-9]*) return 1;; *) [ "$1" -gt 1 ];; esac; }
exe() { [ -r "/proc/$1/exe" ] && readlink "/proc/$1/exe" 2>/dev/null || :; }
corelive() {
  n=$(readpid "$PID")
  pidok "$n" && [ "$(exe "$n")" = "$CORE" ]
}
panellive() {
  n=$(readpid "$PPID")
  pidok "$n" && [ "$(exe "$n")" = "$PANEL" ] &&
    "$BB" tr '\000' '\n' < "/proc/$n/cmdline" |
      "$BB" grep -Fxq "$PCFG"
}
bootid() {
  [ -r /proc/sys/kernel/random/boot_id ] || err "kernel boot_id unavailable"
  cat /proc/sys/kernel/random/boot_id
}
recover_previous_boot_stale() {
  marker=$1
  pidfile=$2
  socketfile=$3
  [ -f "$marker" ] && [ ! -L "$marker" ] ||
    err "stale process state without trusted boot marker"
  oldboot=$(cat "$marker")
  newboot=$(bootid)
  [ -n "$oldboot" ] && [ -n "$newboot" ] &&
    [ "$oldboot" != "$newboot" ] ||
    err "stale process state in same boot; manual diagnosis required"
  [ ! -L "$pidfile" ] && [ ! -L "$socketfile" ] ||
    err "symlink in stale process state"
  # Files are in the installer-owned 0700 directory. After a kernel reboot
  # no old process survives. Never send a signal to a PID from stale files.
  rm -f "$pidfile"
  [ ! -e "$socketfile" ] || [ -S "$socketfile" ] ||
    err "unexpected stale socket type"
  rm -f "$socketfile"
}
startcore() {
  [ -f "$CCFG" ] && [ ! -L "$CCFG" ] || err "Core config absent/symlink"
  if corelive; then
    [ -S "$SOCKET" ] || err "running Core has no control socket"
    say CORE_READY; return 0
  fi
  if [ -e "$PID" ] || [ -e "$SOCKET" ]; then
    recover_previous_boot_stale "$CBOOT" "$PID" "$SOCKET"
  fi
  mkdir -p "$R/ctl" /opt/var/log
  chmod 700 "$R/ctl"
  HOME=/opt TMPDIR=/opt/tmp "$CORE" start --log-file "$CLOG" \
    --pid-file "$PID" --control-socket "$SOCKET" "$CCFG"
  n=0
  while [ "$n" -lt 90 ]; do
    if corelive && [ -S "$SOCKET" ]; then
      bootid > "$CBOOT"
      chmod 600 "$CBOOT"
      say CORE_READY; return 0
    fi
    sleep 1; n=$((n+1))
  done
  err "Core startup timeout"
}
stopcore() {
  if ! corelive; then
    [ ! -e "$SOCKET" ] || err "unowned socket exists"
    say CORE_STOPPED; return 0
  fi
  [ -S "$SOCKET" ] || err "Core IPC socket missing"
  n=$(readpid "$PID")
  HOME=/opt "$CORE" stop --control-socket "$SOCKET"
  i=0
  while [ "$i" -lt 30 ]; do
    if [ "$(exe "$n")" != "$CORE" ] && [ ! -e "$SOCKET" ]; then
      say CORE_STOPPED; return 0
    fi
    sleep 1; i=$((i+1))
  done
  err "Core shutdown not confirmed"
}
panelport() {
  p=$("$BB" sed -n 's/^listen = ".*:\([0-9][0-9]*\)"$/\1/p' "$PCFG" | "$BB" head -n 1)
  [ -n "$p" ] || err "panel port missing"
  printf '%s' "$p"
}
portbound() {
  p=$(panelport)
  netstat -lnt 2>/dev/null | "$BB" grep -Eq ":$p[[:space:]]"
}
startpanel() {
  [ -f "$PCFG" ] && [ ! -L "$PCFG" ] || err "Panel config absent/symlink"
  if panellive; then say PANEL_READY; return 0; fi
  if [ -e "$PPID" ]; then
    recover_previous_boot_stale "$PBOOT" "$PPID" /dev/null
  fi
  portbound && err "Panel port occupied by another process"
  mkdir -p /opt/var/log
  HOME=/opt TMPDIR=/opt/tmp "$PANEL" -config "$PCFG" \
    </dev/null >>"$PLOG" 2>&1 &
  n=$!
  printf '%s\n' "$n" > "$PPID"
  i=0
  while [ "$i" -lt 15 ]; do
    if panellive && portbound; then
      bootid > "$PBOOT"
      chmod 600 "$PBOOT"
      say PANEL_READY; return 0
    fi
    sleep 1; i=$((i+1))
  done
  err "Panel startup timeout; inspect $PLOG"
}
stoppanel() {
  [ -e "$PPID" ] || { say PANEL_STOPPED; return 0; }
  panellive || err "Panel PID identity mismatch; refusing signal"
  n=$(readpid "$PPID")
  kill -TERM "$n" || err "Panel SIGTERM failed"
  i=0
  while [ "$i" -lt 15 ]; do
    if [ "$(exe "$n")" != "$PANEL" ]; then
      rm -f "$PPID"
      say PANEL_STOPPED; return 0
    fi
    sleep 1; i=$((i+1))
  done
  err "Panel still alive; no SIGKILL"
}
uninstall() {
  [ -x "$CORE" ] && [ -x "$PANEL" ] ||
    err "expected lab packages not installed; refusing destructive cleanup"
  [ -f "$CCFG" ] && [ -f "$PCFG" ] ||
    err "managed config missing; refusing uninstall"
  # Stop only verified instances; do not remove other service scripts/packages.
  stoppanel
  stopcore
  disableboot
  /opt/bin/opkg remove telemt-panel-lite || err "Panel package removal failed"
  /opt/bin/opkg remove telemt-ipc-lab || err "Core package removal failed"
  say "UNINSTALLED_PACKAGES_CONFIG_PRESERVED"
  say "Owner-only configs/secrets remain in $R for rollback inspection"
}
status() {
  if corelive && [ -S "$SOCKET" ]; then say CORE_READY; else say CORE_NOT_READY; fi
  if panellive && portbound; then say PANEL_READY; else say PANEL_NOT_READY; fi
  [ ! -e "$I1" ] || say CORE_BOOT_ENABLED
  [ ! -e "$I2" ] || say PANEL_BOOT_ENABLED
}
enableboot() {
  [ -f "$CCFG" ] && [ -f "$PCFG" ] || err "install first"
  [ ! -e "$I1" ] && [ ! -L "$I1" ] &&
    [ ! -e "$I2" ] && [ ! -L "$I2" ] || err "init name conflict"
  cat > "$I1" <<'INIT'
#!/bin/sh
# telemt-mipsel-installer-owned
case "$1" in
 start) exec /opt/etc/telemt-mipsel/service.sh core-start;;
 stop) exec /opt/etc/telemt-mipsel/service.sh core-stop;;
 restart) exec /opt/etc/telemt-mipsel/service.sh core-restart;;
 *) exit 2;;
esac
INIT
  cat > "$I2" <<'INIT'
#!/bin/sh
# telemt-mipsel-installer-owned
case "$1" in
 start) exec /opt/etc/telemt-mipsel/service.sh panel-start;;
 stop) exec /opt/etc/telemt-mipsel/service.sh panel-stop;;
 restart) exec /opt/etc/telemt-mipsel/service.sh panel-restart;;
 *) exit 2;;
esac
INIT
  chmod 700 "$I1" "$I2"
  say BOOT_ENABLED
}
disableboot() {
  for f in "$I1" "$I2"; do
    if [ -e "$f" ] || [ -L "$f" ]; then
      [ ! -L "$f" ] &&
        "$BB" grep -q '^# telemt-mipsel-installer-owned$' "$f" ||
        err "refusing to remove unowned init script"
      rm -f "$f"
    fi
  done
  say BOOT_DISABLED
}
[ "$#" -eq 1 ] || err "command required: start|stop|status|core-start|core-stop|core-restart|core-reload|panel-start|panel-stop|panel-restart|enable-boot|disable-boot|uninstall"
case "$1" in
 start) startcore; startpanel;;
 stop) stoppanel; stopcore;;
 restart) stoppanel; stopcore; startcore; startpanel;;
 status) status;;
 core-start) startcore;;
 core-stop) stopcore;;
 core-restart) stopcore; startcore;;
 core-reload) HOME=/opt "$CORE" reload --control-socket "$SOCKET";;
 panel-start) startpanel;;
 panel-stop) stoppanel;;
 panel-restart) stoppanel; startpanel;;
 enable-boot) enableboot;;
 disable-boot) disableboot;;
 uninstall) uninstall;;
 *) err "unknown command";;
esac
