# KN-1010 TeleMT IPC + Panel Lite MIPSel — managed service kit (research beta)

**Status (2026-11-18):** script committed for review; **not yet executed on physical KN-1010**, no release/feed/installer publication. QEMU 66/66 for separate frozen IPC+Panel pair is accepted, but this new script has **not** inherited that test verdict. Review + shell syntax gate + physical lifecycle verification required.

## Scope

One isolated lab Core \`/opt/bin/telemt-ipc-lab\`, one Panel Lite RC4 \`/opt/bin/telemt-panel\`. Uses existing tested Core configuration \`/opt/etc/telemt-ipc-kn1010-socks5.toml\` (SOCKS5 upstream 10.0.6.78:7890) and local Core API at 127.0.0.1:19091. Panel binds to localhost by default; the operator may opt in to 192.168.107.1 (same address on br0 and sstp0, **not SSTP-only**) on the isolated test router.

Does not overwrite old lab configs, existing S99telemt/S99telemt-panel, production TeleMT or packages. Does not auto-enable startup. Does not run opkg upgrade, modify kernel, BusyBox or firewall. Avoid running alongside a foreground panel already occupying port 18082.

## Frozen binary gates

- \`telemt-ipc-lab\` ELF SHA-256: \`a83caf105dd77248de43c9e096f8248ce3851b322dfe6dd59a934801344d9506\`
- \`telemt-panel\` ELF SHA-256: \`380cb5112b58538eafec9ae9fab27fb22c994fd36ce3130c541c5e11b29a40c8\`
- Original pinned experimental IPKs: \`fbf5ef4c2cad4a564483c29a584986623181574b798ec5b787cdc93c27e15daa\` and \`0236dfb076b14b129a6392de49f287838a11aebe7681e092084d4ce87e771e68\`.

The service kit **requires these two packages to be installed first**; it is not yet a public one-command IPK downloader. It fails closed on an ELF checksum mismatch. These pins must not be silently replaced.

The managed Panel config directs update binary paths to the **isolated lab executables**, not system `/bin/telemt`. Nevertheless **do not use the Panel Updates screen for this research pair**: upstream release assets do not include this IPC patch and the laboratory IPK pins will not be preserved by a generic updater.

## Transfer / local dry-run

Copy \`scripts/telemt-ipc-mipsel-pilot-service.sh\` to \`/opt/tmp/telemt-ipc-mipsel-pilot-service.sh\` over a verified SSH/SFTP connection. On this KN-1010 Entware SSH is on **222**; verify the SSH host fingerprint independently before changing an existing known_hosts entry. If logged in through the already verified terminal, use that session.

\`\`\`sh
sh -n /opt/tmp/telemt-ipc-mipsel-pilot-service.sh
sha256sum /opt/tmp/telemt-ipc-mipsel-pilot-service.sh
# Save the local hash to an evidence note after the exact revision is frozen.
# Ensure old foreground panel has been stopped (Ctrl+C) and no listener on 18082.
netstat -lnt 2>/dev/null | grep ':18082' || echo PANEL_PORT_FREE
\`\`\`

## Opt-in install (creates independent panel config with freshly generated password)

\`\`\`sh
sh /opt/tmp/telemt-ipc-mipsel-pilot-service.sh install 192.168.107.1
# Save NEW_PASSWORD *privately*. Do not paste it into chats or reports.
# Expected: PILOT: INSTALLED (no autostart)
\`\`\`

Managed paths:

- \`/opt/etc/telemt-ipc-pilot/service.sh\` — single service driver, referenced by Panel custom commands.
- \`/opt/etc/telemt-ipc-pilot/panel.toml\` — independent 0600 Panel config with new password, file logs, four custom service commands, direct privilege mode.
- \`/opt/var/run/telemt-panel-ipc-pilot.pid\` — dedicated Panel PID.
- \`/opt/var/log/telemt-panel-ipc-pilot.log\` — dedicated Panel process log.
- \`/opt/var/log/telemt-ipc-kn1010.log\` — Core log, displayed by Panel's file log source.

Original \`/opt/etc/telemt-panel-ipc-kn1010.toml\` and \`.bak\` are left unchanged. Previous chat-exposed password remains in that old config/bak until the owner safely deletes those test-only files after verifying the new panel; do not use the old config again.

## Start, status, GUI control

\`\`\`sh
/opt/etc/telemt-ipc-pilot/service.sh start
/opt/etc/telemt-ipc-pilot/service.sh status
\`\`\`

Open \`http://192.168.107.1:18082\` only from the trusted LAN or SSTP route. Login \`labadmin\` with new private password. Panel \`/server/platform\` should display \`custom\` management. Test GUI \`Stop\`, \`Start\` and \`Restart\` while verifying Core PID/exe and IPC socket in a separate shell. Unlike a stopped foreground SSH process, panel should survive logout due redirected stdio and managed PID; this must be verified on physical hardware, not assumed from QEMU.

The Core handler always uses the in-daemon Unix socket for stop/reload; it **does not issue signals to PID files**. Panel stop has no IPC endpoint; it checks the executable and exact config path in \`/proc/PID/cmdline\` before SIGTERM, with no SIGKILL fallback. This does not eliminate the theoretical race inherent in numeric PID-based Panel shutdown; treat it as separate from the IPC Core safety guarantee.

## Autostart is explicitly opt-in (do this only after physical GUI passes)

\`\`\`sh
/opt/etc/telemt-ipc-pilot/service.sh enable-autostart
# Generates only two new files:
/opt/etc/init.d/S98telemt-ipc-pilot start
/opt/etc/init.d/S99telemt-panel-ipc-pilot start
\`\`\`

Requires an already functional Entware \`rc.unslung\` boot hook. Exact names are checked before creation; no existing init script is overwritten. A reboot test must prove ordering, no duplicate instances, and that services are restored with the expected config and listeners.

To turn boot startup back off:

\`\`\`sh
/opt/etc/telemt-ipc-pilot/service.sh disable-autostart
\`\`\`

This removes only scripts carrying the exact lab ownership marker. No package uninstall or production change.

## Fail-closed behavior and remaining requirements

- Port 18082 already in use: refuse to start/overwrite.
- Existing unknown/stale Core PID/socket or panel PID: refuse unsafe cleanup; diagnose manually.
- Core startup may take 6–40+ seconds depending on Telegram DC reachability; script waits at most 90 seconds for PID+IPC.
- Panel start waits for process + port, not complete API health or real user traffic.
- No unattended install, upgrade, cross-firmware guarantee, system log rotation, automated rollback, or external HTTPS; HTTP 192.168.107.1 is also available on the LAN interface \`br0\`. Never port-forward publicly.
- Do not classify as **public beta** until script is syntax-tested with \`sh -n\`, reviewed, exercised on physical KN-1010 (including GUI control, SSH disconnect, reboot, rollback), and signed/pinned artifacts are prepared.

Relevant existing research: Draft PR #58 (Core IPC), Draft PR #59 (66/66 joint QEMU), Issue #51 (Linux 4.9 stop/reload).
