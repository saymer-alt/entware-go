#!/usr/bin/env python3
"""Fail-closed inspection of a Cargo cc-rs MIPSLE static .a archive.

Never executes archive members; uses MIPS binutils 'ar p' to read bytes and the
research MIPS ELF ABI parser to ensure every object is real soft-float MIPS32.
No side effects on router or release artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from telemt_mipsle_fp_abi_gate import inspect_elf

class ArchiveError(ValueError):
    pass


def ar_cmd(args: list[str]) -> bytes:
    try:
        p = subprocess.run(args, capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ArchiveError(f"archive tool unavailable or timed out: {type(exc).__name__}") from exc
    if p.returncode:
        raise ArchiveError(f"archive tool error: exit={p.returncode}")
    if len(p.stdout) > 64 * 1024 * 1024:
        raise ArchiveError("archive tool produced too many bytes")
    return p.stdout


def inspect_archive(archive: Path, expected_count: int,
                    required_symbol: str | None = None) -> dict:
    if not 1 <= expected_count <= 64:
        raise ArchiveError("expected_count must be between 1 and 64")
    if not archive.is_file() or not 8 <= archive.stat().st_size <= 64 * 1024 * 1024:
        raise ArchiveError("archive missing or outside size bound")
    ar = shutil.which("mipsel-linux-gnu-ar")
    if not ar:
        raise ArchiveError("mipsel-linux-gnu-ar missing")
    raw = ar_cmd([ar, "t", str(archive)])
    try:
        members = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ArchiveError("archive contains invalid member names") from exc
    if len(members) != expected_count:
        raise ArchiveError(f"archive member count {len(members)} != {expected_count}")
    if len(set(members)) != len(members):
        raise ArchiveError("duplicate archive member names")
    if not all(re.fullmatch(r"[A-Za-z0-9_.+-]+\.o", name) for name in members):
        raise ArchiveError("unexpected archive member name")
    records = []
    for name in members:
        data = ar_cmd([ar, "p", str(archive), name])
        if len(data) < 52 or len(data) > 16 * 1024 * 1024:
            raise ArchiveError(f"invalid or oversized ELF object {name}")
        try:
            evidence = inspect_elf(data)
        except (ValueError, IndexError) as exc:
            raise ArchiveError(f"invalid MIPS ELF object {name}: {exc}") from exc
        if evidence["elf_type"] != "ET_REL" or evidence["fp_abi"] != 3 \
                or not evidence["softfloat_abi_ok"]:
            raise ArchiveError(f"{name} is not a MIPS32 softfloat relocatable object")
        records.append({"name": name, "fp_abi": 3,
                        "sha256": hashlib.sha256(data).hexdigest()})
    if required_symbol:
        if not re.fullmatch(r"[A-Za-z0-9_]+", required_symbol):
            raise ArchiveError("unsafe symbol name")
        nm = shutil.which("mipsel-linux-gnu-nm")
        if not nm:
            raise ArchiveError("mipsel-linux-gnu-nm unavailable")
        symbols = ar_cmd([nm, "--defined-only", str(archive)]).decode("utf-8", "replace")
        if not re.search(r"(?m)\s[A-Z]\s+" + re.escape(required_symbol) + r"$", symbols):
            raise ArchiveError(f"required symbol not defined: {required_symbol}")
    return {"status": "CCRS_MIPSLE_ARCHIVE_SOFTFLOAT_PASS",
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "objects": records, "object_count": len(records),
            "scope": "static C-archive only; no Rust linker/Core/CMake acceptance"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--expected-objects", type=int, required=True)
    p.add_argument("--required-symbol")
    args = p.parse_args()
    try:
        print(json.dumps(inspect_archive(args.archive, args.expected_objects,
                                         args.required_symbol), indent=2))
        return 0
    except (ArchiveError, OSError) as exc:
        print(json.dumps({"status": "CCRS_ARCHIVE_BLOCKED", "reason": str(exc)}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
