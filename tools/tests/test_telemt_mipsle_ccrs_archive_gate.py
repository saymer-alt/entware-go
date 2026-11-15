"""No network, no QEMU: cc-rs .a archive gate rejects wrong object ABI."""
from __future__ import annotations
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import telemt_mipsle_ccrs_archive_gate as gate


class ArchiveTests(unittest.TestCase):
    def staged(self):
        tmp = tempfile.TemporaryDirectory()
        p = Path(tmp.name) / "libprobe.a"
        p.write_bytes(b"!<arch>\n" + b"x" * 90)
        return tmp, p

    def test_realistic_single_member_pass(self):
        tmp, p = self.staged()
        try:
            with patch.object(gate.shutil, "which", side_effect=lambda x: "/usr/bin/" + x), \
                 patch.object(gate, "ar_cmd", side_effect=[
                     b"test.o\n", b"\x7fELF" + b"\0" * 70]), \
                 patch.object(gate, "inspect_elf", return_value={
                     "elf_type": "ET_REL", "fp_abi": 3, "softfloat_abi_ok": True}):
                data = gate.inspect_archive(p, 1)
                self.assertEqual(data["object_count"], 1)
                self.assertEqual(data["objects"][0]["fp_abi"], 3)
        finally:
            tmp.cleanup()

    def test_hardfloat_archive_member_refused(self):
        tmp, p = self.staged()
        try:
            with patch.object(gate.shutil, "which", return_value="/usr/bin/mipsel-linux-gnu-ar"), \
                 patch.object(gate, "ar_cmd", side_effect=[
                     b"hard.o\n", b"\x7fELF" + b"\0" * 70]), \
                 patch.object(gate, "inspect_elf", return_value={
                     "elf_type": "ET_REL", "fp_abi": 5, "softfloat_abi_ok": False}):
                with self.assertRaisesRegex(gate.ArchiveError, "not a MIPS32 softfloat"):
                    gate.inspect_archive(p, 1)
        finally:
            tmp.cleanup()

    def test_shared_elf_rejected_even_if_abi_softfloat(self):
        tmp, p = self.staged()
        try:
            with patch.object(gate.shutil, "which", return_value="/usr/bin/mipsel-linux-gnu-ar"), \
                 patch.object(gate, "ar_cmd", side_effect=[
                     b"lib.o\n", b"\x7fELF" + b"\0" * 70]), \
                 patch.object(gate, "inspect_elf", return_value={
                     "elf_type": "ET_DYN", "fp_abi": 3, "softfloat_abi_ok": True}):
                with self.assertRaisesRegex(gate.ArchiveError, "not a MIPS32 softfloat"):
                    gate.inspect_archive(p, 1)
        finally:
            tmp.cleanup()

    def test_missing_object_rejected(self):
        tmp, p = self.staged()
        try:
            with patch.object(gate.shutil, "which", return_value="/usr/bin/mipsel-linux-gnu-ar"), \
                 patch.object(gate, "ar_cmd", return_value=b"one.o\n"):
                with self.assertRaisesRegex(gate.ArchiveError, "member count"):
                    gate.inspect_archive(p, 4)
        finally:
            tmp.cleanup()

    def test_duplicate_member_names_rejected(self):
        tmp, p = self.staged()
        try:
            with patch.object(gate.shutil, "which", return_value="/usr/bin/mipsel-linux-gnu-ar"), \
                 patch.object(gate, "ar_cmd", return_value=b"x.o\nx.o\n"):
                with self.assertRaisesRegex(gate.ArchiveError, "duplicate"):
                    gate.inspect_archive(p, 2)
        finally:
            tmp.cleanup()

    def test_invalid_member_name_refused(self):
        tmp, p = self.staged()
        try:
            with patch.object(gate.shutil, "which", return_value="/usr/bin/mipsel-linux-gnu-ar"), \
                 patch.object(gate, "ar_cmd", return_value=b"../../test.o\n"):
                with self.assertRaisesRegex(gate.ArchiveError, "unexpected"):
                    gate.inspect_archive(p, 1)
        finally:
            tmp.cleanup()

    def test_bad_ar_exit_fails_closed(self):
        with patch.object(gate.subprocess, "run", return_value=
                          subprocess.CompletedProcess([], 1, b"", b"error")):
            with self.assertRaisesRegex(gate.ArchiveError, "exit=1"):
                gate.ar_cmd(["ar", "t", "missing.a"])

    def test_object_count_range_is_bounded(self):
        tmp, p = self.staged()
        try:
            for n in (0, 65):
                with self.assertRaisesRegex(gate.ArchiveError, "expected_count"):
                    gate.inspect_archive(p, n)
        finally:
            tmp.cleanup()

    def test_required_symbol_verified_without_evaluation(self):
        tmp, p = self.staged()
        try:
            with patch.object(gate.shutil, "which",
                              side_effect=lambda x: "/usr/bin/" + x), \
                 patch.object(gate, "ar_cmd", side_effect=[
                     b"obj.o\n", b"\x7fELF" + b"\0" * 70,
                     b"00000000 T ring_core_0_17_14__CRYPTO_memcmp\n"]), \
                 patch.object(gate, "inspect_elf", return_value={
                     "elf_type": "ET_REL", "fp_abi": 3, "softfloat_abi_ok": True}):
                got = gate.inspect_archive(p, 1,
                    required_symbol="ring_core_0_17_14__CRYPTO_memcmp")
                self.assertEqual(got["status"], "CCRS_MIPSLE_ARCHIVE_SOFTFLOAT_PASS")
        finally:
            tmp.cleanup()

    def test_invalid_required_symbol_not_passed_to_nm(self):
        tmp, p = self.staged()
        try:
            with patch.object(gate.shutil, "which",
                              side_effect=lambda x: "/usr/bin/" + x), \
                 patch.object(gate, "ar_cmd", side_effect=[
                     b"obj.o\n", b"\x7fELF" + b"\0" * 70]), \
                 patch.object(gate, "inspect_elf", return_value={
                     "elf_type": "ET_REL", "fp_abi": 3, "softfloat_abi_ok": True}):
                with self.assertRaisesRegex(gate.ArchiveError, "unsafe symbol"):
                    gate.inspect_archive(p, 1, required_symbol="name;rm")
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
