import importlib.util
from io import BytesIO
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "audit", Path(__file__).resolve().parents[1] / "telemt_mipsle_panel_preflight.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def elf32(*, with_interp=False, big_endian=False, arm=False):
    b = bytearray(160)
    b[:6] = b"\x7fELF\x01" + (b"\x02" if big_endian else b"\x01")
    struct.pack_into("<H", b, 16, 2)
    struct.pack_into("<H", b, 18, 40 if arm else 8)
    struct.pack_into("<I", b, 36, 0x70000000)
    if with_interp:
        struct.pack_into("<I", b, 28, 52)
        struct.pack_into("<HH", b, 42, 32, 1)
        struct.pack_into("<IIIII", b, 52, 3, 88, 0, 0, 17)
        b[88:105] = b"/opt/lib/ld.so.1\0"
    return bytes(b)


def tar_gz(members):
    out = BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tf:
        for name, data in members.items():
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            ti.mode = 0o644
            tf.addfile(ti, BytesIO(data))
    return out.getvalue()


def ipk(*, package="telemt-panel", version="0.6.2-1", architecture="mipsel-3.4", payload=None):
    control = f"Package: {package}\nVersion: {version}\nArchitecture: {architecture}\n".encode()
    return tar_gz({"./control.tar.gz": tar_gz({"./control": control}),
                   "./data.tar.gz": tar_gz(payload or {"./opt/bin/telemt-panel": elf32()})})


class Audits(unittest.TestCase):
    def test_raw_lite_static_pass(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "panel"
            p.write_bytes(elf32())
            out = audit.audit(p, "lite-rc4")
            self.assertEqual(out["checks"]["arch"], "PASS: ELF32 MIPS little-endian")
            self.assertIn("NOT_TESTED", out["checks"]["packaging"])

    def test_old_package_pass_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "old.ipk"
            p.write_bytes(ipk())
            out = audit.audit(p, "old-panel", require_legacy_hash=False)
            self.assertEqual(out["checks"]["ipk_control"]["Package"], "telemt-panel")

    def test_legacy_hash_fail(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "old.ipk"
            p.write_bytes(ipk())
            with self.assertRaisesRegex(audit.AuditError, "checksum"):
                audit.audit(p, "old-panel")

    def test_reject_wrong_arch(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "wrong.ipk"
            p.write_bytes(ipk(architecture="aarch64-3.10"))
            with self.assertRaisesRegex(audit.AuditError, "control"):
                audit.audit(p, "old-panel", require_legacy_hash=False)

    def test_reject_dynamic_lite(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "panel"
            p.write_bytes(elf32(with_interp=True))
            with self.assertRaisesRegex(audit.AuditError, "dynamic ELF"):
                audit.audit(p, "lite-rc4")

    def test_reject_non_mips(self):
        with self.assertRaisesRegex(audit.AuditError, "not ELF32"):
            audit.elf_info(elf32(arm=True))

    def test_reject_big_endian(self):
        with self.assertRaisesRegex(audit.AuditError, "not ELF32"):
            audit.elf_info(elf32(big_endian=True))

    def test_reject_configs(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.ipk"
            p.write_bytes(ipk(payload={"./opt/bin/telemt-panel": elf32(),
                                       "./opt/etc/telemt-panel/config.toml": b"secret"}))
            with self.assertRaisesRegex(audit.AuditError, "live config"):
                audit.audit(p, "old-panel", require_legacy_hash=False)

    def test_reject_duplicate(self):
        blob = tar_gz({"./control.tar.gz": b"abc"})
        with self.assertRaisesRegex(audit.AuditError, "control.tar.gz"):
            audit.ipk_parts(blob)

    def test_reject_tar_path_traversal(self):
        unsafe = tar_gz({"../config.toml": b"secret"})
        with self.assertRaisesRegex(audit.AuditError, "unsafe tar path"):
            audit.tar_members(unsafe, label="test")

    def test_reject_tar_absolute_path(self):
        unsafe = tar_gz({"/opt/etc/secret": b"secret"})
        with self.assertRaisesRegex(audit.AuditError, "unsafe tar path"):
            audit.tar_members(unsafe, label="test")

    def test_static_elf_program_header_bounds(self):
        corrupt = bytearray(elf32())
        struct.pack_into("<I", corrupt, 28, 150)
        struct.pack_into("<HH", corrupt, 42, 32, 1)
        with self.assertRaisesRegex(audit.AuditError, "program header"):
            audit.elf_info(bytes(corrupt))


if __name__ == "__main__":
    unittest.main()
