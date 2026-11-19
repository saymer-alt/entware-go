#!/usr/bin/env python3
"""Make unofficial Core-only XZ-on-flash, tmpfs-at-runtime Entware IPK."""
import argparse
import hashlib
import io
import lzma
import math
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from make_compact_ipk import tarball, unpack_frozen_ipk

NAME = "telemt-ipc-compact-ram"
VERSION = "3.5.17-1ipc2ram2"
SOURCE_SHA = "fbf5ef4c2cad4a564483c29a584986623181574b798ec5b787cdc93c27e15daa"
# 16MiB fixed KAS headroom plus 0.75 MiB for xz/liblzma dependencies and opkg state.
RESERVE_KIB = 16384
DEP_KIB = 768


def run(a):
    original = unpack_frozen_ipk(Path(a.frozen_ipk).read_bytes())
    stripped = Path(a.stripped_elf).read_bytes()
    assert stripped[:4] == b"\x7fELF" and len(stripped) < len(original)
    xz = Path(a.xz_payload).read_bytes()
    assert lzma.decompress(xz) == stripped, "xz decompression not identical to frozen stripped ELF"
    scripts = Path(a.scripts)
    loader = (scripts / "telemt-compact-ram-loader.sh").read_bytes()
    assert loader.startswith(b"#!/bin/sh") and b"ELF_KIB_PLACEHOLDER" in loader
    loader = loader.replace(b"ELF_KIB_PLACEHOLDER", str(math.ceil(len(stripped)/1024)).encode())
    service = (scripts / "S99telemt-ipc-compact-ram").read_bytes()
    configurator = (scripts / "telemt-compact-ram-configure").read_bytes()
    assert service.startswith(b"#!/bin/sh") and configurator.startswith(b"#!/bin/sh")
    expected = hashlib.sha256(stripped).hexdigest().encode() + b"\n"
    license_text = Path(a.license).read_bytes()
    assert b"TELEMT LICENSE 3.3" in license_text

    min_flash_kib = (math.ceil(len(xz)/1024) + math.ceil(
        (len(loader)+len(service)+len(configurator)+len(license_text))/1024)
        + RESERVE_KIB + DEP_KIB)
    preinst = f"""#!/bin/sh
set -eu
# Check persistent NAND, not KAS S00ubifs RAM overlay /opt/tmp.
[ -x /opt/bin/opkg ] || exit 1
free_kib=$(df -k /opt | /opt/bin/busybox awk 'END {{print $4}}')
case "$free_kib" in ''|*[!0-9]*) echo 'Cannot measure flash space' >&2; exit 1;; esac
if [ "$free_kib" -lt {min_flash_kib} ]; then
 echo "NOT_ENOUGH_PERSISTENT_FLASH: available=$free_kib KiB required={min_flash_kib} KiB (includes 16 MiB KAS reserve + 0.75 MiB dependency reserve)" >&2
 exit 1
fi
# The launcher separately checks /tmp execute capability, free tmpfs and RAM.
exit 0
""".encode()
    ctrl = (
        f"Package: {NAME}\n"
        f"Version: {VERSION}\n"
        "Architecture: mipsel-3.4\n"
        "Maintainer: saymer-alt/entware-go experimental\n"
        "Section: net\n"
        "Depends: libc, libgcc, libpthread, librt, xz\n"
        f"Installed-Size: {math.ceil((len(xz)+len(loader)+len(service)+len(configurator)+len(license_text))/1024)}\n"
        "Description: Unofficial TeleMT 3.5.17-1ipc2 compact Core-only for MT7621.\n"
        " XZ stored in /opt flash; verified stripped ELF extracted into /tmp tmpfs at runtime.\n"
        " Does not replace ordinary Telemt. No Panel, no default secrets, boot disabled.\n"
        "Source: https://github.com/telemt/telemt\n"
    ).encode()
    control_tar = tarball([
        ("./control", ctrl, 0o644, False),
        ("./preinst", preinst, 0o755, False),
    ])
    data_tar = tarball([
        ("./opt/", b"", 0o755, True),
        ("./opt/bin/", b"", 0o755, True),
        ("./opt/etc/", b"", 0o755, True),
        ("./opt/etc/init.d/", b"", 0o755, True),
        ("./opt/share/", b"", 0o755, True),
        ("./opt/share/telemt-compact-ram/", b"", 0o755, True),
        ("./opt/share/doc/", b"", 0o755, True),
        ("./opt/share/doc/telemt-ipc-compact-ram/", b"", 0o755, True),
        ("./opt/bin/telemt-ipc-compact-ram", loader, 0o755, False),
        ("./opt/bin/telemt-compact-ram-configure", configurator, 0o755, False),
        ("./opt/etc/init.d/S99telemt-ipc-compact-ram", service, 0o644, False),
        ("./opt/share/telemt-compact-ram/telemt.xz", xz, 0o644, False),
        ("./opt/share/telemt-compact-ram/telemt.sha256", expected, 0o644, False),
        ("./opt/share/doc/telemt-ipc-compact-ram/LICENSE.TELEMT.txt",
         license_text, 0o644, False),
    ])
    ipk = tarball([
        ("./debian-binary", b"2.0\n", 0o644, False),
        ("./control.tar.gz", control_tar, 0o644, False),
        ("./data.tar.gz", data_tar, 0o644, False),
    ])
    Path(a.output).write_bytes(ipk)
    with tarfile.open(fileobj=io.BytesIO(ipk),mode="r:gz") as outer:
        contents=outer.extractfile("./data.tar.gz").read()
    with tarfile.open(fileobj=io.BytesIO(contents),mode="r:gz") as inner:
        assert inner.extractfile("./opt/share/telemt-compact-ram/telemt.xz").read()==xz
        assert inner.getmember("./opt/etc/init.d/S99telemt-ipc-compact-ram").mode==0o644
    print(f"ORIGINAL_ELF_BYTES={len(original)}")
    print(f"STRIPPED_ELF_BYTES={len(stripped)}")
    print(f"XZ_ON_FLASH_BYTES={len(xz)}")
    print(f"RAM_VARIANT_IPK_BYTES={len(ipk)}")
    print(f"PREINST_MIN_FLASH_KIB={min_flash_kib}")
    print(f"RAM_VARIANT_IPK_SHA256={hashlib.sha256(ipk).hexdigest()}")
    print(f"RAM_ELF_SHA256={hashlib.sha256(stripped).hexdigest()}")
    print("RAM_XZ_IPK_STRUCTURE_AND_LICENSE_PASS")


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    for arg in ("frozen-ipk","stripped-elf","xz-payload","scripts","license","output"):
        p.add_argument("--"+arg,required=True)
    run(p.parse_args())
