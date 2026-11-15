"""Host-only negative tests for MIPSLE ELF and glibc softfloat SDK gates."""
from __future__ import annotations
import struct
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from telemt_mipsle_fp_abi_gate import AbiError, inspect_elf, gnu_float_abi
from telemt_mipsle_softfloat_probe import ProbeError, require_headers, probe

def fake_elf(fp=3, gnu=None, kind=2, cpr1=1, skip_ph=False, skip_gnu=False):
    blob = bytearray(512)
    blob[:6] = b"\x7fELF\x01\x01"
    struct.pack_into("<HHI", blob, 16, kind, 8, 1)
    if kind != 1 and not skip_ph:
        struct.pack_into("<I", blob, 28, 52)
        struct.pack_into("<HH", blob, 42, 32, 1)
        struct.pack_into("<IIIII", blob, 52, 0x70000003, 344, 0, 0, 24)
    struct.pack_into("<I", blob, 32, 128)
    struct.pack_into("<HHH", blob, 46, 40, 4, 1)
    names = b"\0.shstrtab\0.MIPS.abiflags\0.gnu.attributes\0"
    blob[400:400 + len(names)] = names
    struct.pack_into("<IIIIII", blob, 168, names.index(b".shstrtab"), 3, 0, 0, 400, len(names))
    struct.pack_into("<IIIIII", blob, 208, names.index(b".MIPS.abiflags"), 0x7000002A, 0, 0, 344, 24)
    if not skip_gnu:
        struct.pack_into("<IIIIII", blob, 248, names.index(b".gnu.attributes"), 0x6FFFFFF5, 0, 0, 368, 16)
    blob[346:350] = bytes((32, 2, 1, cpr1))
    blob[351] = fp
    blob[368:384] = b"A\x0f\x00\x00\x00gnu\x00\x01\x07\x00\x00\x00\x04" + bytes((gnu if gnu is not None else fp,))
    return bytes(blob)

class FPTests(unittest.TestCase):
    def test_softfloat_cpr1_32_is_valid(self):
        self.assertTrue(inspect_elf(fake_elf(3, cpr1=1))["softfloat_abi_ok"])

    def test_fpxx_hardfloat_is_not_softfloat(self):
        self.assertFalse(inspect_elf(fake_elf(5))["softfloat_abi_ok"])

    def test_softfloat_relocatable_object(self):
        got = inspect_elf(fake_elf(3, kind=1, cpr1=0))
        self.assertEqual((got["elf_type"], got["fp_abi"]), ("ET_REL", 3))

    def test_mixed_gnu_and_mips_attributes_fail_closed(self):
        with self.assertRaisesRegex(AbiError, "metadata disagreement"):
            inspect_elf(fake_elf(5, gnu=3))

    def test_missing_program_abi_fails(self):
        with self.assertRaisesRegex(AbiError, "missing ELF program headers"):
            inspect_elf(fake_elf(skip_ph=True))

    def test_missing_gnu_attribute_fails(self):
        with self.assertRaisesRegex(AbiError, "missing or duplicated GNU"):
            inspect_elf(fake_elf(skip_gnu=True))

    def test_x86_64_rejected(self):
        blob = bytearray(fake_elf())
        struct.pack_into("<H", blob, 18, 62)
        with self.assertRaisesRegex(AbiError, "not MIPS"):
            inspect_elf(bytes(blob))

    def test_truncated_header_rejected(self):
        with self.assertRaisesRegex(AbiError, "not ELF32"):
            inspect_elf(b"\x7fELF")

    def test_malformed_gnu_vendor_fails(self):
        with self.assertRaisesRegex(AbiError, "malformed GNU vendor"):
            gnu_float_abi(b"A\xff\xff\xff\xffgnu")

class SDKTests(unittest.TestCase):
    def test_missing_sdk_fails(self):
        with self.assertRaisesRegex(ProbeError, "unavailable"):
            require_headers(Path("/missing-mipsel-entware-headers"))

    def test_hardfloat_header_tree_fails(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "features.h").write_text("")
            with self.assertRaisesRegex(ProbeError, "stubs-o32_soft.h"):
                require_headers(Path(td))

    def test_does_not_compile_with_incomplete_headers(self):
        with tempfile.TemporaryDirectory() as td, \
             patch("telemt_mipsle_softfloat_probe.run") as gcc:
            with self.assertRaises(ProbeError):
                probe("mipsel-linux-gnu-gcc", Path(td))
            gcc.assert_not_called()

if __name__ == "__main__":
    unittest.main()
