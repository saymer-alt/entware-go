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


class UpdateWithErrorContractTests(unittest.TestCase):
    """A failed or interrupted update must never leave a silently
    overwritable state: every preflight runs before the first mutation,
    a partially installed retry aborts instead of overwriting, and no
    config or secrets are written before both packages are verified."""

    def setUp(self):
        self.src = INSTALL.read_text(encoding="utf-8")

    def test_preflight_completes_before_first_mutation(self):
        first_install = self.src.index('opkg install "$IPK1"')
        for needle in ('hashmatch "$IPK1"', 'hashmatch "$IPK2"',
                       "nand_check", "ram_check",
                       'available "$PROXY_PORT"', 'available "$PANEL_PORT"',
                       "available 19091"):
            pos = self.src.index(needle)
            self.assertLess(pos, first_install,
                            f"must precede the first opkg install: {needle}")

    def test_partially_installed_state_refuses_silent_overwrite(self):
        # After a mid-install failure (e.g. Core installed, Panel failed) the
        # Core binary exists, so a retry must hit the explicit abort instead
        # of silently replacing the half-installed set.
        abort = self.src.index("Core executable already exists; abort to avoid overwriting")
        installs = self.src.index('opkg install "$IPK1"')
        self.assertLess(abort, installs)
        self.assertIn("Panel executable already exists; abort to avoid overwriting", self.src)
        self.assertIn("init script name already exists", self.src)

    def test_config_directory_only_created_after_both_packages_verified(self):
        installs = self.src.index('opkg install "$IPK2"')
        elf_verify = self.src.index("installed Core ELF differs from pin")
        config = self.src.index('mkdir -p "$R"')
        self.assertLess(installs, elf_verify)
        self.assertLess(elf_verify, config)


if __name__ == "__main__":
    unittest.main()
