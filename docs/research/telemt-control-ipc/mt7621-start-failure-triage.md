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
