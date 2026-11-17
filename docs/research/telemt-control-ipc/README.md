# TeleMT MT7621 / Linux 4.9: in-daemon local stop/reload candidate

**STATUS (17.11.2026): MIPSel experimental IPK 3.5.17-1ipc2 built reproducibly; native QEMU MT7621 Linux 4.9 acceptance 63/63 PASS (run 44154378735); physical KN-1010 NOT_TESTED.**

**Physical hardware pilot:** [KN1010-HARDWARE-PILOT.md](KN1010-HARDWARE-PILOT.md) — SHA256-pinned experimental IPK, read-only preflight, isolated localhost fixture and safe teardown. Research package only; do not replace live TeleMT or publish a feed.

Tracking: [Issue #51](https://github.com/saymer-alt/entware-go/issues/51).
Existing host-only supervisor alternative: [Draft PR #57](https://github.com/saymer-alt/entware-go/pull/57).
Pinned upstream TeleMT SHA: `66708d2866f3f3a4541c4fa67984d408e71a8af4`.

## Why this candidate exists

The Linux 4.9 Ported MT7621 guest lacks `pidfd_open` and built-in
`telemt stop/reload` returns ENOSYS before signalling the daemon.
Replacing it with `kill(pid)` after a PID-file lookup is unsafe: PID reuse
could signal an unrelated process.

This source patch adds an **explicit opt-in** local Unix socket to the running
daemon and the existing `telemt stop/reload` CLI. It does not modify the
existing `src/daemon/pid_file.rs` code or automatically intercept ENOSYS.

## Proposed opt-in CLI (NOT available in existing IPKs)

The parent directory must already exist, have mode 0700, be owned by the
effective daemon UID, and contain no symlink parents.

```sh
# ONLY for a disposable test Linux guest, with synthetic config:
mkdir -m 700 /opt/var/run/telemt-control
/opt/bin/telemt start --control-socket /opt/var/run/telemt-control/ctl.sock --pid-file /opt/var/run/telemt-lab.pid /opt/etc/telemt-lab.toml
/opt/bin/telemt reload --control-socket /opt/var/run/telemt-control/ctl.sock
/opt/bin/telemt stop --control-socket /opt/var/run/telemt-control/ctl.sock
```

**Do NOT execute these commands against a production router or VPS.** No
current IPK includes this option.

## Implementation boundaries

- Only on Linux and only when `--control-socket` is explicitly supplied.
  Existing pidfd-based CLI is unchanged in behavior if the flag is absent.
- The client connects over a filesystem Unix socket in a private directory.
  Client and server verify the kernel-provided peer UID via `SO_PEERCRED`.
  Socket permissions are 0600 and unknown/stale endpoint paths are rejected.
- The running process itself accepts `S`/stop and `R`/reload. STOP sends an
  in-process message to the existing graceful shutdown path. RELOAD calls
  `raise(SIGHUP)` **from the same live process**, rather than signalling any
  PID read from a file. The watcher registers SIGHUP synchronously at
  construction time before the socket is exposed.
- Response `O` means *request accepted*, not shutdown or reload completed.
  Failure, timeout and denied access are nonzero CLI exits. A replacement
  endpoint is not unlinked during normal cleanup.
- Privilege-dropping must happen before binding the socket; bind only after
  the runtime's watcher/reload infrastructure has been prepared.
- No network listener, user credentials, package installs or autostart are
  added by this patch.

## Source patch verification (GitHub read-only research workflow)

On a disposable Linux checkout of the exact upstream SHA:

```sh
git apply --check telemt-3.5.17-mipsle-atomic64-compat.patch
git apply telemt-3.5.17-mipsle-atomic64-compat.patch
git apply --check telemt-3.5.17-daemon-control.patch
git apply telemt-3.5.17-daemon-control.patch
cargo fmt -- --check
cargo check --locked --tests
```

The existing `getrandom` ENOSYS fallback forks are separately assembled in
the accepted getfb build; this source patch does **not** build or alter them.
Exact original Core hashes and Panel hashes must remain untouched.

## Acceptance checklist / negative scenarios

1. Source patch applies **after** the exact original atomic64 patch to the
   pinned upstream tree, without editing/replacing that patch.
2. Host compilation, unit tests: absent socket, wrong owner/private mode,
   preexisting socket, client disconnect, bad opcode, stop path to Tokio
   graceful shutdown, socket replacement not unlinked.
3. Security review: symlink/parent replacement, same-UID threat model,
   privilege drop, timeout, SIGHUP watcher readiness, two concurrent requests,
   early daemon exit and stale socket crash recovery.
4. **New** MIPSel softfloat Core IPK/version/ELF digest; no reuse of
   `3.5.17-2fb1` accepted SHA pins and no changed old IPK.
5. One bounded real QEMU-system Ported 5.1.8 MT7621 cycle: actual builtin
   `telemt reload --control-socket`, `telemt stop --control-socket`,
   in-guest kernel 4.9, no orphan/double workers, Core/Panel health, native
   reboot, rc.unslung startup and safe cleanup. No raw-kill substitute.
6. Security advisory for pinned rustls and real Telegram upstream remain
   separate gates; neither is automatically resolved here.

**Non-goals:** production deployment, release, latest feed, PR merge,
rewriting security-critical Rust dependencies or bypassing safety guards.

STOP on unclassified failures. GitHub host PASS is not native QEMU PASS.

## Verified build and QEMU research, 2026-11-17

- [Experimental lab build 44050853817](https://github.com/saymer-alt/entware-go/actions/runs/44050853817): MIPSel Entware/softfloat/GLIBC 2.27, getrandom fallback gates PASS. Package `telemt-ipc-lab_3.5.17-1ipc1_mipsel-3.4.ipk` has SHA-256 `5079390d513ebf118292323a8eb8f0e1beb663d0348147d7cea9f4d0d0865da9`; ELF `0d3dcce3b9922d5dbffc748045168def7420c770ed6b4336e5e67d418c6f7e66`. It installs only `/opt/bin/telemt-ipc-lab`, no autostart or replacement for the already accepted telemt.
- [First QEMU run 44054630539](https://github.com/saymer-alt/entware-go/actions/runs/44054630539): guest **NOT_STARTED** because dynamically generated SSH command had a literal newline. Corrected and now validated by the emulator's real `load_scenario` before QEMU.
- [Second QEMU run 44062158447](https://github.com/saymer-alt/entware-go/actions/runs/44062158447): real Ported MT7621 4.9 guest boots, Entware initialized, **21/22 steps PASS**, first downloaded lab IPK (step 22) fails `ssh_exit_nonzero_1`: `/opt/lab/` directory was created only later by the synthetic config step. This is guest scenario ordering, **not a TeleMT runtime result**. Original first-hop mirror reports a dropped connection, consistent with wget output path not existing.
- Follow-up repair: explicit `mkdir -p /opt/lab` *before* wget, a cheap plan-only invariant, SHA-verified QEMU cache saved immediately after build (even if a later guest step fails). Unchanged source blobs verified before skipping redundant Rust host/full MIPSLE builds. Original 74/74 and 93/93 accepted proofs unchanged.
- Native socket `stop/reload`, post-reboot no-autostart and removal **remain NOT_TESTED until a guest run reaches those steps**. No real device/release/feed changes.


## Third true MT7621 run: daemon readiness blocked

The [third run, 44066952376](https://github.com/saymer-alt/entware-go/actions/runs/44066952376) completed with **26 PASS out of 27 executed steps** (50 planned). Unlike earlier fixture problems, the actual Ported 5.1.8 guest downloaded and installed the isolated `telemt-ipc-lab` IPK, verified the ELF SHA, installed the synthetic loopback-only config, and rejected absent socket commands correctly. It then failed **step 27**, the combined daemon start/PID/socket/`/proc/exe` readiness check after 31.07 seconds (`ssh_exit_nonzero_1`).

This does not identify which readiness condition failed. In particular, `telemt start` double-forks, so parent exit status alone cannot prove a live child or local IPC socket. **Neither `reload` nor `stop` ran; do not merge/ship or close Issue #51.** No raw stderr/console is preserved in the sanitized artifact.

See [focused post-mortem and diagnostic contract](mt7621-start-failure-triage.md) for separate parent-dir, PID, executable and Unix-socket probes and a foreground-only synthetic diagnostic. This is the **third bounded guest attempt**; no fourth guest cycle has been queued. QEMU executable was cache-saved immediately after its SHA check, before launching the guest, and source/IPK rebuild CI was skipped on unchanged hashes.

## One-shot QEMU authorization while PR #58 remains Draft

GitHub requires a `workflow_dispatch` workflow to be present in the default branch. This isolated research workflow is new in Draft PR #58, so its previous manual-dispatch gate could not actually be used. Do **not** merge the unaccepted code just to obtain a Run workflow button.

The guest workflow now uses a **one-shot PR label event**. To deliberately authorize a future full native MT7621 run, add the exact label `telemt-ipc-one-shot-qemu` to [Draft PR #58](https://github.com/saymer-alt/entware-go/pull/58) as a **new** label action. Ordinary PR updates, reviews and documentation commits run only the cheap host-only safety job; they cannot execute `native-guest`. The job additionally requires the exact PR number 58, same-repo head, pinned research branch and a fresh `labeled` event for that precise label. Once attached, the label does not automatically reauthorize guest cycles on later pushes. To authorize another run in the future, deliberately remove and re-apply the label, subject to the three-attempt budget and evidence review.

**No fourth guest run is currently authorized.** Stop/reload on kernel 4.9 remain NOT_TESTED and the lab PR stays Draft.

## Fourth guest result and portable mode probe

[Run 44075246012](https://github.com/saymer-alt/entware-go/actions/runs/44075246012) reached **27 PASS / 28 executed**, then failed code **43** before TeleMT daemon startup at socket-parent mode/owner preflight. The lab had used `/opt/bin/busybox stat`, although the Entware mipsel-3.4 BusyBox defaults disable `STAT`. This identifies a **test-harness portability mistake** as a plausible immediate cause; no code-level TeleMT failure has yet been proven.

Research commit `88f7dc2` replaces that check with pinned GNU `findutils` numeric mode `%m` and numeric UID `%U`, with no new package, no frozen binary change and no security bypass. [Host-only 44076608873](https://github.com/saymer-alt/entware-go/actions/runs/44076608873): **9/9 PASS**; `native-guest=SKIPPED`. One-shot authorization label consumed/removed after the fourth run. Further QEMU execution requires an explicit new authorization. Full details: [MT7621 post-mortem](mt7621-start-failure-triage.md).

## Fifth guest and pinned lab helper installation

[Run 44078210072](https://github.com/saymer-alt/entware-go/actions/runs/44078210072): 27 PASS of 28 steps executed, fails `ssh_exit_nonzero_43` again at mode-owner preflight, **before daemon start**. The source of code 43 cannot be proven from this sanitized report: `findutils` was in the immutable mirror but its *installation* in the minimal guest was not established. The earlier code had incorrectly treated lock presence as proof of runtime availability.

Commit `010b27b` **only changes the research harness**: downloads the precise, SHA-verified `findutils_4.10.0-1_mipsel-3.4.ipk` from the existing disposable lab mirror and installs it with opkg before inspecting 0700/owner; then separates missing-helper, helper error and actual directory mode codes. The frozen TeleMT IPC binary/IPK and Rust security checks have not changed. [Offline test 44079464107](https://github.com/saymer-alt/entware-go/actions/runs/44079464107): 9/9 PASS, native-guest SKIPPED. No sixth full guest run initiated. Details in [triage](mt7621-start-failure-triage.md).

## Sixth guest and BusyBox-only diagnostic preflight

[One-shot real guest run 44080117428](https://github.com/saymer-alt/entware-go/actions/runs/44080117428) reached **28/29 executed PASS**, then `ssh_exit_nonzero_53`: despite verified installation of GNU `findutils`, its `find -printf %m` command exited nonzero before any daemon start. The sanitized evidence does not reveal the precise error. The real parent mode/UID and kernel4.9 IPC stop/reload remain untested, not failed.

Commit `a618e05` now uses the already-installed, pinned BusyBox `find` applet for exact directory mode `-perm 700` and numeric owner `-user UID`, with exact-path output checks; no external findutils package is needed. This is **research-harness only**. [Offline host CI 44081576144](https://github.com/saymer-alt/entware-go/actions/runs/44081576144) **9/9 PASS**, including actual BusyBox positive/negative permission and owner tests. `native-guest=SKIPPED`. Sixth one-shot label was removed; seventh guest test has **not** been authorized or run. Full evidence: [triage](mt7621-start-failure-triage.md).

## Seventh guest — PID readiness failure after successful start CLI return

[Run 44082699704](https://github.com/saymer-alt/entware-go/actions/runs/44082699704) reached **29/30 executed PASS** of 56 planned steps. Strict BusyBox parent mode/UID preflight **PASS**, and `IPC_START_RETURNED=PASS`. The following 30 s PID-file readiness check failed with `ssh_exit_nonzero_46`. Since `start` double-forks, exit 0 from the initial process does **not** prove a running grandchild, and the PID file might have been removed during early shutdown. **Real IPC stop/reload and reboot/rollback have not run.**

Commit `05b2fe38` makes the PID readiness failure **diagnostic and sanitized** by distinguishing a transient PID, live ELF without PID, orphan socket, on-guest log class or sibling lock from a truly empty state; it exports *only error codes*, never the log or credentials. [Host-only CI 44084478933](https://github.com/saymer-alt/entware-go/actions/runs/44084478933) **10/10 PASS**, native-guest SKIPPED. Seventh one-shot authorization consumed/removed, eighth guest not launched. Detailed evidence: [triage](mt7621-start-failure-triage.md). Current PR remains Draft and cannot be merged as an IPC acceptance result.

## Eighth guest: transient/invalid PID across separate SSH checks

[Run 44086477281](https://github.com/saymer-alt/entware-go/actions/runs/44086477281): **30 PASS / 31 executed**, then code `47` at child PID parsing. The previous `IPC_PIDFILE_READY` had PASS in **0.32s** because it checked only file readability, not numeric contents or survival. The next SSH could not obtain a valid decimal PID. The exact cause (rapid PID removal, empty file or other contents) remains unknown; the daemon and IPC stop/reload are **not accepted**.

Commit `935088d` removes this premature-ready race: require numeric PID, live pinned `/proc/exe`, and same PID/executable after 2 seconds in **one SSH action**; otherwise attempt the already-prepared bounded, sanitized foreground diagnosis. An absent PID during the following identity check now returns distinct code `57`. [Host-only CI 44088243812](https://github.com/saymer-alt/entware-go/actions/runs/44088243812): **12/12 PASS, native-guest SKIPPED**. No ninth QEMU run approved. [Detailed evidence](mt7621-start-failure-triage.md).

## Ninth run and resilient Entware asset cache

[Run 44090600095](https://github.com/saymer-alt/entware-go/actions/runs/44090600095) stopped **before QEMU** while downloading the pinned Entware bootstrap installer: `urllib.error.URLError: <urlopen error timed out>`. No guest report exists, so this run **does not provide new evidence about the TeleMT daemon**.

Research commits `1e4e6e4`, `27767bb`, `9bba71d` add a separate, hash-verified GitHub Actions cache for **all 26 exact MIPSLE Entware assets**, bounded curl retries including timeouts, and safe copying into a fresh disposable guest workspace. Neither the emulator nor production TeleMT IPK/ELF changes. [Host-only CI 44092970076](https://github.com/saymer-alt/entware-go/actions/runs/44092970076) **14/14 PASS** (native-guest SKIPPED), all four workflows green. A tenth real guest cycle is still required to test stable PID, foreground diagnosis and IPC `stop/reload`; it has **not** been started. [Post-mortem](mt7621-start-failure-triage.md).

## Tenth guest — verified cache succeeded, BusyBox lacks timeout

[One-shot native MT7621 run 44097680620](https://github.com/saymer-alt/entware-go/actions/runs/44097680620): **29 PASS / 30 executed**, failure `ssh_exit_nonzero_69` before the diagnostic foreground launch because the guest's pinned BusyBox has **no `timeout` applet**. The new SHA-locked Entware prefetch/cache worked in this actual QEMU cycle: all **26 assets** verified and the cache was saved, no installer download timeout. Still **no native IPC stop/reload evidence**.

Research fix `d697637` uses the directly spawned, ownership-checked shell child (`$!`) with a 12-second observation window and bounded TERM + two-second grace, never a PID-file signal. It fails closed on unexpected process identity or termination. [Host-only tests 44099690272](https://github.com/saymer-alt/entware-go/actions/runs/44099690272): **15/15 PASS**, native-guest skipped. Draft remains BLOCKED, no eleventh full guest run initiated; [detailed evidence](mt7621-start-failure-triage.md).

## Eleventh MT7621 guest — foreground diagnostics reached, generic code 60

[Run 44100755605](https://github.com/saymer-alt/entware-go/actions/runs/44100755605): **29 PASS of 30 executed steps (56 planned)**. The new direct-child foreground fallback ran to completion after the normal daemon PID had failed its 2-second stable identity check. Its result was masked by a nonempty **ordinary main-daemon log**, yielding `ssh_exit_nonzero_60`. There is no evidence yet of a live IPC endpoint or actual `reload/stop`; this is an unclassified early subprocess completion, not proof of a Rust local IPC defect.

Commit `95f3aaa` makes the foreground subprocess's **own** exit class and output/log presence take precedence over main daemon log existence, without leaking any raw guest data. [Host-only CI 44102897741](https://github.com/saymer-alt/entware-go/actions/runs/44102897741) **16/16 PASS**, `native-guest=SKIPPED`. Run 11's one-shot label removed; run 12 not started. [Detailed triage](mt7621-start-failure-triage.md).
