#!/usr/bin/env python3
"""Offline, no-exec audit of TeleMT Core/Panel IPKs and binaries for Entware MIPSLE.

Based on tools/telemt_mipsle_panel_preflight.py (Draft PR #42, panel modes kept
unchanged) and extended with a "core" mode for the dynamically linked TeleMT
3.5.17 core built against the Entware mipsel-3.4 ABI.

Does NOT attest provenance, execute the binary, install IPK, or prove QEMU runtime.
Only Python standard library is required. Run on a trusted desktop/CI host.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tarfile

MAX_INPUT = 64 * 1024 * 1024
MAX_MEMBER = 64 * 1024 * 1024
KNOWN_LEGACY_PANEL_SHA256 = "0cfb926660bf130fcc81e87c1ad40514d0f7ff2e0c1973cc9dbe7ad1928ab9a2"
ENTWARE_INTERP = "/opt/lib/ld.so.1"


class AuditError(ValueError):
    pass


def bounded_file(path: Path) -> bytes:
    if not path.is_file() or path.stat().st_size > MAX_INPUT:
        raise AuditError("input missing or exceeds 64 MiB")
    return path.read_bytes()


def tar_members(blob: bytes, *, label: str) -> dict[str, bytes]:
    try:
        t = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")
    except (tarfile.TarError, OSError) as exc:
        raise AuditError(f"invalid gzip tar: {label}") from exc
    out = {}
    total = 0
    with t:
        ms = t.getmembers()
        if len(ms) > 256:
            raise AuditError(f"too many tar entries: {label}")
        for m in ms:
            raw_name = m.name
            if raw_name.startswith("/") or ".." in raw_name.split("/"):
                raise AuditError(f"unsafe tar path: {label}")
            key = raw_name.removeprefix("./")
            if m.issym() or m.islnk() or m.isdev():
                raise AuditError(f"unsafe tar member type: {label}")
            if not m.isfile():
                continue
            if m.size > MAX_MEMBER or key in out or not key or key.startswith("/"):
                raise AuditError(f"oversized, duplicated or unsafe tar member: {label}")
            total += m.size
            if total > MAX_MEMBER * 2:
                raise AuditError("extracted members exceed 128 MiB")
            f = t.extractfile(m)
            if f is None:
                raise AuditError("unreadable member")
            out[key] = f.read(MAX_MEMBER + 1)
            if len(out[key]) > MAX_MEMBER:
                raise AuditError("member too large")
    return out


def ar_members(blob: bytes) -> dict[str, bytes]:
    if not blob.startswith(b"!<arch>\n"):
        raise AuditError("not an ar archive")
    p = 8
    out = {}
    while p < len(blob):
        if p + 60 > len(blob) or blob[p + 58:p + 60] != b"\x60\n":
            raise AuditError("malformed ar header")
        header = blob[p:p + 60]
        name = header[:16].decode("ascii", "strict").strip().rstrip("/")
        size_str = header[48:58].decode("ascii", "strict").strip()
        if not size_str.isdecimal():
            raise AuditError("invalid ar size")
        size = int(size_str)
        p += 60
        if size > MAX_MEMBER or p + size > len(blob) or name in out or not name or name.startswith("#1/"):
            raise AuditError("invalid, duplicate or unsupported ar member")
        out[name] = blob[p:p + size]
        p += size + (size & 1)
    return out


def ipk_parts(blob: bytes) -> tuple[dict[str, str], dict[str, bytes]]:
    if blob.startswith(b"!<arch>\n"):
        outer = ar_members(blob)
    else:
        outer = tar_members(blob, label="outer IPK")
    cont = [k for k in outer if k.startswith("control.tar.")]
    data = [k for k in outer if k.startswith("data.tar.")]
    if len(cont) != 1 or len(data) != 1 or not cont[0].endswith(".gz") or not data[0].endswith(".gz"):
        raise AuditError("expected unique control.tar.gz and data.tar.gz")
    control = tar_members(outer[cont[0]], label="control.tar.gz")
    payload = tar_members(outer[data[0]], label="data.tar.gz")
    if "control" not in control:
        raise AuditError("missing control file")
    fields = {}
    try:
        raw_text = control["control"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuditError("non-UTF8 control") from exc
    for line in raw_text.splitlines():
        if ": " not in line:
            continue
        k, v = line.split(": ", 1)
        if k in {"Package", "Version", "Architecture"}:
            if k in fields:
                raise AuditError(f"duplicated {k} in control")
            fields[k] = v
    return fields, payload


def elf_info(binary: bytes) -> dict:
    if len(binary) < 52 or binary[:4] != b"\x7fELF":
        raise AuditError("not an ELF binary")
    if binary[4:6] != b"\x01\x01" or struct.unpack_from("<H", binary, 18)[0] != 8:
        raise AuditError("not ELF32 little-endian MIPS")
    e_type = struct.unpack_from("<H", binary, 16)[0]
    flags = struct.unpack_from("<I", binary, 36)[0]
    phoff = struct.unpack_from("<I", binary, 28)[0]
    phentsize, phnum = struct.unpack_from("<HH", binary, 42)
    if phnum > 256 or (phnum and phentsize < 32) or phoff + phentsize * phnum > len(binary):
        raise AuditError("invalid ELF program header table")
    interp = None
    dynamic = False
    fp_abis = []
    for n in range(phnum):
        at = phoff + n * phentsize
        p_type, p_offset, _, _, p_filesz = struct.unpack_from("<IIIII", binary, at)
        if p_offset + p_filesz > len(binary):
            raise AuditError("ELF segment outside file")
        if p_type == 0x70000003:  # PT_MIPS_ABIFLAGS
            if p_filesz != 24:
                raise AuditError("malformed PT_MIPS_ABIFLAGS")
            fp_abis.append(binary[p_offset + 7])
        if p_type == 2:
            dynamic = True
        if p_type == 3:
            s = binary[p_offset:p_offset + p_filesz].rstrip(b"\0")
            interp = s.decode("ascii", "replace")
    return {"elf_class": "ELF32", "endianness": "little", "machine": "MIPS", "elf_type": e_type,
            "mips_arch_flag": f"0x{flags & 0xf0000000:08x}", "interpreter": interp,
            "dynamic_segment": dynamic, "mips_fp_abi": fp_abis[0] if len(fp_abis) == 1 else None,
            "mips_abi_segments": len(fp_abis), "size_bytes": len(binary)}


def audit(path: Path, kind: str, require_legacy_hash: bool = True) -> dict:
    blob = bounded_file(path)
    expected = {
        "old-panel": ("telemt-panel", "0.6.2-1", "telemt-panel"),
        "lite-rc4": ("telemt-panel-lite", "1.0.0~rc.4-1", "telemt-panel"),
        "core": ("telemt", "3.5.17-1", "telemt"),
        # getrandom-ENOSYS-only /dev/urandom fallback rebuild (research-only,
        # separate workflow; see docs/research/telemt-mipsle-ipk-3517/getrandom-fallback/)
        "core-getfb": ("telemt", "3.5.17-2fb1", "telemt"),
    }
    pkg, version, program = expected[kind]
    is_ipk = not blob.startswith(b"\x7fELF")
    if kind == "old-panel" and not is_ipk:
        raise AuditError("historical panel must be checked as complete IPK")
    output = {"mode": kind, "input": path.name, "sha256": hashlib.sha256(blob).hexdigest(),
              "format": "ipk" if is_ipk else "ELF", "checks": {}, "limitations": [
                  "No executable was started", "No QEMU/opkg/Telegram/KN-1913 runtime verification",
                  "An observed SHA256 does not by itself prove publisher trust"]}
    if kind == "old-panel" and require_legacy_hash and output["sha256"] != KNOWN_LEGACY_PANEL_SHA256:
        raise AuditError("historical IPK checksum differs from independently recorded PoC")
    if is_ipk:
        fields, payload = ipk_parts(blob)
        wanted = {"Package": pkg, "Version": version, "Architecture": "mipsel-3.4"}
        if fields != wanted:
            raise AuditError(f"unexpected package control: {fields}")
        matches = [(name, data) for name, data in payload.items() if name.rsplit("/", 1)[-1] == program]
        if len(matches) != 1:
            raise AuditError("expected exactly one program binary")
        forbidden = [name for name in payload if name.startswith(("opt/etc/", "opt/var/")) or
                     name.startswith("opt/etc/init.d/")]
        if forbidden:
            raise AuditError("package carries live config, service scripts or state under /opt/etc or /opt/var")
        binary = matches[0][1]
        output["checks"]["ipk_control"] = fields
        output["checks"]["binary_path"] = matches[0][0]
    else:
        binary = blob
    info = elf_info(binary)
    if kind == "lite-rc4" and (info["interpreter"] or info["dynamic_segment"]):
        raise AuditError("expected self-contained pure-Go Lite binary, got dynamic ELF")
    if kind in ("core", "core-getfb"):
        if not info["dynamic_segment"]:
            raise AuditError("expected dynamically linked TeleMT core, got static ELF")
        if info["interpreter"] != ENTWARE_INTERP:
            raise AuditError(f"expected Entware interpreter {ENTWARE_INTERP}, got {info['interpreter']}")
        if info["mips_abi_segments"] != 1 or info["mips_fp_abi"] != 3:
            raise AuditError("Core MIPS FP ABI is not Entware softfloat (PT_MIPS_ABIFLAGS=3 required)")
    output["checks"]["elf"] = info
    output["checks"]["arch"] = "PASS: ELF32 MIPS little-endian"
    if kind in ("core", "core-getfb"):
        output["checks"]["entware_abi"] = f"PASS: dynamic, MIPS softfloat fp_abi=3, interpreter {ENTWARE_INTERP} (glibc versions separately gated via readelf -V)"
    output["checks"]["packaging"] = "PASS: control and payload" if is_ipk else "NOT_TESTED: raw ELF"
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", required=True,
                        choices=("old-panel", "lite-rc4", "core", "core-getfb"))
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--skip-legacy-hash", action="store_true",
                        help="Only for synthetic fixtures; do not use to approve real archived packages")
    args = parser.parse_args()
    try:
        result = audit(args.file, args.kind, require_legacy_hash=not args.skip_legacy_hash)
    except (AuditError, OSError, struct.error, tarfile.TarError) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"status": "STATIC_PREFLIGHT_PASS", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
