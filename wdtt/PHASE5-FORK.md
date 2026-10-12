# Phase 5: independent pinned source

WDTT effective source is maintained in the real GitHub fork
[saymer-alt/proxy-turn-vk-android](https://github.com/saymer-alt/proxy-turn-vk-android),
branch `feature/wdtt-hardened-20261012`, commit
`ff88cae7184561fe901e6e6a64f983ac6dd62980`.
Upstream awg-client base remains
`1110a75f76e42c23149b8e24f9182c1ff179e515`. Both upstream branches and all seven
tags are preserved, as are GPLv3 LICENSE and authorship/notices.

`fork-source-lock.json` pins the repository, commit and SHA256 of every source
file. Build checks the exact file set, every digest and unchanged client Go
module locks. The three archived security patches are already applied in the
fork; build no longer applies them or injects client/relay overlays. Effective
client source lives in go_client; relay source in hardened-relay. The original
root server.go remains only upstream reference/negative AUTH baseline.

`build-report.source` remains the explicitly named upstream base for the
existing KAS admission contract. `fork_source`, `source_repository`,
`fork_source_lock_sha256` and `fork_tree_verified` identify the actual checkout.
IPK provenance points to the fork commit; version gains that revision. This is
not a claim that the fork commit equals upstream. KAS scripts remain unchanged.

`phase4-source-baseline.json` records Phase4 executable and notices/inventory
digests. A source-only port must retain identical four client ELFs and relay;
the build fails on any difference. IPK SHA changes are expected because version,
fork/tree provenance and owner recipe digests change. Private owner retention,
real opkg and pinned POSIX/BusyBox lifecycle acceptance are rerun. All public
uploads remain JSON/TXT evidence only. Production package/workflow files and
latest are unchanged and checked read-only.

## Backup / recovery

Owner-local mirror and complete bundle are retained outside GitHub at:

```text
C:\Users\Saymer\Documents\Codex\backups\wdtt-phase5-20261012\fork.git
C:\Users\Saymer\Documents\Codex\backups\wdtt-phase5-20261012\wdtt-phase5.bundle
```

`git fsck --full`, bundle verify and fresh mirror restoration were checked.
Bundle contains upstream branches/tags plus the maintained source branch. Only
repository history is backed up; no owner config, token, runtime credentials or
private hardware/VPS files were added. Existing upstream public source is
preserved byte-for-byte, rather than claiming a new historical secret audit.

To update, retain the old bundle and fetch into a new mirror/snapshot; never
mirror-push to GitHub:

```sh
git clone --mirror https://github.com/saymer-alt/proxy-turn-vk-android.git /owner/backups/wdtt-NEW.git
git -C /owner/backups/wdtt-NEW.git fsck --full
git -C /owner/backups/wdtt-NEW.git bundle create /owner/backups/wdtt-NEW.bundle --all
git -C /owner/backups/wdtt-NEW.git bundle verify /owner/backups/wdtt-NEW.bundle
git clone --mirror /owner/backups/wdtt-NEW.bundle /owner/backups/wdtt-NEW-restore.git
git -C /owner/backups/wdtt-NEW-restore.git fsck --full
```

Compare `git for-each-ref` in source/restored mirrors. Offline builds can restore
an ordinary checkout from the bundle, select the exact pinned fork revision,
and pass it as `build_lab.py --source /absolute/clean-checkout`. This removes
GitHub source availability as a prerequisite. SDK and Go module archives remain
separate build dependencies; the source bundle is not a promise of an entirely
offline SDK/module bootstrap.

Upstream update: fetch upstream, `merge --ff-only` only the tracking branch,
stop on divergence, ordinary push. The maintained branch requires separate
review/integration and full regression; no force-push, automatic merge or
release. Exact commands and patch lineage are in the fork's provenance/README.

[qWDTT compatibility decision](QWDTT-COMPATIBILITY.md) is research only. Existing
deferred distribution work remains KAS#126; no license re-audit or public
binary channel is enabled by creating the fork.
