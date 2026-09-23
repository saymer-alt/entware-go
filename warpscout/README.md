# WARPSCOUT for Keenetic / Entware (ARM64)

Entware package for WARPSCOUT, targeted at the owner's ARM64 Keenetic routers
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

## One-line installer

With Entware present on an ARM64 Keenetic:

```sh
opkg update && opkg install curl ca-bundle && \
curl -fSsL https://raw.githubusercontent.com/saymer-alt/entware-go/gh-action-build/warpscout/install.sh | sh
```

`warpscout/install.sh` is intentionally idempotent. It checks the target architecture, tries
the configured Entware feed first, falls back to the current `warpscout_*.ipk` asset in the
repository's `latest` release when necessary, creates the persistent state directory, preserves
an existing account, and registers a fresh account only when none exists.

The installer uses `umask 077`, keeps the state directory private, and sets the account file to
mode 600 when possible. It never prints the account contents.

The script exits after setup and prints example scan commands; WARPSCOUT remains an on-demand CLI,
not a background service.

## Target and layout

- architecture: **aarch64 only** in this fork's workflow;
- lower practical resource target: **512 MB RAM**;
- utility only: no init script, daemon or autostart;
- binary path: `/opt/bin/warpscout`;
- persistent account/report directory: `/opt/etc/warpscout`;
- automatic production output is published as a single `aarch64-3.10` IPK in the repository's `latest` release after CI verification.

WARPSCOUT upstream defaults to 10 tunnel workers. The first live KN-1812 test (1 GB RAM)
showed that `-jt 10` and `-jt 16` both run comfortably; CPU was mostly idle because scans
are dominated by network waits. For the still-untested 512 MB target, start conservatively
with four workers:

```sh
cd /opt/etc/warpscout
JT=4
# JT=16  # tested on KN-1812 / 1 GB
```

The account file contains WARP credentials/private material. Keep
`/opt/etc/warpscout/warpscout-account.json` private and do not commit or publish it.

Do not infer a router's best endpoint from a VPS scan: run WARPSCOUT on the router whose ISP/path
you actually want to measure.

## Russia / filtered-network workflow

This section follows WARPSCOUT's documented filtering model instead of treating plain WireGuard
as the default. Upstream documents that plain WireGuard is commonly filtered on such networks and
specifically notes DPI filtering on the Moscow Cloudflare edge (`DME`) since April 2026.

### AWG version terminology

WARPSCOUT v0.16.0 has no CLI switch for an `AWG2` or `AWG3` protocol version. Its documented
AmneziaWG interface is `-p awg` plus the obfuscation controls:

- `-gen-i1 quic|dns|sip|stun|random` and `-i1-sni HOST`;
- `-jc`, `-jmin`, `-jmax` for junk packets;
- `-gen-junk` to randomize the junk values;
- `find-junk` to search for a working I1/junk set.

The upstream recommendation is to change **I1 first**. Junk sizes are usually secondary. Do not
invent undocumented AWG-version flags in router commands.

### 1. Start with AWG + QUIC I1

On the tested KN-1812 this profile changed the result from plain-WG `0/70` to AWG `70/70`:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic -o awg-all.txt
```

`-P` is important on a filtering network because it measures ping/loss **inside** the tunnel and
can flag endpoints that complete a handshake but are torn down by DPI after traffic starts.

### 2. Find Cloudflare nodes outside Russia

For the goal "do not use a Cloudflare edge physically inside Russia", use the built-in node-country
filter rather than maintaining a guessed list of Russian colo codes:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic \
  -exclude-country RU -o awg-foreign.txt
```

To exclude only the Moscow edge named by upstream documentation:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic \
  -exclude-node DME -o awg-no-dme.txt
```

`-exclude-country RU` operates on **NODE LOCATION**, not on `SEEN AS`. This is deliberate.
`NODE` tells you which Cloudflare edge carries the tunnel and is the relevant field for avoiding
edge-local filtering. `SEEN AS` tells you which country websites are likely to associate with the
exit. The two can differ: the live KN-1812 scan saw RIX (Riga, LV) while `SEEN AS` remained RU.

Positive filters are available too, for example when a scan has already shown useful foreign nodes:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic \
  -node HEL,ARN,RIX,FRA -o awg-selected-colos.txt
```

Those codes are examples, not a promise that the current ISP will reach them. Scan the actual router
path first.

### 3. Save all useful endpoints, then pick the best

Without `-best`, the report file keeps the full working set plus the best endpoint per node. This is
the useful mode when the goal is to build an inventory of endpoint -> NODE -> NODE LOCATION -> SEEN AS.

To print only the best foreign endpoint:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic \
  -exclude-country RU -best
```

To choose by measured download speed instead of ping:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic \
  -exclude-country RU -best -best-by speed
```

To emit a ready Mihomo proxy block for the best foreign endpoint:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic \
  -exclude-country RU -conf warp-awg.yaml -conf-type mihomo
