# Entware fork, package layout, workflows and release ownership

> **Source-preserving move — 2026-11-07.** Read when changing package recipes, Entware architectures, Actions, release handling, upstream merges, or introducing a package.
>
> All sections below are preserved from the root `AGENTS.md` on `gh-action-build` at `e5739548655fa1c5eb350a8f15306719ee1ee21b`. Only relative Markdown link paths, if any, are rebased to this directory; inline-code repository paths still assume repo root. References to previous SDK versions, package releases, tests or hardware validation are historical until checked against current source/Actions.
>
> Read this guide **only when relevant**. The short [root AGENTS.md](../../AGENTS.md) remains binding. The repo is the `saymer-alt` fork, not upstream. No read permission, approval of a Draft PR or old documented success authorizes a release, IPK publication, SDK migration, upstream push or production router changes.

---

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

- `mihomo/`, `beszel-agent/` — source-built Go package dirs: `Makefile`
  (PKG_NAME/PKG_VERSION/PKG_RELEASE/PKG_SOURCE_*/PKG_MIRROR_HASH), `files/`
  (procd init `S99<pkg>` + config), `patches/` if needed.
- `warpscout/` — fork-specific ARM64 diagnostic package for Keenetic-class Entware targets.
  WARPSCOUT v0.16.0 requires Go 1.26.3 while the current Entware SDK v2026.07.04 ships
  Go 1.26.1, so this package intentionally repacks the official upstream
  `linux_arm64` release asset with a pinned SHA-256 instead of weakening
  `GOTOOLCHAIN=local`. It installs only `/opt/bin/warpscout` and
  `/opt/etc/warpscout`; there is no init script or daemon.
- `.github/workflows/`:
  - `build-mihomo.yml` — every six hours + manual + changes to `mihomo/Makefile`; checks
    whether the `latest` package release already has the complete asset set for the
    latest MetaCubeX/mihomo release, then runs an SDK Go-version preflight before
    building. Complete sets retry pruning without rebuilding, including manual dispatch.
    Publication validates/uploads/verifies the complete new set before pruning older
    Mihomo assets. Installer/Actions-only changes run safety tests without rebuilding IPKs.
  - `build-beszel.yml` — manual only; the version is explicit via the `version` input,
    default is pinned in the workflow. It never follows the upstream latest release
    automatically; the `preflight` job gates the build (see Go compatibility rule).
  - `build-warpscout.yml` — aarch64-only WARPSCOUT packaging workflow. It checks upstream
    every six hours (offset from Mihomo), packages the official Linux/ARM64 release asset,
    verifies GitHub's asset SHA-256 plus the packaged binary identity, and publishes only
    `warpscout_*.ipk` into the shared `latest` release. PR runs build/verify only and never
    publish. The first live KN-1812 install/register/scan test passed on 2026-09-23.
  - `sync-upstream.yml` — daily + manual; merges `upstream/master` into `gh-action-build`.
    Clean merge → merge commit + fast-forward push. Conflict → push a
    `sync-upstream/conflict-*` branch and open a PR; the job itself never resolves conflicts.
  - `telegram-push.yml` — arrived from upstream, triggers only on push to `master`, so it
    is inert here. Keep it as-is; do not wire it up.
- The `latest` release of this repo is the package feed: each workflow replaces only the
  assets matching its own package glob (`mihomo_*`, `beszel-agent_*`, `warpscout_*`).
  A WARPSCOUT publication must never delete or overwrite Mihomo/Beszel assets.

Publication jobs for all three packages share `entware-latest-publication`; each
writer still owns only its own package glob. Beszel/Mihomo refuse to overwrite a
healthy conflicting candidate and verify SHA-256/size metadata before pruning.
Mihomo cleanup retries on the next scheduled/manual run without rebuilding IPKs.
The consumer selection contract is implemented in keenetic-auto-setup PR #114.

## Fork-specific vs upstream

- Fork-specific workflows (do not exist upstream; they must survive every upstream sync):
  `build-mihomo.yml`, `build-beszel.yml`, `build-warpscout.yml`, `sync-upstream.yml`.
- Package dirs may carry fork-specific changes, but they are not automatically "ours".
  On every upstream merge, review the actual diff of each package dir and analyze any
  conflict or divergence separately.
- A normal upstream sync never modifies files that don't exist upstream. If a sync ever
  reports a conflict in fork-specific files (same path added upstream), treat it as a
  conflict: stop and analyze. Never resolve conflicts with automatic "ours"/"theirs".

