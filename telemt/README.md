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

[`build-telemt.yml`](../.github/workflows/build-telemt.yml) is active in
`gh-action-build` (merged PR #26). PR checks verify the pinned official upstream
binary, checksum, license and ARM64 ELF properties. The expensive PR SDK build
stays **opt-in** via the `run-telemt-sdk` label. PR jobs never publish packages.

On `gh-action-build`, the workflow checks the latest
stable official TeleMT release every six hours, including its release-asset
SHA-256 digest. If `latest` already contains
`telemt_<version>-1_aarch64-3.10.ipk`, SDK packaging is skipped.
Otherwise the SDK repacks the verified official ARM64 MUSL executable, validates
binary identity, licenses and package safety boundaries, uploads an Actions
artifact, and publishes **only `telemt_*.ipk`** to the shared GitHub
`latest` release. It downloads the published file to verify byte identity
**before** pruning only older TeleMT assets; Mihomo, WARPSCOUT and Beszel
assets remain untouched. Concurrent release writers share
`entware-latest-publication`.

The live router configuration, API tokens, S99 service and DDNS are never
bundled or modified by these workflows. GitHub Release publication does not
automatically update an installed router: `opkg` uses its configured package
indexes, or an explicitly installed verified GitHub IPK. New major/runtime
behavior should be field-tested before installing on a production router.

## Before enabling service

Verify the Entware architecture with `opkg print-architecture`; save
existing `/opt/etc/telemt` and any `S99telemt` scripts; check available RAM
and WAN port conflicts. Start with a modest `max_connections` limit. Keep
any control API or management panel bound to loopback/LAN, and publish only the
intended Telegram TCP listener. Test from a separate mobile network. In
particular, a working Direct mode does not prove Middle-End mode is working.

Never commit Telegram proxy secrets, external home IPs or panel passwords.

## Updating on Entware

See the [Russian update guide](../docs/telemt-updates.ru.md) for read-only checks,
verified release downloads, private backups, manual upgrades and why GitHub
Release publication does not automatically update an installed router.
