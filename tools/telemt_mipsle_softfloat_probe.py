#!/usr/bin/env python3
"""Tiny compile-only preflight: require genuine glibc-2.27 MIPSLE softfloat headers.

No Rust, QEMU, downloads, system changes or target execution.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from telemt_mipsle_fp_abi_gate import AbiError, inspect_elf

class ProbeError(RuntimeError):
    pass

def require_headers(path: Path) -> Path:
    if not path.is_dir():
        raise ProbeError(f"header root unavailable: {path}")
    for name in ("features.h", "gnu/stubs-o32_soft.h", "time.h", "sys/stat.h"):
        if not (path / name).is_file():
            raise ProbeError(f"missing glibc softfloat header {name} in {path}")
    return path.resolve(strict=True)

def run(cmd, *, input_text=None):
    try:
        p = subprocess.run(cmd, input=input_text, text=True, capture_output=True,
                           timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError(f"compiler missing or timed out: {exc}") from exc
    if p.returncode:
        raise ProbeError(f"compiler exit={p.returncode}: {p.stderr[:1200]}")
    return p.stdout

def probe(gcc, include):
    include = require_headers(include)
    flags = ["-msoft-float", "-isystem", str(include)]
    macros = run([gcc, *flags, "-dM", "-E", "-x", "c", "-"],
                 input_text="#include <features.h>\n")
    versions = {key: m.group(1) for key in ("__GLIBC__", "__GLIBC_MINOR__")
                if (m := re.search(r"^#define\s+" + key + r"\s+([0-9]+)\s*$", macros, re.M))}
    if versions != {"__GLIBC__": "2", "__GLIBC_MINOR__": "27"}:
        raise ProbeError(f"expected glibc 2.27 C headers; got {versions}")
    with tempfile.TemporaryDirectory(prefix="mipsel-sf-compile-") as td:
        src, obj = Path(td) / "probe.c", Path(td) / "probe.o"
        src.write_text("#include <time.h>\n#include <sys/stat.h>\n#include <unistd.h>\n"
                       "int test_stat(const char *p) { struct stat s; return stat(p, &s); }\n")
        run([gcc, *flags, "-fPIC", "-c", str(src), "-o", str(obj)])
        try:
            abi = inspect_elf(obj.read_bytes())
        except (OSError, AbiError) as exc:
            raise ProbeError(f"C object has no valid MIPS FP ABI proof: {exc}") from exc
        if not abi["softfloat_abi_ok"]:
            raise ProbeError(f"compiler did not produce a softfloat C object: {abi}")
    return {"status": "SOFTFLOAT_CC_PROBE_PASS", "glibc_headers": "2.27",
            "fp_abi": abi["fp_abi"], "scope": "C compile only; not linker/Rust/Core runtime"}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gcc", default="mipsel-linux-gnu-gcc")
    parser.add_argument("--headers", type=Path,
                        default=Path(os.environ.get("ENTWARE_MIPSEL_SOFTFLOAT_HEADERS",
                                                 "/missing-entware-mipsel-sdk")))
    args = parser.parse_args()
    try:
        print(json.dumps(probe(args.gcc, args.headers), indent=2))
        return 0
    except ProbeError as exc:
        print(json.dumps({"status": "SOFTFLOAT_SDK_BLOCKED", "reason": str(exc)},
                         indent=2), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
