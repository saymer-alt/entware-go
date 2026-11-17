# TeleMT MT7621 / Linux 4.9: in-daemon local stop/reload candidate

**STATUS: NATIVE MIPSLE LAB IPK BUILT, ABI PASS; QEMU-SYSTEM IPC ACCEPTANCE NOT YET PASS.**
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
