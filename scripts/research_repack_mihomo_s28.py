#!/usr/bin/env python3
"""Repack one PINNED EXISTING Mihomo MIPSel IPK into an isolated S28 research candidate.

This deliberately does not touch Mihomo ELF bytes, config.yaml, other architectures,
KAS code, the Entware feed or any router. The artifact is NOT an automatic release.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import io
from pathlib import Path
import re
import tarfile

ORIGINAL_SHA = "290c0802e60b12e38eb43f58656de3d8f0de317532a0bb67d2dda30b80fdadf6"
ORIGINAL_VERSION = b"1.19.34-2"
CANDIDATE_VERSION = b"1.19.34-3"
INIT_SHA = "06ba8f6abe78a3b109d2037c902d826085d5a4814cf4b4aca0d135b22a7b86d9"
OLD = "opt/etc/init.d/S99mihomo"
NEW = "opt/etc/init.d/S28mihomo"
MIPS = "opt/bin/mihomo"
FIXED_MTIME = 1763568000


def members(data: bytes):
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        result = []
        for ent in tar:
            name = ent.name.lstrip("./")
            if ent.isreg():
                content = tar.extractfile(ent).read()
            else:
                content = None
            if not ent.isreg() and not ent.isdir():
                raise ValueError(f"unexpected non-file tar member: {ent.name}")
            result.append((copy.copy(ent), name, content))
    assert len(result) and len({x[1] for x in result}) == len(result), "duplicate archive entry"
    return result


def make_gz_tar(items):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0, filename="") as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tar:
            for entry, _, raw in items:
                entry.mtime = FIXED_MTIME
                entry.uid, entry.gid = 0, 0
                entry.uname, entry.gname = "", ""
                if entry.isreg():
                    entry.size = len(raw)
                    tar.addfile(entry, io.BytesIO(raw))
                else:
                    tar.addfile(entry)
    return buf.getvalue()


def main(src: Path, dst: Path):
    raw = src.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ORIGINAL_SHA, "source release digest mismatch"
    outer = members(raw)
    assert {x[1] for x in outer} == {"debian-binary", "control.tar.gz", "data.tar.gz"}
    parts = {name: b for _, name, b in outer}
    assert parts["debian-binary"] == b"2.0\n"
    ctrls = members(parts["control.tar.gz"])
    data = members(parts["data.tar.gz"])
    binaries = [b for _, name, b in data if name == MIPS]
    assert len(binaries) == 1 and binaries[0].startswith(b"\x7fELF")
    assert [n for _, n, _ in data].count(OLD) == 1
    assert NEW not in [n for _, n, _ in data]
    assert {n for _, n, b in data if b is not None and "/init.d/" in n} == {OLD}
    current = [b for _, name, b in data if name == OLD][0]
    assert hashlib.sha256(current).hexdigest() == INIT_SHA, "init script does not match KAS contract"

    for i, (ent, name, b) in enumerate(ctrls):
        if name == "control":
            assert b.startswith(b"Package: mihomo\n")
            assert b"Architecture: mipsel-3.4\n" in b
            assert len(re.findall(rb"(?m)^Version: " + re.escape(ORIGINAL_VERSION) + rb"$", b)) == 1
            b = re.sub(rb"(?m)^Version: " + re.escape(ORIGINAL_VERSION) + rb"$",
                       b"Version: " + CANDIDATE_VERSION, b)
            ctrls[i] = (ent, name, b)
        elif b is not None:
            assert b"S99mihomo" not in b, f"control script {name} contains old init references"
    assert any(n == "control" for _, n, _ in ctrls)

    for i, (ent, name, b) in enumerate(data):
        if name == OLD:
            ent.name = ent.name.replace("S99mihomo", "S28mihomo")
            assert ent.mode & 0o111, "init script not executable"
            data[i] = (ent, NEW, b)

    control_new = make_gz_tar(ctrls)
    data_new = make_gz_tar(data)
    outer_new = []
    for entry, name, blob in outer:
        if name == "control.tar.gz":
            blob = control_new
        if name == "data.tar.gz":
            blob = data_new
        outer_new.append((entry, name, blob))
    new_pkg = make_gz_tar(outer_new)
    dst.write_bytes(new_pkg)

    # Self-verify all package members and unchanged binary and runtime config.
    verified = {name: b for _, name, b in members(new_pkg)}
    v_data = members(verified["data.tar.gz"])
    orig_files = {n: b for _, n, b in data}
    after_files = {n: b for _, n, b in v_data}
    assert OLD not in after_files and NEW in after_files
    assert after_files[NEW] == current
    assert after_files[MIPS] == binaries[0]
    assert len(after_files) == len(orig_files)
    assert {n: b for n, b in after_files.items() if n != NEW} == \
           {n: b for n, b in orig_files.items() if n != NEW}
    checkctrl = {name: b for _, name, b in members(verified["control.tar.gz"])}
    assert b"Version: 1.19.34-3\n" in checkctrl["control"]

    print(f"ORIGINAL_IPK_SHA256={ORIGINAL_SHA}")
    print(f"MIHOMO_ELF_SHA256={hashlib.sha256(binaries[0]).hexdigest()}")
    print(f"INIT_S28_SHA256={INIT_SHA}")
    print(f"CANDIDATE_IPK_BYTES={len(new_pkg)}")
    print(f"CANDIDATE_IPK_SHA256={hashlib.sha256(new_pkg).hexdigest()}")
    print("MIHOMO_S28_REPACK_IDENTITY_PASS")
    print("MIPS32_SOFT_FLOAT_HARDWARE_RUNTIME_NOT_TESTED")
    print("NO_RELEASE_NO_FEED_NO_ROUTER_CHANGES")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    main(args.source, args.output)
