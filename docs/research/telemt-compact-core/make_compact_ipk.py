#!/usr/bin/env python3
"""Pack an unofficial stripped TeleMT IPC MIPSLE binary as an isolated opkg IPK.

The original frozen IPC binary is NOT recompiled or replaced on existing routers.
Outer IPK is a gzip-compressed tar containing debian-binary, control and data tarballs.
"""
import argparse
import gzip
import hashlib
import io
import math
from pathlib import Path
import tarfile

PACKAGE = "telemt-ipc-compact"
VERSION = "3.5.17-1ipc2c1"
ARCH = "mipsel-3.4"
SOURCE_SHA = "fbf5ef4c2cad4a564483c29a584986623181574b798ec5b787cdc93c27e15daa"
RESERVE_KIB = 16 * 1024
EPOCH = 1760380800


def tarball(entries):
    mem = io.BytesIO()
    with gzip.GzipFile(fileobj=mem, mode="wb", compresslevel=9, mtime=0, filename="") as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tf:
            for name, data, mode, is_dir in entries:
                info = tarfile.TarInfo(name)
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mtime = EPOCH
                info.mode = mode
                if is_dir:
                    info.type = tarfile.DIRTYPE
                    info.size = 0
                else:
                    info.size = len(data)
                tf.addfile(info, None if is_dir else io.BytesIO(data))
    return mem.getvalue()


def unpack_frozen_ipk(ipk):
    assert hashlib.sha256(ipk).hexdigest() == SOURCE_SHA, "frozen source IPK SHA-256 mismatch"
    with tarfile.open(fileobj=io.BytesIO(ipk), mode="r:gz") as outer:
        data = outer.extractfile("./data.tar.gz").read()
        control = outer.extractfile("./control.tar.gz").read()
    with tarfile.open(fileobj=io.BytesIO(control), mode="r:gz") as inner:
        meta = inner.extractfile("./control").read().decode()
        assert "Package: telemt-ipc-lab\n" in meta
        assert "Version: 3.5.17-1ipc2\n" in meta
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as inner:
        files = [x for x in inner.getmembers() if x.isfile()]
        assert len(files) == 1 and files[0].name.lstrip("./") == "opt/bin/telemt-ipc-lab"
        elf = inner.extractfile(files[0]).read()
    assert elf[:4] == b"\x7fELF"
    return elf


def run(args):
    original_ipk = Path(args.frozen_ipk).read_bytes()
    original_elf = unpack_frozen_ipk(original_ipk)
    binary = Path(args.stripped_elf).read_bytes()
    assert binary[:4] == b"\x7fELF" and len(binary) < len(original_elf)
    root = Path(args.scripts)
    init = (root / "S98telemt-ipc-compact").read_bytes()
    configurator = (root / "telemt-compact-configure").read_bytes()
    assert init.startswith(b"#!/bin/sh") and configurator.startswith(b"#!/bin/sh")
    needed = math.ceil(len(binary) / 1024) + math.ceil(len(init) / 1024) + math.ceil(len(configurator) / 1024) + RESERVE_KIB
    control = (
        f"Package: {PACKAGE}\n"
        f"Version: {VERSION}\n"
        f"Architecture: {ARCH}\n"
        "Maintainer: saymer-alt/entware-go unofficial port\n"
        "Section: net\n"
        "Depends: libc, libgcc, libpthread, librt\n"
        f"Installed-Size: {math.ceil((len(binary)+len(init)+len(configurator))/1024)}\n"
        "Description: Unofficial TeleMT IPC MIPSel stripped Core-only for MT7621.\n"
        " Local control socket for Linux 4.9; no Panel; isolated from /opt/bin/telemt.\n"
        " Not tested on physical KN-1913; no automatic start until owner opts in.\n"
        "Source: https://github.com/telemt/telemt\n"
    ).encode()
    preinst = f"""#!/bin/sh
# Fail closed BEFORE unpacking to persistent /opt. Deliberately conservative:
# assumes no filesystem compression, reserves 16 MiB for KAS/Mihomo upgrades.
set -eu
[ -d /opt ] && [ -x /opt/bin/opkg ] || exit 1
free_kib=$(df -k /opt | /opt/bin/busybox awk 'END {{print $4}}')
case "$free_kib" in ''|*[!0-9]*) echo 'Cannot measure persistent flash' >&2; exit 1;; esac
if [ "$free_kib" -lt {needed} ]; then
 echo "NOT_ENOUGH_PERSISTENT_FLASH: free=$free_kib KiB, required={needed} KiB (includes 16 MiB safety reserve)" >&2
 echo 'Do not delete KAS/Mihomo; use external /opt or a smaller verified binary.' >&2
 exit 1
fi
exit 0
""".encode()
    control_gz = tarball([
        ("./control", control, 0o644, False),
        ("./preinst", preinst, 0o755, False),
    ])
    data_gz = tarball([
        ("./opt/", b"", 0o755, True),
        ("./opt/bin/", b"", 0o755, True),
        ("./opt/etc/", b"", 0o755, True),
        ("./opt/etc/init.d/", b"", 0o755, True),
        ("./opt/bin/telemt-ipc-compact", binary, 0o755, False),
        ("./opt/bin/telemt-compact-configure", configurator, 0o755, False),
        # Intentional 0644: disabling auto start until owner explicitly enables it.
        ("./opt/etc/init.d/S98telemt-ipc-compact", init, 0o644, False),
    ])
    payload = tarball([
        ("./debian-binary", b"2.0\n", 0o644, False),
        ("./control.tar.gz", control_gz, 0o644, False),
        ("./data.tar.gz", data_gz, 0o644, False),
    ])
    Path(args.output).write_bytes(payload)
    # In-memory integrity and mode regression gate
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as pkg:
        c = pkg.extractfile("./control.tar.gz").read()
        d = pkg.extractfile("./data.tar.gz").read()
    with tarfile.open(fileobj=io.BytesIO(c), mode="r:gz") as inner:
        assert inner.getmember("./preinst").mode == 0o755
        assert inner.extractfile("./control").read() == control
    with tarfile.open(fileobj=io.BytesIO(d), mode="r:gz") as inner:
        paths = {p.name.lstrip("./") for p in inner.getmembers() if p.isfile()}
        assert paths == {"opt/bin/telemt-ipc-compact", "opt/bin/telemt-compact-configure",
                         "opt/etc/init.d/S98telemt-ipc-compact"}
        assert inner.getmember("./opt/etc/init.d/S98telemt-ipc-compact").mode == 0o644
        assert inner.extractfile("./opt/bin/telemt-ipc-compact").read() == binary
    print(f"ORIGINAL_ELF_BYTES={len(original_elf)}")
    print(f"COMPACT_ELF_BYTES={len(binary)}")
    print(f"ORIGINAL_IPK_BYTES={len(original_ipk)}")
    print(f"COMPACT_IPK_BYTES={len(payload)}")
    print(f"CONSERVATIVE_MIN_FREE_KIB={needed}")
    print(f"COMPACT_IPK_SHA256={hashlib.sha256(payload).hexdigest()}")
    print("IPK_STRUCTURE_AND_PREINST_PASSED")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen-ipk", required=True)
    ap.add_argument("--stripped-elf", required=True)
    ap.add_argument("--scripts", required=True)
    ap.add_argument("--output", required=True)
    run(ap.parse_args())
