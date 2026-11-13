# TeleMT for ARM64 Keenetic / Entware (experimental)

This directory contains an **unofficial Entware IPK recipe** for the unmodified
official [TeleMT](https://github.com/telemt/telemt) ARM64 Linux MUSL release.
It is intentionally kept independent of the Go toolchain and other packages in
this fork. The first target is `aarch64-3.10` on Keenetic / Netcraze; other
architectures are **not** supported by this recipe.

## Pinned source and integrity

- Upstream tag: `3.5.17` (official Release, 2026-11-08).
- Archive: `telemt-aarch64-linux-musl.tar.gz`.
- SHA256: `c80b0159b41cf410b2a87cf62676d67a16a537bd7207602b60dd9ce56e14d1f6`.
- Archive produced by upstream's release workflow contains the `telemt`
  executable. Its contents are **not modified** when packaged.
- Upstream license: `TELEMT LICENSE 3.3`, retained verbatim in
  `files/LICENSE` and installed at `/opt/share/licenses/telemt/LICENSE`.
  This is **not an official TeleMT distribution**.

## Package layout and activation

The IPK installs only:

- `/opt/bin/telemt`
- `/opt/share/licenses/telemt/LICENSE`

It does **not** install or replace `/opt/etc/telemt/config.toml`, does not
generate secrets, does not open firewall ports and does **not** create an
init script or start a daemon. Use upstream's configuration documentation to
prepare a private `config.toml` separately after confirming the binary works
on the target router.

For example, after obtaining a CI artifact **and verifying its provenance**:

```sh
opkg install /tmp/telemt_3.5.17-1_aarch64-3.10.ipk
/opt/bin/telemt --help
```

The first command above is an example, not part of CI. Actual package name must
match the emitted artifact; do not run these commands on production routers
until hardware acceptance is approved.

## GitHub Actions

[`build-telemt.yml`](../.github/workflows/build-telemt.yml) performs a
lightweight upstream digest/license preflight on PRs. To prevent expensive SDK
runs on every PR revision, the Entware SDK build is opt-in: an owner can add the
`run-telemt-sdk` label to the PR and re-trigger a `labeled` event. Once the
workflow is present on the default branch, its manual `workflow_dispatch`
can also run a build. The build verifies the produced IPK's filename, ELF
architecture, absence of a dynamic loader/dependencies, matching upstream
binary SHA256 and bundled license. The tested IPK is uploaded as a **temporary
Actions artifact only**.

The workflow does not edit the shared `latest` GitHub Release, publish a feed,
notify an aggregator, or alter Mihomo/WARPSCOUT workflows. Hardware validation
on a Keenetic router remains a separate acceptance gate.

## Before enabling service

Verify the Entware architecture with `opkg print-architecture`; save
existing `/opt/etc/telemt` and any `S99telemt` scripts; check available RAM
and WAN port conflicts. Start with a modest `max_connections` limit. Keep
any control API or management panel bound to loopback/LAN, and publish only the
intended Telegram TCP listener. Test from a separate mobile network. In
particular, a working Direct mode does not prove Middle-End mode is working.

Never commit Telegram proxy secrets, external home IPs or panel passwords.