```

### 4. Deep scans

The normal scan samples five addresses per subnet. `-f` tests all 256 addresses of every built-in
AWG/WG subnet, which is the exhaustive mode but is much slower:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic -f \
  -exclude-country RU -o awg-foreign-full.txt
```

Do the sampled scan first on a 512 MB router; the full-scan runtime has not yet been live-tested on
that lower-memory target.

A port can theoretically land differently even for the same endpoint address. To keep phase 1 and
then test every reachable port separately:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic \
  -sweep-ports open -exclude-country RU -o awg-foreign-ports.txt
```

For a promising subnet, narrow the sweep with `-target`:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 quic \
  -target 188.114.98.0/24 -sweep-ports open -exclude-country RU \
  -o awg-target-ports.txt
```

### 5. If QUIC I1 is blocked

Try the other documented I1 generators before changing junk parameters:

```sh
warpscout scan -p awg -P -jt "$JT" -gen-i1 dns
warpscout scan -p awg -P -jt "$JT" -gen-i1 sip
warpscout scan -p awg -P -jt "$JT" -gen-i1 stun
warpscout scan -p awg -P -jt "$JT" -gen-i1 random
```

If none works, use the upstream automatic search:

```sh
warpscout find-junk -jt "$JT" -gen-i1 random
```

`find-junk` repeatedly tries fresh random junk plus a fresh generated I1 until the configured
threshold is reached, then prints a ready scan command. This is preferable to blindly adding
`-gen-junk` to every routine scan.

## MASQUE H2 / H3

MASQUE has no AWG junk or I1. Its visible obfuscation knob is SNI, and the working SNI can differ
between the QUIC/HTTP3 and TCP/HTTP2 transports. Search them separately:

```sh
# MASQUE over TCP / HTTP2
warpscout find-sni -p masque-h2 -jt "$JT"

# MASQUE over QUIC / HTTP3
warpscout find-sni -p masque -jt "$JT"
```

Each `find-sni` command prints a ready `warpscout scan ... -masque-sni HOST` command. Use the SNI
it found for that transport; do not assume the H2 SNI will work for H3.

For a chosen H2 SNI, a normal scan samples the two real `/24` pools; `-f` covers every address in
`162.159.198.0/24` and `162.159.199.0/24`:

```sh
warpscout scan -p masque-h2 -P -jt "$JT" -masque-sni HOST -o masque-h2.txt
warpscout scan -p masque-h2 -P -jt "$JT" -masque-sni HOST -f -o masque-h2-full.txt
```

Replace `HOST` with the value printed by `find-sni`; it is a placeholder, not a literal hostname.

For MASQUE over QUIC/H3, the endpoint set is fixed and small, so there is no reason to add `-f`:

```sh
warpscout scan -p masque -P -jt "$JT" -masque-sni HOST -o masque-h3.txt
```

### Why there is no `-exclude-country RU` for MASQUE

This is an important protocol difference. WARPSCOUT documents that **all MASQUE endpoints in one
run use the same Cloudflare NODE**, and that NODE is selected by the current network/path rather
than by the endpoint address. Therefore `-node`, `-country`, `-exclude-node` and
`-exclude-country` are deliberately rejected for both `masque` and `masque-h2`.

If a MASQUE run from the current ISP lands on DME, scanning more H2/H3 endpoint IPs will tell you
which addresses/ports pass traffic, but it will not turn that same path into FRA/HEL/ARN/RIX.
Selecting a different MASQUE endpoint is not a colo-selection mechanism; the network/path has to
change.

### Confirm the apparent exit of a selected AWG endpoint

`NODE LOCATION` and `SEEN AS` answer different questions. To validate the apparent country with a
third-party service, first pick a foreign-node AWG endpoint:

```sh
EP="$(warpscout scan -p awg -P -jt "$JT" -gen-i1 quic -exclude-country RU -best)"
printf '%s\n' "$EP"
```

Then run the test SOCKS tunnel:

```sh
warpscout socks -e "$EP" -p awg -gen-i1 quic
```

and from another shell:

```sh
curl -x socks5h://127.0.0.1:1080 https://ifconfig.co/json
```

The SOCKS mode is for endpoint validation only, not permanent routing.

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
Plain WG returned **0 working endpoints** on that home path.

The same router was then scanned with AWG plus generated QUIC I1:

```sh
warpscout scan -p awg -P -jt 16 -gen-i1 quic
```

That run completed in about **11 seconds** and returned **70/70 working endpoints**. WARPSCOUT
observed `DME` and `RIX` nodes, `SEEN AS=RU`; the best DME paths were about **2 ms**
in-tunnel with 0% loss, while RIX was around **37-38 ms**.

This contrast — WG 0/70 versus AWG 70/70 on the same router/path — is strong live evidence that
the Entware package and WARPSCOUT runtime are healthy and that transport/path filtering is the
dominant cause of the plain-WG failure. It does not by itself identify the provider's exact filtering
mechanism.

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
