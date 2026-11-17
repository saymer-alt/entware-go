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


def tiny_elf(*, dynamic: bool, interp: str | None, fp_abi: int | None = 3) -> bytes:
    """52-byte ELF32 MIPS LE header + optional PT_INTERP program header."""
    phnum = 0
    extra = b""
    phoff = 52
    if interp is not None:
        # PT_DYNAMIC (type 2) marks the ELF dynamic; PT_INTERP (type 3) carries the loader path.
        phnum = 2 if fp_abi is None else 3
        payload = interp.encode() + b"\0"
        offset = 52 + 32 * phnum
        dynamic_hdr = struct.pack("<IIIIIIII", 2, 0, 0, 0, 0, 0, 0, 0)
        interp_hdr = struct.pack("<IIIIIIII", 3, offset, 0, 0, len(payload), 0, 0, 0)
        if fp_abi is None:
            extra = dynamic_hdr + interp_hdr + payload
        else:
            abi = struct.pack("<HBBBBBBIIII", 0, 32, 2, 1, 0, 0, fp_abi, 0, 0, 0, 0)
            abi_hdr = struct.pack("<IIIIIIII", 0x70000003, offset + len(payload),
                                  0, 0, len(abi), len(abi), 4, 8)
            extra = dynamic_hdr + interp_hdr + abi_hdr + payload + abi
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

    def test_core_rejects_hard_float(self) -> None:
        blob = make_ipk(CORE_CONTROL, {"opt/bin/telemt": tiny_elf(
            dynamic=True, interp="/opt/lib/ld.so.1", fp_abi=5)})
        with self.assertRaisesRegex(pf.AuditError, "softfloat"):
            pf.audit(self._write(blob), "core")

    def test_core_rejects_missing_fp_abi(self) -> None:
        blob = make_ipk(CORE_CONTROL, {"opt/bin/telemt": tiny_elf(
            dynamic=True, interp="/opt/lib/ld.so.1", fp_abi=None)})
        with self.assertRaisesRegex(pf.AuditError, "softfloat"):
            pf.audit(self._write(blob), "core")

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


