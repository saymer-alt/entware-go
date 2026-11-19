#!/usr/bin/env python3
"""Create isolated research MIPSel IPK with UPX-packed TeleMT Core.

Never changes the existing RAM2 install or copies secrets into the package.
"""
import argparse
import hashlib
import io
import math
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from make_compact_ipk import tarball, unpack_frozen_ipk

PACKAGE = "telemt-ipc-upx"
VERSION = "3.5.17-1ipc2upx1"
SPARE_KIB = 7168  # 7MiB reserve for controlled experiment
OVERHEAD_KIB = 512


def main(a):
    source = Path(a.original_ipk).read_bytes()
    frozen_elf = unpack_frozen_ipk(source)
    packed = Path(a.upx_elf).read_bytes()
    unpacked = Path(a.unpacked_elf).read_bytes()
    assert packed[:4] == b"\x7fELF" and unpacked[:4] == b"\x7fELF"
    assert len(packed) < len(unpacked) < len(frozen_elf)
    # Externally run UPX -t and -d; builder verifies the externally unpacked bytes.
    assert unpacked == Path(a.stripped_elf).read_bytes(), "UPX unpacking changes binary"
    license_text = Path(a.license).read_bytes()
    assert b"TELEMT LICENSE 3.3" in license_text
    service = Path(a.init_script).read_bytes()
    assert service.startswith(b"#!/bin/sh")
    assert b"/opt/etc/telemt-compact-ram" in service
    assert b"S99telemt-ipc-upx" in service
    assert b"S99telemt-ipc-compact-ram" in service, "missing dual-boot guard"
    installed_bytes = len(packed) + len(service) + len(license_text)
    needed_kib = math.ceil(installed_bytes / 1024) + SPARE_KIB + OVERHEAD_KIB
    preinst = f"""#!/bin/sh
# Conservative no-compression estimate; keeps 7MiB free after first install.
set -eu
[ -x /opt/bin/opkg ] || exit 1
free_kib=$(df -k /opt | /opt/bin/busybox awk 'END {{print $4}}')
case "$free_kib" in ''|*[!0-9]*) echo 'unable to measure NAND' >&2; exit 1;; esac
if [ "$free_kib" -lt {needed_kib} ]; then
  echo "TELEMT_UPX_FLASH_GUARD: free=$free_kib KiB required={needed_kib} KiB (7MiB safety reserve)" >&2
  exit 1
fi
exit 0
""".encode()
    ctrl = (
        f"Package: {PACKAGE}\n"
        f"Version: {VERSION}\n"
        "Architecture: mipsel-3.4\n"
        "Maintainer: entware-go MIPSel laboratory <noreply@users.noreply.github.com>\n"
        "Section: net\n"
        "Depends: libc, libgcc, libpthread, librt\n"
        f"Installed-Size: {math.ceil(installed_bytes / 1024)}\n"
        "Description: Experimental TeleMT MIPSel native UPX ELF Core only.\n"
        " Contains no panel/config, reuses existing RAM2 secret, no autostart.\n"
        " Separate binary and init name; never overwrites other TeleMT or KAS.\n"
        " Only for supervised hardware validation, not production feed.\n"
        "Source: https://github.com/telemt/telemt\n"
    ).encode()
    c = tarball([("./control", ctrl, 0o644, False), ("./preinst", preinst, 0o755, False)])
    d = tarball([
        ("./opt/", b"", 0o755, True),
        ("./opt/bin/", b"", 0o755, True),
        ("./opt/etc/", b"", 0o755, True),
        ("./opt/etc/init.d/", b"", 0o755, True),
        ("./opt/share/", b"", 0o755, True),
        ("./opt/share/doc/", b"", 0o755, True),
        ("./opt/share/doc/telemt-ipc-upx/", b"", 0o755, True),
        ("./opt/bin/telemt-ipc-upx", packed, 0o755, False),
        ("./opt/etc/init.d/S99telemt-ipc-upx", service, 0o644, False),
        ("./opt/share/doc/telemt-ipc-upx/LICENSE.TELEMT.txt", license_text, 0o644, False),
    ])
    ipk = tarball([
        ("./debian-binary", b"2.0\n", 0o644, False),
        ("./control.tar.gz", c, 0o644, False),
        ("./data.tar.gz", d, 0o644, False),
    ])
    Path(a.output).write_bytes(ipk)
    with tarfile.open(fileobj=io.BytesIO(ipk), mode="r:gz") as outer:
        assert set(outer.getnames()) == {"./debian-binary", "./control.tar.gz", "./data.tar.gz"}
        data_bytes = outer.extractfile("./data.tar.gz").read()
        control_bytes = outer.extractfile("./control.tar.gz").read()
    with tarfile.open(fileobj=io.BytesIO(data_bytes),mode="r:gz") as inner:
        files={e.name.lstrip("./") for e in inner.getmembers() if e.isfile()}
        assert files == {
            "opt/bin/telemt-ipc-upx",
            "opt/etc/init.d/S99telemt-ipc-upx",
            "opt/share/doc/telemt-ipc-upx/LICENSE.TELEMT.txt"}
        assert inner.getmember("./opt/etc/init.d/S99telemt-ipc-upx").mode == 0o644
        assert inner.extractfile("./opt/bin/telemt-ipc-upx").read() == packed
    with tarfile.open(fileobj=io.BytesIO(control_bytes),mode="r:gz") as inner:
        assert inner.getmember("./preinst").mode == 0o755
        assert b"Architecture: mipsel-3.4" in inner.extractfile("./control").read()
    print(f"ORIGINAL_ELF_BYTES={len(frozen_elf)}")
    print(f"UPX_NATIVE_ELF_BYTES={len(packed)}")
    print(f"UPX_NATIVE_IPK_BYTES={len(ipk)}")
    print(f"UPX_MIN_NAND_FREE_KIB={needed_kib}")
    print(f"UPX_NATIVE_IPK_SHA256={hashlib.sha256(ipk).hexdigest()}")
    print("UPX_IPK_CONTENTS_AND_SERVICE_GUARD_PASS")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for v in ("original-ipk", "stripped-elf", "upx-elf", "unpacked-elf", "init-script",
              "license", "output"):
        p.add_argument("--"+v, required=True)
    main(p.parse_args())
