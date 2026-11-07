# SDK Go toolchain compatibility and commit verification

> **Source-preserving move — 2026-11-07.** Read when building/updating Go-based IPKs, changing the SDK, or preparing an approved workflow or package change.
>
> All sections below are preserved from the root `AGENTS.md` on `gh-action-build` at `e5739548655fa1c5eb350a8f15306719ee1ee21b`. Only relative Markdown link paths, if any, are rebased to this directory; inline-code repository paths still assume repo root. References to previous SDK versions, package releases, tests or hardware validation are historical until checked against current source/Actions.
>
> Read this guide **only when relevant**. The short [root AGENTS.md](../../AGENTS.md) remains binding. The repo is the `saymer-alt` fork, not upstream. No read permission, approval of a Draft PR or old documented success authorizes a release, IPK publication, SDK migration, upstream push or production router changes.

---

## Go compatibility rule (high-care)

The Entware SDK ships one Go toolchain with `GOTOOLCHAIN=local`; a package build fails if
that tag's `go.mod` requires a newer Go. Therefore:
- Before building or bumping any Go package, check the `go` directive in that tag's
  `go.mod` against the Go version actually shipped by the Entware SDK.
- Never "fix" a toolchain mismatch by upgrading Go, changing the SDK, or setting
  `GOTOOLCHAIN=auto` in a workflow. Build an older package version, or wait for an SDK
  update, and report the situation to the owner.
- `build-beszel.yml` implements this check (preflight reads the SDK's Go version from
  `staging_dir/host/go/VERSION`). Keep the preflight when copying this pattern.

WARPSCOUT exception is explicit and narrow: when the selected current WARPSCOUT release
requires a newer Go patch level than the SDK, do not lower its `go` directive and do not
inject another Go toolchain. The current experimental ARM64 package instead repacks the
official upstream Linux/ARM64 release binary and verifies its release digest plus binary
identity. Reconsider source-building only after the Entware SDK satisfies upstream's Go
requirement.

## Before every commit / push

- `git status` + `git diff` — the diff must be exactly the intended change.
- Never commit `PKG_MIRROR_HASH:=skip` (CI-only sed at build time is the convention).
- Push only fast-forward to `gh-action-build`. Forbidden: force push, history rewrite,
  branch deletion, disabling workflows to hide failures, `--force`/bypass flags.
- After changing a workflow: dispatch it manually and watch the run to the expected
  result. A red run with clear diagnostics is better than a green run that silently
  lost changes.

