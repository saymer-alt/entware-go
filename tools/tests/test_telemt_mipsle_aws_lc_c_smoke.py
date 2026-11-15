"""Offline contract tests for pinned aws-lc-sys C subset."""
from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import telemt_mipsle_aws_lc_c_smoke as aws
from telemt_mipsle_gcc8_cc1_smoke import ProbeError


class AwsLCSubsetTests(unittest.TestCase):
    def test_pinned_crate_hash(self):
        self.assertEqual(aws.CRATE_SHA,
            "9bff6c3b54fad79a2e60b8102caf565819711497c1f5f092f49508e2f5c31b27")
        self.assertEqual(aws.VERSION, "0.45.0")

    def test_corrupt_cached_crate_blocked_before_network(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / aws.CRATE).write_bytes(b"corrupt")
            with patch.object(aws, "urlopen") as network:
                with self.assertRaisesRegex(ProbeError, "SHA-256 mismatch"):
                    aws.pinned_crate(Path(td))
                network.assert_not_called()

    def test_two_distinct_c_sources(self):
        self.assertEqual(len(aws.FILES), 2)
        self.assertEqual(len(set(aws.FILES)), 2)
        self.assertTrue(all(n.endswith(".c") for n in aws.FILES))

    def test_tar_invalid_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(Exception):
                aws.unpack_source(b"not gz", Path(td))

    def test_aws_codegen_requires_softfloat(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            for s in aws.FILES:
                f = work / s
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text("int x;")
            with patch.object(aws, "assemble"), \
                 patch.object(aws, "inspect_elf", return_value={
                     "fp_abi": 5, "softfloat_abi_ok": False}):
                for n in range(len(aws.FILES)):
                    # Emit an object for the independent ABI check to reject.
                    (work / "output").mkdir(exist_ok=True)
                    (work / "output" / f"aws-lc-{n}.o").write_bytes(b"bad")
                with self.assertRaisesRegex(ProbeError, "incompatible ABI"):
                    aws.run_subset(work, work, work / "output")


if __name__ == "__main__":
    unittest.main()
