#!/usr/bin/env python3
"""Pinned ring 0.17.14 C subset smoke with official Entware GCC8 softfloat.

Replicates the known ring build.rs PREFIX_SYMBOLS header for four real C files.
Not a full ring build, no Rust/Cargo, no AWS-LC, no production release.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
from urllib.request import urlopen

from telemt_mipsle_gcc8_cc1_smoke import ProbeError, prepare_sdk
from telemt_mipsle_cc_bridge import assemble, parse_command
from telemt_mipsle_fp_abi_gate import inspect_elf

VERSION = "0.17.14"
CRATE = f"ring-{VERSION}.crate"
CRATE_SHA = "a4689e6c2294d81e88dc6261c768b63bc4fcdb852be6d1352498b114f61383b7"
CRATE_URL = f"https://static.crates.io/crates/ring/{CRATE}"
FILES = (
    "crypto/mem.c",
    "crypto/limbs/limbs.c",
    "crypto/fipsmodule/aes/aes_nohw.c",
    "crypto/curve25519/curve25519.c",
)
COMMON_FLAGS = (
    "-fPIC", "-O2", "-g0", "-DNDEBUG", "-fvisibility=hidden", "-std=c1x",
    "-Wall", "-Wshadow", "-Wsign-conversion", "-ffunction-sections", "-fdata-sections",
)


def pinned_ring(cache: Path) -> bytes:
    path = cache / CRATE
    if path.exists():
        blob = path.read_bytes()
    else:
        with urlopen(CRATE_URL, timeout=32) as r:
            if r.status != 200 or r.geturl() != CRATE_URL:
                raise ProbeError("unexpected ring crate redirect/status")
            blob = r.read(2_400_000)
    if hashlib.sha256(blob).hexdigest() != CRATE_SHA:
        raise ProbeError("ring crate checksum mismatch")
    if not path.exists():
        path.write_bytes(blob)
    return blob


def extract_pinned_ring(blob: bytes, workspace: Path) -> Path:
    target = workspace / f"ring-{VERSION}"
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        items = 0
        for member in tar:
            p = PurePosixPath(member.name)
            if p.is_absolute() or ".." in p.parts or not p.parts or p.parts[0] != f"ring-{VERSION}":
                raise ProbeError("untrusted ring archive path")
            if not member.isfile():
                if member.isdir():
                    continue
                raise ProbeError("unsupported tar entry in ring crate")
            if member.size > 3_000_000:
                raise ProbeError("oversized ring source")
            dst = workspace.joinpath(*p.parts)
            if not dst.parent.resolve().is_relative_to(workspace.resolve()):
                raise ProbeError("ring archive escapes workspace")
            dst.parent.mkdir(parents=True, exist_ok=True)
            body = tar.extractfile(member)
            if body is None:
                raise ProbeError("inaccessible ring source file")
            dst.write_bytes(body.read())
            items += 1
    if items < 300 or not (target / "build.rs").is_file():
        raise ProbeError("ring crate incomplete")
    return target


def extract_build_rs_symbols(contents: str, declaration: str) -> str:
    pattern = "static " + declaration + ":"
    start = contents.find(pattern)
    if start < 0:
        raise ProbeError("ring build.rs symbol declarations not found")
    end = contents.find("];", start)
    if end < 0:
        raise ProbeError("ring build.rs symbol declarations not terminated")
    return contents[start:end]


def ring_prefix_header(buildrs: str) -> str:
    renames = re.findall(
        r'\("([A-Za-z0-9_]+)",\s*"([A-Za-z0-9_]+)"\)',
        extract_build_rs_symbols(buildrs, "SYMBOLS_TO_RENAME"))
    names = re.findall(r'"([A-Za-z0-9_]+)"',
                       extract_build_rs_symbols(buildrs, "SYMBOLS_TO_PREFIX"))
    if len(renames) != 7 or len(names) != 155 or len(names) != len(set(names)):
        raise ProbeError("ring build.rs symbol inventory changed")
    # Exact upstream rule: [CARGO_PKG_NAME, "core", major, minor, patch, prerelease]
    # joined with "_" and then an extra "_" before each renamed symbol.
    prefix = "ring_core_0_17_14__"
    lines = ["#ifndef ring_core_generated_PREFIX_SYMBOLS_H",
             "#define ring_core_generated_PREFIX_SYMBOLS_H"]
    lines += [f"#define {old} {new}" for old, new in renames]
    lines += [f"#define {name} {prefix}{name}" for name in names]
    lines.append("#endif")
    return "\n".join(lines) + "\n"


def compile_ring_subset(guestroot: Path, ring: Path, output: Path) -> list[dict]:
    output.mkdir(parents=True, exist_ok=True)
    generated = output / "generated/ring_core_generated/prefix_symbols.h"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text(ring_prefix_header((ring / "build.rs").read_text()), encoding="ascii")
    records = []
    for i, name in enumerate(FILES):
        src = ring / name
        dst = output / f"ring-{i}.o"
        # Real published ring build.rs adds generated_dir, c_root/include,
        # warnings and NDEBUG; output is a representative subset only.
        argv = ["-c", str(src), "-o", str(dst), *COMMON_FLAGS,
                "-I", str(ring / "include"), "-I", str(ring / "crypto"),
                "-I", str(output / "generated")]
        got_src, got_dst, opts = parse_command(argv)
        info = assemble(guestroot, got_src, got_dst, opts)
        checked = inspect_elf(dst.read_bytes())
        if info["fp_abi"] != 3 or checked["fp_abi"] != 3:
            raise ProbeError("ring subset object is non-softfloat")
        records.append({"source": name, "sha256": hashlib.sha256(dst.read_bytes()).hexdigest(),
                        "abi": checked["fp_abi"], "status": "PASS"})
    return records


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True, type=Path)
    args = p.parse_args()
    try:
        workspace = args.workspace.resolve()
        guestroot = prepare_sdk(workspace / "sdk")
        cache = workspace / "cache"
        cache.mkdir(exist_ok=True)
        ring = extract_pinned_ring(pinned_ring(cache), workspace / "crates")
        objects = compile_ring_subset(guestroot, ring, workspace / "compiled-ring")
        print(json.dumps({"status": "RING_C_SUBSET_SOFTFLOAT_PASS",
                          "ring_version": VERSION, "objects": objects,
                          "limitations": ["4 C sources only", "no full ring build",
                                          "no AWS-LC/Cargo/Core execution"]}, indent=2))
        return 0
    except (ProbeError, OSError, ValueError, tarfile.TarError,
            subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "RING_C_SUBSET_BLOCKED", "reason": str(exc)}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
