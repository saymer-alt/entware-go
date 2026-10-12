# Phase 5 source update

Effective client/relay now come from the pinned saymer-alt fork: [source/backup/verification](PHASE5-FORK.md), [qWDTT design](QWDTT-COMPATIBILITY.md). Entware recipes and KAS lifecycle stay in their owning repositories.

Phase4: [устанавливаемые owner-local IPK, private retention и настоящий opkg fixture](PHASE4-OWNER-LOCAL.md). Ниже сохранены Phase2/3 public-channel ограничения; owner-local технический admission описан отдельно.

# WDTT standalone laboratory build

## Личный некоммерческий исследовательский проект

Владелец ведёт проект прежде всего для себя, публично сохраняя разработки. Некоммерческое назначение не отменяет лицензий upstream. **До подтверждения условий распространения WDTT бинарники/IPK не загружаются в публичные CI artifacts, Releases или latest.** Предупреждение об экспериментальном статусе не заменяет этот gate. Независимые Mihomo/WARPSCOUT/Beszel сборки не изменяются.

Development base: `gh-action-build`. This directory is the only WDTT build location; no new repository, no use of retired mihomo-auto-build.

Source: [hoaxisr/proxy-turn-vk-android](https://github.com/hoaxisr/proxy-turn-vk-android/tree/1110a75f76e42c23149b8e24f9182c1ff179e515), exact SHA `1110a75f76e42c23149b8e24f9182c1ff179e515`, go_client plus maintained patches and lab overlay. Client go.mod/go.sum hashes are locked. The fixture server uses the **client module graph** to include Pion TURN and netstack; this is not a production server module lock.

Compiler: unmodified Go1.26.1 from existing [Entware SDK v2026.07.04](https://github.com/ownik/entware-sdk/releases/tag/v2026.07.04), archive SHA256 `d51f30c126425ebff203b107a1a0aa9d3a5844f6c481bc6ff4c117cadc208674`. No setup-go, SDK/toolchain upgrade, GOTOOLCHAIN=auto, dynamic upstream tag or upstream install script. CGO=0; GOMIPS=softfloat; readonly modules + sum.golang.org; trimpath and empty buildid. Extraction uses SDK compiler directly for this gated static-binary experiment; an SDK feed Makefile and installable package are not claimed.

## Build-only CI

[build-wdtt-lab.yml](../.github/workflows/build-wdtt-lab.yml) supports workflow_dispatch and PRs to gh-action-build. Contents permission is read-only. It uploads **JSON/TXT evidence only**, never binaries/IPKs/releases. A new workflow may not be manually dispatchable until present on the default branch; use the PR run while merge is forbidden. Do not change the default branch or merge to work around this restriction.

```sh
# Download and SHA256-verify the SDK as shown in the workflow, extract host/go.
python3 wdtt/build_lab.py --go /absolute/sdk/staging_dir/host/go/bin/go \
  --sdk-archive /absolute/sdk.tar.zst --work /absolute/fresh-build-directory
python3 wdtt/test_packaging.py
```

Builds Linux AMD64 (local functional tests), AArch64, MIPSel and MIPS BE. ELF machine/endian and absence of PT_INTERP are checked. MIPS Go build metadata must say softfloat. Native/QEMU -h checks verify startup and the narrow standalone CLI, **not target hardware, kernel support, RAM or full ABI acceptance**. All build and overlay/source/lock digests are recorded in build-report.json. Phase2 client SHA256 matched between local WSL and independent GitHub Ubuntu runner; repeat Phase3 evidence records the same distinction from hardware acceptance.

## Security boundary

The lab entry point accepts only `-config-file /absolute/private/client.json` and help. Legacy secret argv flags, AWGM socket/log/protocol, RAW, socks, hash-check and interactive STDIN are unavailable. Password, call hash and account credentials come from owner-only regular 0600 files in non-symlink 0700 directories; wrong mode/UID/hardlink/symlink is rejected. Parent ancestors and privileged same-UID/root attackers are outside this file-permission boundary. Do not put secrets in filenames, environment or shell history; the program does not consume secret environment variables.

Upstream stdout, stderr, STDIN and core dumps are disabled before execution. This also suppresses HTTP error bodies, cookies, captcha protocol and vendor loggers; it deliberately removes upstream diagnostics rather than claiming a universal redactor. Only fixed status codes are written. Received WG config and captcha profiles use atomic 0600 writes within the private runtime directory. No plaintext config event or private key is printed. Account credential refresh is not unattended-ready; sessions are capped at 30 minutes. Treat runtime directory as private volatile storage, never a public report directory.

UDP bind is exclusive (upstream SO_REUSEADDR removed). Port/config/auth failures terminate with78; temporary worker failures have exponential backoff and a five-attempt bound, exit75 when exhausted. No router TUN or AWG Manager daemon is required for vpn mode. The linked awgmproto library remains MIT, with notice retained; control sockets are never initialized in this profile.

`CONFIG_READY` is only a file event. The local test also waits for `WORKER_REGISTERED`, emitted after UDP dispatcher registration, before starting the application. Neither event proves WG connectivity: the test separately requires handshake/counters and successful TCP/UDP. First CI run38146507134 built every architecture but failed the first TCP request with curl52 after GETCONF. Startup timing was a hypothesis; the explicit registration gate and separate literal-IP/DNS probes preserve that distinction rather than treating a config file as readiness.

Server patch020 requires AUTH password + known/bound device, and rejects unapproved first packets/failed GETCONF before UDP forwarding. The unchanged upstream fails three local negative tests; patched handler passes those plus the positive test. WRAP key to credential binding, production WRAP/DDoS and full gateway review remain open. Phase3 adds an expiring, pre-bound relay profile with active revocation and a separate main that never invokes those upstream subsystems; see [server candidate](server/README.md). A local AUTH test is not a complete server security audit.

## Local functional PoC

`lab/server_pair_fixture_test.go` is opt-in, loopback-only: Pion TURN, actual patched upstream WRAP/DTLS/GETCONF/AUTH handler, userspace WG netstack and private synthetic keys. It never invokes server main, OS TUN, routes, NAT, sysctl, Telegram or control API. `local_pair.py` connects the actual standalone client and Mihomo v1.19.32, then checks tunnel DNS, HTTP/TCP, SOCKS5 UDP echo 64/512/1000/1200/1400, WG handshake/counters, argv/log canaries and application failure after transport stop.

This passed locally with synthetic TURN credentials. **No VK, router, VPS, WAN packet capture, NAT traversal, real-provider MTU or reboot acceptance is claimed.** The test Mihomo is a digest-verified official compatible AMD64 asset used privately; it is not redistributed by this workflow. The ordinary AMD64 asset requires v3 CPU features on the local host and could not start; compatible asset was used explicitly.

## IPK / rollback / release gates

`ipk_recipe.py` builds deterministic Entware outer tar.gz with control/data archives with a version that includes source and binary SHA, versioned `/opt/libexec/wdtt-lab/` payload, notices and normalized provenance. Host paths and test timings are excluded from package inputs. ARM64 and MIPSel real ELF packages are built **only in private quarantine** and inspected. By default only JSON checksums/format evidence is retained; the owner can now request **explicit private local retention** with `verify_quarantine.py --retain-private-dir /absolute/path/wdtt-private-...` (outside the checkout and public outputs). This preserves installation-blocked quarantine IPKs and private SHA manifests for later technical inspection; neither CI nor the production feed uploads those packages. The `wt-client-quarantine` preinst intentionally returns exit 78, so these archives **cannot be installed by opkg** and must never be described as ready-to-use IPKs. Their Package is `wt-client-quarantine`; preinst always exits78 under dash and BusyBox. These are not installable candidates or a license bypass. No real IPK/binary is uploaded. Normal `wt-client-lab` emission still refuses all open release-gates.json and install_ready=false, without an install/publication override.

`license_audit.py` collects selected Go/S/embedded files for both target builds, module versions/sums, per-file SHA and copyright headers, ancestor license/NOTICE/PATENTS texts including the compiler runtime. NOTICE-COLLECTION is a **collection**, not a licensing approval. fhttp@v0.6.8 commit `ecfe905c2db9d1ec769a16a14191ec84553dd235` has tree `0269bf1f6abe7a103b173d07394b9894b356995f` (Phase2 called the commit a tree). No applicable LICENSE/COPYING/NOTICE was found; Go-derived BSD headers do not prove fork-specific licensing. No binary redistribution is enabled. Other module scope/exceptions and GPL corresponding-source delivery must also be approved before distribution. No silent dependency replacement or downgrade is used to claim closure. awgmproto MIT and root GPL notices are retained.

Build privately with the same SDK command above, then:

```sh
python3 wdtt/verify_quarantine.py --build /absolute/fresh-build-directory --report /absolute/fresh-build-directory/quarantine-ipk-report.json
# Локальный компьютер владельца, только в PRIVATE каталоге (не в git checkout):
# parent directory заранее существует; новый каталог wdtt-private-... не существует.
python3 wdtt/verify_quarantine.py --build /absolute/fresh-build-directory \
  --report /absolute/fresh-build-directory/quarantine-ipk-report.json \
  --retain-private-dir /home/USER/work/wdtt-private-phase3
```

KAS has a manual-only Entware lifecycle prototype with separate persistent/volatile paths, checksum/ABI/resource admission and verified own-PID stop/rollback/uninstall. Installation remains source-gated and hardware/reboot acceptance is NOT RUN. See [KAS Phase3](https://github.com/saymer-alt/keenetic-auto-setup/blob/feature/wdtt-experimental-poc-20261011/experimental/wdtt/PHASE3-HARDWARE.md). Do not edit gates to force a test tomorrow.

## Existing publication safety

Existing Mihomo/Beszel/WARPSCOUT workflows and scripts are unchanged. Their shared latest release writer lock is `entware-latest-publication`; each owns only its package glob, validates/uploads/verifies before old-set prune, notifies feedly with AGGREGATOR_PAT, then prunes. This workflow never invokes publish_ipks.py, references that secret, sends a package-built dispatch or writes to latest. Record release asset IDs/digests before/after; independent scheduled workflows may change latest while this experiment is running.

WG-obfuscator remains next after WDTT readiness; no new workflow/IPK here. CSQTT patch/results/PolyForm notices remain in the separate KAS research PR; no CSQTT package is created.

Package format and Installed-Size (uncompressed data-tar bytes) follow the pinned SDK `scripts/ipkg-build`, SHA256 `68f37a86b21ea5b8d765a42e9c08ce3ce87a925d99dc3114273730320aa3e5e1`. Format inspection is not an opkg installation test.
