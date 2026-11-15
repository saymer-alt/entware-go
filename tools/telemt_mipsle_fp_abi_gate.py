#!/usr/bin/env python3
"""Strict ELF32 MIPSLE softfloat ABI check: .MIPS.abiflags and GNU attributes.

No QEMU, network, compiler or production-package changes.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import sys

class AbiError(ValueError):
    pass

def u16(b, i):
    return struct.unpack_from("<H", b, i)[0]

def u32(b, i):
    return struct.unpack_from("<I", b, i)[0]

def bounded(b, off, size, name):
    if off < 0 or size < 0 or off + size > len(b):
        raise AbiError(f"{name}: out of bounds")
    return b[off:off + size]

def uleb(b, pos, end):
    val = 0
    for shift in range(0, 35, 7):
        if pos >= end:
            raise AbiError("truncated ULEB in GNU attributes")
        v = b[pos]
        pos += 1
        val |= (v & 127) << shift
        if v & 128 == 0:
            return val, pos
    raise AbiError("oversized ULEB in GNU attributes")

def gnu_float_abi(data):
    # The MIPS GNU Tag_File / Tag_GNU_MIPS_ABI_FP fields are ULEB-encoded.
    if not data or data[0] != 65:
        raise AbiError("unknown GNU attribute format")
    pos, vals = 1, []
    while pos < len(data):
        start = pos
        bounded(data, pos, 4, "vendor length")
        size = u32(data, pos)
        end = start + size
        if size < 9 or end > len(data):
            raise AbiError("malformed GNU vendor length")
        zero = data.find(b"\0", pos + 4, end)
        if zero < 0:
            raise AbiError("unterminated GNU vendor")
        vendor, pos = data[pos + 4:zero], zero + 1
        while pos < end:
            sub = pos
            tag, pos = uleb(data, pos, end)
            if pos + 4 > end:
                raise AbiError("truncated GNU subsection")
            length = u32(data, pos)
            pos += 4
            subend = sub + length
            if subend < pos or subend > end:
                raise AbiError("invalid GNU subsection length")
            if vendor == b"gnu" and tag == 1:
                while pos < subend:
                    code, pos = uleb(data, pos, subend)
                    if code != 4:
                        raise AbiError(f"unexpected GNU MIPS attribute {code}")
                    fp, pos = uleb(data, pos, subend)
                    vals.append(fp)
            pos = subend
        pos = end
    if len(vals) != 1:
        raise AbiError(f"expected 1 GNU FP ABI attribute, found {len(vals)}")
    return vals[0]

def inspect_elf(b):
    if len(b) < 52 or b[:6] != b"\x7fELF\x01\x01":
        raise AbiError("not ELF32 little-endian")
    if u16(b, 18) != 8:
        raise AbiError("not MIPS")
    kind = u16(b, 16)
    if kind not in (1, 2, 3):
        raise AbiError("unsupported ELF kind")
    shoff, shents, shnum, shstr = u32(b, 32), u16(b, 46), u16(b, 48), u16(b, 50)
    if not shoff or not 0 < shnum <= 256 or shents < 40 or shstr >= shnum:
        raise AbiError("missing ELF sections")
    bounded(b, shoff, shents * shnum, "section table")
    sections = []
    for i in range(shnum):
        sections.append(struct.unpack_from("<IIIIII", b, shoff + i * shents)[:6])
    _, _, _, _, strings_off, strings_size = sections[shstr]
    strings = bounded(b, strings_off, strings_size, "section names")
    evidence, gnu = [], []
    for nameoff, typ, _, _, off, size in sections:
        if nameoff >= len(strings):
            raise AbiError("invalid ELF section name")
        end = strings.find(b"\0", nameoff)
        if end < 0:
            raise AbiError("unterminated ELF section name")
        name = strings[nameoff:end]
        if typ == 0x7000002a or name == b".MIPS.abiflags":
            x = bounded(b, off, size, ".MIPS.abiflags")
            if typ != 0x7000002a or size != 24:
                raise AbiError("invalid MIPS ABI flags section")
            evidence.append(("section", x[7], x[5]))
        if typ == 0x6ffffff5 or name == b".gnu.attributes":
            if typ != 0x6ffffff5:
                raise AbiError("invalid GNU attribute section type")
            gnu.append(gnu_float_abi(bounded(b, off, size, ".gnu.attributes")))
    if kind != 1:
        phoff, phents, phnum = u32(b, 28), u16(b, 42), u16(b, 44)
        if not phoff or not 0 < phnum <= 256 or phents < 32:
            raise AbiError("missing ELF program headers")
        bounded(b, phoff, phents * phnum, "program table")
        for i in range(phnum):
            typ, off, _, _, size = struct.unpack_from("<IIIII", b, phoff + i * phents)
            if typ == 0x70000003:
                x = bounded(b, off, size, "PT_MIPS_ABIFLAGS")
                if size != 24:
                    raise AbiError("bad PT_MIPS_ABIFLAGS size")
                evidence.append(("program", x[7], x[5]))
    if not evidence or (kind != 1 and not any(e[0] == "program" for e in evidence)):
        raise AbiError("missing MIPS ABI evidence")
    if len(gnu) != 1:
        raise AbiError("missing or duplicated GNU FP ABI")
    floats = {x[1] for x in evidence}
    cpr1s = {x[2] for x in evidence}
    if len(floats) != 1 or len(cpr1s) != 1 or next(iter(floats)) != gnu[0]:
        raise AbiError("ABI metadata disagreement (.gnu.attributes / MIPS ABI flags)")
    fp = next(iter(floats))
    # CPR1-size may legitimately be 32 even for soft-float Go binaries.
    return {"elf_type": {1: "ET_REL", 2: "ET_EXEC", 3: "ET_DYN"}[kind],
            "fp_abi": fp, "cpr1_size": next(iter(cpr1s)),
            "gnu_fp_attribute": gnu[0], "evidence": [e[0] for e in evidence],
            "softfloat_abi_ok": fp == 3}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+", help="MIPS ELF/.o, not IPK")
    args = parser.parse_args()
    rows = []
    for path in args.files:
        try:
            if not path.is_file() or path.stat().st_size > 96 * 1024 * 1024:
                raise AbiError("missing or oversized input ELF")
            got = inspect_elf(path.read_bytes())
            if not got["softfloat_abi_ok"]:
                raise AbiError(f"FP ABI={got['fp_abi']}, expected softfloat=3")
            rows.append({"path": str(path), "status": "SOFTFLOAT_PASS", **got})
        except (AbiError, OSError, struct.error) as exc:
            rows.append({"path": str(path), "status": "SOFTFLOAT_FAIL", "reason": str(exc)})
    failed = any(row["status"] != "SOFTFLOAT_PASS" for row in rows)
    print(json.dumps({"status": "FAIL" if failed else "PASS", "files": rows}, indent=2))
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
