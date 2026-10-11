#!/usr/bin/env python3
"""Synthetic smoke test for manual-only WDTT lab IPK output."""
import gzip
import hashlib
import io
import json
import tarfile
import tempfile
from pathlib import Path
from owner_test_ipk import make_lab_packages

with tempfile.TemporaryDirectory(prefix="wdtt-owner-ipk-") as t:
    base=Path(t)
    binaries=base/"binaries"; binaries.mkdir()
    out=base/"out"; out.mkdir()
    records=[]
    for arch in ("arm64","mipsle"):
        payload=b"\x7fELF" + (arch.encode("ascii") * 64)
        (binaries/("wt-client-linux-"+arch)).write_bytes(payload)
        records.append({"arch":arch,"sha256":hashlib.sha256(payload).hexdigest()})
    report=base/"report.json"
    report.write_text(json.dumps({"source":"a"*40,"install_ready":False,"license_gate":"BLOCKED","builds":records}))
    make_lab_packages(report,binaries,out)
    ipks=sorted(out.glob("*.ipk"))
    assert len(ipks)==2
    manifest=json.loads((out/"MANIFEST.json").read_text())
    assert len(manifest)==2
    assert "не заменяет" in (out/"README-FIRST.md").read_text()
    for p in ipks:
        raw=p.read_bytes()
        assert raw.startswith(b"!<arch>\n")
        members={};cursor=8
        while cursor<len(raw):
            h=raw[cursor:cursor+60];cursor+=60
            size=int(h[48:58])
            name=h[:16].decode().strip().rstrip("/")
            members[name]=raw[cursor:cursor+size]
            cursor+=size+size%2
        assert set(members)=={"debian-binary","control.tar.gz","data.tar.gz"}
        assert members["debian-binary"]==b"2.0\n"
        with tarfile.open(fileobj=io.BytesIO(gzip.decompress(members["control.tar.gz"]))) as tf:
            control=tf.extractfile("./control").read().decode()
        assert "Package: wt-client-lab" in control
        assert "Architecture: " in control and "Experimental" in control
        with tarfile.open(fileobj=io.BytesIO(gzip.decompress(members["data.tar.gz"]))) as tf:
            names=[m.name for m in tf]
            assert len(names)==3
            assert any(p.endswith("/wt-client") for p in names)
            notice=next(n for n in names if n.endswith("/NOTICES"))
            assert "ТОЛЬКО ДЛЯ ЛАБОРАТОРНЫХ" in tf.extractfile(notice).read().decode()
            assert not any("/init.d/" in n or "postinst" in n for n in names)
        assert any(x["file"]==p.name and x["ipk_sha256"]==hashlib.sha256(raw).hexdigest() for x in manifest)
    assert len((out/"SHA256SUMS").read_text().splitlines())==2
print("PASS: owner-test IPKs labelled, SHA verified, no init scripts; real router admission still closed")
