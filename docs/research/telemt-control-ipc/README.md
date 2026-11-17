# TeleMT MT7621 / Linux 4.9: in-daemon local stop/reload candidate

**STATUS: SOURCE-PATCH CANDIDATE — NOT BUILT FOR MIPSEL, NOT ACCEPTED.**
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
