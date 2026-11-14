# TeleMT 3.5.17 — MIPS32r2 atomic64 compat layer (research artifact)

This directory contains the single reviewed patch that makes upstream TeleMT
3.5.17 (`telemt/telemt` @ `66708d2866f3f3a4541c4fa67984d408e71a8af4`) typecheck
and build for `mipsel-unknown-linux-gnu` (MIPS32r2 little-endian, softfloat,
Entware `mipsel-3.4` glibc ABI), without changing any accounting or concurrency
semantics.

Contents:

- `telemt-3.5.17-mipsle-atomic64-compat.patch` — the whole source delta:
  - `src/compat.rs` (new): `compat::AtomicU64` re-export.
  - import rewrites in the files that name `AtomicU64` (57 files),
    fully-qualified rewrites (`src/quota_state.rs`), one `mod compat;` line in
    `src/main.rs`.
  - `src/config/load/validate_web.rs` + `validate_web/memory.rs`: the 4 GiB
    `usize` const-eval overflow fix (E0080) — envelope ceiling computed in
    `u64`, widening cast is lossless, validation semantics unchanged.
  - `Cargo.toml`: target-scoped `portable-atomic = "1.11.0"` dependency
    (`[target.'cfg(not(target_has_atomic = "64"))'.dependencies]`).
  - `Cargo.lock`: lock update for the new dependency.

## Design

`src/compat.rs` re-exports one alias:

```rust
#[cfg(target_has_atomic = "64")]
pub use std::sync::atomic::AtomicU64;      // x86_64, aarch64, ... — zero change

#[cfg(not(target_has_atomic = "64"))]
pub use portable_atomic::AtomicU64;        // MIPS32r2 — global-lock fallback
```

- Native 64-bit targets keep the exact `std` type upstream used; no hot-path
  change, no behavior change.
- MIPS32r2 has no 64-bit LL/SC: `portable-atomic` provides `AtomicU64` with a
  global-lock fallback built on native 32-bit atomics. Same type API, same
  `Ordering` semantics; counters, traffic limiter CAS windows, quota charge,
  replay protection and slot-budget admission code paths are untouched.
- No `AtomicU64` was replaced by `AtomicU32` or narrower; no limits removed.
- The dependency is target-scoped so 64-bit builds resolve exactly the
  upstream dependency graph.

Audit facts (see the PR description and Issue #37 for the full matrix):
`AtomicU64` appears in 76 `src/` files (692 mentions, 427 struct fields);
only `AtomicU64` (no `AtomicI64`); no aliased imports; no `repr(C)`/FFI
exposure; `.wait()`/`.notify()`/`.as_ptr()` are never used on `AtomicU64`
(only on native-width atomics), so the 32-bit futex limitation does not apply.

## Reproduce locally (host cross-check, no device)

```sh
git clone https://github.com/telemt/telemt upstream
git -C upstream checkout 66708d2866f3f3a4541c4fa67984d408e71a8af4
git -C upstream apply --whitespace=nowarn \
  docs/research/telemt-mipsle-compat-3517/telemt-3.5.17-mipsle-atomic64-compat.patch

# Host (x86_64) — native std path, full semantics:
cargo +stable check --locked
cargo +stable test --locked --bin telemt compat::

# MIPS32r2 LE softfloat typecheck (nightly, Tier 3 target, build-std):
rustup toolchain install nightly --profile minimal --component rust-src
RUSTFLAGS='-C target-cpu=mips32r2 -C target-feature=+soft-float' \
  cargo +nightly -Z build-std=std,panic_abort \
  check --release --locked --target mipsel-unknown-linux-gnu --bin telemt
```

CI reproduction: `.github/workflows/telemt-mipsle-compat-3517-check.yml`
(host tests job + one bounded MIPSLE cross-check → ELF32 build on PASS).

## Status gates (measured 2026-11-14)

| Gate | Result | Evidence |
|---|---|---|
| `ATOMIC64_SOURCE_AUDIT` | PASS | 692 `AtomicU64` mentions in 76 `src/` files (427 struct fields); no `AtomicI64`, no aliased imports, no `repr(C)`/FFI exposure; `.wait()`/`.notify()`/`.as_ptr()` never used on `AtomicU64`; CAS sites: slot_budget, traffic_limiter, quota_store, replay, user_admission, ip_tracker, me/writer_counters |
| `ATOMIC64_PORT_TEST` (host x86_64, native path) | PASS | `cargo test --bin telemt`: **2774 passed, 76 ignored**; 3 parallel-execution flakes (`proxy::client` TLS-masking) pass 3/3 in isolation and are unrelated to the compat layer (host alias is the identical `std` type) |
| `MIPSLE_CROSS_CHECK` | PASS | `cargo +nightly -Z build-std=std,panic_abort check --release --locked --target mipsel-unknown-linux-gnu --bin telemt` with `-C target-cpu=mips32r2 -C target-feature=+soft-float`: **0 errors**; nightly 1.102.0-nightly (2026-11-13), portable-atomic 1.15.0 |
| `MIPSLE_BINARY_BUILD` | PASS | `file`: `ELF 32-bit LSB pie executable, MIPS, MIPS32 rel2, dynamically linked, interpreter /lib/ld.so.1`; `readelf -h`: `o32, mips32r2, pic`; ~26.8 MB unstripped, cross gcc 12.3.0 (noble cross packages), glibc 2.39 sysroot |
| `QEMU` | NOT_TESTED | emulator not ready |
| `OPKG` | NOT_TESTED | no IPK built or published by design |
| `FIELD` | NOT_TESTED | no router access without owner GO |

A green host build proves typechecking and host semantics only. Lock-fallback
throughput/latency on MT7621, `ring` crypto behavior, memory usage and `opkg`
integration remain `NOT_TESTED` until a QEMU emulator run is available; field
validation requires explicit owner approval.
