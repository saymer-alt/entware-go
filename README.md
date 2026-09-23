# entware-go

Fork-specific Entware package feed for Go and Go-adjacent utilities used on Keenetic and other Entware targets.

The production package release is [`latest`](https://github.com/saymer-alt/entware-go/releases/tag/latest).
Automated workflows build or package only their own assets and publish them into that shared release.

## Packages

- **mihomo** — multi-architecture Entware package, built automatically from the latest MetaCubeX/mihomo release.
- **beszel-agent** — manually built Entware package.
- **warpscout** — ARM64-only Entware package for WARPSCOUT, intended for Keenetic-class routers such as KN-1012 / KN-1812 / KN-3811 / KN-3812.

## WARPSCOUT on ARM64 Keenetic

WARPSCOUT is packaged only for `aarch64-3.10`. It is a command-line diagnostic utility, not a daemon:
there is no init script or autostart.

Install from a configured feed after the package has been indexed:

```sh
opkg update
opkg install warpscout
```

Or copy the current `warpscout_*.ipk` from the repository's `latest` release to the router and install it directly:

```sh
opkg install /tmp/warpscout_<version>-<release>_aarch64-3.10.ipk
warpscout version
```

Keep WARPSCOUT state on persistent Entware storage:

```sh
mkdir -p /opt/etc/warpscout
cd /opt/etc/warpscout
warpscout register
```

The generated `warpscout-account.json` contains private WARP account material. Do not publish or commit it.

For a 512 MB ARM64 router, start conservatively with four tunnel workers:

```sh
warpscout scan -p wg -P -jt 4
warpscout scan -p awg -P -jt 4 -gen-i1 quic
warpscout scan -p masque -P -jt 4 -masque-sni 4pda.to
warpscout scan -p masque-h2 -P -jt 4 -masque-sni 4pda.to
```

On a KN-1812 with 1 GB RAM, `-jt 10` and `-jt 16` completed normally in live testing.
The 512 MB target still needs its own runtime/concurrency test before raising that recommendation.

A result such as `no working endpoints found` is a network-path result, not by itself an installation failure.
The first KN-1812 live test installed and ran WARPSCOUT v0.16.0 successfully; direct Cloudflare WARP API
registration was unavailable on that home path, but WARPSCOUT's relay fallback registered the account and
the scanner completed. WG returned no working endpoints on that path, consistent with the user's known
home-provider WARP blocking.

See [`warpscout/README.md`](warpscout/README.md) for packaging details and CI verification.

## WARPSCOUT update policy

`.github/workflows/build-warpscout.yml` checks the latest upstream WARPSCOUT release every six hours,
offset from the Mihomo workflow. When a new version is missing from this repository's `latest` release it:

1. locates the official upstream `linux_arm64` release asset and verifies GitHub's SHA-256 digest;
2. packages it as an Entware `aarch64-3.10` IPK;
3. verifies the payload is AArch64 and the packaged binary is byte-identical to the official upstream binary;
4. uploads the new `warpscout_*.ipk` to `latest`;
5. removes only older `warpscout_*.ipk` assets;
6. notifies the feed aggregator.

WARPSCOUT v0.16.0 requires Go 1.26.3 while the current Entware SDK v2026.07.04 contains Go 1.26.1.
The workflow therefore repacks the official static Linux/ARM64 upstream binary instead of modifying or
bypassing the Entware SDK Go toolchain.
