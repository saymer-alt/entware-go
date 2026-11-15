#!/usr/bin/env python3
"""Research-only cc-rs-style C/.S compiler bridge for MIPSLE Entware GCC8.

C: actual native GCC8 cc1 executed inside isolated qemu-user, host MIPS assembler.
.S: target GCC preprocessor (not C compiler), target assembler, both softfloat.
Compile-only, never links; unsupported flags fail closed, no network in guest.
Does NOT prove cargo/aws-lc/ring full builds or replace Entware buildroot.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from telemt_mipsle_fp_abi_gate import inspect_elf
from telemt_mipsle_gcc8_cc1_smoke import CC1, ProbeError, check_root


def parse_command(argv: list[str]) -> tuple[Path, Path, list[str]]:
    """Accept bounded GCC -c commands, no arbitrary gcc driver/linker actions."""
    source: str | None = None
    output: str | None = None
    opts: list[str] = []
    saw_compile = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-c",):
            saw_compile = True
        elif arg == "-o":
            i += 1
            if i >= len(argv) or output is not None:
                raise ProbeError("missing or duplicated -o")
            output = argv[i]
        elif arg in ("-I", "-D", "-U", "-isystem", "-iquote", "-include"):
            i += 1
            if i >= len(argv):
                raise ProbeError("missing flag value")
            opts.extend((arg, argv[i]))
        elif arg.startswith(("-I", "-D", "-U")) and len(arg) > 2:
            opts.append(arg)
        elif arg in ("-pipe", "-pthread"):
            # -pipe does not affect a single-output cc1; -pthread defines _REENTRANT.
            if arg == "-pthread":
                opts.append("-D_REENTRANT")
        elif arg in ("-fPIC", "-fpic", "-fPIE", "-fpie", "-fno-omit-frame-pointer",
                     "-ffunction-sections", "-fdata-sections", "-fvisibility=hidden",
                     "-fno-builtin", "-fno-strict-aliasing", "-fno-common",
                     "-fstack-protector", "-fstack-protector-strong",
                     "-fno-stack-protector", "-fno-asynchronous-unwind-tables",
                     "-fomit-frame-pointer", "-w", "-pedantic", "-pedantic-errors",
                     "-fno-unwind-tables", "-fno-lto"):
            opts.append(arg)
        elif arg.startswith(("-O", "-g")) and re.fullmatch(
                r"-(?:O[0-3sSz]|g(?:[0-3]|gdb[0-3]|dwarf-[2-5])?)", arg):
            opts.append(arg)
        elif arg.startswith(("-Wl,", "-Wa,", "-Wp,", "-Wl=", "-Wa=", "-Wp=")):
            raise ProbeError(f"unsupported compiler-driver pass-through {arg!r}")
        elif arg.startswith("-W") and re.fullmatch(r"-W[A-Za-z0-9_,=.+-]+", arg):
            opts.append(arg)
        elif arg.startswith("-std=") and re.fullmatch(r"-std=(?:c(?:89|90|99|11|17|1x|2x)|gnu(?:89|90|99|11|17|1x|2x))", arg):
            opts.append(arg)
        elif arg in ("-msoft-float", "-mips32r2", "-march=mips32r2", "-mabi=32",
                     "-EL", "-funsigned-char", "-fsigned-char"):
            # These settings are compatible with target; ensure no hard-float overrides.
            opts.append(arg)
        elif arg.startswith("-"):
            raise ProbeError(f"unsupported or unsafe GCC flag {arg!r}")
        elif source is None:
            source = arg
        else:
            raise ProbeError("multiple input files not supported")
        i += 1
    if not saw_compile or not source or not output:
        raise ProbeError("compile-only -c SOURCE -o OUTPUT required")
    src, dst = Path(source).resolve(), Path(output).absolute()
    if src.suffix not in (".c", ".s", ".S"):
        raise ProbeError(f"unsupported source extension: {src.suffix}")
    if not src.is_file() or src.stat().st_size > 2 * 1024 * 1024:
        raise ProbeError("missing or oversized source")
    if not dst.parent.is_dir() or dst.is_dir():
        raise ProbeError("output parent must exist")
    # Do not accept environment-supplied response files or link inputs.
    if any("@" in item for item in opts):
        raise ProbeError("response-file style arguments not supported")
    return src, dst, opts


def exec_bounded(cmd: list[str], seconds: int, *, no_guest_net: bool = False) -> None:
    p = subprocess.run(cmd, timeout=seconds, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                       env={"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": "/tmp"})
    if p.returncode:
        raise ProbeError(f"compile step failed: exit={p.returncode}; stderr={p.stderr[:850].decode('utf-8','replace')}")


def assemble(root: Path, src: Path, dst: Path, opts: list[str]) -> dict:
    check_root(root)
    for n in ("qemu-mipsel", "unshare", "mipsel-linux-gnu-as"):
        if not shutil.which(n):
            raise ProbeError(f"required tool unavailable: {n}")
    if src.suffix == ".S" and not shutil.which("mipsel-linux-gnu-gcc"):
        raise ProbeError("preprocessing .S requires target mipsel-linux-gnu-gcc")
    with tempfile.TemporaryDirectory(prefix="telemt-cc8-bridge-") as td:
        stage = Path(td)
        asm, obj = stage / "input.s", stage / "output.o"
        if src.suffix == ".c":
            # cc1 accepts compile options, not driver-only '-c' or '-o' of arbitrary objects.
            cc1 = root / CC1
            cmd = [shutil.which("unshare"), "--user", "--map-root-user", "--net", "--",
                   shutil.which("qemu-mipsel"), "-cpu", "24Kc", "-L", str(root),
                   str(cc1), "-quiet", "-msoft-float", "-march=mips32r2",
                   "-isystem", str(root / "opt/include"),
                   *opts, str(src), "-o", str(asm)]
            exec_bounded(cmd, 45, no_guest_net=True)
        elif src.suffix == ".S":
            # No host x86 preprocessor built-ins; use target cross GCC -E only.
            ccopts = [x for x in opts if x not in ("-fPIC", "-fpic", "-fPIE", "-fpie")
                      and not x.startswith(("-O", "-g", "-W", "-f"))]
            exec_bounded([shutil.which("mipsel-linux-gnu-gcc"), "-E", "-x",
                          "assembler-with-cpp", "-msoft-float", "-march=mips32r2",
                          "-nostdinc", "-isystem", str(root / "opt/include"),
                          *ccopts, str(src), "-o", str(asm)], 20)
        else:
            shutil.copyfile(src, asm)
        if not asm.is_file() or asm.stat().st_size == 0:
            raise ProbeError("compiler generated empty assembly")
        exec_bounded([shutil.which("mipsel-linux-gnu-as"), "-mips32r2",
                      "-msoft-float", "-EL", "-o", str(obj), str(asm)], 20)
        if not obj.is_file() or obj.stat().st_size == 0:
            raise ProbeError("assembler generated empty object")
        evidence = inspect_elf(obj.read_bytes())
        if evidence["fp_abi"] != 3 or not evidence["softfloat_abi_ok"]:
            raise ProbeError(f"FP ABI incompatible: {evidence['fp_abi']}")
        # A fresh validated result atomically replaces an old object.
        scratch = dst.parent / (dst.name + ".telemt-validated-tmp")
        if scratch.exists():
            raise ProbeError("refuse to overwrite existing temporary output")
        try:
            scratch.write_bytes(obj.read_bytes())
            os.replace(scratch, dst)
        finally:
            if scratch.exists():
                scratch.unlink()
    return {"status": "SOFTFLOAT_C_BRIDGE_PASS", "kind": src.suffix, "fp_abi": 3}


def detect_compiler_family(root: Path, argv: list[str]) -> int:
    """cc-rs '-E path.c' family detection via the *real* Entware GCC8 cc1.

    GCC-family recognition must not silently use a host x86 or distro hardfloat
    compiler. This mode is preprocessing only: no object/library can be emitted.
    """
    if len(argv) != 2 or argv[0] != "-E":
        raise ProbeError("unsupported preprocessor invocation")
    source = Path(argv[1]).resolve()
    if not source.is_file() or source.suffix != ".c" or source.stat().st_size > 100_000:
        raise ProbeError("unsafe compiler-family probe source")
    check_root(root)
    qemu, unshare = shutil.which("qemu-mipsel"), shutil.which("unshare")
    if not qemu or not unshare:
        raise ProbeError("QEMU isolation unavailable for -E probe")
    cmd = [unshare, "--user", "--map-root-user", "--net", "--",
           qemu, "-cpu", "24Kc", "-L", str(root),
           str(root / CC1), "-E", "-quiet", "-msoft-float",
           "-march=mips32r2", "-isystem", str(root / "opt/include"), str(source)]
    result = subprocess.run(cmd, timeout=16, stdin=subprocess.DEVNULL,
                            capture_output=True, check=False,
                            env={"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": "/tmp"})
    if result.returncode:
        raise ProbeError(f"compiler family probe failed: exit={result.returncode}; "
                         f"stderr={result.stderr[:400]!r}")
    if len(result.stdout) > 1_000_000:
        raise ProbeError("oversized compiler-family probe output")
    sys.stdout.buffer.write(result.stdout)
    return 0


def main() -> int:
    try:
        root_name = os.environ.get("ENTWARE_MIPSEL_GUESTROOT", "")
        if not root_name:
            raise ProbeError("ENTWARE_MIPSEL_GUESTROOT is required; never auto-download inside cc-rs")
        root = Path(root_name).resolve(strict=True)
        if sys.argv[1:2] == ["-E"]:
            return detect_compiler_family(root, sys.argv[1:])
        source, output, args = parse_command(sys.argv[1:])
        evidence = assemble(root, source, output, args)
        if os.environ.get("ENTWARE_CC_VERBOSE") == "1":
            print(evidence, file=sys.stderr)
        return 0
    except (ProbeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"ENTWARE_MIPSEL_CC_BRIDGE_BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
