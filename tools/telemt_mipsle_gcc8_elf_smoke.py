#!/usr/bin/env python3
"""Prove a tiny dynamic Entware MIPSLE GCC8 ELF runs under isolated qemu-user.

C/GCC8 cc1 + host GNU MIPS assembler/linker + real Entware glibc 2.27.
NOT TeleMT, rustc, cargo, native opkg, KeeneticOS nor release acceptance.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

from telemt_mipsle_fp_abi_gate import inspect_elf
from telemt_mipsle_gcc8_cc1_smoke import (
    ProbeError, compile_source, prepare_sdk, run_cmd,
)

GCC8_LIB = "opt/lib/gcc/mipsel-openwrt-linux-gnu/8.4.0"
TEST_PROGRAM = "int main(void) { return 17; }\n"
INTERP = b"/opt/lib/ld.so.1"


def elf_interp(data: bytes) -> bytes:
    """Read actual PT_INTERP; a runnable static binary is not sufficient."""
    if len(data) < 52 or data[:6] != b"\x7fELF\x01\x01":
        raise ProbeError("invalid ELF32LE")
    phoff, entsize, count = struct.unpack_from("<I", data, 28)[0], *struct.unpack_from("<HH", data, 42)
    if entsize < 32 or count < 1 or count > 256 or phoff + entsize * count > len(data):
        raise ProbeError("invalid program table")
    matches = []
    for i in range(count):
        typ, off, _, _, size = struct.unpack_from("<IIIII", data, phoff + i * entsize)
        if typ == 3:
            if size < 2 or off + size > len(data) or data[off + size - 1] != 0:
                raise ProbeError("invalid PT_INTERP")
            matches.append(data[off:off + size - 1])
    if len(matches) != 1:
        raise ProbeError("expected exactly one dynamic PT_INTERP")
    return matches[0]


def link_and_run(root: Path) -> dict:
    qemu, unshare, ld = (shutil.which(tool) for tool in ("qemu-mipsel", "unshare", "mipsel-linux-gnu-ld"))
    if not all((qemu, unshare, ld)):
        raise ProbeError("qemu-mipsel/unshare/mipsel-linux-gnu-ld must be installed")
    lib = root / GCC8_LIB
    for file in ("crt1.o", "crti.o", "crtbegin.o", "crtend.o", "crtn.o", "libc.so", "libc_nonshared.a"):
        if not (lib / file).is_file():
            raise ProbeError(f"missing genuine Entware GCC8 library {file}")
    with tempfile.TemporaryDirectory(prefix="telemt-mipsle-elf-smoke-") as td:
        stage = Path(td)
        source, obj, executable = stage / "hello.c", stage / "hello.o", stage / "hello"
        source.write_text(TEST_PROGRAM, encoding="ascii")
        compile_source(root, source, obj)
        run_cmd([ld, "-m", "elf32ltsmip", "-EL", "--eh-frame-hdr",
                 "-dynamic-linker", INTERP.decode("ascii"),
                 "-o", str(executable),
                 str(lib / "crt1.o"), str(lib / "crti.o"), str(lib / "crtbegin.o"),
                 "-L", str(lib), "-L", str(root / "opt/lib"),
                 str(obj), "-rpath", "/opt/lib",
                 "-lgcc_s", "-lc", "-lgcc_s",
                 str(lib / "crtend.o"), str(lib / "crtn.o")], timeout=25)
        data = executable.read_bytes()
        abi = inspect_elf(data)
        if not abi["softfloat_abi_ok"] or abi["fp_abi"] != 3:
            raise ProbeError("linked binary is not softfloat FP ABI 3")
        interp = elf_interp(data)
        if interp != INTERP:
            raise ProbeError(f"unexpected PT_INTERP {interp!r}")
        p = subprocess.run([unshare, "--user", "--map-root-user", "--net", "--",
                            qemu, "-cpu", "24Kc", "-L", str(root), str(executable)],
                           capture_output=True, timeout=18, check=False,
                           env={"PATH": "/usr/bin:/bin", "LANG": "C"})
        if p.returncode != 17 or p.stdout or p.stderr:
            raise ProbeError(f"MIPSLE dynamic runtime failed: exit={p.returncode}; stderr={p.stderr[:200]!r}")
        return {"status": "DYNAMIC_ENTWARE_GCC8_GLIBC227_QEMU_USER_PASS",
                "main_exit": p.returncode, "fp_abi": abi["fp_abi"],
                "pt_interp": interp.decode("ascii"),
                "elf_sha256": hashlib.sha256(data).hexdigest(),
                "scope": "minimal C executable only; no TeleMT/Cargo/MT7621/opkg acceptance"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True, type=Path, help="disposable scratch workspace")
    args = p.parse_args()
    try:
        root = prepare_sdk(args.workspace)
        print(json.dumps(link_and_run(root), indent=2))
        return 0
    except (ProbeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
