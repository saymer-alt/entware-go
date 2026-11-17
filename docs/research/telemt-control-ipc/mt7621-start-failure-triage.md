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


## Ninth one-shot: pre-guest Entware network timeout, NOT an MT7621 runtime failure

- [Ninth label-authorized workflow 44090600095](https://github.com/saymer-alt/entware-go/actions/runs/44090600095), exact head `7d43144cc48de3b54c009c87c52958c82dd5a0d0`, 2026-11-17: `safety=SUCCESS`, `native-guest=FAILURE` **before QEMU or any guest command**. Source SHA, frozen IPC IPK/ELF checksum, QEMU binary/cache SHA, Ported image downloads, disposable NAND and SSH credentials setup all completed. In `mt7621_guest.py -> lab.build_entware.build() -> fetch()`, `urllib.request.urlopen(url, timeout=90)` for pinned `EN_mipsel-installer.tar.gz` timed out: `urllib.error.URLError: <urlopen error timed out>`. The existing emulator downloader only retried particular HTTP status codes, not this network timeout. There was **no guest report/artifact**; job uploader explicitly warned `No files were found`. There is **no new PID, foreground, process, or IPC stop/reload evidence** from run 9.
- No change to `saymer-alt/router-emulator` SHA `64a446deaacb0bca10d6053781ff1f7ad4a29552`, accepted stable Core/Panel, frozen separate IPC IPK/ELF, or real routers.
- On the Draft PR research branch, added `prefetch_entware_assets.py` at `1e4e6e4`, wired the one-shot native workflow and fresh-workspace guest fixture at `27767bb`, and fixed the strict archive-name regex to accept the real `opkg_2025.11.05~80503d94-1_mipsel-3.4.ipk` at `9bba71d55ba87e0d8cdd8b5d688fc15fa8f9d748`. The pipeline now *before* expensive guest execution restores the shared GitHub Actions cache keyed to the **exact pinned mipselsf lock**, verifies **all 26 public asset SHA256 digests**, fetches missing files with bounded curl retries including transient network failures, and **saves the verified cache before any QEMU guest work**. A new, separate external cache is copied into the *fresh* per-run private workspace only after its existing `exist_ok=False` boundary; no credentials, UART, log or guest config can enter the shared cache. A hash mismatch, symlink or unexpected extra file fails closed.
- [Host-only CI 44092970076](https://github.com/saymer-alt/entware-go/actions/runs/44092970076) **14/14 PASS**, with pinned-lock manifest check `PINNED_ENTWARE_ASSET_PLAN_PASS count=26`; all four latest workflows SUCCESS, `native-guest=SKIPPED`. This proves syntax, manifest, hash and cache invariants **but does not prove a real network prefetch or QEMU boot on this new revision**.
- One-shot authorization label consumed and removed after the ninth invocation. **No tenth QEMU guest cycle launched or authorized**. Issue #51 and Draft PR #58 remain blocked pending actual in-daemon kernel4.9 `stop/reload` acceptance; no release or merge.


## Tenth native guest: no BusyBox timeout applet, foreground not yet executed

- [Tenth one-shot native run 44097680620](https://github.com/saymer-alt/entware-go/actions/runs/44097680620), fixed head `3a19b7b7b6c4768c73b8aa31e36f90810f9c8c31`, sanitized [artifact 14335925307](https://github.com/saymer-alt/entware-go/actions/runs/44097680620/artifacts/14335925307): **29 PASS / 30 executed of 56 planned**, guest cycle **256.95 s**. Failure `RuntimeError: ssh_exit_nonzero_69` in the `IPC_PIDFILE_READY` SSH step after 34.32 s. Its code path checks `/opt/bin/busybox --list | grep -qx timeout || exit 69` before starting the diagnostic foreground process. Therefore the real pinned Entware BusyBox in the guest did **not** expose the `timeout` applet. **No bounded foreground TeleMT diagnosis ran.** Stable numeric PID + live pinned `/proc/exe` over two seconds was not established; preceding boot/IPK/ELF SHA/config/private-parent/CLI-parent checks passed. Real IPC `reload/stop`, reboot and rollback remain NOT_TESTED. Do not infer a TeleMT IPC failure from code 69.
- **The Entware prefetch/cache fix is confirmed in an actual run**: native workflow `Prefetch and verify every pinned Entware input before QEMU = SUCCESS` with `PINNED_ENTWARE_ASSET_CACHE_PASS count=26`, and `Save verified Entware cache before QEMU = SUCCESS`. The subsequent `lab.build_entware.build` stage and QEMU guest boot succeeded; the ninth run's earlier installer download timeout did not recur. The cache contains only SHA-locked public packages, no credentials, raw guest logs or images.
- Research-only commit `d697637d6587fb7b45d792270b3983d5b52b0008` **removes** dependence on the absent BusyBox `timeout` applet: when detached daemon PID readiness is not confirmed, the disposable guest launches the *separate* foreground diagnostic directly as a shell child (`fg_pid=$!`), sleeps at most 12 seconds before checking `/proc/$fg_pid/exe` against the pinned binary, and sends `SIGTERM` **only to that verified direct child, never to an untrusted PID from a PID file**. It observes termination for two more seconds and refuses to signal on unverified identity (code `71`) or ambiguous/failed termination (code `72`). The shell retains ownership of the child until `wait`, preventing PID-reuse by ordinary unreaped direct-child semantics. No `kill -9`, `pkill`, `kill(pidfile)`, insecure fallback, or production code change. Existing sanitized foreground log classification is retained (codes 62–68,70); code 69 is historical/retired from the active plan.
- [Host-only CI 44099690272](https://github.com/saymer-alt/entware-go/actions/runs/44099690272): **15/15 PASS** on the real pinned emulator parser, shell syntax, exact test sequencing, no-PID-file-kill restrictions, and an *executed* POSIX direct-child SIGTERM identity control using a disposable host `/bin/sleep`. `native-guest=SKIPPED`; other source/IPK and publication checks SUCCESS. This **does not yet establish** the new child controller's behavior on the MIPSLE guest. One-shot label removed, **no eleventh QEMU run authorized or launched**. Draft PR #58 remains unaccepted and Issue #51 BLOCKED.


## Eleventh real MT7621 guest: foreground exit but generic main-log code 60

- [Eleventh explicitly authorized QEMU-system run 44100755605](https://github.com/saymer-alt/entware-go/actions/runs/44100755605), pinned guest SHA `82bab34fcc7fe966c8ec89b5d789d8bbb308e0f5`, sanitized [artifact #14336232786](https://github.com/saymer-alt/entware-go/actions/runs/44100755605/artifacts/14336232786): **29 PASS / 30 executed of 56 planned**, total guest **210.34 seconds**. `FAIL` at `IPC_PIDFILE_READY`, `RuntimeError: ssh_exit_nonzero_60`, failing SSH action **45.6 seconds**. Real Entware cache restore/verify **PASS** on all 26 immutable assets, guest boot/Entware, separate frozen IPC IPK/ELF, synthetic config, absent-socket negative test, strict 0700/owner and detached CLI parent return **PASS**. The 2-second stable pinned numeric PID/executable readiness was not achieved.
- Unlike run 10's missing BusyBox `timeout`, the run 11 fallback made it through the **direct-shell-child foreground diagnostic** and its exit/error-categorization checks. The command waited 12s, then `wait "$fg_pid"` completed without the `fg_timed=1` condition and without matching the known panic, filesystem/bind, config parse, missing file, unsupported syscall or clean-exit codes. The pre-existing main-daemon `LOG` file was nonempty, so the then-last general fallback `[ -s LOG ] && exit 60` won. This indicates an unclassified **early foreground subprocess completion**, not a proven error in local IPC. The exact shell exit status and source of log text are **not exported**, so neither a crash nor a specific Rust error may be asserted. There is **no verified live daemon, Unix control socket, IPC `reload/stop`, reboot or rollback**. No production change was made.
- Research harness-only commit `95f3aaa050004e617b9bafa13a72f071de65903a` fixes the **classification-order bug**: after known error signatures and clean-exit/success handling, classify foreground shell status `132/134/137/139` as signal-like (**code 73**, not proof of signal), `126/127` as launcher/exec (**74**), nonempty *foreground* captured stdout/stderr (**75**) or its separate file log (**76**) **before** allowing the original detached daemon's routine log to yield `60`. The original generic fallback and transient PID classifications remain fail closed. Foreground child remains owned by the test shell, identity checked via `/proc/$fg_pid/exe` before TERM, never an untrusted PID-file signal. The harness continues to export **fixed numeric codes only**, no raw log/config, secret, process arguments or UART.
- [Host-only CI 44102897741](https://github.com/saymer-alt/entware-go/actions/runs/44102897741): **16/16 PASS**, native emulator parser + POSIX shell syntax, direct-child ownership, no PID-file signalling, strict startup preflight, classification precedence. All four workflows completed SUCCESS with `native-guest=SKIPPED`. This is **not** kernel4.9 IPC acceptance on the updated head.
- The eleventh one-shot label has been **removed**. **No twelfth QEMU run approved or launched.** Stable TeleMT Core/Panel, frozen experimental IPC ELF/IPK and pinned emulator checkout remain untouched. Draft PR #58 and Issue #51 remain BLOCKED until the actual Unix IPC `reload/stop` plus reboot/rollback tests can pass.


## Twelfth guest plan: comparative A/B/C foreground diagnosis (2026-11-17)

Hypothesis set before the run (from source reading of upstream `66708d2` and
the research patch):

1. **H1 (leading):** the experimental child reaches `LocalControl::bind`
   (last startup step before `wait_for_shutdown`) and that bind fails with an
   io error. In daemonized mode stderr goes to `/dev/null`, so the child exits
   orderly (RAII removes the PID file — consistent with runs 7/8/11: no panic
   or permission keyword in the nonempty main log, sibling lock also gone).
   In foreground mode the exact error text lands in the captured `.out` file.
2. **H2:** the lab build itself regressed somewhere the accepted build did
   not; the child then dies with or without `--control-socket`.
3. **H3:** the child survives to `wait_for_shutdown` and is killed or
   gracefully shut down by an external signal; the tracing log would then
   contain `Received shutdown signal` / `Shutting down`.
4. **H4:** the current lab environment is subtly broken and even the accepted
   binary would now fail; the accepted binary is run in the same session as a
   live control.

Key source facts this diagnosis relies on (upstream `66708d2`):

- The accepted 74/74 scenario *did* start the same guest daemonized with the
  accepted Core (`TELEMT_STARTED`, `DAEMON_PROC_ALIVE`, `SOCKETS_LISTENING`,
  `STABLE_AFTER_10S` all PASS), so double-fork, PID file, Tokio runtime and
  tracing file logging work on kernel 4.9 with the accepted bytes.
- `main.rs` double-forks before the runtime; `maestro::run_inner` acquires
  the PID file before `run_telemt_core`; `LocalControl::bind` runs only after
  bootstrap, listeners and the watcher; every error returns through `main`,
  prints `Error: …` to stderr, and exits 1 (RAII cleanup).
- `--control-socket` reaches the start path through both patched parsers
  (`cli.rs` second loop and `daemon_commands.rs::parse_daemon_args`).
- The accepted frozen Core IPK `telemt_3.5.17-2fb1_mipsel-3.4.ipk`
  (outer SHA-256 `2c8a84fb…85d8d`, ELF `d4ba4381…b216f`) was re-verified out
  of band against the same ABI audit the guest uses (softfloat, `/opt/lib/ld.so.1`).

New static scenario steps (no new diagnostic exit codes 41–76 are consumed;
every new step exits 0 and reports only sanitized markers):

- `IPC_CORE_OPKG`: SHA-pinned accepted Core install from the same mirror.
- `IPC_FGA_<d>_<status>` / `IPC_FGB_<status…>` / `IPC_FGC_<status…>`: bounded
  12 s foreground runs of A (accepted Core), B (lab binary, no flag) and C
  (lab binary, `--control-socket …/ctl-fg.sock`), strictly sequential, each a
  verified direct shell child (`$!`), identity-checked via `/proc/$fgp/exe`
  before a bounded TERM. `<d>` encodes 0 healthy, 1 control socket missing
  (C), 2 listeners not LISTENing, 3 both, 9 early exit; `<status>` is the raw
  `wait` status or `W` when TERM did not terminate within 10 s.
- `IPC_CLS_<a>_<b>_<c>`: per-variant numeric content-classification masks of
  the captured `.out`/`.log` files (1 banner, 2 Error:, 4 panic, 8 os error,
  16 permission, 32 control-socket text, 64 tracing initialised, 128 graceful
  shutdown, 256 shutdown signal, 512 address-in-use, 1024 missing file,
  2048 output nonempty). Every grep is `-q`-quiet; no content leaves the guest.
- `IPC_DLOG_<mask>`: the same milestone probing for the *detached* daemon's
  own log right after the existing `IPC_START_RETURNED` step, so a repeat of
  the run-7/8/11 failure is finally localised (died before tracing, died
  after listeners, received a shutdown signal, panic, unsupported syscall…).

Expected discriminations: A=0/B=0/C=9_1 with C-class mask bit 32 or 8 → H1
(bind failure, exact Rust error classified); A=0/B=9_x → H2 (build
regression, B's mask localises it); any `8`/`16` shutdown bits in logs → H3;
A failing → H4 (environment re-check against the 74/74 evidence).

Host-only validation before the run: emulator `load_scenario` accepts the 62
step plan (`PINNED_IPC_GUEST_PLAN_PASS`), all SSH commands parse under POSIX
`/bin/sh -n` (and busybox `ash -n` locally), 20/20 logic tests pass (the two
`/bin/sh` execution tests run only on Linux CI), classification masks were
exercised against synthetic captured files, and a non-quiet grep leak in the
first draft of the classification step was caught and fixed (all greps now
quiet; test `test_diagnosis_greps_are_quiet_and_never_emit_guest_content`).
The one-shot `telemt-ipc-one-shot-qemu` label must still be applied
deliberately; ordinary commits cannot start QEMU.

## Twelfth guest result: the candidate is IPC-specific; accepted and flagless variants are healthy (2026-11-17)

[Run 44116455403](https://github.com/saymer-alt/entware-go/actions/runs/44116455403),
sanitized artifact 14344076596, head `023f95c`, 62 planned steps: **35 PASS, FAIL
at step 36** (`IPC_PIDFILE_READY`, `ssh_exit_nonzero_75`, 47.12 s). New evidence:

- `IPC_CORE_OPKG` PASS: the frozen accepted Core `3.5.17-2fb1` installs beside the
  lab package exactly as pinned.
- **All three bounded foreground probes executed** (elapsed 13.57 / 13.55 / 12.40 s).
  The detached `IPC_START_RETURNED` parent again exited 0 and `IPC_DLOG` ran;
  the detached daemon still failed the stable-PID readiness contract, and its
  fallback foreground child died early with **nonempty, unclassified captured
  output** (code 75: no panic, no permission/with-space, no config, no missing-file,
  no enosys wording).
- The report/junit export only action/outcome/elapsed — the A/B/C markers were
  matched in memory and are not preserved, so variant health cannot be asserted
  from this run's artifact alone. The design conclusion stands regardless: the
  next run must export verdicts through SSH exit codes, the only free-form field
  in the sanitized report (`ssh_exit_nonzero_<n>`).

Source work between runs:

- Upstream `wait_for_shutdown_signal` registers SIGINT/SIGTERM/SIGQUIT and waits,
  so a child that reaches it stays alive — the observed early orderly death
  (RAII PID cleanup, no panic in the log) fits an `Error: …` return that is
  silently discarded by the double fork's `/dev/null` stderr.
- `opt-ndmsv2` (the Keenetic Entware structure package) ships `/opt/var` and
  `/opt/var/run` as **0755**, and a local WSL `mkfs.ext4 -d` test shows the image
  root is 0755 root — the ancestor-trust hypothesis is now weak, but the lab
  created `/opt/var/run/telemt-ipc-lab` with the session umask and never
  measured it; `validate_trusted_directory` walks **every** ancestor with
  O_NOFOLLOW and rejects group/world-writable or non-root-owned components.
  Crucially, that validation runs **only** in variant C (the client-side
  `private_parent` also fails closed, so `IPC_ABSENT_REJECTED`'s nonzero exit
  is ambiguous by design and never proved the trust chain was fine).
- The first foreground C attempt in run 12 left the stale `ctl-fg.sock` behind
  (bind succeeds, then an orderly error exit skips `close()`), so the separate
  fallback probe in `IPC_PIDFILE_READY` may have failed on
  *"control socket path already exists"* instead of the original cause — its
  unclassified output (75) is therefore contaminated evidence.

## Thirteenth guest plan: verdict exit codes + ancestor normalization (2026-11-17)

Research-only changes (`fg_probe_step` rewrite, synthetic-step normalization):

1. **Ancestor normalization** (lab repair, not a security weakening): the
   synthetic-config step now also `chmod 755 /opt/lab /opt/var /opt/var/run
   /opt/var/log /opt/etc` — the same modes `opt-ndmsv2` ships on real installs —
   before any binary runs.
2. **Stale-socket hygiene**: the C probe removes its own disposable
   `ctl-fg.sock` before starting and after a confirmed child death, so the
   separate fallback probe sees a fresh path.
3. **Fail-closed verdict export** through SSH exit status, per variant:
   A = 120+n, B = 136+n, C = 152+n with n ∈ 0..15 (0 control-socket wording,
   1 permission/ownership wording, 2 missing path, 3 address-in-use, 4 panic,
   5 unsupported syscall, 6 generic `Error:`, 7 silent-but-log-nonempty,
   8 fully silent orderly exit, 9 fully silent signal-status exit, 10-12
   alive-but-degraded, 13 TERM wedged after two bounded rounds (then a
   verified-direct-child KILL keeps the lab clean), 14 TERMed nonzero,
   15 nonempty unclassified output). Healthy exits 0 with an
   `IPC_FG<tag>_HEALTHY` marker.

Expected discriminations: A/B PASS + C = 152+0/152+1 → the Rust IPC trust
validation is the blocker and the class names the message; C = 152+2/152+3 →
path/bind mechanics; C PASS but detached still failing → daemonize-specific;
A/B/C all PASS and full detached acceptance completes → the guest environment
was the root cause and the run doubles as native IPC acceptance.

## Fourteenth guest result: ROOT CAUSE CONFIRMED (2026-11-17)

[Run 44126323538](https://github.com/saymer-alt/entware-go/actions/runs/44126323538),
sanitized artifact (report.json): 28 executed steps, 27 PASS, FAIL at the new
`IPC_ANCESTORS_TRUSTED` preflight with **`ssh_exit_nonzero_110`** — the
**firmware root "/" violates `validate_trusted_directory`** (owned by root or
not, and group/world-writable without a compensating sticky bit) **and the
chown 0:0 + chmod 755 repair did not clear the violation** (the second
verification failed, so the root filesystem is read-only; a writable root
would have accepted a root chmod). Code 110 is emitted only after the repair
attempt failed, so this is not a transient.

This closes the investigation opened after guest run 3:

- `local_control::private_parent` calls upstream `AnchoredPath::open_trusted_parent`,
  which walks the **entire** absolute path with `O_NOFOLLOW` and applies the
  trust rule to **every** component, starting at `/`.
- On the Ported KeeneticOS 5.1.8 MT7621 guest (and, by firmware identity, on
  real Keenetic MT7621 devices) `/` itself does not satisfy that rule and
  cannot be repaired, so **every** opt-in control-socket bind fails with
  `Custom { kind: PermissionDenied, error: "directory path is not owned and
  protected from group/world writes" }`, the daemon child returns an orderly
  error, the double-fork discards stderr, RAII removes the PID file — exactly
  the silent early death of runs 7, 8, 11 and 12's detached step (code 75),
  and exactly variant-C-only behavior (runs 13: A=HEALTHY, B=HEALTHY, C=153).
- The client-side `stop --control-socket` fails the same way, which is why the
  historical `IPC_ABSENT_REJECTED` PASS was ambiguous and never proved the
  trust chain was satisfiable.
- Everything else was methodically excluded: build recipe identical to the
  accepted Core (same rustc pin, sysroot alias, gates), the SIGHUP watcher
  change compiles into both A/B and B stays healthy, stale-socket
  "already exists" contamination was removed as a factor, and the /opt
  subdirs plus the ext4 image root (0755 root, verified by replicating the
  exact CI `mkfs.ext4 -d` command in WSL) all satisfy the rule.

**Fix direction (research patch, not upstream security weakening):** the
namespace root is a mount boundary — its directory entry cannot be renamed,
removed, or exchanged through any parent, so a permissive `/` gives no path
redirection vector into `/opt/...`. The patch will anchor the trust walk
below the root: validate every component from the first mount point downward
(unchanged rule), skip only the root's own validation, and document why.
Private-parent 0700 + same-UID + no-symlink requirements are unchanged.

## Fix candidate 1ipc2: mount-boundary root trust (2026-11-17)

Per the review guidance the fix is a **targeted exception for the root only**,
never a blanket disabling of the trust rule, and it is verified host-first:

- New opt-in constructor `AnchoredPath::open_trusted_parent_below_root`
  (research patch to `src/util/secure_fs/path.rs`): the walk keeps the
  unchanged `O_NOFOLLOW`, owner and mode validation for **every** component
  below the root. The root component alone is accepted when it satisfies the
  ordinary rule **or** when `statvfs("/")` reports `ST_RDONLY`; a writable
  root that violates the ordinary rule, and any statvfs failure, still fail
  closed. `open_trusted_parent` and all other callers are byte-identical.
- `local_control::private_parent` switches to the boundary constructor with
  the platform rationale documented in code; the 0700 same-UID private
  parent, stale-socket refusal, `MSG_NOSIGNAL`, `SO_PEERCRED` and
  no-PID-signalling rules are untouched.
- Host verification before any QEMU: patched tree `cargo check --locked
  --tests` PASS, `daemon::local_control::tests` 5/5 PASS, secure_fs suite
  11/11 PASS (4 new tests: boundary constructor agrees with the ordinary
  rule on plain hosts, still rejects symlinks and group-writable dirs below
  the root, and the statvfs probe answers), `rustfmt --check` clean on both
  patched files; CI source gate repeated all of it on ubuntu (`44139876704`).
- Lab version bumped to `3.5.17-1ipc2`; frozen 1ipc1 ELF/IPK pins stay frozen
  and unused. New candidate from run `44139876820`, verified out-of-band:
  IPK SHA-256 `fbf5ef4c2cad4a564483c29a584986623181574b798ec5b787cdc93c27e15daa`,
  ELF SHA-256 `a83caf105dd77248de43c9e096f8248ce3851b322dfe6dd59a934801344d9506`,
  softfloat `/opt/lib/ld.so.1` ABI, payload only `/opt/bin/telemt-ipc-lab`.
- The guest preflight is now **diagnose-only**: it records the original
  ancestor facts (owner, group/world-writable, sticky) plus the
  `/proc/mounts` read-only flag of `/` and fails closed on contradictions
  (110 root violating and not read-only; 111-114 non-root or group/world
  writable ancestors or a wrong private dir; 115 no find applet) without any
  chmod/chown. The synthetic step creates ancestor directories with
  `mkdir -m 755` instead of post-hoc normalization.

Fifteenth guest plan (one-shot label, final run of the session budget): boot,
Entware, 1ipc2 install + ELF SHA, diagnose-only preflight, A/B/C probes with
verdict codes, then the full detached acceptance chain — stable PID/ELF,
control socket, `reload` (same PID + SIGHUP marker), unsafe-parent rejection,
no implicit pidfd fallback, empty-path rejection, IPC `stop` cleanliness,
second `stop` rejection, native reboot with no autostart, manual restart and
opkg rollback.

## Fifteenth guest result: the entire IPC acceptance chain PASSED (2026-11-17)

[Run 44146539784](https://github.com/saymer-alt/entware-go/actions/runs/44146539784),
head `ea888a8`, sanitized report: **58 of 59 executed steps PASS**, run stopped
at the first after-reboot assertion. The real Ported 5.1.8 MT7621 kernel-4.9
guest proved, with the `1ipc2` mount-boundary candidate:

- `IPC_ANCESTORS_TRUSTED`: the diagnose-only preflight measured the expected
  platform signature (root violating the ordinary rule while
  `/proc/mounts` shows it read-only; every component below the root trusted)
  with **no repair attempt** — the exact facts behind the root cause;
- `IPC_FGA_HEALTHY`, `IPC_FGB_HEALTHY`, `IPC_FGC_HEALTHY`: all three bounded
  foreground variants healthy, **including C with the control socket** —
  the mount-boundary fix works on the real guest;
- detached daemon readiness: `IPC_START_RETURNED`, `IPC_PIDFILE_READY`
  (stable numeric PID + pinned `/proc/exe` + 2 s stability),
  `IPC_CHILD_EXE_CONFIRMED`, `IPC_CONTROL_SOCKET_READY`, `IPC_DAEMON_ALIVE`;
- **native in-daemon IPC on kernel 4.9**: `IPC_RELOAD_SAME_PID`
  (same PID after reload), `IPC_UNSAFE_PARENT_REJECTED`,
  `IPC_NO_IMPLICIT_PIDFD_FALLBACK`, `IPC_EMPTY_PATH_REJECTED`,
  `IPC_STOP_CLEAN` (no orphan, no socket), `IPC_SECOND_STOP_REJECTED`;
- native reboot completed (`Activated system reboot` … `MARK42`, `/opt ext4`).

The only FAIL (`IPC_REBOOT_NO_AUTOSTART`, `ssh_exit_nonzero_1`) is a **harness
defect, not a TeleMT result**: the reboot block still grepped for the stale
`Version: 3.5.17-1ipc1` while the installed candidate is `3.5.17-1ipc2`, so
`opkg status | grep` deterministically returned 1. Commit `c4c374a` replaces
the last version reference and adds a host guard test that fails the suite on
any stale lab version in the scenario. `IPC_REBOOT_ABSENT_REJECTED`,
`IPC_REBOOT_MANUAL_START`, `IPC_REBOOT_STOP_CLEAN` and `IPC_ROLLBACK_OK` are
therefore NOT_TESTED on the guest; the scenario is ready for one explicit
one-shot re-run when authorized (the four-run session budget was consumed).
