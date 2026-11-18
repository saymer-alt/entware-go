#!/bin/sh
# Read-only KN-1010 TeleMT IPC + Panel Lite preflight.
# NO installs, config changes, service restarts, network changes or logs.
# Run from Entware SSH: sh ./kn1010-preflight-readonly.sh

printf '\n=== Device / kernel ===\n'
uname -a 2>&1
printf '\n=== Entware architecture ===\n'
if [ -x /opt/bin/opkg ]; then
    /opt/bin/opkg print-architecture 2>&1
else
    printf '%s\n' 'MISSING /opt/bin/opkg; do NOT install lab packages'
fi
printf '\n=== Existing TeleMT packages ===\n'
if [ -x /opt/bin/opkg ]; then
    /opt/bin/opkg list-installed 2>&1 |
        grep -i -E '^(telemt|telemt-panel|telemt-ipc-lab)( |-|$)' ||
        printf '%s\n' 'No matching TeleMT packages reported'
fi
printf '\n=== Available space / RAM ===\n'
df -k /opt 2>&1
[ -r /proc/meminfo ] &&
    grep -E '^(MemTotal|MemAvailable|SwapTotal):' /proc/meminfo
printf '\n=== Paths and directory permissions ===\n'
for p in / /opt /opt/tmp /opt/etc /opt/var /opt/var/run /opt/bin /opt/etc/init.d; do
    if [ -e "$p" ]; then ls -ld "$p"; else printf 'ABSENT %s\n' "$p"; fi
done
printf '\n=== Root and /opt mounts ===\n'
[ -r /proc/mounts ] &&
    awk '$2=="/" || $2=="/opt" {print $1, $2, $3, $4}' /proc/mounts
printf '\n=== Lab listener ports (13443 / 18082 / 19091) ===\n'
if command -v netstat >/dev/null 2>&1; then
    netstat -lnt 2>/dev/null |
        grep -E ':(13443|18082|19091)[[:space:]]' ||
        printf '%s\n' 'No matching listeners reported'
elif command -v ss >/dev/null 2>&1; then
    ss -lnt 2>/dev/null |
        grep -E ':(13443|18082|19091)[[:space:]]' ||
        printf '%s\n' 'No matching listeners reported'
else
    printf '%s\n' 'netstat/ss not available; port occupancy NOT_VERIFIED'
fi
printf '\n=== Relevant executables (listing only) ===\n'
for p in /opt/bin/telemt /opt/bin/telemt-ipc-lab /opt/bin/telemt-panel; do
    if [ -e "$p" ]; then ls -l "$p"; else printf 'ABSENT %s\n' "$p"; fi
done
printf '\n=== SHA256 of staged lab IPKs (if present) ===\n'
for p in /opt/tmp/telemt-ipc-lab_3.5.17-1ipc2_mipsel-3.4.ipk \
         /opt/tmp/telemt-panel-lite_1.0.0.rc.4-1_mipsel-3.4.ipk; do
    [ ! -f "$p" ] || sha256sum "$p"
done
printf '\nPreflight complete: no system changes made.\n'
