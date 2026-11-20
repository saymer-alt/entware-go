# KN-1913 (MT7621 / Entware MIPSel): universal TeleMT IPC + Panel Lite installation candidate

**State:** research installer, NOT A RELEASE. First owner hardware trial scheduled for 2026-11-19; no physical KN-1913 results yet. Existing physical KN-1010 pilot (IPC Core + Panel Lite and owner live-profile startup) and QEMU 66/66 are evidence for the pinned binaries only, NOT for this new installer.

## Compatibility and prerequisites

Keenetic KN-1913 uses MT7621A with 256 MiB RAM. Official Keenetic guidance selects the **mipsel** Entware archive for KN-1913. Confirm via `/opt/bin/opkg print-architecture` that the installed feed supports `mipsel-3.4`; this exact configuration is required by the frozen research IPKs. No automatic Entware installation or upgrades.

Requires a **clean** target for this research pair: neither `/opt/bin/telemt-ipc-lab` nor `/opt/bin/telemt-panel` nor dedicated init names may be occupied. Existing `/opt/bin/telemt` from an unrelated package is not touched, but port clashes are still rejected. Have enough USB/EXT4 disk, RAM and a working SOCKS5 endpoint accessible from the router; a SOCKS5 value suitable for KN-1010 is **not** assumed to apply to KN-1913.

## Files supplied by the operator for this pilot

1. Two local frozen IPKs, retrieved from accepted CI Actions artifacts and verified by the installer:
   - `telemt-ipc-lab_3.5.17-1ipc2_mipsel-3.4.ipk`, SHA256 `fbf5ef4c2cad4a564483c29a584986623181574b798ec5b787cdc93c27e15daa`.
   - `telemt-panel-lite_1.0.0.rc.4-1_mipsel-3.4.ipk`, SHA256 `0236dfb076b14b129a6392de49f287838a11aebe7681e092084d4ce87e771e68`.
2. `scripts/telemt-mipsel-install.sh` and `scripts/telemt-mipsel-service.sh` from this exact repository revision. Save these **both** in the same temporary folder, e.g. `/opt/tmp`. CI host syntax/TOML gate output contains SHA256 digests for precise transfer checks. This is NOT a network download installer: preserving the exact frozen IPC patch takes precedence over pulling unverified newer upstream assets.

## One install command, no hand-written TOML

On the KN-1913 in the verified root Entware SSH session:

```sh
cd /opt/tmp || exit 1
sh -n telemt-mipsel-install.sh && sh -n telemt-mipsel-service.sh || exit 1

sh telemt-mipsel-install.sh \
  ./telemt-ipc-lab_3.5.17-1ipc2_mipsel-3.4.ipk \
  ./telemt-panel-lite_1.0.0.rc.4-1_mipsel-3.4.ipk \
  YOUR_SOCKS5_IP:PORT \
  YOUR_HOST_OR_IP \
  127.0.0.1
```

Parameters are: `CORE.ipk PANEL.ipk SOCKS5_IP:PORT TELEGRAM_LINK_HOST PANEL_BIND_IP`.

- `SOCKS5_IP:PORT` is the existing SOCKS5 endpoint reachable from **this** router, not a hard-coded laboratory address.
- `TELEGRAM_LINK_HOST` is the hostname/IP seen by the Telegram client; can be local/VPN for first check. The installer does not create an external IP, open firewall policy, or configure upstream NAT.
- `PANEL_BIND_IP` defaults to operator-selected local IP `127.0.0.1` for maximum safety; if you choose a router LAN address, only trusted LAN/VPN users should reach HTTP 18082. **Do not expose Panel/API to WAN**. Link to Panel uses TCP/18082; Core API is bound to loopback TCP/19091.
- MTProxy listener binds TCP `0.0.0.0:13443`; select ingress rules accordingly.

The installer performs mipsel/port/pre-existing-file checks, verifies exact IPK hashes before OPKG installation, verifies exact ELF hashes afterwards, generates independent MTProxy DD user secret and Panel admin password via /dev/urandom, writes root-only config and credential files, starts Core and Panel, and reports status. **It never prints the generated secrets**; use local `/opt/etc/telemt-mipsel/private-telegram-link.txt` and `private-panel-password.txt` (mode 0600). Do not paste them in chat.

## Services and autostart

```sh
/opt/etc/telemt-mipsel/service.sh status
# After first real Telegram client success:
/opt/etc/telemt-mipsel/service.sh enable-boot
# New init scripts S98telemt-mipsel, S99telemt-mipsel-panel
```

Existing KeeneticOS/Entware must launch `/opt/etc/init.d/rc.unslung` at boot. Do not assume an install-time status check proves boot reliability: verify after two owner-approved reboots. Service subcommands `start`, `stop`, `restart`, `core-start`, `core-stop`, `core-restart`, `core-reload`, `panel-start`, `panel-stop`, `panel-restart`, `enable-boot`, `disable-boot`, `status` and `uninstall`. Core shutdown uses Unix IPC, not PID-file kill.

For laboratory removal:

```sh
/opt/etc/telemt-mipsel/service.sh uninstall
```

Uninstall explicitly stops managed processes, removes ONLY the two lab-owned init scripts, uninstalls the two frozen packages, and preserves root-only credentials/configuration for inspection; it fails closed on unknown/stale process identities. **Do not run `rm -rf /opt/etc` or `rc.unslung restart`.**

## Known candidate limitations

- Only `mipsel-3.4` and the pinned `3.5.17-1ipc2` + `1.0.0-rc.4` IPKs.
- Installer requires locally transferred verified IPKs. A one-file public installer, versioned release/asset publishing and verified updater are **NOT YET READY**.
- Panel Lite runs a `memory` store. Persistence of Panel-only historical data across restart is not guaranteed; distinguish it from Core's own quota path.
- The generic installer has not yet been executed on KN-1913 or tested with two reboots, real Telegram client, failed package installation and rollback. It doesn't yet fully clean up a partial package install; manual incident diagnosis may be necessary.
- Generic Panel updater must not replace the IPC-patched binary from upstream releases; do not click Update until exact version/asset workflow is reviewed.
- The MIPSel panel has 256 MiB RAM to share with Keenetic/Entware; check process RSS/swap and log rotation during sustained use.
- No built-in network firewall/NAT changes; external clients depend on separate verified ingress.
- Self-hosted Panel admin HTTP is not TLS. Keep it on loopback or a trusted/private network.

Acceptance and beta-to-stable criteria are tracked in Issue #61 and research PRs #58/#59/#60. Do not merge stable or publish feed from this file.
