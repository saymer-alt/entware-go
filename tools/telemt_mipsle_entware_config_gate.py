#!/usr/bin/env python3
"""Cheap offline guard for selecting the *real* Entware MIPSLE 3.4 toolchain.

Checks the Entware buildroot configuration and compiler version. This is
not a substitute for the glibc 2.27 C-header and ELF probes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


class ConfigError(ValueError):
    pass


EXPECTED = {
    "CONFIG_TARGET_mipsel_3_4": "y",
    "CONFIG_TARGET_ARCH_PACKAGES": '"mipsel-3.4"',
    "CONFIG_CPU_TYPE": '"mips32r2"',
    "CONFIG_SOFT_FLOAT": "y",
    "CONFIG_GCC_VERSION": '"8.4.0"',
    "CONFIG_GLIBC_VERSION": '"2.27"',
    "CONFIG_LIBC_USE_GLIBC": "y",
    "CONFIG_GCC_USE_VERSION_8": "y",
    "CONFIG_GLIBC_USE_VERSION_2_27": "y",
    "CONFIG_NEED_TOOLCHAIN": "y",
}


def check_config(content: str) -> dict:
    values = {}
    for line in content.splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            name, val = line.split("=", 1)
            if name in values:
                raise ConfigError(f"duplicate {name}")
            values[name] = val.strip()
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            key = line[2:-11]
            if key in values:
                raise ConfigError(f"duplicate {key}")
            values[key] = "n"
    for key, expected in EXPECTED.items():
        if values.get(key) != expected:
            raise ConfigError(f"{key}: expected {expected}, got {values.get(key)}")
    if values.get("CONFIG_EXTERNAL_TOOLCHAIN") == "y":
        raise ConfigError("external toolchain selected: buildroot settings do not prove its ABI")
    if values.get("CONFIG_TARGET_mips_3_4") == "y":
        raise ConfigError("big-endian MIPS target enabled")
    flags = values.get("CONFIG_TARGET_OPTIMIZATION", "")
    if "-mips32r2" not in flags or "-mtune=mips32r2" not in flags:
        raise ConfigError("target optimization is not MIPS32r2")
    return {"config": "ENTWARE_MIPSEL_3_4_PASS",
            "gcc_expected": "8.4.0", "glibc_expected": "2.27",
            "softfloat": True}


def check_compiler(cmd: str) -> dict:
    try:
        info = subprocess.run([cmd, "-dumpfullversion"], capture_output=True, text=True,
                              timeout=8, check=True).stdout.strip()
        target = subprocess.run([cmd, "-dumpmachine"], capture_output=True, text=True,
                                timeout=8, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ConfigError(f"compiler unavailable: {type(exc).__name__}") from exc
    if not info.startswith("8.4.0") or not re.fullmatch(
            r"mipsel(?:-[a-z0-9_+.-]+){1,}", target):
        raise ConfigError(f"compiler mismatch: version={info!r} target={target!r}")
    return {"compiler": "ENTWARE_MIPSEL_COMPILER_VERSION_PASS",
            "version": info, "target": target}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--gcc", help="explicit Entware GCC8.4 path (optional)")
    args = parser.parse_args()
    try:
        config = check_config(args.config.read_text(encoding="utf-8"))
        if args.gcc:
            config.update(check_compiler(args.gcc))
        else:
            config["compiler"] = "NOT_TESTED"
        print(json.dumps(config, ensure_ascii=False, indent=2))
        return 0
    except (ConfigError, OSError, UnicodeError) as exc:
        print(json.dumps({"status": "CONFIG_BLOCKED", "reason": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
