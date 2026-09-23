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

### One-line install and registration

For an ARM64 Keenetic with Entware already installed:

```sh
opkg update && opkg install curl ca-bundle && \
curl -fSsL https://raw.githubusercontent.com/saymer-alt/entware-go/gh-action-build/warpscout/install.sh | sh
```

The installer is safe to run again. It:

- verifies `aarch64` plus Entware `aarch64-3.10`/`aarch64-3.10_kn`;
- first tries `opkg install warpscout`;
- if the configured feed does not contain WARPSCOUT yet, downloads the current ARM64 IPK from this repository's `latest` release and installs it directly;
- creates `/opt/etc/warpscout` with private permissions;
- keeps an existing `warpscout-account.json`, or runs `warpscout register` when no account exists;
- prints ready-to-copy WG/AWG/H3/H2 scan commands and then exits. WARPSCOUT itself remains an on-demand CLI utility.

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

### Recommended workflow for Russia / filtered networks

Plain WireGuard is useful as a diagnostic baseline, but it is **not** the recommended first scan on a filtered Russian access network. WARPSCOUT upstream explicitly recommends AmneziaWG or MASQUE when plain WireGuard is filtered, and documents the Moscow `DME` edge as DPI-filtered since April 2026.

WARPSCOUT v0.16.0 does **not** expose an `AWG2`/`AWG3` protocol selector. The supported AWG path is `-p awg` with the documented obfuscation controls (`I1`, junk packet count/sizes and the I1 generators). Do not add undocumented AWG-version flags.

For a 512 MB ARM64 router start with four tunnel workers. The tested KN-1812 with 1 GB RAM handled `-jt 16` comfortably:

```sh
cd /opt/etc/warpscout
JT=4        # 512 MB starting point
# JT=16     # tested on KN-1812 / 1 GB
```

Start with AWG and a generated QUIC-looking I1 packet. This was the successful live profile on the KN-1812:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic -o awg-all.txt
```

To keep only Cloudflare edge nodes physically **outside Russia**, use the node-country filter:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic \
  -exclude-country RU -o awg-foreign.txt
```

If the goal is only to reject the Moscow edge while keeping other Russian nodes, use:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic \
  -exclude-node DME -o awg-no-dme.txt
```

`-exclude-country RU` filters **NODE LOCATION**, not the `SEEN AS` region. A tunnel may therefore land on a foreign node such as RIX/ARN/HEL/FRA while websites still see `SEEN AS=RU`. That distinction matters: NODE is the useful field when avoiding filtering attached to a Russian Cloudflare edge; `SEEN AS` is the field to inspect when you also care about the apparent exit country.

Useful selectors once a foreign node is found:

```sh
# Best foreign endpoint only
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic \
  -exclude-country RU -best

# Best foreign endpoint as a ready Mihomo proxy block
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic \
  -exclude-country RU -conf warp-awg.yaml -conf-type mihomo

# Rank the selected foreign candidates by measured download speed
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic \
  -exclude-country RU -best -best-by speed
```

For a deep search, `-f` tests all 256 addresses in every built-in AWG/WG subnet. It is much slower; use the normal sampled scan first, especially on a 512 MB router:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic -f \
  -exclude-country RU -o awg-foreign-full.txt
```

To see whether different reachable ports of the same sampled endpoint land differently, use the official port sweep:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic \
  -sweep-ports open -exclude-country RU -o awg-foreign-ports.txt
```

If QUIC I1 does not pass the filter, try the other documented I1 generators before touching junk sizes. Upstream says I1 is usually the important part:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 dns
warpscout scan -p awg -P -jt "$JT" -gen-i1 sip
warpscout scan -p awg -P -jt "$JT" -gen-i1 stun
warpscout scan -p awg -P -jt "$JT" -gen-i1 random
```

If none of those profiles works, let WARPSCOUT search both fresh I1 and junk settings:

```sh
warpscout find-junk -jt "$JT" -gen-i1 random
```

`find-junk` prints a ready-to-run `warpscout scan ...` command when it finds a set that reaches the threshold. There is normally no reason to force `-gen-junk` on every regular scan.

### MASQUE H2 / H3 on a filtered network

MASQUE uses SNI instead of AWG junk/I1. Find the SNI independently for each transport:

```sh
# TCP / HTTP/2 fallback — the more important first test on a filtering network
warpscout find-sni -p masque-h2 -jt "$JT"

# QUIC / HTTP/3 transport
warpscout find-sni -p masque -jt "$JT"
```

Each command prints the scan command containing the SNI it found; use that exact SNI for the corresponding transport. An SNI that works for H2 may fail for H3 and vice versa.

For `masque` (QUIC/H3), WARPSCOUT automatically covers the fixed anycast addresses and their known ports. For `masque-h2`, the real endpoint pools are `162.159.198.0/24` and `162.159.199.0/24`; add `-f` to the printed H2 scan if you intentionally want to test every address in both pools.

**Important MASQUE limitation:** all MASQUE endpoints in one run land on the same Cloudflare NODE, chosen by the network/path rather than by the endpoint IP. WARPSCOUT therefore rejects `-node`, `-country`, `-exclude-node` and `-exclude-country` for both MASQUE transports. If MASQUE from the current ISP lands on DME, changing only the MASQUE endpoint IP will not select FRA/HEL/ARN/RIX; a different network/path is required.

The first live KN-1812 test is a good example of why the transport matters: plain WG returned **0/70**, while AWG with `-gen-i1 quic` returned **70/70 in about 11 seconds**. The AWG scan saw DME and RIX nodes with `SEEN AS=RU`, and the best DME paths were about 2 ms while RIX was about 37-38 ms.

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
