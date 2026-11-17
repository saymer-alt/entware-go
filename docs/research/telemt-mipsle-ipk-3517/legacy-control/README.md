# TeleMT MT7621 / Linux 4.9: legacy stop/reload supervisor prototype

**Status: RESEARCH ONLY / NOT A TeleMT fix / NOT APPROVED FOR DEVICE INSTALLATION.**
Tracking issue: [entware-go #51](https://github.com/saymer-alt/entware-go/issues/51).
Pinned upstream TeleMT source: `66708d2866f3f3a4541c4fa67984d408e71a8af4`.
Verified guest baseline: router-emulator PR #95 (Core 74/74) and #96 (Panel+Core 93/93).

## Measured reason to investigate

The existing upstream `telemt stop` and `telemt reload` call
`signal_pid_file -> pidfd_open`, returning ENOSYS on the real Ported
`4.9-ndm-5` QEMU MT7621 guest. Sending raw `kill(pid)` after checking a PID
file/lock is **not** a safe equivalent: an unrelated process can receive a
recycled PID between identity verification and signalling.

No binary, IPK, installer, release pipeline, runtime device or user configuration
is changed by this research-only prototype.

## Safe experimental idea (not transparent built-in CLI replacement)

`legacy-supervisor.c` runs **one explicitly foreground** process as its own
direct child. The supervisor creates a same-UID-only local Unix control socket
in an owner-only (0700) directory, and supports `status`, `reload` and
`stop`. It does NOT read TeleMT PID files. Clients never call `kill(pid)`.
Only the actual parent sends `SIGHUP`/`SIGTERM` to its known child.

The parent uses Linux `waitid(P_PID, ..., WEXITED|WNOHANG|WNOWAIT)` to observe
exit *without reaping*. Even if the child exits immediately before the signal,
its PID cannot be reassigned while it remains the parent's unreaped zombie.
Only after exiting the management loop does the supervisor call `waitpid`,
release the socket, and terminate. This addresses the particular numeric PID
reuse race that prevents a blind `kill` fallback from being equivalent to
`pidfd_send_signal`.

The old `telemt stop/reload` still fail closed: this prototype introduces
distinct `legacy-supervisor stop/reload` commands. The modern-kernel `pidfd`
path remains untouched. A future production solution should compare integrating
daemon-owned IPC into upstream TeleMT against an independently maintained
supervisor; this prototype is **not** an authorization to ship a second daemon.

### Host-only usage with a synthetic disposable worker

```sh
cc -std=c11 -Wall -Wextra -Werror -O2 legacy-supervisor.c -o legacy-supervisor
mkdir -m 700 /tmp/telemt-legacy-OWNED
./legacy-supervisor serve /tmp/telemt-legacy-OWNED/control.sock -- /path/to/foreground-worker
./legacy-supervisor status /tmp/telemt-legacy-OWNED/control.sock
./legacy-supervisor reload /tmp/telemt-legacy-OWNED/control.sock
./legacy-supervisor stop /tmp/telemt-legacy-OWNED/control.sock
```

Use **synthetic foreground test worker only**. Do not point it at an installed
TeleMT on physical routers or VPS. The source assumes the managed process does
not double-fork, daemonize, or hand the service to a grandchild. The current
MT7621 lab Core's `start --foreground` behavior was demonstrated in PR #95,
but **supervisor + real TeleMT has NOT been tested**.

## Host verification

`python3 -m unittest discover -s docs/research/telemt-mipsle-ipk-3517/legacy-control -p test_legacy_supervisor.py -v`

Locally on Linux x86_64: **4/4 PASS** (C compile with `-Werror`,
synthetic child reload/stop/exited, absent endpoint, insecure parent, preexisting
endpoint, early child exit). The same host proof is invoked from the already-allowlisted
`tools/tests/telemt_mipsle_ipk_preflight_tests.py` by the existing getfb research
workflow, without expanding either MIPSel boundary guard. These are **HOST MOCK PASS**, not MIPSel, ABI,
QEMU-system, or actual TeleMT acceptance.

## Known limitations / hard STOP gates

- No MIPSel cross-build, FP ABI verification, real Entware `opkg` install,
  QEMU-system, native reboot, clean rollback or live Telegram upstream proof.
- No integration with the TeleMT's built-in `stop/reload` commands; Issue #51
  still open. No `pidfd_open` interception or unsafe PID-file fallback.
- Only a same-UID caller is checked (SO_PEERCRED); a different trust policy,
  inherited privileges or service user changes require explicit review.
- Stale Unix socket after a hard crash is rejected rather than unlinked
  blindly; recovery protocol and inode/parent hardening need design.
- Owner-private control directory must be established before runtime; the
  current lab `/opt/var/run` must not be assumed 0700.
- Process startup, signal handling, bounded accepted-client reads and
  late SIGTERM behavior need target-kernel stress testing. Parent checks
  only its **direct child**; any daemon double-fork invalidates the guarantee.
- No automatic restart, privileged installs or watchdog. The supervisor
  currently exits successfully when a child exits on its own; a production
  service-manager would need explicit health/failure policy.
- Before any MIPSel build: protect original Core IPK/ELF SHA, pinned toolchain,
  ABI and getrandom fallback, and show negative tests for uid mismatch,
  process exit/reuse race, socket replacement, stale lock, concurrent commands,
  crash cleanup and orphan/grandchild behavior. New package identity is required.

**Next step:** review this narrow prototype versus upstream daemon-owned IPC,
then (only if justified) prepare an isolated native MIPSel source/ABI build and
a dedicated bounded QEMU guest cycle. Do **not** reuse Core 74/74 or Panel 93/93
as evidence of this prototype's target-platform compatibility.
