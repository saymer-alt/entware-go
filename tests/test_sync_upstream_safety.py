import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SyncUpstreamSafetyTests(unittest.TestCase):
    def test_conflict_markers_are_not_published_in_mihomo(self):
        makefile = (ROOT / "mihomo" / "Makefile").read_text(encoding="utf-8")
        for marker in ("<<<<<<<", "=======", ">>>>>>>"):
            self.assertNotIn(marker, makefile)

    def test_fork_init_script_is_present(self):
        makefile = (ROOT / "mihomo" / "Makefile").read_text(encoding="utf-8")
        self.assertIn("./files/S99mihomo", makefile)
        self.assertTrue((ROOT / "mihomo" / "files" / "S99mihomo").is_file())

    def test_conflict_path_never_publishes_branches_or_prs(self):
        workflow = (ROOT / ".github" / "workflows" / "sync-upstream.yml").read_text(encoding="utf-8")
        self.assertNotIn("gh pr create", workflow)
        self.assertNotIn("git checkout -b", workflow)
        self.assertIn("git diff --name-only --diff-filter=U", workflow)
        self.assertIn('>> "$GITHUB_STEP_SUMMARY"', workflow)
        self.assertIn("exit 1", workflow)


if __name__ == "__main__":
    unittest.main()
