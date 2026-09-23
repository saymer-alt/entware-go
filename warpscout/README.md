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
- CI output is an Actions artifact only until a real router install/runtime test succeeds.

WARPSCOUT upstream defaults to 10 tunnel workers. For a 512 MB router start conservatively
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

This proves packaging did not alter the upstream executable. It does **not** replace the
required live Keenetic test.

## CI policy

`.github/workflows/build-warpscout.yml` resolves the official Linux/ARM64 asset and its
GitHub-provided SHA-256 digest, packages it with the Entware aarch64 SDK, verifies that the
IPK contains executable `/opt/bin/warpscout`, and checks that the payload is ARM64.

The experimental workflow does not publish to the repository's `latest` release/feed.
Publication is gated on a successful real Keenetic installation and runtime test.
