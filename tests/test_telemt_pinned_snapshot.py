"""Ensure an archival TeleMT dependency snapshot is not a fake Cargo project."""
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "docs/research/telemt-mipsle-ipk-3517/getrandom-fallback"
SNAPSHOT = RESEARCH / "telemt-patched-deps.snapshot"

class TelemtLockSnapshotTests(unittest.TestCase):
    def test_snapshot_preserves_locked_dependency_graph(self):
        self.assertTrue(SNAPSHOT.is_file())
        lock = tomllib.loads(SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(lock["version"], 4)
        self.assertEqual(
            sorted(x["version"] for x in lock["package"] if x["name"] == "getrandom"),
            ["0.2.17", "0.3.4", "0.4.3"])
        self.assertEqual(
            len([x for x in lock["package"] if x["name"] == "rustls"]), 1)

    def test_no_orphan_lock_or_fabricated_manifest(self):
        self.assertFalse((RESEARCH / "Cargo.lock").exists())
        self.assertFalse((RESEARCH / "Cargo.toml").exists())

    def test_assembler_restores_to_real_upstream_manifest(self):
        asm = (RESEARCH / "assemble-forks.sh").read_text(encoding="utf-8")
        self.assertIn('test -f "$RESEARCH_DIR/telemt-patched-deps.snapshot"', asm)
        self.assertIn('test ! -e "$RESEARCH_DIR/Cargo.lock"', asm)
        self.assertIn('cp "$RESEARCH_DIR/telemt-patched-deps.snapshot" "$UP/Cargo.lock"', asm)
        self.assertIn('cargo metadata --format-version 1 --locked', asm)

if __name__ == "__main__":
    unittest.main()
