# TeleMT 3.5.17 → Entware MIPSLE / MT7621: host-only R&D plan

**Status 2026-11-14:** NOT BUILDABLE unmodified; no production IPK, no QEMU field validation. Experimental plan only.

## Scope and immutable constraints

- Target: **Keenetic KN-1913 / MT7621A, MIPS32r2 little-endian, softfloat, Entware \`mipsel-3.4\` (glibc)**.
- First goal: **TeleMT core MTProxy**, not a UI; Panel Lite RC4 already has a separate host cross-build PASS in Draft #40, no need to rebuild it.
- No network access to working devices. No personal configs, IP addresses, domains, keys, SNI, or Telegram client identities.
- No publication to \`latest\`, package feeds, releases, no modifications to existing ARM64 6-hourly pipelines, no installation on KN-1913 before explicit owner approval.
- Keep this work in isolated source clone/worktree or Draft PR; do not modify \`telemt/telemt\` upstream automatically.
- Avoid repeating already completed experimental workflows and avoid SDK/QEMU until host-build proof exists.

## Grounded evidence

1. Draft #40 / run 43583373749:
   - Historic \`telemt_3.5.5-1_mipsel-3.4.ipk\` downloaded and metadata-inspected; ELF32 MIPS LE **exists**, provenance/signature unknown.
   - Panel Lite RC4 \`GOARCH=mipsle GOMIPS=softfloat CGO_ENABLED=0\`: host cross-build PASS, QEMU/field NOT_TESTED.
2. Draft #41 / run 43591784527, source SHA \`66708d2866f3f3a4541c4fa67984d408e71a8af4\` (TeleMT 3.5.17):
   - Cross tools, nightly Rust \`rust-src\`, standard library build, and dependency checks progressed.
   - **32 Rust errors** in the main crate: widespread E0432 \`std::sync::atomic::AtomicU64\` unavailable on MIPS32; one E0080 \`usize\` overflow from \`4 * 1024 * 1024 * 1024\` constant.
   - Source text has **696 \`AtomicU64\` mentions in 76 \`src/\` files** (includes tests; NOT 696 independent atomic variables).
   - \`rustc --print cfg --target mipsel-unknown-linux-gnu\`: no \`target_has_atomic="64"\`.
   - Old 3.5.5 binary: ELF32 little-endian, interpreter \`/opt/lib/ld.so.1\`, dynamic dependencies \`libgcc_s, librt, libpthread, libm, libdl, libc\`, GLIBC symbols observed up to 2.25. Do NOT execute this untrusted archival binary on the CI host.
   - Upstream **3.5.5 source already imports/uses \`AtomicU64\`** in \`src/proxy/traffic_limiter.rs\`, \`src/stats/replay.rs\`, and \`src/proxy/relay/io/counters.rs\`: historical MIPS IPK cannot be explained by a lack of atomic64 usage in 3.5.5; provenance/patchset is still UNKNOWN.
3. Upstream developer explicitly treats lack of 64-bit atomics and performance as unsupported engineering boundary: https://github.com/telemt/telemt/discussions/719
4. \`portable-atomic\` (https://docs.rs/portable-atomic/latest/portable_atomic/) provides \`AtomicU64\` on MIPS-class 32-bit targets with default \`fallback\` implementation using global locks when necessary. **Candidate for a proof only, not an accepted fix**.

## Agent assignment — one hypothesis and one bounded test

**Hypothesis**: A dedicated architecture-specific atomic64 abstraction (backed by \`portable-atomic\` only where \`target_has_atomic="64"\` is unavailable), plus an explicit 32-bit-safe WEB memory validation fix, can make upstream 3.5.17 *typecheck* on MIPS32r2 without changing correctness of concurrency and accounting.

1. **READ-ONLY audit first**. Inspect upstream pinned source and existing \`Cargo.lock\`. Classify \`AtomicU64\` callsites into counters, limits, CAS-based admission, quota/replay/security/WEB, and any public API/FFI type usage. Check source for fully-qualified type names and structs exposing atomics. Confirm known 3.5.5 paths also contain atomic64. Provide short risk matrix.
2. **Minimal prototype**, isolated source branch; do **not** wholesale replace \`AtomicU64\` with \`AtomicU32\` or remove traffic limits. Prefer one \`compat::AtomicU64\` alias controlled by \`cfg(target_has_atomic = "64")\`; use \`portable_atomic::AtomicU64\` with fallback only on MIPS32. Handle imports precisely. Keep 64-bit targets on std/native path. Pin exact dependency version and update lockfile.
3. **Fix 4GiB constant without truncation** in \`src/config/load/validate_web.rs\`. Use \`u64\` for the 4GiB envelope and checked conversions; preserve the intended validation failure semantics on 32-bit. Do not silently clamp or disable validation.
4. **Offline/host testing first**: x86_64 unit/regression tests for counters, rate limit, CAS loops, replay/quota, integer boundaries and concurrent access. Ensure \`cargo fmt --check\`, \`cargo test\` selected, \`cargo clippy\` where practical. Build/test with a pinned Rust version (>=1.88 for upstream 3.5.17).
5. **Exactly one bounded MIPSLE cross-check** (nightly \`-Z build-std\`, cross GCC/sysroot, softfloat target, locked dependencies) after local tests. On PASS, one bounded host *binary build*. Record the **first concrete blocker** if it fails. Do not add long retry loops or attempt full SDK build.
6. **Risk gate**: even a green MIPSLE ELF is \`HOST BUILD PASS\` only; correctness of lock fallback, latency/jitter under load, \`ring\` crypto, memory usage and \`opkg\` remain NOT_TESTED until QEMU; field only after explicit approval.

## Required report format

- Exact source SHA, build commands, Rust, cross toolchain, Cargo.lock changes, target triple/ABI.
- \`ATOMIC64_SOURCE_AUDIT\` / \`ATOMIC64_PORT_TEST\` / \`MIPSLE_CROSS_CHECK\` / \`MIPSLE_BINARY_BUILD\` / \`QEMU\` / \`OPKG\` / \`FIELD\`: each PASS, FAIL, BLOCKED, or NOT_TESTED with evidence.
- If host build fails, stop after identifying blocker and record *why*; no fake IPK or release.
- Publish only sanitized, narrow Draft PR and report in Issue #37. **Do not merge/publish**.

## References

- Research tracker: https://github.com/saymer-alt/entware-go/issues/37
- Historical/Go Panel proof: https://github.com/saymer-alt/entware-go/pull/40
- TeleMT core baseline proof: https://github.com/saymer-alt/entware-go/pull/41
- Core baseline run: https://github.com/saymer-alt/entware-go/actions/runs/43591784527
