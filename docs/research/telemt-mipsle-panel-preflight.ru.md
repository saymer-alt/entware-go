# MIPSLE TeleMT Panel: offline preflight and QEMU handoff

Status 2026-11-14: **research only**. No QEMU or physical KN-1913 validation; no IPK publication or installation.

## Candidates

| Candidate | Existing evidence | Outstanding |
| --- | --- | --- |
| Legacy `telemt-panel_0.6.2-1_mipsel-3.4.ipk` | Historical test IPK downloaded in #40; ELF32 MIPSLE and package metadata pass. Observed SHA256: `0cfb926660bf130fcc81e87c1ad40514d0f7ff2e0c1973cc9dbe7ad1928ab9a2` | Publisher provenance, dynamic dependencies, runtime, panel/API compatibility |
| New `telemt-panel-lite 1.0.0-rc.4` | Go pure cross-build MIPSLE host PASS in #40 at upstream SHA `758d155fe309ec99bea6df2544d0e3c5d1bb8ad4`; output 17,105,087 bytes | No preserved/packaged IPK, QEMU startup, RAM/latency, panel/API compatibility |
| TeleMT Core 3.5.17 | Separate #41 proved cross-check blocker (AtomicU64 / 32-bit usize) | Z AI separately ports core; no current MIPSLE Core IPK |

**Do not install historical test binaries on physical equipment solely on the basis of a matching hash.** SHA comparison identifies bytes seen in CI, not an authenticated software publisher.

## Offline preflight (desktop/CI host only)

Download candidate files from their documented sources, then inspect locally without executing them:

    python3 tools/telemt_mipsle_panel_preflight.py --kind old-panel --file ./telemt-panel_0.6.2-1_mipsel-3.4.ipk
    python3 tools/telemt_mipsle_panel_preflight.py --kind lite-rc4 --file ./telemt-panel-mipsle

The Lite command accepts an ELF32 binary; once an IPK exists, pass the IPK instead. Check the JSON status `STATIC_PREFLIGHT_PASS` or failure. Accepts original gzip/tar Entware IPK and ar container. For current scope, control/data must be gzip tarballs. The legacy SHA is pinned; `--skip-legacy-hash` is **only** for synthetic fixtures, never real user approval.

The tool checks package/architecture/version, ELF class/endianness/MIPS machine, interpreter/dynamic segments, unsafe paths, and unexpected active /opt/etc or /opt/var payload files. It does not execute archives, run post-install hooks, access network or devices, validate a Telegram session, or establish publisher authenticity.

Tests (12 synthetic cases checked on Python 3):

    python3 -m unittest discover -s tools/tests -p 'test_telemt_mipsle_panel_preflight.py' -v

## Handoff checklist for the MT7621 QEMU task

1. Only when MIPSLE guest is available: verify `uname -m`, `opkg print-architecture`, boot and filesystem state; take an isolated snapshot.
2. Verify interpreter `/opt/lib/ld.so.1` and old Panel shared dependencies **inside the guest**, never on a workstation with an unknown historical executable.
3. Test Lite and old panel separately: version/help, cold start, RSS/PSS, response time and exit behavior under 256 MiB available RAM.
4. Use synthetic TeleMT API fixtures and non-secret dummy users only; test UI read, limits, failures, authorization, LAN-only binding. Never point the test panel at the home/prod TeleMT.
5. Verify real `opkg` install/rollback and negative ARM64-on-MIPS arch refusal. Package must preserve existing /opt/etc and not enable an unexpected service.
6. Record separate statuses: static preflight, host build, QEMU runtime, opkg lifecycle, hardware field; **no production distribution** before verified Core+Panel integration and explicit owner authorization.

Related: [Issue #37](https://github.com/saymer-alt/entware-go/issues/37), [Panel PoC #40](https://github.com/saymer-alt/entware-go/pull/40), [Core PoC #41](https://github.com/saymer-alt/entware-go/pull/41).

Scope: isolated panel preflight only; no changes to Core agent work, upstream sources, ARM64 release workflows, feed, latest release, production routers or router-emulator work.
