"""Host-only negative tests; no QEMU execution and no heavy build."""
from __future__ import annotations

import hashlib
from pathlib import Path
from subprocess import CompletedProcess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import telemt_mipsle_qemu_user_smoke as smoke


class OfflineTests(unittest.TestCase):
    def test_rejects_wrong_checksum(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "fake.ipk"
            src.write_bytes(b"fake")
            with self.assertRaisesRegex(smoke.SmokeError, "SHA-256 mismatch"):
                smoke.verify_ipk(src, "core", "0" * 64)

    def test_rejects_malformed_expected_checksum(self):
        with self.assertRaisesRegex(smoke.SmokeError, "64 lowercase"):
            smoke.verify_ipk(Path("/missing"), "core", "invalid")

    def test_accepts_preflight_approved_stub(self):
        with tempfile.TemporaryDirectory() as td, \
             patch.object(smoke, "audit", return_value={"format": "ipk", "sha256": "test"}), \
             patch.object(smoke, "ipk_parts", return_value=({}, {"opt/bin/telemt": b"core"})):
            src = Path(td) / "test.ipk"
            src.write_bytes(b"test")
            report, binary = smoke.verify_ipk(src, "core", hashlib.sha256(b"test").hexdigest())
            self.assertEqual((report["format"], binary), ("ipk", b"core"))

    def test_rejects_unexpected_ipk_payload(self):
        with tempfile.TemporaryDirectory() as td, \
             patch.object(smoke, "audit", return_value={"format": "ipk"}), \
             patch.object(smoke, "ipk_parts", return_value=({}, {"opt/bin/telemt": b"core", "opt/etc/secret": b"bad"})):
            src = Path(td) / "test.ipk"
            src.write_bytes(b"test")
            with self.assertRaisesRegex(smoke.SmokeError, "payload paths"):
                smoke.verify_ipk(src, "core", hashlib.sha256(b"test").hexdigest())

    def test_rejects_elf_not_full_ipk(self):
        with tempfile.TemporaryDirectory() as td, \
             patch.object(smoke, "audit", return_value={"format": "ELF"}):
            src = Path(td) / "test.ipk"
            src.write_bytes(b"test")
            with self.assertRaisesRegex(smoke.SmokeError, "complete IPK"):
                smoke.verify_ipk(src, "core", hashlib.sha256(b"test").hexdigest())

    def test_qemu_unavailable_blocks(self):
        with patch.object(smoke.shutil, "which", return_value=None):
            with self.assertRaisesRegex(smoke.SmokeError, "requires qemu-mipsel"):
                smoke.run_qemu_cli(b"anything", Path("/missing"))

    def test_library_missing_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(smoke.SmokeError, "library missing"):
                smoke.verify_lib_dir(Path(td))

    def test_library_escape_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "libs"
            root.mkdir()
            (root / "ld.so.1").symlink_to("/bin/sh")
            with self.assertRaisesRegex(smoke.SmokeError, "escapes"):
                smoke.verify_lib_dir(root)

    def test_isolated_invocation_and_no_host_env_leak(self):
        with tempfile.TemporaryDirectory() as td, \
             patch.object(smoke.shutil, "which", side_effect=lambda n: "/usr/bin/" + n), \
             patch.object(smoke, "verify_lib_dir", return_value=(Path(td), Path(td) / "ld.so.1")), \
             patch.object(smoke.subprocess, "run", return_value=CompletedProcess([], 0, b"TeleMT 3.5.17\n", b"")) as invoke:
            result = smoke.run_qemu_cli(b"mock-code", Path(td))
            argv = invoke.call_args.args[0]
            self.assertEqual(argv[:5], ["/usr/bin/unshare", "--user", "--map-root-user", "--net", "--"])
            self.assertIn("--library-path", argv)
            self.assertEqual(argv[-1], "--version")
            self.assertEqual(invoke.call_args.kwargs["env"]["HOME"], invoke.call_args.kwargs["cwd"])
            self.assertNotIn("LD_PRELOAD", invoke.call_args.kwargs["env"])
            self.assertEqual(result["status"], "QEMU_USER_CLI_SMOKE_PASS")

    def test_nonzero_exit_is_not_pass(self):
        with tempfile.TemporaryDirectory() as td, \
             patch.object(smoke.shutil, "which", side_effect=lambda n: "/usr/bin/" + n), \
             patch.object(smoke, "verify_lib_dir", return_value=(Path(td), Path(td) / "ld.so.1")), \
             patch.object(smoke.subprocess, "run", return_value=CompletedProcess([], 1, b"", b"failure")):
            with self.assertRaisesRegex(smoke.SmokeError, "exit=1"):
                smoke.run_qemu_cli(b"mock-code", Path(td))


if __name__ == "__main__":
    unittest.main()
