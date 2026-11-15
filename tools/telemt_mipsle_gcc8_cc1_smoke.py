#!/usr/bin/env python3
"""Compile a tiny MIPSLE C object using the genuine Entware GCC 8.4 cc1 via QEMU.

Research-only: no Cargo, linking, live routers, network inside guest or releases.
Use with the fixed upstream shim.c; do NOT use as a general drop-in Cargo compiler.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen

from telemt_mipsle_fp_abi_gate import inspect_elf

FEED = "https://bin.entware.net/mipselsf-k3.4/"
PINS = {
    "gcc_8.4.0-9_mipsel-3.4.ipk": "2d56b649742903e229235e231898effef4aa969c5b5d48468a7e1a6d2bb39db5",
    "libc_2.27-12_mipsel-3.4.ipk": "45c7ef0bda2acb4475a75efee9734e83f69f54e128971b7a196d88c8b048a222",
    "libgcc_8.4.0-12_mipsel-3.4.ipk": "bbecc26b579470d52053b72e41dddb70415963eac9f74baf1747b9d2ecdcaaa3",
    "libstdcpp_8.4.0-12_mipsel-3.4.ipk": "5e1c6a59222ed9bc65a9a55f7f48aaba53655b53f4f9e3f36d5845bb101dcddc",
}
REQUIRED = (
    "opt/lib/ld.so.1",
    "opt/lib/libc.so.6",
    "opt/lib/libgcc_s.so.1",
    "opt/lib/libstdc++.so.6",
    "opt/include/gnu/stubs-o32_soft.h",
    "opt/include/features.h",
    "opt/lib/gcc/mipsel-openwrt-linux-gnu/8.4.0/cc1",
)
CC1 = "opt/lib/gcc/mipsel-openwrt-linux-gnu/8.4.0/cc1"
MAX_IPK = 48 * 1024 * 1024

class ProbeError(ValueError):
    pass

def verified_ipk(name: str, cache: Path) -> bytes:
    if name not in PINS:
        raise ProbeError("unapproved IPK")
    path = cache / name
    if path.is_file():
        blob = path.read_bytes()
    else:
        with urlopen(FEED + name, timeout=50) as r:
            if r.geturl() != FEED + name or r.status != 200:
                raise ProbeError(f"unexpected package redirect/status: {name}")
            blob = r.read(MAX_IPK + 1)
        if len(blob) > MAX_IPK:
            raise ProbeError("IPK exceeds bounded size")
    if hashlib.sha256(blob).hexdigest() != PINS[name]:
        raise ProbeError(f"SHA-256 mismatch for {name}")
    if not path.exists():
        path.write_bytes(blob)
    return blob

def safe_member_path(name: str) -> Path:
    posix = PurePosixPath(name)
    parts = [part for part in posix.parts if part != "."]
    if not parts or posix.is_absolute() or ".." in parts or parts[0] != "opt":
        raise ProbeError(f"unsafe package member: {name}")
    return Path(*parts)

def unpack_ipk(blob: bytes, root: Path, package: str) -> int:
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as ar:
            archive = next((item for item in ar if item.name.lstrip("./") == "data.tar.gz"), None)
            if archive is None:
                raise ProbeError(f"missing data.tar.gz: {package}")
            stream = ar.extractfile(archive)
            if stream is None:
                raise ProbeError("inaccessible IPK data")
            payload = stream.read(170 * 1024 * 1024 + 1)
        if len(payload) > 170 * 1024 * 1024:
            raise ProbeError("unpacked IPK data exceeds limit")
        count = 0
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as contents:
            for member in contents:
                if member.name in ('.', './'):
                    continue
                dst = safe_member_path(member.name)
                if dst.parts[:2] not in (("opt", "include"), ("opt", "lib"), ("opt", "bin")):
                    continue
                dest = root / dst
                if not dest.parent.resolve().is_relative_to(root.resolve()):
                    raise ProbeError("package archive escapes root")
                if member.isdir():
                    dest.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    if member.size > 64 * 1024 * 1024:
                        raise ProbeError("oversized ELF/header file")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    src = contents.extractfile(member)
                    if src is None:
                        raise ProbeError("missing tar member body")
                    dest.write_bytes(src.read())
                    dest.chmod(member.mode & 0o755)
                    count += 1
                elif member.issym():
                    target = PurePosixPath(member.linkname)
                    if target.is_absolute() or ".." in target.parts:
                        raise ProbeError("unsafe symlink in IPK")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if dest.exists() or dest.is_symlink():
                        raise ProbeError("duplicate symlink target")
                    dest.symlink_to(member.linkname)
                elif member.islnk():
                    raise ProbeError("hardlink in IPK not supported")
        return count
    except (tarfile.TarError, OSError) as exc:
        raise ProbeError(f"invalid IPK {package}: {type(exc).__name__}") from exc

def check_root(root: Path) -> None:
    for file in REQUIRED:
        p = root / file
        if not p.is_file() or not p.resolve().is_relative_to(root.resolve()):
            raise ProbeError(f"SDK missing or escaping required file {file}")
    if b"# include <gnu/stubs-o32_soft.h>" not in (root / "opt/include/gnu/stubs.h").read_bytes():
        raise ProbeError("SDK has unexpected soft-float stubs selection")

def run_cmd(args: list[str], timeout: int) -> None:
    p = subprocess.run(args, capture_output=True, text=True, check=False,
                       timeout=timeout, env={"PATH": "/usr/bin:/bin", "LANG": "C"})
    if p.returncode:
        raise ProbeError(f"command failed (exit {p.returncode}): {p.stderr[:500]}")

def compile_source(root: Path, src: Path, output: Path) -> dict:
    check_root(root)
    if not src.is_file() or not src.resolve().is_file() or src.stat().st_size > 100_000:
        raise ProbeError("source missing or too large")
    if output.exists():
        raise ProbeError("refusing to overwrite output")
    qemu = shutil.which("qemu-mipsel")
    unshare = shutil.which("unshare")
    assembler = shutil.which("mipsel-linux-gnu-as")
    if not all((qemu, unshare, assembler)):
        raise ProbeError("qemu-mipsel, unshare and mipsel-linux-gnu-as required")
    cc1 = root / CC1
    with tempfile.TemporaryDirectory(prefix="telemt-gcc8-softfloat-") as td:
        asm = Path(td) / "shim.s"
        obj = Path(td) / "shim.o"
        run_cmd([unshare, "--user", "--map-root-user", "--net", "--",
                 qemu, "-cpu", "24Kc", "-L", str(root), str(cc1),
                 "-quiet", "-msoft-float", "-fPIC",
                 "-isystem", str(root / "opt/include"),
                 str(src.resolve()), "-o", str(asm)], timeout=35)
        run_cmd([assembler, "-mips32r2", "-o", str(obj), str(asm)], timeout=15)
        evidence = inspect_elf(obj.read_bytes())
        if not evidence["softfloat_abi_ok"] or evidence["fp_abi"] != 3:
            raise ProbeError("compiler/assembler produced non-softfloat object")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(obj.read_bytes())
        return {"status": "GENUINE_GCC8_CC1_SOFTFLOAT_OBJECT_PASS",
                "fp_abi": evidence["fp_abi"],
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "scope": "C object only; not full GCC driver, linker, Cargo or TeleMT runtime"}

def prepare_sdk(workspace: Path) -> Path:
    work = workspace.resolve()
    if work in (Path("/"), Path("/opt"), Path("/usr")):
        raise ProbeError("use a disposable scratch workspace")
    work.mkdir(parents=True, exist_ok=True)
    root, cache = work / "guestroot", work / "verified-ipks"
    root.mkdir(exist_ok=True)
    cache.mkdir(exist_ok=True)
    for name in PINS:
        unpack_ipk(verified_ipk(name, cache), root, name)
    check_root(root)
    return root


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True, type=Path, help="scratch directory, not /opt")
    p.add_argument("--source", required=True, type=Path, help="local existing C source")
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    try:
        root = prepare_sdk(a.workspace)
        result = compile_source(root, a.source, a.output)
        print(json.dumps(result, indent=2))
        return 0
    except (ProbeError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
