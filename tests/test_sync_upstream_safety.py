import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SyncUpstreamSafetyTests(unittest.TestCase):
    def test_conflict_markers_are_not_published_in_mihomo(self):
        makefile = (ROOT / "mihomo" / "Makefile").read_text(encoding="utf-8")
        for marker in ("<<<<<<<", "=======", ">>>>>>>"):
            self.assertNotIn(marker, makefile)

    def test_fork_init_script_is_present(self):
        # The fork ships the upstream Entware policy init name (S28, upstream
        # commit ee4b689) so future upstream syncs converge instead of
        # conflict.  The legacy S99 file stays in the source tree but must
        # never be packaged again, and the S99/S28 payloads remain
        # byte-identical (fork commit 8ceb41c rationale).
        makefile = (ROOT / "mihomo" / "Makefile").read_text(encoding="utf-8")
        self.assertIn("./files/S28mihomo", makefile)
        self.assertNotIn("./files/S99mihomo", makefile)
        self.assertTrue((ROOT / "mihomo" / "files" / "S28mihomo").is_file())
        self.assertEqual(
            (ROOT / "mihomo" / "files" / "S28mihomo").read_bytes(),
            (ROOT / "mihomo" / "files" / "S99mihomo").read_bytes(),
        )

    def test_conflict_path_never_publishes_branches_or_prs(self):
        workflow = (ROOT / ".github" / "workflows" / "sync-upstream.yml").read_text(encoding="utf-8")
        self.assertNotIn("gh pr create", workflow)
        self.assertNotIn("git checkout -b", workflow)
        self.assertIn("git diff --name-only --diff-filter=U", workflow)
        self.assertIn('>> "$GITHUB_STEP_SUMMARY"', workflow)
        self.assertIn("exit 1", workflow)


if __name__ == "__main__":
    unittest.main()
