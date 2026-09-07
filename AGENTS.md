# AGENTS.md — entware-go (saymer-alt fork)

Instructions for coding agents working in this repository.
When something is unclear or dangerous: stop and report to the owner — do not improvise.

## What this repo is

- Entware package feed for Go-language packages (OpenWrt-style buildroot; everything
  installs under `/opt` on the target device).
- Fork of a fork: `Entware/entware-go` (upstream, branch `master`) → `spatiumstas/entware-go`
  → `saymer-alt/entware-go` (this repo).
- The only working branch of this fork is `gh-action-build` (also the default branch).
  Upstream `master` is a merge source only. Never create, push to, or build from a
  `master` branch in this fork.
- This is not a Go module repo: no root `go.mod`, nothing is built locally. Packages are
  built only in GitHub Actions via the Entware SDK (`ownik/gh-action-entware-sdk@v1`,
  OpenWrt buildbot container, `GOTOOLCHAIN=local`).

## Layout

- `mihomo/`, `beszel-agent/` — package dirs: `Makefile` (PKG_NAME/PKG_VERSION/PKG_RELEASE/
  PKG_SOURCE_*/PKG_MIRROR_HASH), `files/` (procd init `S99<pkg>` + config), `patches/` if needed.
- `.github/workflows/`:
  - `build-mihomo.yml` — daily + manual; compares latest MetaCubeX/mihomo release with
    `PKG_VERSION`, builds and publishes only on change (manual dispatch always builds).
  - `build-beszel.yml` — manual only; the version is explicit via the `version` input,
    default is pinned in the workflow. It never follows the upstream latest release
    automatically; the `preflight` job gates the build (see Go compatibility rule).
  - `sync-upstream.yml` — daily + manual; merges `upstream/master` into `gh-action-build`.
    Clean merge → merge commit + fast-forward push. Conflict → push a
    `sync-upstream/conflict-*` branch and open a PR; the job itself never resolves conflicts.
  - `telegram-push.yml` — arrived from upstream, triggers only on push to `master`, so it
    is inert here. Keep it as-is; do not wire it up.
- The `latest` release of this repo is the package feed: each workflow replaces only the
  assets matching its own package glob (`mihomo_*`, `beszel-agent_*`).

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

## Fork-specific vs upstream

- Fork-specific workflows (do not exist upstream; they must survive every upstream sync):
  `build-mihomo.yml`, `build-beszel.yml`, `sync-upstream.yml`.
- Package dirs may carry fork-specific changes, but they are not automatically "ours".
  On every upstream merge, review the actual diff of each package dir and analyze any
  conflict or divergence separately.
- A normal upstream sync never modifies files that don't exist upstream. If a sync ever
  reports a conflict in fork-specific files (same path added upstream), treat it as a
  conflict: stop and analyze. Never resolve conflicts with automatic "ours"/"theirs".

## Before every commit / push

- `git status` + `git diff` — the diff must be exactly the intended change.
- Never commit `PKG_MIRROR_HASH:=skip` (CI-only sed at build time is the convention).
- Push only fast-forward to `gh-action-build`. Forbidden: force push, history rewrite,
  branch deletion, disabling workflows to hide failures, `--force`/bypass flags.
- After changing a workflow: dispatch it manually and watch the run to the expected
  result. A red run with clear diagnostics is better than a green run that silently
  lost changes.

## Requires explicit owner approval

- Changing the Entware SDK or Go toolchain in any workflow.
- Creating releases/branches beyond the documented scheme, publishing to the feed
  manually, changing repo settings, wiring up `telegram-push.yml`.
- Any conflict resolution in fork-specific files during upstream sync.
