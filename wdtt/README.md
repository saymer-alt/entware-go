# WDTT standalone laboratory build

Development base: `gh-action-build`. This directory is the only WDTT build location; no new repository, no use of retired mihomo-auto-build.

Source: [hoaxisr/proxy-turn-vk-android](https://github.com/hoaxisr/proxy-turn-vk-android/tree/1110a75f76e42c23149b8e24f9182c1ff179e515), exact SHA `1110a75f76e42c23149b8e24f9182c1ff179e515`, go_client plus maintained patches and lab overlay. Client go.mod/go.sum hashes are locked. The fixture server uses the **client module graph** to include Pion TURN and netstack; this is not a production server module lock.

Compiler: unmodified Go1.26.1 from existing [Entware SDK v2026.07.04](https://github.com/ownik/entware-sdk/releases/tag/v2026.07.04), archive SHA256 `d51f30c126425ebff203b107a1a0aa9d3a5844f6c481bc6ff4c117cadc208674`. No setup-go, SDK/toolchain upgrade, GOTOOLCHAIN=auto, dynamic upstream tag or upstream install script. CGO=0; GOMIPS=softfloat; readonly modules + sum.golang.org; trimpath and empty buildid. Extraction uses SDK compiler directly for this gated static-binary experiment; an SDK feed Makefile and installable package are not claimed.

## Build-only CI

[build-wdtt-lab.yml](../.github/workflows/build-wdtt-lab.yml) supports workflow_dispatch and PRs to gh-action-build. Contents permission is read-only. It uploads **JSON evidence only**, never binaries/IPKs/releases. A new workflow may not be manually dispatchable until present on the default branch; use the PR run while merge is forbidden. Do not change the default branch or merge to work around this restriction.

```sh
# Download and SHA256-verify the SDK as shown in the workflow, extract host/go.
python3 wdtt/build_lab.py --go /absolute/sdk/staging_dir/host/go/bin/go \
  --sdk-archive /absolute/sdk.tar.zst --work /absolute/fresh-build-directory
python3 wdtt/test_packaging.py
```

Builds Linux AMD64 (local functional tests), AArch64, MIPSel and MIPS BE. ELF machine/endian and absence of PT_INTERP are checked. MIPS Go build metadata must say softfloat. Native/QEMU -h checks verify startup and the narrow standalone CLI, **not target hardware, kernel support, RAM or full ABI acceptance**. All build and overlay/source/lock digests are recorded in build-report.json. Reproducibility across independent hosts is still an acceptance item.

## Security boundary

The lab entry point accepts only `-config-file /absolute/private/client.json` and help. Legacy secret argv flags, AWGM socket/log/protocol, RAW, socks, hash-check and interactive STDIN are unavailable. Password, call hash and account credentials come from owner-only regular 0600 files in non-symlink 0700 directories; wrong mode/UID/hardlink/symlink is rejected. Parent ancestors and privileged same-UID/root attackers are outside this file-permission boundary. Do not put secrets in filenames, environment or shell history; the program does not consume secret environment variables.

Upstream stdout, stderr, STDIN and core dumps are disabled before execution. This also suppresses HTTP error bodies, cookies, captcha protocol and vendor loggers; it deliberately removes upstream diagnostics rather than claiming a universal redactor. Only fixed status codes are written. Received WG config and captcha profiles use atomic 0600 writes within the private runtime directory. No plaintext config event or private key is printed. Account credential refresh is not unattended-ready; sessions are capped at 30 minutes. Treat runtime directory as private volatile storage, never a public report directory.

UDP bind is exclusive (upstream SO_REUSEADDR removed). Port/config/auth failures terminate with78; temporary worker failures have exponential backoff and a five-attempt bound, exit75 when exhausted. No router TUN or AWG Manager daemon is required for vpn mode. The linked awgmproto library remains MIT, with notice retained; control sockets are never initialized in this profile.

Server patch020 requires AUTH password + known/bound device, and rejects unapproved first packets/failed GETCONF before UDP forwarding. The unchanged upstream fails three local negative tests; patched handler passes those plus the positive test. WRAP key to credential binding, revocation of already-active connections, persistent server files, TCP API, Telegram and startup side effects still need production review. A local AUTH test is not a complete server security audit.

## Local functional PoC

`lab/server_pair_fixture_test.go` is opt-in, loopback-only: Pion TURN, actual patched upstream WRAP/DTLS/GETCONF/AUTH handler, userspace WG netstack and private synthetic keys. It never invokes server main, OS TUN, routes, NAT, sysctl, Telegram or control API. `local_pair.py` connects the actual standalone client and Mihomo v1.19.32, then checks tunnel DNS, HTTP/TCP, SOCKS5 UDP echo 64/512/1000/1200/1400, WG handshake/counters, argv/log canaries and application failure after transport stop.

This passed locally with synthetic TURN credentials. **No VK, router, VPS, WAN packet capture, NAT traversal, real-provider MTU or reboot acceptance is claimed.** The test Mihomo is a digest-verified official compatible AMD64 asset used privately; it is not redistributed by this workflow. The ordinary AMD64 asset requires v3 CPU features on the local host and could not start; compatible asset was used explicitly.

## IPK / rollback / release gates

`ipk_recipe.py` implements deterministic ar + control.tar.gz + data.tar.gz with versioned `/opt/libexec/wdtt-lab/<source-version>/` payload, notices and provenance. It has no init script/maintainer script/autostart. Synthetic archive/path tests pass. Actual package emission is refused by release-gates.json and build-report.install_ready=false; there is no CLI bypass. **No real WDTT IPK has been emitted or published.**

Dependency gate: main GPL-3.0-or-later; awgmproto v0.1.1 MIT. The retained Phase1 inventory covers 31 actually imported modules, root license texts only, not a complete scope approval. `fhttp@v0.6.8` refers to a BSD-style Go license but lacks LICENSE/COPYING/NOTICE at pinned tree `ecfe905c2db9d1ec769a16a14191ec84553dd235`; exact Go-derived and fork-specific notices/scopes remain unresolved. No incompatible-license conclusion is invented, and no binary redistribution is enabled.

Future rollback keeps previous own version/provenance and atomically selects it after verified stop. KAS contains a separately tested local sandbox lifecycle; live Entware installation/uninstall/reboot admission remains closed pending hardware and safety gates. See [KAS experimental branch](https://github.com/saymer-alt/keenetic-auto-setup/tree/feature/wdtt-experimental-poc-20261011/experimental/wdtt).

## Existing publication safety

Existing Mihomo/Beszel/WARPSCOUT workflows and scripts are unchanged. Their shared latest release writer lock is `entware-latest-publication`; each owns only its package glob, validates/uploads/verifies before old-set prune, notifies feedly with AGGREGATOR_PAT, then prunes. This workflow never invokes publish_ipks.py, references that secret, sends a package-built dispatch or writes to latest. Record release asset IDs/digests before/after; independent scheduled workflows may change latest while this experiment is running.

WG-obfuscator remains next after WDTT readiness; no new workflow/IPK here. CSQTT patch/results/PolyForm notices remain in the separate KAS research PR; no CSQTT package is created.
