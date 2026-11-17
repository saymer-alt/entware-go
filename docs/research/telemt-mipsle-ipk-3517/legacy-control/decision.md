# Decision: Linux 4.9 MT7621 TeleMT stop/reload without pidfd

2026-11-17. **Research/design only. Not a new accepted Core build.**
Owner issue: [entware-go #51](https://github.com/saymer-alt/entware-go/issues/51).
Source pinned at telemt/telemt `66708d2866f3f3a4541c4fa67984d408e71a8af4`.
Existing accepted artifacts remain unmodified: Core `3.5.17-2fb1`,
Panel Lite `1.0.0-rc.4`.

## Problem and invariant

The real Ported MT7621 Linux `4.9-ndm-5` guest returns ENOSYS from
`pidfd_open`. TeleMT `signal_pid_file` calls this before delivering SIGTERM
or SIGHUP, so the built-in `stop/reload` commands fail. The existing
`/opt/etc/init.d/S99telemtlab` uses raw `kill(pid)` in a disposable test
fixture; it is **not** a safe production fallback.

**Hard requirement:** never send a signal to an untrusted or recycled PID on
the basis of a PID file, process name, `kill -0` or held flock alone. Modern
Linux `pidfd` semantics must not regress. No silent ENOSYS -> raw kill.

## Option comparison

| Option | Benefits | Costs/risks | Decision |
|---|---|---|---|
| Keep pidfd and report ENOSYS | No code or security regression | No built-in stop/reload on old kernel; explicit service control still required | Safe baseline/fallback if no candidate passes |
| ENOSYS -> `flock + /proc/starttime + kill` | Small source diff | Uncloseable TOCTOU between identity check and signal; reused PID could be unrelated | **Reject** |
| C child-owned supervisor, private AF_UNIX control | Avoids recycled PID while child remains unreaped; can keep old accepted Core binary | A second long-lived process and service protocol; direct-child-only guarantee; startup, crash/recovery and privilege lifecycle complexity; built-in CLI unchanged | Host-only research in PR #57; do not ship |
| **Daemon-owned AF_UNIX control endpoint** | No external PID signal at all, reuse existing TeleMT shutdown/reload machinery, one managed process, no second service manager | Opt-in code/ABI/security review and a NEW MIPSLE Core build; socket lifecycle and credential checks; more extensive acceptance | **Preferred prototype for next isolated Draft PR** |

The already-accepted Core 74/74 + Panel 93/93 runs are evidence of the
old binary only. Neither proves the new control path.

## Proposed opt-in contract (not implemented here)

- Introduce a dedicated `--control-socket /absolute/private/telemt.sock`
  mode for daemon startup and `telemt stop/reload [--control-socket ...]`.
  No automatic fallback if pidfd returns ENOSYS without an explicit opt-in.
- Parent of socket must be a trusted private owned directory, resolved with
  anchored no-follow traversal; reject symlinks, wrong owner, group/other
  writable parents, existing unexpected endpoint, oversized path and races.
  Bind Unix filesystem socket mode 0600; never TCP or public listeners.
- Auth is kernel-issued AF_UNIX `SO_PEERCRED`: reject other UID and missing
  credentials; do not log secrets. On privilege drop, define/verify the
  post-drop intended UID and ownership before exposing the endpoint.
- The **running daemon itself** handles the accepted command, schedules its
  existing graceful shutdown or SIGHUP reload and replies. It must not look
  up or signal a process by PID. Socket availability must be ordered *after*
  core runtime signal/reload handlers are active.
- Client imposes bounded connect/read and distinguishes `ACCEPTED` from
  completion. A successful response must mean only that the operation was
  accepted, not that the daemon has already stopped or reloaded.
- Socket inode is recorded; on ordinary shutdown unlink only the matching
  inode. On unclean crash the candidate must fail closed or follow a separate
  reviewed stale-socket recovery protocol; never unlink arbitrary path.
- When this opt-in flag is absent, existing `pidfd_open` and strict runtime
  policy remain untouched on all architectures and kernels, including ARM64.

## Acceptance gates before creating any deliverable IPK

1. **Host unit/integration first:** Linux modern pidfd path unchanged; opt-in
   signal/command behavior; nonexistent/bad/oversized socket; symlink and
   hard-link attack; wrong UID; stale endpoint; double-start; concurrent
   stop/reload; client disconnect; worker exit; path replacement; bounded
   deadline; no signals to unrelated processes. A deterministic reused-PID
   negative test must be designed, not inferred from `kill -0`.
2. **Immutable source context:** separate patch applied only to pinned TeleMT
   commit, after existing getrandom and atomic64 changes; original patched
   `Cargo.lock` preserved or security-updated in a *separate* explicit
   candidate. Protect original IPK/ELF pins, ARM64, tags, release feeds.
3. **One native MIPSel build:** prove ELF MIPS32r2 LE, softfloat FP ABI=3,
   interpreter `/opt/lib/ld.so.1`, glibc compatibility and **new**
   independent ELF/IPK SHA256. Zero reuse or relabeling of old digests.
4. **One bounded real QEMU-system MT7621 cycle:** use verified genuine Entware
   `opkg` and loopback-only lab ports; test actual built-in `telemt stop`
   and `reload` using opt-in control socket, SIGTERM shutdown, pid and
   health transitions, no orphans, explicit stale process negative, Panel
   integration, native reboot + `rc.unslung` and clean rollback.
5. Fail closed on missing listener, unauthorized request, unexpected PID/file
   state or shell/init uncertainty. Record FAIL/BLOCKED/NOT_TESTED honestly.
   Do not connect to real Telegram upstream or production routers/VPS.

**Scope:** research branch/Draft only; no merge/release/publish/live install.
**STOP:** two identical failures or 3 fixes/full heavy runs for this blocker
whichever occurs first; do not use a new branch to reset the existing budget.

## Next engineering step

Review TeleMT's pinned `src/daemon/pid_file.rs`, `src/cli/daemon_commands.rs`,
`src/cli.rs`, `src/maestro/mod.rs` and current Tokio shutdown/reload
wiring. Implement the opt-in listener at the point where runtime handlers are
ready, with negative tests before any MIPSLE build. Keep PR #57 unmerged as
a C supervisor comparison and do **not** call built-in `stop/reload` fixed.
