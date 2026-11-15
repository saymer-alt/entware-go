"""Host-only regressions for official, SHA-pinned Entware GCC8 native cc1 runner."""
from __future__ import annotations
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import telemt_mipsle_gcc8_cc1_smoke as gate


class EntwareCompilerTests(unittest.TestCase):
    def test_pinned_gcc_sha_is_complete(self):
        self.assertEqual(
            gate.PINS["gcc_8.4.0-9_mipsel-3.4.ipk"],
            "2d56b649742903e229235e231898effef4aa969c5b5d48468a7e1a6d2bb39db5",
        )

    def test_unknown_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(gate.ProbeError, "unapproved"):
                gate.verified_ipk("fake.ipk", Path(td))

    def test_bad_cached_sha_fails_closed_without_network(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "gcc_8.4.0-9_mipsel-3.4.ipk").write_bytes(b"tampered")
            with patch.object(gate, "urlopen") as req:
                with self.assertRaisesRegex(gate.ProbeError, "SHA-256 mismatch"):
                    gate.verified_ipk("gcc_8.4.0-9_mipsel-3.4.ipk", Path(td))
                req.assert_not_called()

    def test_member_rejects_absolute_and_traversal(self):
        for path in ("/etc/passwd", "../opt/bin/x", "./opt/../../etc", "/opt/lib/ld.so.1"):
            with self.subTest(path=path):
                with self.assertRaises(gate.ProbeError):
                    gate.safe_member_path(path)

    def test_member_accepts_only_relative_opt(self):
        self.assertEqual(str(gate.safe_member_path("./opt/include/features.h")),
                         "opt/include/features.h")

    def test_invalid_ipk_refused(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(gate.ProbeError):
                gate.unpack_ipk(b"not tar", Path(td), "fixture")

    def test_missing_sdk_root_refused(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(gate.ProbeError, "missing"):
                gate.check_root(Path(td))

    def test_refuse_overwrite_compiled_object(self):
        with tempfile.TemporaryDirectory() as td:
            root, src, dest = Path(td), Path(td) / "shim.c", Path(td) / "shim.o"
            src.write_text("int a;")
            dest.write_bytes(b"preserve")
            with patch.object(gate, "check_root"):
                with self.assertRaisesRegex(gate.ProbeError, "overwrite"):
                    gate.compile_source(root, src, dest)
            self.assertEqual(dest.read_bytes(), b"preserve")

    def test_missing_qemu_blocks_before_spawning(self):
        with tempfile.TemporaryDirectory() as td:
            root, src, out = Path(td), Path(td) / "shim.c", Path(td) / "shim.o"
            src.write_text("int a;")
            with patch.object(gate, "check_root"), patch.object(gate.shutil, "which", return_value=None):
                with self.assertRaisesRegex(gate.ProbeError, "qemu-mipsel"):
                    gate.compile_source(root, src, out)
            self.assertFalse(out.exists())

    def test_bad_command_exit_blocks(self):
        with patch.object(gate.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "failure")):
            with self.assertRaisesRegex(gate.ProbeError, "exit 1"):
                gate.run_cmd(["qemu-mipsel", "--version"], timeout=5)

    def test_good_mock_command_return(self):
        with patch.object(gate.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            gate.run_cmd(["qemu-mipsel", "--version"], timeout=5)

    def test_softfloat_abi_required_for_compiled_object(self):
        with tempfile.TemporaryDirectory() as td:
            root, src, out = Path(td), Path(td) / "shim.c", Path(td) / "shim.o"
            src.write_text("int a;")
            with patch.object(gate, "check_root"), \
                 patch.object(gate.shutil, "which", side_effect=lambda n: "/usr/bin/" + n), \
                 patch.object(gate, "run_cmd") as invoke, \
                 patch.object(gate, "inspect_elf", return_value={"softfloat_abi_ok": False, "fp_abi": 5}):
                def fake_output(args, timeout):
                    Path(args[args.index("-o") + 1]).write_bytes(b"hardfloat")
                invoke.side_effect = fake_output
                with self.assertRaisesRegex(gate.ProbeError, "non-softfloat"):
                    gate.compile_source(root, src, out)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
