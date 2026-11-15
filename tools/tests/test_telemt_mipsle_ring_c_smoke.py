"""Host-only ring subset verification (no crates.io requests)."""
from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import telemt_mipsle_ring_c_smoke as smoke
from telemt_mipsle_gcc8_cc1_smoke import ProbeError


class RingTests(unittest.TestCase):
    def test_locked_version_and_sha(self):
        self.assertEqual(smoke.VERSION, "0.17.14")
        self.assertEqual(smoke.CRATE_SHA,
            "a4689e6c2294d81e88dc6261c768b63bc4fcdb852be6d1352498b114f61383b7")

    def test_bad_cached_crate_blocks_before_network(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / smoke.CRATE).write_bytes(b"tampered")
            with patch.object(smoke, "urlopen") as network:
                with self.assertRaisesRegex(ProbeError, "checksum mismatch"):
                    smoke.pinned_ring(Path(td))
                network.assert_not_called()

    def test_absent_static_symbols_denied(self):
        with self.assertRaisesRegex(ProbeError, "not found"):
            smoke.ring_prefix_header("fn main(){}")

    def test_changed_symbol_count_denied(self):
        content = ("static SYMBOLS_TO_RENAME: &[(&str, &str)] = &[(\"a\", \"b\")];\n"
                   "static SYMBOLS_TO_PREFIX: &[&str] = &[\"a\", \"b\"];\n")
        with self.assertRaisesRegex(ProbeError, "inventory changed"):
            smoke.ring_prefix_header(content)

    def test_exact_symbol_prefix_for_pin(self):
        renames = ",\n".join(f'("a{i}","b{i}")' for i in range(7))
        names = ",\n".join(f'"SYM{i}"' for i in range(155))
        content = ("static SYMBOLS_TO_RENAME: &[(&str,&str)] = &[" + renames + "];\n"
                   "static SYMBOLS_TO_PREFIX: &[&str] = &[" + names + "];\n")
        h = smoke.ring_prefix_header(content)
        self.assertIn("#define a0 b0", h)
        self.assertIn("#define SYM154 ring_core_0_17_14__SYM154", h)

    def test_four_distinct_locked_ring_sources(self):
        self.assertEqual(len(smoke.FILES), 4)
        self.assertEqual(len(set(smoke.FILES)), 4)
        self.assertTrue(all(p.endswith(".c") for p in smoke.FILES))


if __name__ == "__main__":
    unittest.main()
