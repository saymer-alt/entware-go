#!/usr/bin/env python3
"""Unit tests for tools/telemt_mipsle_ipk_preflight.py using synthetic fixtures.

Fixtures are minimal hand-built archives/ELFs; no real binaries, no network,
nothing is executed. Run: python3 -m unittest discover tools/tests
"""
from __future__ import annotations

import gzip
import io
import os
import struct
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import telemt_mipsle_ipk_preflight as pf  # noqa: E402


def tiny_elf(*, dynamic: bool, interp: str | None) -> bytes:
    """52-byte ELF32 MIPS LE header + optional PT_INTERP program header."""
    phnum = 0
    extra = b""
    phoff = 52
    if interp is not None:
        # PT_DYNAMIC (type 2) marks the ELF dynamic; PT_INTERP (type 3) carries the loader path.
        phnum = 2
        payload = interp.encode() + b"\0"
        dynamic_hdr = struct.pack("<IIIIIIII", 2, 0, 0, 0, 0, 0, 0, 0)
        interp_hdr = struct.pack("<IIIIIIII", 3, 116, 0, 0, len(payload), 0, 0, 0)
        extra = dynamic_hdr + interp_hdr + payload
    ident = b"\x7fELF" + bytes([1, 1, 1, 0]) + b"\0" * 8
    eh = ident + struct.pack("<HHIIIIIHHHHHH", 2, 8, 1, 0, phoff, 0, 0, 0, 32, phnum, 0, 0, 0)
    return eh + extra


def make_ipk(control_fields: dict[str, str], payload: dict[str, bytes]) -> bytes:
    def member(files: dict[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o755 if name.endswith((".bin", "telemt", "telemt-panel")) else 0o644
                t.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    control_text = "".join(f"{k}: {v}\n" for k, v in control_fields.items()).encode()
    inner = io.BytesIO()
    with tarfile.open(fileobj=inner, mode="w:gz") as t:
        info = tarfile.TarInfo("./control")
        info.size = len(control_text)
        t.addfile(info, io.BytesIO(control_text))
    outer = io.BytesIO()
    with tarfile.open(fileobj=outer, mode="w:gz") as t:
        for name, blob in (("./debian-binary", b"2.0\n"),
                           ("./control.tar.gz", inner.getvalue()),
                           ("./data.tar.gz", member(payload))):
            info = tarfile.TarInfo(name)
            info.size = len(blob)
            t.addfile(info, io.BytesIO(blob))
    return outer.getvalue()


CORE_CONTROL = {"Package": "telemt", "Version": "3.5.17-1", "Architecture": "mipsel-3.4"}
PANEL_CONTROL = {"Package": "telemt-panel-lite", "Version": "1.0.0~rc.4-1", "Architecture": "mipsel-3.4"}


class CoreModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, blob: bytes) -> Path:
        p = self.dir / "fixture.ipk"
        p.write_bytes(blob)
        return p

    def test_core_ipk_pass(self) -> None:
        blob = make_ipk(CORE_CONTROL, {"opt/bin/telemt": tiny_elf(dynamic=True, interp="/opt/lib/ld.so.1")})
        out = pf.audit(self._write(blob), "core")
        self.assertEqual(out["checks"]["ipk_control"]["Architecture"], "mipsel-3.4")
        self.assertEqual(out["checks"]["binary_path"], "opt/bin/telemt")

    def test_core_rejects_wrong_interpreter(self) -> None:
        blob = make_ipk(CORE_CONTROL, {"opt/bin/telemt": tiny_elf(dynamic=True, interp="/lib/ld.so.1")})
        with self.assertRaises(pf.AuditError):
            pf.audit(self._write(blob), "core")

    def test_core_rejects_wrong_arch(self) -> None:
        bad = dict(CORE_CONTROL, Architecture="aarch64-3.10")
        blob = make_ipk(bad, {"opt/bin/telemt": tiny_elf(dynamic=True, interp="/opt/lib/ld.so.1")})
        with self.assertRaises(pf.AuditError):
            pf.audit(self._write(blob), "core")

    def test_core_rejects_config_or_initd(self) -> None:
        blob = make_ipk(CORE_CONTROL, {"opt/bin/telemt": tiny_elf(dynamic=True, interp="/opt/lib/ld.so.1"),
                                       "opt/etc/init.d/S99telemt": b"#!/bin/sh\n"})
        with self.assertRaises(pf.AuditError):
            pf.audit(self._write(blob), "core")

    def test_core_rejects_unsafe_tar_path(self) -> None:
        blob = make_ipk(CORE_CONTROL, {"opt/bin/../secret": b"x"})
        with self.assertRaises(pf.AuditError):
            pf.audit(self._write(blob), "core")


class PanelModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_lite_rc4_rejects_dynamic_elf(self) -> None:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            info = tarfile.TarInfo("./opt/bin/telemt-panel")
            data = tiny_elf(dynamic=True, interp="/opt/lib/ld.so.1")
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
        p = self.dir / "panel"
        p.write_bytes(buf.getvalue())
        with self.assertRaises(pf.AuditError):
            pf.audit(p, "lite-rc4")

    def test_old_panel_requires_recorded_hash(self) -> None:
        blob = make_ipk({"Package": "telemt-panel", "Version": "0.6.2-1", "Architecture": "mipsel-3.4"},
                        {"opt/bin/telemt-panel": tiny_elf(dynamic=True, interp="/opt/lib/ld.so.1")})
        p = self.dir / "old.ipk"
        p.write_bytes(blob)
        with self.assertRaises(pf.AuditError):
            pf.audit(p, "old-panel")


if __name__ == "__main__":
    unittest.main()
