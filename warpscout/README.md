# WARPSCOUT for Keenetic / Entware (ARM64)

Experimental Entware package for WARPSCOUT, targeted at the owner's ARM64 Keenetic routers
(KN-1012 / KN-1812 / KN-3811 / KN-3812 class).

## Packaging choice

The current tested target is WARPSCOUT **v0.16.0**. Its `go.mod` requires Go 1.26.3,
while the current Entware SDK release `v2026.07.04` ships Go 1.26.1 and this fork deliberately
uses `GOTOOLCHAIN=local`.

Therefore the package does **not** lower WARPSCOUT's Go requirement and does not install a
different compiler into the SDK. Instead it repacks the official upstream
`warpscout_0.16.0_linux_arm64.tar.gz` release asset. Upstream builds that Linux artifact
with `CGO_ENABLED=0` and compresses it with UPX.

Pinned v0.16.0 asset SHA-256:

```text
261ef88a1ac6eb405ea2d11d80fcce823913ae1faaff9cdc1dff4465c516483d
```

When the Entware SDK reaches Go >= 1.26.3, source-building WARPSCOUT through `golang.mk`
can be reconsidered. Until then binary repack keeps the full current feature set (including
MASQUE H2) without weakening the SDK/toolchain contract.

## Target and layout

- architecture: **aarch64 only** in this fork's workflow;
- lower practical resource target: **512 MB RAM**;
- utility only: no init script, daemon or autostart;
- binary path: `/opt/bin/warpscout`;
- persistent account/report directory: `/opt/etc/warpscout`;
- automatic production output is published as a single `aarch64-3.10` IPK in the repository's `latest` release after CI verification.

WARPSCOUT upstream defaults to 10 tunnel workers. The first live KN-1812 test (1 GB RAM)
showed that `-jt 10` and `-jt 16` both run comfortably; CPU was mostly idle because the scan
is dominated by network waits. For the still-untested 512 MB target, start conservatively
with four workers:

```sh
mkdir -p /opt/etc/warpscout
cd /opt/etc/warpscout

warpscout register
warpscout scan -p wg -P -jt 4
warpscout scan -p wg -P -jt 4 -best
warpscout scan -p masque -P -jt 4 -masque-sni 4pda.to
warpscout scan -p masque-h2 -P -jt 4 -masque-sni 4pda.to
```

The account file contains WARP credentials/private material. Keep
`/opt/etc/warpscout/warpscout-account.json` private and do not commit or publish it.

Do not infer a router's best endpoint from a VPS scan: run WARPSCOUT on the router whose ISP/path
you actually want to measure.

## First CI proof (2026-09-23)

The first successful aarch64 packaging run produced:

```text
warpscout_0.16.0-1_aarch64-3.10.ipk
```

Payload verification reported:

```text
ELF 64-bit LSB executable, ARM aarch64, statically linked
```

The packaged binary SHA-256 exactly matched the binary extracted from the official upstream
v0.16.0 Linux/ARM64 release archive:

```text
eb7ae4b141b9a2d4677a67630f1f8e45105ff9396bb015442cf7d3071ef5c092
```

This proves packaging did not alter the upstream executable.

## First live Keenetic proof (2026-09-23)

The package was then installed on a real **KN-1812 / aarch64 / 1 GB RAM** Entware router:

```text
opkg install warpscout_0.16.0-1_aarch64-3.10.ipk -> success
/opt/bin/warpscout version -> 0.16.0
```

`warpscout register` could not reach the Cloudflare WARP API directly on that home path, but
the built-in relay fallback succeeded and created the local account file.

WG scans executed correctly at `-jt 4`, `-jt 8`, `-jt 10` and `-jt 16`. The complete
`-jt 10` run finished in about 57 seconds and the complete `-jt 16` run in about 40 seconds.
Both returned no working WG endpoints. That is consistent with the known WARP blocking on that
home-provider path and is treated as a connectivity result, not a package/runtime failure.

This live test closes the basic ARM64 package smoke-test gate: install, executable startup,
registration fallback and real scanning all work on Keenetic.

## CI policy

`.github/workflows/build-warpscout.yml` resolves the official Linux/ARM64 asset and its
GitHub-provided SHA-256 digest, packages it with the Entware aarch64 SDK, verifies that the
IPK contains executable `/opt/bin/warpscout`, and checks that the payload is ARM64.

The production workflow checks upstream every six hours. A pull-request run always builds and
verifies but never publishes. Scheduled runs build only when the latest upstream WARPSCOUT version
is missing from this repository's `latest` release. Manual dispatch and relevant pushes rebuild
the current latest version.

Publication uploads only `warpscout_*.ipk`, verifies the new asset, removes only older
WARPSCOUT package assets, and dispatches the feed aggregator. Mihomo and Beszel assets are outside
this workflow's ownership and must not be modified.
