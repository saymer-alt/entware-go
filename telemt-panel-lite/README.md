# TeleMT Panel Lite for ARM64 Keenetic / Entware (experimental)

Unofficial, opt-in Entware IPK recipe for the **unmodified** official
[amirotin/telemt_panel](https://github.com/amirotin/telemt_panel) **1.0.0-rc.3 Lite**
binary. This is a prerelease candidate, **not** the latest stable 0.6.2.
No Rust or Go compilation takes place: the static Linux ARM64 MUSL binary is
repackaged as `telemt-panel-lite_1.0.0~rc.3-1_aarch64-3.10.ipk`.

## Provenance and licensing

- Source release: `v1.0.0-rc.3` (2026-10-06).
- Asset: `telemt-panel-lite-aarch64-linux-musl.tar.gz`
- Archive SHA256: `bf8f6160240521653d6abb02f953794aa1eab526b8f30e5682f69c07f17ed271`.
- The upstream archive contains one file named `telemt-panel`.
- Binary is byte-identical to the upstream archive; package layout is unofficial.
- Original MIT LICENSE and upstream THIRD_PARTY_NOTICES.md are kept in `files/`
  and installed beneath `/opt/share/licenses/telemt-panel/`.

The Lite profile has **memory-only history** (no SQLite storage). It still
persists authentication state, sessions, passkeys and settings separately in
the configured `data_dir`; keep that data on protected persistent storage.
The upstream Go 1.27 build is pure Go/static and embeds the browser UI; no
Node.js/Go runtime is needed on the router.

## Contents and safety boundary

The IPK installs ONLY:

- `/opt/bin/telemt-panel`
- `/opt/share/licenses/telemt-panel/LICENSE`
- `/opt/share/licenses/telemt-panel/THIRD_PARTY_NOTICES.md`

No file in `/opt/etc/telemt-panel`, `/opt/var/lib/telemt-panel`, firewall,
router policy or `/opt/etc/init.d` is created or overwritten by this recipe.
The package does not start the panel or enable its web listener. It conflicts
with the existing `telemt-panel` package name to prevent silent overwrites
of older Entware packages which install the same binary path.

**DO NOT** simply copy a 0.6.x config into 1.x. The config schema and service
command requirements changed. First back up the old config, state and executable;
follow the official [upgrade guide](https://github.com/amirotin/telemt_panel/blob/v1.0.0-rc.3/docs/UPGRADING.md)
and [Entware notes](https://github.com/amirotin/telemt_panel/blob/v1.0.0-rc.3/docs/ENTWARE.md).
Use `[store] driver = "memory"` in Lite, preserve an absolute writable
`data_dir`, and generate an administrator bcrypt password hash with the panel's
`hash-password` command. TeleMT must expose its local Control/Config API before
management functions work. The `[telemt]` API token in the panel must match the
TeleMT instance; it must never appear in git or logs.

Bind the administration panel to `127.0.0.1` and reach it via SSH tunnel or a
separately authenticated local network reverse proxy. Do not open the admin
listener to the public WAN. Do not disable authentication.

## GitHub Actions and upgrade stages

[`build-telemt-panel.yml`](../.github/workflows/build-telemt-panel.yml) is
active in `gh-action-build` (merged PR #27, GitHub asset-name fix PR #28).
A PR checks the pinned official ARM64 Lite archive and digest. Expensive PR SDK
packaging requires the `run-telemt-panel-sdk` label. PRs do **not** publish or deploy.

A six-hour schedule on `gh-action-build` checks official
Panel **1.x** releases, including RC builds, rather than GitHub's latest stable
0.6.x release. It selects the highest supported 1.x version with the expected
official ARM64 MUSL Lite asset and a SHA-256 digest; unexpected releases, missing
assets and downgrades fail closed. The SDK build stages the official tagged
MIT `LICENSE` and `THIRD_PARTY_NOTICES.md`, verifies the repackaged binary's
SHA256 and absence of default configuration/init scripts, then publishes only
`telemt-panel-lite_*.ipk` into the shared `latest` release. Published bytes
are downloaded and compared before old Panel Lite assets are pruned; other
packages are untouched and release writes share `entware-latest-publication`.

This is still an unofficial upstream-binary package. Upstream 1.x changes may
require manual adjustments to `/opt/etc/telemt-panel/config.toml`, service
scripts or state migration; **GitHub CI will not rewrite or restart them**.
A GitHub Release asset is not automatically an `opkg` feed update.

After a separately approved build, download and verify the temporary Actions
artifact before any test installation:

```sh
opkg print-architecture
opkg install /tmp/telemt-panel-lite_1.0.0~rc.3-1_aarch64-3.10.ipk
/opt/bin/telemt-panel --help
/opt/bin/telemt-panel config check --config /opt/etc/telemt-panel/config.toml
```

These commands are examples; they are **not** automatically run by CI. The
last check requires an already prepared, valid 1.x configuration. Real Keenetic
service and API tests, migration, resource measurements and rollback remain
separate acceptance gates.

## Updating on Entware

See the [Russian update guide](../docs/telemt-updates.ru.md) for the distinction
between package updates and the panel's own upstream-binary update mechanism,
including the `~rc` / `.rc` GitHub Release asset name difference, verification,
private backups and manual installation.
