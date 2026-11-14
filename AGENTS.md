# AGENTS.md — entware-go fork, lean agent startup contract

**Read this short file at startup; do not preload all historical guidance, package recipes or workflow code.** This is the `saymer-alt/entware-go` fork of `spatiumstas/entware-go`, itself derived from `Entware/entware-go`. The only normal integration/default branch here is **`gh-action-build`**, **not `main` or `master`**. Upstream `master` is an input to a controlled sync, never the target branch for changes in this fork.

## Purpose, scope and owner authorization

This repo builds/packages Entware IPK artifacts for Keenetic and other `/opt`-based Entware targets (including Mihomo, Beszel Agent and ARM64 WARPSCOUT). This is **not a root Go module**; don't run generic root `go build` or assume local builds match the SDK. `Makefile` and GitHub Actions are the actual packaging sources. The public shared `latest` release is a package feed, not a scratch area.

- **Default mode:** inspect source, edit on a task branch, run read-only/static tests, open a **Draft PR targeting `gh-action-build`**. No direct commit/merge to default branch, no `main`/`master` creation, no force-push, no upstream push, no release/tag/feed publish, no repository-setting change, and no live router/Entware installation or restart without a separate explicit **owner GO**.
- For nontrivial tasks identify the exact base SHA, expected user outcome, existing work, owner permissions, scope/non-goals, negative acceptance and rollback before editing; use the [shared agent task contract](https://github.com/saymer-alt/saymer-alt/blob/main/AGENT-TASK-CONTRACT.md). For a major new subsystem compare existing/manual, smallest safe, and expanded options under [Proof Before Build](https://github.com/saymer-alt/saymer-alt/blob/main/PROOF-BEFORE-BUILD.md). Do not enlarge scope or over-engineer a simple fix.
- **WORKING-FIRST / LICENSE AUDIT DEFERRED:** prioritize safe working builds, tests, IPKs and existing releases; do not reopen an abstract project-wide license audit on every request, disable healthy CI or stall unrelated packages over a speculative WDTT inventory question. **But public/noncommercial use does not grant copyright permission**: preserve upstream LICENSE/NOTICE/provenance; when a concrete component's distribution rights are demonstrably blocked, do not publish *that component* without resolution. Any exception, release or publication still requires owner GO.

## Mandatory package, CI and release invariants

- **Go compatibility is fail-closed.** The Entware SDK supplies a particular Go toolchain under `GOTOOLCHAIN=local`. Before bumping source tags, read the tagged upstream `go.mod` and compare its `go` directive with the **actual SDK Go version**. Do not silently upgrade the SDK/Go, switch to `GOTOOLCHAIN=auto`, lower upstream requirements, or waive toolchain preflight. If incompatible: use an approved older version or report BLOCKED/wait for SDK.
- **WARPSCOUT ARM64 exception is intentional:** it repacks a versioned official `linux_arm64` asset verified by SHA-256/digest and binary identity, rather than injecting a newer Go compiler. Package is for `aarch64-3.10`; it is a CLI, **not an autostart daemon**. Preserve the exact verification, architecture gate, installer/update fallback, WARP account data, and non-destructive reinstall behavior. The historical Go SDK/WARPSCOUT versions are not automatically current.
- **Shared `latest` release: ownership by package glob.** `mihomo_*`, `beszel-agent_*` and `warpscout_*` workflows must upload/verify only their own assets and must never erase/overwrite another package family's IPKs. Preserve complete-set checks, SHA-256 and size verification before pruning and collision refusal; `entware-latest-publication` protects concurrent writes. An incomplete build cannot be reported as an accepted package set.
- **Preserve forks during upstream synchronization.** `sync-upstream.yml` merges `Entware/entware-go` `master` into `gh-action-build`. Keep fork-specific workflows and modifications; conflicting added paths/recipes require human review. Never silently choose `ours`/`theirs`, rewrite history or resolve conflicts automatically. `telegram-push.yml` targets upstream `master` and is intentionally inert here: do not activate it.
- **Only intended workflows may publish.** PR checks and docs changes must not mutate `latest`, notify a feed, push a package, or bypass release permission gates. Do not change the current Actions triggers, GitHub token permissions, SDK identity or shared release machinery without explicit scope. Healthy Mihomo/Beszel/WARPSCOUT/KAS builds must not be disabled to "simplify" a workflow.
- **Don't weaken package verification.** Never commit `PKG_MIRROR_HASH:=skip`; handle any CI build-time convention only in the approved workflow. Preserve architecture/ABI targets and exact package version, asset naming, signatures/digests, package scripts and `/opt` paths; do not assume a successful Actions build proves on-device Keenetic compatibility, ping-check behavior, or rollback.
- No credentials, tokens, account files, private keys or subscriber secrets in logs/repo/artifacts. Experimental WDTT must remain isolated from production release/package feeds unless explicitly authorized; do not infer permission from a separate prototype PR.

## Minimal working loop

1. Check default branch `gh-action-build`, immutable HEAD, intended package/workflow and existing open PRs. Read **only the related detailed guide** below and actual affected `Makefile`, installer, workflow and tests.
2. Make a minimal, non-destructive diff. Respect package isolation and upstream sync boundaries. Keep unrelated license reports, dependency bumps and cleanup out of the task.
3. Run proportional, **read-only** checks. Existing `safety-tests.yml` runs installer syntax/ShellCheck and Python regression fixtures; use them for relevant changes. Package/SDK workflows may need a separately authorized build dispatch; never initiate a release/publish just to "test" a docs edit.
4. Inspect final SHA, diff, expected CI. Report PASS / FAIL / BLOCKED / NOT TESTED accurately. A PR build does **not** imply hardware field acceptance. Open Draft PR; merge/promote, release, deploy, conflict resolution or feed modifications require owner GO.

## Detailed guidance — load on demand

- [01 — owner policy, WORKING-FIRST, scope and approval](docs/agent-guidance/01-owner-policy-and-authority.md) — for owner exceptions, design or license questions.
- [02 — repository layout, fork lineage, Actions and package feed](docs/agent-guidance/02-repository-fork-and-package-publishing.md) — for packaging, releases, upstream sync and asset ownership.
- [03 — Go compatibility and release-change checklist](docs/agent-guidance/03-go-compatibility-and-change-checklist.md) — for toolchain/version bumps and CI changes.

Detailed old release history and measured behavior stay in the guides for provenance; they are not mandatory startup context or authorization to touch routers.

## Token economy (KAS #420; ZCode/Codex/Kimi)

Обязателен [узкий рабочий цикл](docs/agent-token-economy.md): одно задание и exact SHA; точечные источники и тесты (изменяемые installer/upgrade/rollback/publisher читать целиком перед правкой); `sh -n`/ShellCheck/host mocks перед SDK/QEMU; после **2 одинаковых бесполезных попыток** сменить гипотезу или `BLOCKED`. Повторять PASS лишь при совпадении SHA/SDK/asset digest; `CI PASS ≠ QEMU PASS ≠ FIELD PASS`. Не раздувать `latest`, сборки или токены ради квоты. Документы/PR/исследование не дают разрешения на merge/release или обновление роутера. Handoff: `PR | SHA | gates | run | blocker | next GO`.