class CoreGetFbModeTests(unittest.TestCase):
    """core-getfb: the getrandom-fallback rebuild pins its own IPK version."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, blob: bytes) -> Path:
        p = self.dir / "fixture.ipk"
        p.write_bytes(blob)
        return p

    GETFB_CONTROL = {"Package": "telemt", "Version": "3.5.17-2fb1", "Architecture": "mipsel-3.4"}

    def test_core_getfb_ipk_pass(self) -> None:
        blob = make_ipk(self.GETFB_CONTROL,
                        {"opt/bin/telemt": tiny_elf(dynamic=True, interp="/opt/lib/ld.so.1")})
        out = pf.audit(self._write(blob), "core-getfb")
        self.assertEqual(out["checks"]["ipk_control"]["Version"], "3.5.17-2fb1")
        self.assertIn("entware_abi", out["checks"])

    def test_core_getfb_rejects_the_frozen_3517_1_control(self) -> None:
        # the frozen PR #44 artifact keeps version 3.5.17-1; the fallback kind
        # must never accept it (separately named experimental IPKs)
        blob = make_ipk(CORE_CONTROL,
                        {"opt/bin/telemt": tiny_elf(dynamic=True, interp="/opt/lib/ld.so.1")})
        with self.assertRaises(pf.AuditError):
            pf.audit(self._write(blob), "core-getfb")

    def test_core_kind_still_pins_3517_1(self) -> None:
        blob = make_ipk(self.GETFB_CONTROL,
                        {"opt/bin/telemt": tiny_elf(dynamic=True, interp="/opt/lib/ld.so.1")})
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



class TelemtLockSnapshotTests(unittest.TestCase):
    """Archive is an actual pinned dependency graph, not a Cargo project."""

    RESEARCH = (Path(__file__).resolve().parents[2] /
                "docs/research/telemt-mipsle-ipk-3517/getrandom-fallback")

    def test_patched_snapshot_contains_three_forks(self):
        import tomllib
        snap = self.RESEARCH / "telemt-patched-deps.snapshot"
        self.assertTrue(snap.is_file())
        lock = tomllib.loads(snap.read_text(encoding="utf-8"))
        self.assertEqual(lock["version"], 4)
        self.assertEqual(sorted(
            x["version"] for x in lock["package"] if x["name"] == "getrandom"),
            ["0.2.17", "0.3.4", "0.4.3"])
        self.assertEqual(len([
            x for x in lock["package"] if x["name"] == "rustls"]), 1)

    def test_no_orphan_lock_or_fabricated_manifest(self):
        self.assertFalse((self.RESEARCH / "Cargo.lock").exists())
        self.assertFalse((self.RESEARCH / "Cargo.toml").exists())

    def test_assembler_restores_snapshot_into_pinned_upstream(self):
        script = (self.RESEARCH / "assemble-forks.sh").read_text(encoding="utf-8")
        self.assertIn('test -f "$RESEARCH_DIR/telemt-patched-deps.snapshot"', script)
        self.assertIn('test ! -e "$RESEARCH_DIR/Cargo.lock"', script)
        self.assertIn('cp "$RESEARCH_DIR/telemt-patched-deps.snapshot" "$UP/Cargo.lock"', script)
        self.assertIn('cargo metadata --format-version 1 --locked', script)



class TelemtNightlyPinTests(unittest.TestCase):
    """The getfb build is pinned, while the original 3.5.17-1 stays unchanged."""

    def test_workflow_requires_original_compiler_and_guest_pins(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root / '.github/workflows/telemt-mipsle-ipk-3517-getfb-experimental.yml').read_text()
        self.assertIn('RUST_NIGHTLY_PIN: nightly-2026-11-16', workflow)
        self.assertIn('RUST_BUILD_TOOLCHAIN: nightly', workflow)
        self.assertIn('cp -a "$archive" "$original"', workflow)
        self.assertIn('RESTORED_RUST_SYSROOT', workflow)
        self.assertIn('5f4effd57', workflow)
        self.assertIn('d4ba43815883dd1ce9aa57349602598127781e8966d51dab97616dbdb35b216f', workflow)
        self.assertIn('2c8a84fb93535303eeb4bb8a0a5057370f4e625b1cdf0e102f04e33e28c85d8d', workflow)
        self.assertIn('sha256sum -c "$RUNNER_TEMP/getfb-accepted.sha256"', workflow)

    def test_legacy_stays_floating_and_getfb_is_pinned(self):
        root = Path(__file__).resolve().parents[2]
        script = (root / 'docs/research/telemt-mipsle-ipk-3517/scripts/build-telemt-core.sh').read_text()
        self.assertIn('RUST_NIGHTLY_TOOLCHAIN=nightly', script)
        self.assertIn('if [ "${TELEMT_GETFB:-0}" = "1" ]; then', script)
        self.assertIn('RUST_NIGHTLY_TOOLCHAIN="${RUST_BUILD_TOOLCHAIN:?getfb needs a verified nightly alias}"', script)
        self.assertIn('cargo +"$RUST_NIGHTLY_TOOLCHAIN" -Z build-std=std,panic_abort', script)

    def test_entropy_build_uses_same_pin(self):
        root = Path(__file__).resolve().parents[2]
        script = (root / 'docs/research/telemt-mipsle-ipk-3517/getrandom-fallback/gate.sh').read_text()
        self.assertIn('rustc +"${RUST_BUILD_TOOLCHAIN:?missing verified nightly alias}" -V', script)
        self.assertEqual(script.count('cargo +"$RUST_BUILD_TOOLCHAIN" -Z build-std=std,panic_abort'), 2)


if __name__ == "__main__":
    unittest.main()
