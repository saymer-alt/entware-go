# MT7621 in-daemon IPC: third guest run startup failure (2026-11-17)

## Evidence and exact stopping point

- Immutable research PR: [entware-go Draft #58](https://github.com/saymer-alt/entware-go/pull/58) at commit `5cad7a2682df32f2670dfa582b3dc352706d673d`.
- [QEMU-system guest workflow 44066952376](https://github.com/saymer-alt/entware-go/actions/runs/44066952376), job `133983110489`, sanitized artifact `telemt-ipc-mt7621-guest-evidence` (artifact ID `14321412415`).
- **26 of 27 executed steps PASS; step 27 FAIL**: `RuntimeError: ssh_exit_nonzero_1` after ~31.07 s. Original plan contains 50 steps.
- Confirmed in real Ported KeeneticOS 5.1.8 / MT7621 guest: boots / Entware setup, pinned MIPSLE IPC IPK download, opkg installation of **separate** `telemt-ipc-lab` package, exact installed ELF SHA verification, synthetic loopback config, and negative control command against absent Unix socket (nonzero).
- **NOT PROVEN**: real daemon-ready/PID/socket, native IPC reload and stop, no-orphan cleanup, reboot/no-autostart, package rollback. Do not mark Issue #51 fixed.
- Accepted lab IPK `telemt-ipc-lab_3.5.17-1ipc1_mipsel-3.4.ipk` SHA-256 `5079390d513ebf118292323a8eb8f0e1beb663d0348147d7cea9f4d0d0865da9`; ELF SHA-256 `0d3dcce3b9922d5dbffc748045168def7420c770ed6b4336e5e67d418c6f7e66`. These pins MUST NOT change unless a distinct version is explicitly rebuilt and audited.

## Why a generic SSH failure is not enough to fix Core

Step 27 combines all of these checks in one SSH command:

1. `telemt-ipc-lab start --log-file ... --pid-file ... --control-socket ...` exits with code 0;
2. `/opt/var/run/telemt-ipc-lab/ctl.sock` is seen as a Unix socket within 30 s;
3. `/opt/var/run/telemt-ipc-lab.pid` is readable;
4. `/proc/$pid/exe` matches exactly `/opt/bin/telemt-ipc-lab`.

Its only sanitized error is `ssh_exit_nonzero_1`, which does **not** distinguish any of these. Source at pinned TeleMT `src/main.rs:56-75` and `src/daemon/mod.rs:116-152` confirms **classic double-fork before runtime startup**: the first `start` process can exit successfully while its detached grandchild fails later. The upstream `src/maestro/orchestrator.rs` source patch binds the opt-in socket **after** runtime/bootstrap, listeners, reload watcher and signal handler setup; therefore a missing control socket does not by itself prove an AF_UNIX failure.

In the research patch `local_control::private_parent()` requires an existing 0700 same-effective-UID directory and traverses every ancestor with `O_NOFOLLOW`. An Entware symlink, ownership/mode mismatch, or an early bootstrap failure could reject the socket; **none is confirmed yet**. The separate `test -S`/proc path and PID creation checks are other plausible failure points.

**Do not change the security checks, turn off `O_NOFOLLOW`, or replace the CLI with `kill(pidfile)` based on this result.** That would risk hiding the actual failure or reintroducing a PID-reuse vulnerability.

## Diagnostic contract for an explicitly authorized *next* guest visit

Separate acceptance into stages and return only fixed, echo-safe markers; do not upload the guest's raw stdout, `/opt/etc/telemt-lab.secret`, config, full command lines, UART, or app logs.

1. **Before start:** verify `/opt/lab` exists, socket parent exists/0700, `/opt/var/run` and its ancestor components are directories (not symlinks). Distinguish `IPC_PARENT_MISSING`, `IPC_PARENT_UNTRUSTED`, `IPC_PARENT_SYMLINK`, `IPC_PARENT_OK`.
2. **Start command exit:** record the immediate `start` exit code as a bounded category (`IPC_START_PARENT_OK` or `IPC_START_PARENT_NONZERO`); do not infer daemon readiness.
3. **After bounded wait:** check PID file readable and parseable, `/proc/$pid/exe` identity, socket file type with the guest's `test -S`, and a single active executable identity. Distinguish `IPC_NO_PIDFILE`, `IPC_PID_DEAD`, `IPC_EXE_MISMATCH`, `IPC_NO_SOCKET`, `IPC_SOCKET_AND_PROCESS_OK`.
4. **Only if not ready:** on the disposable guest, test **foreground mode** with separate lab PID/socket names and synthetic config. Capture bounded stderr/daemon output *inside the guest* and classify it to allowlisted constants such as `IPC_FS_PERMISSION_ERROR`, `IPC_CONFIG_ERROR`, `IPC_SOCKET_BIND_ERROR`, `IPC_OTHER_START_FAILURE` (do not report raw log content). Check for an already-running instance first, so no double bind or fabricated refusal. Record a capped exit/timeout result. Foreground errors are generally observable, unlike double-fork stderr redirected to `/dev/null`.
5. Check in advance on host that markers cannot be matched by the echoed command itself (existing `load_scenario` contract). Assert the diagnostic command is itself syntactically valid on BusyBox `ash`. Add small host unit tests for each diagnostic classification.
6. Only when the live daemon's PID/exe/socket are independently proven should `reload`, `stop`, reboot, and rollback tests run.

The guest should always fail closed on unexpected output, a mismatched guest image, wrong IPK/ELF hash, or an unsafe parent. No signals to PIDs read from stale files, no real Telegram upstream.

## Budget and next disposition

Three bounded full QEMU guest cycles were attempted for this research gate:

1. Run `44054630539`: scenario rejected **before boot** by the runner (literal newline in SSH command);
2. Run `44062158447`: 21 PASS / 22 executed, failed IPK wget before `/opt/lab` existed;
3. Run `44066952376`: 26 PASS / 27 executed, failed daemon readiness; **first real opportunity to investigate IPC startup**.

No fourth run automatically. The patched QEMU binary has now been independently SHA-checked and saved to the cache prior to guest execution, but cache availability is not permission to bypass the explicit budget or rerun without new evidence.

**Current gate:** `MIPSEL_IPC_LAB_IPK_BUILD=PASS`, `PORTed_MT7621_GUEST_PREP=PASS`, `IPC_DAEMON_READY=BLOCKED`, `IPC_RELOAD/STOP=NOT_TESTED`, `MERGE/RELEASE=NO`. Evidence notes are research-only; do not modify the frozen Core/Panel pins or actual routers.


## Implemented host-only diagnostic gates after the third guest attempt

- Commit `9f91cbce`: the previous aggregated step #27 is split into **seven ordered checks**. The harness now reports specific sanitized SSH exit statuses rather than a generic exit 1. It does **not** start TeleMT during host-only validation.
- Commit `c4fccd4a` plus the `d39e0249` host-test fix: `test_mt7621_guest_plan.py` runs seven cheap Python tests on the exact pinned `router-emulator` parser; test ordering, synthetic credentials, echo safety, one-line SSH command constraint, code mapping, and no fallback `kill(pidfile)`. The tests also deliberately inject malformed newlines and echo-unsafe markers and demand rejection.
- [Offline CI 44072301488](https://github.com/saymer-alt/entware-go/actions/runs/44072301488) **PASS (7/7 in 0.038 s)**. The `native-guest` job is **SKIPPED** because ordinary PR updates cannot authorize another QEMU-system guest cycle. A future human-applied `telemt-ipc-one-shot-qemu` label on Draft PR #58 triggers one eligible `pull_request/labeled` event. The label is not applied automatically. `workflow_dispatch` is unavailable until the workflow file exists on the default branch (which it must **not** be merged into solely to enable this test).


- The seventh test parses the entire generated SSH command collection with `/bin/sh -n -c`: syntax is checked but **no guest command is executed**, and no shell starts TeleMT. This catches malformed quotes, `case`, `while`, and shell redirections before any future QEMU run.

The new accepted exit-status mapping, visible as `RuntimeError: ssh_exit_nonzero_XX` in the sanitized guest report, is:

| Code | Exactly what failed |
| --- | --- |
| 41 | At least one control-socket ancestor is a symlink |
| 42 | Missing control-socket ancestor or a non-directory component |
| 43 | Control-socket parent is not in the expected private mode 0700 |
| 44 | Effective UID differs from control-socket parent owner |
| 45 | The immediate `telemt start` CLI returned nonzero |
| 46 | PID file did not become readable within 30 s |
| 47 | PID file content was not a positive decimal PID |
| 48 | `/proc/<pid>/cmdline` was not readable (child not alive or inaccessible) |
| 49 | `/proc/<pid>/exe` was not the expected pinned `telemt-ipc-lab` executable |
| 50 | Unix control socket did not appear within 30 s |
| 51 | Final simultaneous process/executable/socket consistency assertion failed |

These are **prospective categories, not evidence of which error actually occurred on run 44066952376**. The old run recorded only `ssh_exit_nonzero_1`, so it remains unclassified. The new code can be used only on a future explicitly authorized guest session. No runtime claims are upgraded by passing these host-only tests.

## Fourth native run: BusyBox stat diagnostic mismatch, NOT an IPC verdict

- [One-shot label-triggered native run 44075246012](https://github.com/saymer-alt/entware-go/actions/runs/44075246012), 2026-11-17; sanitized evidence artifact `14323414441`, committed head `f0f9867f8f1f4bf2be13268243ae90fb617c7327`. The actual Ported MT7621 4.9 guest executed **28 of 56 planned steps: 27 PASS / 1 FAIL**. The precise failure is `RuntimeError: ssh_exit_nonzero_43` at the *pre-daemon* step `IPC_PARENT_OWNER_MODE`. Earlier `IPC_PARENT_COMPONENTS_SAFE` passed. Installation and exact SHA checks of the frozen candidate IPK/ELF, synthetic config and absent socket negative command all passed again. **The daemon was never started; `stop/reload` remain NOT_TESTED.**
- The step used `/opt/bin/busybox stat -c %a` and `stat -c %u`. Entware's official [mipsel-3.4 configuration](https://github.com/Entware/Entware/blob/master/configs/mipsel-3.4.config) has `# CONFIG_BUSYBOX_DEFAULT_STAT is not set`, an excellent explanation for immediate 0.41-second code 43 even after the earlier synthetic fixture's `chmod 700`. **Do not infer the actual mode is insecure** and **do not relax Rust's socket-parent security contract**. The exact guest BusyBox applet listing was not preserved, so the precise 43 subcause remains unproven; this is a source-supported lab-harness diagnosis.
- Only the research fixture changed on commit `88f7dc23b5eff1523fa1560d402788a874d94ca2`: parent mode and numeric owner checks now use `/opt/bin/find ... -maxdepth 0 -printf %m` and `-printf %U` (GNU findutils) rather than a disabled BusyBox applet. The pinned emulator's `lab/entware-mipselsf.lock.json` includes `findutils` MIPSLE, and no extra package or feed modification is required.
- [Host-only test run 44076608873](https://github.com/saymer-alt/entware-go/actions/runs/44076608873) **9/9 PASS**: real emulator scenario parser, POSIX syntax, source/package pin constraints, explicit `findutils` lock inclusion, actual GNU find mode/numeric UID semantics, and negative parser tests. `native-guest=SKIPPED`. No fifth real guest run executed.
- The `telemt-ipc-one-shot-qemu` authorization label was removed from Draft PR #58 after the fourth run. A further full guest cycle requires a new deliberate label action and an evidence-based decision. Existing Core/Panel artifacts, source hashes, ARM64 and real routers remain unchanged.

## Fifth real guest: mode probe still blocked, lab dependency repaired

- [Explicit fifth QEMU-system run 44078210072](https://github.com/saymer-alt/entware-go/actions/runs/44078210072), pinned head `7bcc93311051d829d539fefefeca46f0142513cb`, sanitized artifact ID `14326535507`: 56 planned steps; **27 PASS / 28 executed, FAIL** at `IPC_PARENT_OWNER_MODE` with `RuntimeError: ssh_exit_nonzero_43`, 0.38 s for the failing step. The Linux 4.9 MT7621 guest booted; pinned lab IPK/ELF install and synthetic fixture, absent-socket rejection, and parent component checks passed. **TeleMT daemon was not started, native IPC stop/reload, reboot and uninstall remain NOT_TESTED.**
- The fifth preflight used `test -x /opt/bin/find` and GNU `find -printf %m`. Although `findutils` is **present in the pinned offline feed lock**, the minimal Entware guest bootstrap does **not prove it was installed**. The last 43 could mean the helper is absent, command error, or genuinely wrong directory mode; the sanitized report cannot disambiguate. This is a laboratory prerequisite/diagnostics gap, not evidence the Rust IPC is defective. `chmod 700` earlier passed in the guest.
- Research-only commit `010b27b824128f415972298a7c60a8007f5a5cd2` adds an **explicit** guest-local installation of pinned `findutils_4.10.0-1_mipsel-3.4.ipk` from the already frozen local mirror, checks package SHA-256 `03a9b78dc1f3fb257fbead58f95a56e9da5eb09db79e13faa46b2952b8e73f20`, opkg status and executable presence **before** the parent trust probes. Fails closed if the repo's existing lock has changed. The later mode check distinguishes: `52` missing helper, `53` GNU find mode invocation failed, `43` genuine `mode != 0700`, `54` GNU find owner invocation failed, `44` wrong numeric owner. Parent symlink rejection and security invariants remain intact.
- [Offline CI 44079464107](https://github.com/saymer-alt/entware-go/actions/runs/44079464107): **9/9 host-only tests PASS** on the pinned emulator's real parser, updated lock/pin assertions, GNU find semantics, shell syntax; `native-guest=SKIPPED`. This is **not** proof the installed guest helper worked (a next explicit native cycle is required).
- The fifth one-shot authorization label was **removed**. No sixth QEMU run authorized or executed. Stable/accepted Core and Panel files, the separate IPC IPK/ELF, upstream emulator SHA and physical devices remain untouched. Keep Draft PR #58 and Issue #51 open; guest IPC acceptance remains BLOCKED.

## Sixth real guest: GNU find probe exit, BusyBox-only fix

- [Sixth explicitly authorized QEMU-system run 44080117428](https://github.com/saymer-alt/entware-go/actions/runs/44080117428) (fixed head `fae843981eb711c16ec1644bb80ca654fef53871`), sanitized report artifact [14327256568](https://github.com/saymer-alt/entware-go/actions/runs/44080117428/artifacts/14327256568): **28 PASS / 29 executed**, `RuntimeError: ssh_exit_nonzero_53` at `IPC_PARENT_OWNER_MODE` (0.42s); elapsed 178.15s. Crucially, the new exact-sha **`IPC_FINDUTILS_INSTALLED=PASS`**, so the guest did install GNU findutils. All earlier boot/Entware, separate IPC IPK/ELF and synthetic fixture checks pass. `53` means the `/opt/bin/find ... -maxdepth 0 -printf %m` subprocess returned nonzero; no stderr was published, so the underlying reason is **not determined**. Actual directory permissions/ownership have not been disproved. **No daemon started, native IPC stop/reload/reboot/removal NOT_TESTED.**
- The experiment had successively relied on `busybox stat` (applet disabled), then GNU findutils available in the feed but not installed, and then GNU findutils actually installed but its mode query failed. Rather than chasing a second utility, research commit `a618e052a39c9e7e7d80d9c62d2c169a157b2810` uses the **already installed pinned BusyBox 1.38.0-5** with `busybox find PATH -maxdepth 0 -type d -perm 700 -print` for **exact** mode and `busybox find PATH -maxdepth 0 -type d -user "$uid" -print` for numeric owner. Its presence is protected by a lock-pinned SHA and an applet-list check. Captured stdout must be the exact target path: BusyBox `find` can return exit code 0 for **no match**, so exit-code alone is not a validation. Invocation errors are distinguished as 53/54, actual mismatches as 43/44, unavailable applet as 52. The GNU findutils install and its extra mirror dependency have been removed from the research scenario. Rust's `O_NOFOLLOW`/UID/0700 security contract is **not weakened**.
- Source cross-check: Entware's [MIPSLE BusyBox build config](https://github.com/Entware/Entware/blob/master/configs/mipsel-3.4.config) enables `CONFIG_BUSYBOX_DEFAULT_FIND=y` and `FEATURE_FIND_MAXDEPTH`, `FEATURE_FIND_PERM`, `FEATURE_FIND_TYPE`, `FEATURE_FIND_USER`, unlike `STAT`. The exact pinned guest BusyBox package is `busybox_1.38.0-5_mipsel-3.4.ipk` SHA-256 `0ba41200b8fdd51c2b606fc92c141059350cd3da7a45233eb0174aeaea1bfa32`.
- [Cheap CI 44081576144](https://github.com/saymer-alt/entware-go/actions/runs/44081576144) **9/9 PASS**, including actual host BusyBox `-perm` and `-user` positive/negative mode/owner controls, pinned emulator parser and one-line POSIX shell syntax. `native-guest=SKIPPED`; source, MIPSLE binary gate and publication/installer safety also PASS on `a618e05`. **No seventh full QEMU run launched or authorized**. Sixth authorization label consumed and removed; accepted Core/Panel and actual routers untouched. PR #58 remains Draft, Issue #51 BLOCKED until native Unix IPC is exercised.

## Seventh real MT7621 guest: daemon parent returned, PID did not stabilize

- [One-shot QEMU run 44082699704](https://github.com/saymer-alt/entware-go/actions/runs/44082699704), pinned head `7bbb3f8e4ac8c67b169d4b2eb1f2c4afea81fe6b`, sanitized [report artifact #14327378159](https://github.com/saymer-alt/entware-go/actions/runs/44082699704/artifacts/14327378159): **29 PASS of 30 executed, 56 planned**, `FAIL` at `IPC_PIDFILE_READY`, `RuntimeError: ssh_exit_nonzero_46`, after 30.94 seconds in the failing SSH step; total guest test 195.85 seconds. Boot, Entware, separate frozen IPC IPK opkg+installed ELF SHA, localhost fixture, absent-socket negative test, no-symlink parent, exact 0700 mode/numeric UID **all PASS**. Critically, **`IPC_START_RETURNED=PASS`**; thus the daemon CLI parent returned 0. However no readable `/opt/var/run/telemt-ipc-lab.pid` was observed before the 30 s timeout. **Do not claim the PID was never briefly created, or that the daemon child successfully initialized.** PID process identity, Unix control socket, stop/reload, reboot and uninstall still NOT_TESTED.
- Upstream TeleMT v3.5.17's `src/main.rs` uses double-fork before Tokio runtime, so the original parent exits 0 before the long-lived child completes startup. `src/maestro/mod.rs` then obtains a PID file with a RAII holder before calling the orchestrator. Child failure before PID acquisition, or a later runtime shutdown that removes the PID file, are both possible. The sanitized result cannot distinguish these or identify the exact error; it proves **only the absent/unreadable PID at the end of the timeout**. Original 93/93 accepted non-IPC TeleMT product suite is separate evidence and is not reclassified.
- Research-only commit `05b2fe38a3ad645be8df56cecf01ffc14611d8d7` adds **fail-closed, no-secret classification** directly in the PID readiness SSH step. Only a fixed exit code may leave the guest: `55` socket without PID; `56` pinned ELF still alive but PID absent; `57` PID observed then disappeared; `58` local log panic keyword; `59` local log permission/bind keyword; `60` other nonempty local log; `61` persistent sibling PID lock without PID; `46` none of the above. Do **not** print logfile, process command lines, synthetic secret, UART or raw stderr. The scenario's lock path matches upstream `pid_file.rs::sibling_lock_path` (`<pid>.lock`). No PID-file signaling or other unsafe stop workaround is introduced. This new diagnostic is not an explanation of the just-finished guest result; it can only classify **a future explicitly authorized run**.
- [Host-only CI 44084478933](https://github.com/saymer-alt/entware-go/actions/runs/44084478933): **10/10 PASS**, including native emulator's pinned scenario parser, POSIX shell syntax, PID classifier static safety contract and existing BusyBox mode/UID negative controls. `native-guest=SKIPPED`; other source/IPK and publication checks PASS. The one-shot label was removed following the seventh guest. **No eighth QEMU run launched or authorized.** Separate experimental ELF/IPK, original Core/Panel, pinned emulator, and physical Keenetic unaffected. Keep Draft PR #58 and Issue #51 BLOCKED pending native IPC acceptance.

## Eighth real guest: PID was readable but content was unavailable/invalid on next SSH

- [One-shot MT7621 kernel4.9 QEMU run 44086477281](https://github.com/saymer-alt/entware-go/actions/runs/44086477281), exact guest-source head `bf7fdf66a0dfd29986f971e6b1e98b13715d5f74`, sanitized [artifact #14329622748](https://github.com/saymer-alt/entware-go/actions/runs/44086477281/artifacts/14329622748): **30 PASS / 31 executed of 56 planned**, elapsed **180.25s**, failure `RuntimeError: ssh_exit_nonzero_47` at `IPC_CHILD_EXE_CONFIRMED` (0.36s). Notably, `IPC_PIDFILE_READY=PASS` immediately beforehand (0.32s), but that step checked **readability only**, not file contents, process identity, or persistence. The next SSH read returned an empty or nondecimal PID (or failed to read the file); all these possibilities map to 47 in that historical run. **Actual PID contents and precise child termination are not established.**
- The boot/Entware, pinned isolated IPC IPK/ELF, synthetic config, absent socket negative test, 0700/owner checks, double-fork parent exit 0 and initial PID-file readability all passed. **The daemon's live executable and Unix socket were NOT confirmed; kernel4.9 IPC stop/reload, reboot and rollback NOT_TESTED.**
- The upstream [TeleMT `PidFile::acquire`](https://github.com/telemt/telemt/blob/66708d2866f3f3a4541c4fa67984d408e71a8af4/src/daemon/pid_file.rs) writes a numeric PID to the file and the RAII guard releases it on shutdown; a child that shuts down soon after startup can cause a cross-SSH race. This is a plausible interpretation, **not proof** of a crash versus malformed contents.
- Research-only fix `935088d55062426f170f66bf12d55122355ea2f6`: the `IPC_PIDFILE_READY` step now waits until the content is a numeric PID, the *exact pinned* `/proc/$pid/exe` is alive, and both identity and PID remain the same after a **2-second stability check within the same SSH session**. Merely passing `test -r` no longer yields `PASS`. If the child is absent/unstable, the existing bounded, separate-path foreground diagnostic runs and returns a sanitized error category without exposing logs. On the subsequent separate identity check, **an absent/unreadable PID now maps to 57**, while 47 remains malformed or empty content. No untrusted PID-file signal or insecure cleanup was introduced. Frozen experimental binary/IPK, stable Core/Panel, and original emulator unchanged.
- [Host-only Actions 44088243812](https://github.com/saymer-alt/entware-go/actions/runs/44088243812) **12/12 PASS**, including scenario parser, POSIX shell syntax, identity/stability ordering and no-PID-kill safety checks; `native-guest=SKIPPED`. Other source, IPK and publication/installer safety workflows PASS. Eighth one-shot label removed, **ninth guest run NOT approved or started**. Draft PR #58 remains unaccepted, Issue #51 BLOCKED pending real stop/reload.

