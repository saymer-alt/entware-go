# WARPSCOUT for Keenetic / Entware (ARM64)

Experimental Entware package for WARPSCOUT, targeted at the owner's ARM64 Keenetic routers
(KN-1012 / KN-1812 / KN-3811 / KN-3812 class).

Scope of the first release:

- architecture: **aarch64 only**;
- lower resource target: a router with **512 MB RAM**;
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
`/opt/etc/warpscout/warpscout-account.json` private and do not commit it.

Do not infer a router's best endpoint from a VPS scan: run WARPSCOUT on the router whose ISP/path
you actually want to measure.

## Build policy

`.github/workflows/build-warpscout.yml` uses the Entware aarch64 SDK and its bundled Go
toolchain with `GOTOOLCHAIN=local`. It fails before build when the selected WARPSCOUT tag
requires a newer Go version than the SDK provides. Do not bypass this by installing another Go
toolchain into the workflow.

The experimental workflow does not publish to the repository's `latest` release/feed.
Publication is gated on a successful real Keenetic test.
