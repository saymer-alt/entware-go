#!/usr/bin/env python3
"""Pinned aws-lc-sys 0.45.0 two-C-file smoke for Entware GCC8 MIPSLE.

Research-only: not a full aws-lc CMake build, Cargo or crypto runtime test.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
from urllib.request import urlopen

from telemt_mipsle_gcc8_cc1_smoke import ProbeError, prepare_sdk
from telemt_mipsle_cc_bridge import assemble, parse_command
from telemt_mipsle_fp_abi_gate import inspect_elf

VERSION = "0.45.0"
PKG_NAME = "aws-lc-sys"
CRATE = f"{PKG_NAME}-{VERSION}.crate"
CRATE_URL = f"https://static.crates.io/crates/{PKG_NAME}/{CRATE}"
CRATE_SHA = "9bff6c3b54fad79a2e60b8102caf565819711497c1f5f092f49508e2f5c31b27"
FILES = ("crypto/mem.c", "crypto/bytestring/cbs.c")


def pinned_crate(cache: Path) -> bytes:
    path = cache / CRATE
    if path.exists():
        blob = path.read_bytes()
    else:
        with urlopen(CRATE_URL, timeout=35) as r:
            if r.status != 200 or r.geturl() != CRATE_URL:
                raise ProbeError("untrusted aws-lc crate URL or HTTP status")
            blob = r.read(11_000_000)
    if hashlib.sha256(blob).hexdigest() != CRATE_SHA:
        raise ProbeError("aws-lc crate SHA-256 mismatch")
    if not path.exists():
        path.write_bytes(blob)
    return blob


def unpack_source(blob: bytes, workspace: Path) -> Path:
    prefix = f"{PKG_NAME}-{VERSION}"
    workspace.mkdir(parents=True, exist_ok=True)
    count = 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
        for member in archive:
            p = PurePosixPath(member.name)
            if p.is_absolute() or ".." in p.parts or not p.parts or p.parts[0] != prefix:
                raise ProbeError("unsafe aws-lc archive path")
            if member.isdir():
                continue
            if not member.isfile():
                raise ProbeError("unsupported aws-lc tar member")
            if member.size > 5_000_000:
                raise ProbeError("oversized aws-lc source member")
            dst = workspace.joinpath(*p.parts)
            if not dst.parent.resolve().is_relative_to(workspace.resolve()):
                raise ProbeError("aws-lc archive escape")
            dst.parent.mkdir(parents=True, exist_ok=True)
            body = archive.extractfile(member)
            if body is None:
                raise ProbeError("inaccessible aws-lc tar member")
            dst.write_bytes(body.read())
            count += 1
    root = workspace / prefix / "aws-lc"
    if count < 1800 or not (root / FILES[0]).is_file():
        raise ProbeError("aws-lc crate incomplete")
    return root


def run_subset(guestroot: Path, aws: Path, dest: Path) -> list[dict]:
    dest.mkdir(parents=True, exist_ok=True)
    records = []
    for index, name in enumerate(FILES):
        source = aws / name
        obj = dest / f"aws-lc-{index}.o"
        args = ["-c", str(source), "-o", str(obj), "-fPIC", "-O2", "-g0",
                "-DNDEBUG", "-I", str(aws / "include"),
                "-I", str(aws / "crypto"), "-I", str(aws)]
        src, output, opts = parse_command(args)
        assemble(guestroot, src, output, opts)
        got = inspect_elf(obj.read_bytes())
        if got["fp_abi"] != 3 or not got["softfloat_abi_ok"]:
            raise ProbeError("aws-lc source generated incompatible ABI")
        records.append({"source": name, "abi": got["fp_abi"],
                        "sha256": hashlib.sha256(obj.read_bytes()).hexdigest(),
                        "status": "PASS"})
    return records


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True, type=Path)
    a = p.parse_args()
    try:
        work = a.workspace.resolve()
        guest = prepare_sdk(work / "sdk")
        cache = work / "cache"
        cache.mkdir(exist_ok=True)
        aws = unpack_source(pinned_crate(cache), work / "crates")
        records = run_subset(guest, aws, work / "compiled-aws-lc")
        print(json.dumps({"status": "AWS_LC_C_SUBSET_SOFTFLOAT_PASS",
                          "aws_lc_version": VERSION, "objects": records,
                          "limitations": ["2 source files only",
                                          "no CMake / full aws-lc / TeleMT / runtime"]},
                         indent=2))
        return 0
    except (ProbeError, OSError, ValueError, tarfile.TarError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "AWS_LC_C_SUBSET_BLOCKED", "reason": str(exc)},
                         file=sys.stderr))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
