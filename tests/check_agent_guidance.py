#!/usr/bin/env python3
"""Read-only, no-network guard against agent-context and package-authority regression."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ["docs/agent-guidance/01-owner-policy-and-authority.md","docs/agent-guidance/02-repository-fork-and-package-publishing.md","docs/agent-guidance/03-go-compatibility-and-change-checklist.md"]
SOURCE_HEADINGS = ["## Owner-wide design gate — SIMPLICITY-FIRST (2026-10-24)","## ⚑ Решение владельца от 2026-10-11: WORKING-FIRST / LICENSE AUDIT DEFERRED","## What this repo is","## Layout","## Go compatibility rule (high-care)","## Fork-specific vs upstream","## Before every commit / push","## Requires explicit owner approval","## Technical debt"]
MANDATORY = ["gh-action-build","spatiumstas/entware-go","Draft PR","owner GO","WORKING-FIRST","LICENSE","GOTOOLCHAIN=local","GOTOOLCHAIN=auto","go.mod","SHA-256","latest","entware-latest-publication","PKG_MIRROR_HASH:=skip","warpscout","mihomo","beszel-agent","sync-upstream.yml","telegram-push.yml","main","master","/opt","WDTT"]

def main():
    root = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    size = len(root.encode("utf-8"))
    assert size <= 10_240, f"AGENTS.md startup exceeds 10 KiB: {size}"
    for term in MANDATORY:
        assert term.casefold() in root.casefold(), f"missing mandatory startup safety item: {term}"
    corpus = ""
    for guide in GUIDES:
        assert f"]({guide})" in root, f"root does not link scoped guide: {guide}"
        data = (ROOT / guide).read_text(encoding="utf-8")
        assert "Source-preserving move" in data, f"missing source preservation marker: {guide}"
        corpus += data + "\n"
    for heading in SOURCE_HEADINGS:
        assert heading in corpus, f"original agent section missing: {heading}"
    for name in ["AGENTS.md", *GUIDES]:
        for url in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", (ROOT / name).read_text(encoding="utf-8")):
            target = url.split("#", 1)[0]
            if not target or re.match(r"^(?:https?:|mailto:|/)", target, re.I):
                continue
            assert ((ROOT / name).parent / target).is_file(), f"broken local Markdown link {name} -> {url}"
    print(f"Agent context contract: PASS, {size} bytes, {len(GUIDES)} guides, {len(SOURCE_HEADINGS)} original headings")

if __name__ == "__main__":
    main()
