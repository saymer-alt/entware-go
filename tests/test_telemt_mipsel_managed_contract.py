"""Static host contract for the TeleMT MIPSel managed-kit installer.

The installer itself needs Entware root plus /opt, so it is exercised
functionally by the MT7621 guest lab.  This suite pins the *reuse*
configuration contract on the host side: a --reuse-config reinstall must
preserve every existing user setting, secret and Telegram link — it must
never regenerate or rewrite them.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "docs/research/telemt-control-ipc/scripts/telemt-mipsel-install.sh"


class ReuseConfigContractTests(unittest.TestCase):
    def setUp(self):
        self.src = INSTALL.read_text(encoding="utf-8")

    def guarded_region(self):
        """Everything between the reuse guard and the closing else branch."""
        marker = 'if [ -z "$REUSE_CONFIG" ]; then'
        start = self.src.index(marker)
        end = self.src.index('else\n  ok "REUSING_CONFIG', start)
        return start, end

    def test_secret_generation_is_inside_the_reuse_guard(self):
        start, end = self.guarded_region()
        guarded = self.src[start:end]
        for needle in (
            "/dev/urandom",            # Telegram secret hex
            "base64",                  # Panel password
            "hash-password",           # bcrypt hash generation
            "cat > \"$R/core.toml\"",  # Core config rewrite
            "cat > \"$R/panel.toml\"", # Panel config rewrite
            "private-telegram-link.txt",
            "private-panel-password.txt",
            "chmod 600",
        ):
            self.assertIn(needle, guarded, f"expected inside reuse guard: {needle}")

    def test_reuse_branch_never_rewrites_configs_or_secrets(self):
        start, end = self.guarded_region()
        after_else = self.src[end:]
        self.assertIn("REUSING_CONFIG", after_else)
        self.assertIn("nothing regenerated", after_else)
        for needle in ("/dev/urandom", "hash-password", "cat > \"$R/core.toml\"",
                       "cat > \"$R/panel.toml\"", "> \"$R/private-telegram-link.txt\"",
                       "> \"$R/private-panel-password.txt\""):
            self.assertNotIn(needle, after_else, f"must not run in reuse mode: {needle}")

    def test_reuse_requires_existing_non_symlink_configs(self):
        self.assertIn('--reuse-config requires existing core.toml and panel.toml', self.src)
        self.assertIn('[ -f "$R/core.toml" ] && [ ! -L "$R/core.toml" ]', self.src)
        self.assertIn('[ -f "$R/panel.toml" ] && [ ! -L "$R/panel.toml" ]', self.src)
        self.assertIn('[ -d "$R" ] || fail "--reuse-config requires the managed config directory', self.src)

    def test_preflight_guards_run_for_both_install_modes(self):
        # NAND and RAM guards must stay before the fresh/reuse split so a
        # reinstall over an existing directory is checked as well.
        nand = self.src.index("nand_check\n")
        ram = self.src.index("ram_check\n")
        reuse_option = self.src.index("--reuse-config")
        fresh_install = self.src.index('ok "installing verified local IPKs')
        self.assertLess(nand, fresh_install)
        self.assertLess(ram, fresh_install)
        self.assertLess(reuse_option, nand)

    def test_reuse_mode_reports_ignored_endpoint_arguments(self):
        self.assertIn("ARGS_IGNORED_IN_REUSE", self.src)


if __name__ == "__main__":
    unittest.main()
