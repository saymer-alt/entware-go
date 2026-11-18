#!/usr/bin/env python3
"""Download SHA-pinned public Entware inputs before starting the disposable MT7621 guest."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

INSTALLER_URL = "https://bin.entware.net/mipselsf-k3.4/installer/EN_mipsel-installer.tar.gz"
INSTALLER_SHA = "f7fa2611cbbefa3cb770b90f02121fb057a4b343db87f0c2a1ef7be28a14613f"


def assets(emulator_root):
    root = Path(emulator_root).resolve()
    sys.path.insert(0, str(root))
    from lab.build_entware import MIPSLSF_ORIGIN, validate_mipsel_lock
    lock = json.loads((root / "lab/entware-mipselsf.lock.json").read_text())
    validate_mipsel_lock(lock)
    if lock["installer"] != {"url": INSTALLER_URL, "sha256": INSTALLER_SHA}:
        raise ValueError("pinned Entware installer drift")
    rows = [("installer.tar.gz", INSTALLER_URL, INSTALLER_SHA)]
    for p in lock["packages"]:
        name, digest = p["Filename"], p["SHA256sum"]
        url = MIPSLSF_ORIGIN + ("keenetic/" if p["feed"] == "keenetic" else "") + name
        if (not re.fullmatch(r"[A-Za-z0-9._+~-]+\.ipk", name)
                or p["url"] != url or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("untrusted Entware asset")
        rows.append((name, url, digest))
    if len({row[0] for row in rows}) != len(rows):
        raise ValueError("duplicate cache destination")
    return rows


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_cache(cache, rows):
    cache = Path(cache)
    if not cache.is_dir() or cache.is_symlink():
        raise ValueError("missing or symlinked public asset cache")
    if {p.name for p in cache.iterdir()} != {r[0] for r in rows}:
        raise ValueError("public asset cache incomplete or contains unexpected files")
    for name, _, digest in rows:
        path = cache / name
        if path.is_symlink() or not path.is_file() or sha256(path) != digest:
            raise ValueError("public asset cache hash mismatch: " + name)
    return len(rows)


def warm_cache(cache, rows):
    cache = Path(cache)
    if cache.is_symlink():
        raise ValueError("symlinked public asset cache")
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name, url, digest in rows:
        path = cache / name
        if path.exists() or path.is_symlink():
            if path.is_symlink() or not path.is_file() or sha256(path) != digest:
                raise ValueError("restored asset hash mismatch: " + name)
            continue
        fd, temporary = tempfile.mkstemp(prefix=name + ".", suffix=".partial", dir=cache)
        os.close(fd)
        try:
            command = [
                "curl", "--fail", "--location", "--silent", "--show-error",
                "--retry", "4", "--retry-all-errors", "--retry-delay", "3",
                "--retry-max-time", "360", "--connect-timeout", "15",
                "--max-time", "120", "--output", temporary, url
            ]
            result = subprocess.run(command, capture_output=True, timeout=420)
            if result.returncode != 0:
                raise RuntimeError("bounded download failed for pinned asset: " + name)
            if sha256(temporary) != digest:
                raise ValueError("download checksum mismatch: " + name)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return verify_cache(cache, rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emulator-root", type=Path, required=True)
    ap.add_argument("--cache-dir", type=Path)
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args()
    rows = assets(args.emulator_root)
    if args.check_only:
        print("PINNED_ENTWARE_ASSET_PLAN_PASS count=" + str(len(rows)))
        return 0
    if args.cache_dir is None:
        ap.error("--cache-dir required unless --check-only")
    count = warm_cache(args.cache_dir, rows)
    print("PINNED_ENTWARE_ASSET_CACHE_PASS count=" + str(count))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
