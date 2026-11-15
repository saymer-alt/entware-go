#!/usr/bin/env python3
"""Offline TeleMT MIPSLE IPK verification and opt-in isolated qemu-user CLI smoke.

NOT full MT7621, native opkg, RAM, crypto, network, or physical acceptance.
No package installation, release mutation, or default process execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

from telemt_mipsle_ipk_preflight import audit, bounded_file, elf_info, ipk_parts

# Frozen GitHub Actions run 43624729371 / PR #44, verified 2026-11-14.
CORE_SHA = "a04f754375056439c3d5584bf7d868eb547f844c4779e3076bfbdd84129d63fa"
PANEL_SHA = "0236dfb076b14b129a6392de49f287838a11aebe7681e092084d4ce87e771e68"
NEEDED_LIBS = (
    "ld.so.1", "libc.so.6", "libgcc_s.so.1", "libpthread.so.0",
    "librt.so.1", "libm.so.6", "libdl.so.2",
)


class SmokeError(RuntimeError):
    pass


def mips_fp_abi(binary: bytes) -> int:
    """Read ELF32 MIPS PT_MIPS_ABIFLAGS.fp_abi; 3 is softfloat."""
    if len(binary) < 52 or binary[:6] != b"\x7fELF\x01\x01":
        raise SmokeError("invalid ELF32 little-endian")
    phoff = struct.unpack_from("<I", binary, 28)[0]
    phentsize, phnum = struct.unpack_from("<HH", binary, 42)
    if phentsize < 32 or phnum > 256 or phoff + phentsize * phnum > len(binary):
        raise SmokeError("invalid ELF32 program header table")
    matches = []
    for index in range(phnum):
        typ, offset, _, _, size = struct.unpack_from("<IIIII", binary, phoff + index * phentsize)
        if typ == 0x70000003:  # PT_MIPS_ABIFLAGS
            if size != 24 or offset + size > len(binary):
                raise SmokeError("malformed PT_MIPS_ABIFLAGS")
            matches.append(binary[offset + 7])
    if len(matches) != 1:
        raise SmokeError("expected exactly one PT_MIPS_ABIFLAGS segment")
    return matches[0]


def verify_ipk(path: Path, kind: str, expected_sha: str) -> tuple[dict, bytes]:
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha):
        raise SmokeError("expected SHA-256 must be 64 lowercase hex digits")
    blob = bounded_file(path)
    if hashlib.sha256(blob).hexdigest() != expected_sha:
        raise SmokeError(f"{kind}: package SHA-256 mismatch; no execution")
    report = audit(path, kind)
    if report["format"] != "ipk":
        raise SmokeError("expected complete IPK, not standalone ELF")
    _, payload = ipk_parts(blob)
    binary_path = "opt/bin/telemt" if kind == "core" else "opt/bin/telemt-panel"
    if set(payload) != {binary_path}:
        raise SmokeError(f"unexpected IPK payload paths (expected only {binary_path})")
    binary = payload[binary_path]
    if kind == "core":
        fp_abi = mips_fp_abi(binary)
        if fp_abi != 3:
            raise SmokeError(f"Core FP ABI {fp_abi} != Entware softfloat 3")
        report["checks"]["fp_abi"] = "PASS: MIPS softfloat (3)"
    return report, binary


def verify_lib_dir(lib_dir: Path) -> tuple[Path, Path]:
    if not lib_dir.is_dir():
        raise SmokeError("Entware library directory does not exist")
    root = lib_dir.resolve(strict=True)
    for name in NEEDED_LIBS:
        item = root / name
        if not item.is_file() or not item.resolve().is_relative_to(root):
            raise SmokeError(f"library missing or escapes provided Entware directory: {name}")
        try:
            info = elf_info(item.read_bytes())
        except (OSError, ValueError) as exc:
            raise SmokeError(f"invalid MIPS ELF library: {name}") from exc
        if info["machine"] != "MIPS" or info["elf_class"] != "ELF32":
            raise SmokeError(f"wrong library architecture: {name}")
    if mips_fp_abi((root / "ld.so.1").read_bytes()) != 3:
        raise SmokeError("Entware loader is not softfloat FP ABI=3")
    return root, root / "ld.so.1"


def run_qemu_cli(core: bytes, lib_dir: Path, timeout_seconds: int = 12) -> dict:
    qemu = shutil.which("qemu-mipsel")
    unshare = shutil.which("unshare")
    if not qemu or not unshare:
        raise SmokeError("QEMU_USER_BLOCKED: requires qemu-mipsel AND unshare (user+network namespaces)")
    libs, _loader = verify_lib_dir(lib_dir)
    with tempfile.TemporaryDirectory(prefix="telemt-qemu-user-") as td:
        root = Path(td) / "guestroot"
        bindir, libdir = root / "opt/bin", root / "opt/lib"
        bindir.mkdir(parents=True)
        libdir.mkdir(parents=True)
        binary = bindir / "telemt"
        binary.write_bytes(core)
        binary.chmod(0o700)
        # Copy the vetted Entware libraries into a disposable guest prefix.
        # Dereference symlinks verified to stay inside the trusted library dir.
        for name in NEEDED_LIBS:
            shutil.copyfile(libs / name, libdir / name)
        # Execute the guest *ELF itself*, so QEMU validates the actual
        # executable's PT_MIPS_ABIFLAGS against its PT_INTERP (PR #44 blocker).
        cmd = [unshare, "--user", "--map-root-user", "--net", "--",
               qemu, "-cpu", "24Kc", "-L", str(root), str(binary), "--version"]
        env = {"HOME": td, "TMPDIR": td, "PATH": "/usr/bin:/bin", "LANG": "C"}
        try:
            p = subprocess.run(cmd, cwd=td, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            raise SmokeError("QEMU_USER_BLOCKED: CLI test timed out (not a PASS)") from exc
        if p.returncode != 0:
            raise SmokeError(f"QEMU_USER_BLOCKED: guest exit={p.returncode}; inspect local stderr privately")
        return {"status": "QEMU_USER_CLI_SMOKE_PASS", "exit_code": p.returncode,
                "stdout_preview": p.stdout.decode("utf-8", "replace")[:300],
                "limitations": ["native guest ELF and actual PT_INTERP executed",
                                "no opkg/MT7621/crypto/network/real-router acceptance",
                                "library provenance must be verified separately"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-ipk", required=True, type=Path)
    parser.add_argument("--panel-ipk", type=Path)
    parser.add_argument(
        "--run-core-cli", action="store_true",
        help="opt-in QEMU user CLI smoke with user+network namespace isolation",
    )
    parser.add_argument(
        "--entware-lib-dir", type=Path,
        help="already unpacked, trusted Entware 2.27 /opt/lib",
    )
    args = parser.parse_args(argv)
    try:
        report, core = verify_ipk(args.core_ipk, "core", CORE_SHA)
        output = {
            "status": "STATIC_PREFLIGHT_PASS", "core": report["sha256"],
            "panel": "NOT_SUPPLIED", "QEMU_USER_CORE_CLI": "NOT_TESTED",
            "QEMU_SYSTEM_MT7621": "NOT_TESTED", "OPKG_INSTALL_ROLLBACK": "NOT_TESTED",
            "PHYSICAL_DEVICE": "NOT_TESTED",
        }
        if args.panel_ipk:
            panel, _ = verify_ipk(args.panel_ipk, "lite-rc4", PANEL_SHA)
            output["panel"] = panel["sha256"]
        if args.run_core_cli:
            if args.entware_lib_dir is None:
                raise SmokeError("--run-core-cli requires --entware-lib-dir")
            output["QEMU_USER_CORE_CLI"] = run_qemu_cli(core, args.entware_lib_dir)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (SmokeError, ValueError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
