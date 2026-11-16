# getrandom ENOSYS-only `/dev/urandom` fallback for the Entware MIPSLE TeleMT build

Research-only source fix for the proven TeleMT Core blocker on KeeneticOS Ported
5.1.8 MT7621 (MIPS32r2 LE, Entware `mipselsf-k3.4`, glibc 2.27 softfloat).

## Proven root cause (2026-11-16)

The Ported kernel `Linux version 4.9-ndm-5` does not expose `getrandom(2)`
(syscall returns ENOSYS) while the `/dev/urandom` driver itself works
(`random: crng init done` in the boot log). `rand 0.10.2`'s `ThreadRng`
panics at `rngs/thread.rs:163` (`could not initialize ThreadRng: Function not
implemented (os error 89)`) in both a tokio worker and `main`, ~1.5 s after the
daemon fork, killing the child. In daemon mode stderr goes to `/dev/null`, so
only a `start --foreground` probe could capture it (router-emulator Draft PR
#93, round 2 diagnostic cycle).

Upstream `getrandom` provides a reviewed `/dev/urandom` fallback
(`linux_android_with_fallback` + `use_file` with a `/dev/random` poll readiness
barrier) but routes it only for musl and a fixed arch list that does not
include MIPS; on `mipsel-unknown-linux-gnu` the stock backend propagates the
ENOSYS error and rand panics.

## Fix shape: three checksum-verified forks, one reviewed delta each

`[patch.crates-io]` (see `patch-section.toml.snippet`) redirects all three
locked getrandom versions to in-build forks assembled by `assemble-forks.sh`:

| Crate | Why it must be fixed | Users in the release binary |
|---|---|---|
| getrandom 0.4.3 | proven ThreadRng panic | rand 0.10.2 (rand_core 0.10.1) |
| getrandom 0.3.4 | same ENOSYS failure class | rand_core 0.9.5 (rand 0.9.5 users) |
| getrandom 0.2.17 | same; ring's `SystemRandom` calls `getrandom::getrandom()` (ring `src/rand.rs:165`) | ring 0.17.14 (rustls), x25519-dalek via rand_core 0.6.4 |

Each fork = the crates.io source **verified against the checksum recorded in
the committed Cargo.lock** (single provenance source) plus one delta patch:

1. A new module `linux_mips_with_fallback.rs` — a verbatim copy of upstream's
   own `linux_android_with_fallback.rs` for that version, with the readiness
   barrier, EINTR/partial handling, futex synchronization and fail-closed
   semantics untouched. The only functional delta: **fallback on ENOSYS only**
   (upstream additionally falls back on `EPERM` for seccomp-blocked getrandom;
   deliberately not adopted here per the research assignment, so any other
   error surfaces as a hard failure instead of switching entropy source).
2. Routing in `backends.rs` (0.3.4/0.4.3) or `lib.rs` (0.2.17) — a new branch
   selected **only** for `all(target_os = "linux", target_arch = "mips",
   target_env = "gnu")`. No other platform's backend selection changes; the
   explicit `getrandom_backend` cfg overrides still win.
3. Test-only hooks (`getrandom_test_linux_fallback` /
   `getrandom_test_linux_without_fallback`) — verbatim upstream 0.4.x hooks,
   added to the 0.2.17 fork which predates them.
4. `tests/mips_fallback_integration.rs` (registered as an explicit `[[test]]`
   target because upstream declares its test targets) and one unit test inside
   the mips module (compiled only on the mips target).

The time64/softfloat Entware ABI machinery (crt stripping, shim.o, wrappers)
is unchanged; the forks are pure Rust crates and inherit the same gates.

## Deliberately rejected alternatives

- **LD_PRELOAD getrandom shim** — a C-ABI impersonation that would fake the
  platform result; rejected (also documented in router-emulator PR #93).
- **getrandom custom backend (`--cfg getrandom_backend="custom"`)** — the cfg
  is global per rustc invocation, so 0.3.4 and 0.4.3 would both route to the
  same `__getrandom_v03_custom` symbol with two different `Error` types; a
  single provider would rely on cross-crate layout assumptions. Rejected as
  fragile; the per-version fork keeps each version's own reviewed code.
- **Patching only 0.4.3** — after ThreadRng survives, ring's TLS entropy and
  rand_core-0.9/0.6 users would hit the same ENOSYS class; all three versions
  in the graph are covered.

## Test matrix (gate.sh, run in CI before the IPK is uploaded)

| Level | Modes | Assertion |
|---|---|---|
| Host (x86_64) fork regression tests | stock / forced fallback / without-fallback guard | upstream suite passes; integration matrix `2 passed; 0 failed`; no panics |
| qemu-user mipsel probe (`entropy-probe-rs`) | plain (getrandom present via host kernel) | `RS_THREADRNG_OK` + all three forks OK + distinct bytes |
| qemu-user mipsel probe | `getrandom_test_linux_fallback` (the guest-kernel scenario) | same, served through the readiness barrier + `/dev/urandom` |
| qemu-user mipsel fail-closed (`entropy-failclosed-rs`) | mount namespace with empty `/dev` | every fork returns Err; exit 0 only on `RS_FAIL_CLOSED_OK` |
| ABI | readelf | `FP ABI: Soft float`, interpreter `/opt/lib/ld.so.1` |

Real-platform acceptance remains the single QEMU-system MT7621 guest cycle
(router-emulator research branch): native `opkg install` of the new IPK,
in-guest dual SHA verification, foreground start with the private UART log,
`/proc/<pid>/exe` identity, loopback-only API, bounded liveness, stop/start,
and only then native reboot + `rc.unslung` autostart.

## IPK identity

New experimental Core IPK `telemt_3.5.17-2fb1_mipsel-3.4.ipk` (artifact
`telemt-core-mipsel-experimental-getfb`, preflight kind `core-getfb`). The
Panel Lite IPK is unchanged (Go binary, its own entropy handling) and is NOT
rebuilt — the pinned artifact of run 43742529964 stays authoritative. Nothing
is published to releases/feeds; upstream sources and pins of PR #44 are not
modified (this branch only adds research files and a separate workflow).
