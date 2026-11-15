"""Fast negative tests: Entware MIPSLE toolchain configuration contract."""
import sys
from pathlib import Path
from subprocess import CompletedProcess
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from telemt_mipsle_entware_config_gate import (
    EXPECTED, ConfigError, check_compiler, check_config
)


def valid_config():
    return "\n".join(f"{key}={value}" for key, value in EXPECTED.items()) + (
        '\nCONFIG_TARGET_OPTIMIZATION="-O2 -pipe -mips32r2 -mtune=mips32r2"\n'
        '# CONFIG_EXTERNAL_TOOLCHAIN is not set\n'
        '# CONFIG_TARGET_mips_3_4 is not set\n'
    )


class ConfigTests(unittest.TestCase):
    def test_matching_entware_config_pass(self):
        self.assertTrue(check_config(valid_config())["softfloat"])

    def test_hardfloat_denied(self):
        with self.assertRaisesRegex(ConfigError, "CONFIG_SOFT_FLOAT"):
            check_config(valid_config().replace("CONFIG_SOFT_FLOAT=y", "CONFIG_SOFT_FLOAT=n"))

    def test_wrong_glibc_denied(self):
        with self.assertRaisesRegex(ConfigError, "CONFIG_GLIBC_VERSION"):
            check_config(valid_config().replace('"2.27"', '"2.39"'))

    def test_wrong_gcc_denied(self):
        with self.assertRaisesRegex(ConfigError, "CONFIG_GCC_VERSION"):
            check_config(valid_config().replace('"8.4.0"', '"12.2.0"'))

    def test_wrong_endianness_denied(self):
        with self.assertRaisesRegex(ConfigError, "big-endian"):
            check_config(valid_config().replace(
                '# CONFIG_TARGET_mips_3_4 is not set', 'CONFIG_TARGET_mips_3_4=y'))

    def test_external_toolchain_denied(self):
        with self.assertRaisesRegex(ConfigError, "external toolchain"):
            check_config(valid_config().replace(
                '# CONFIG_EXTERNAL_TOOLCHAIN is not set', 'CONFIG_EXTERNAL_TOOLCHAIN=y'))

    def test_duplicate_value_denied(self):
        with self.assertRaisesRegex(ConfigError, "duplicate CONFIG_SOFT_FLOAT"):
            check_config(valid_config() + "CONFIG_SOFT_FLOAT=n\n")

    def test_missing_mips32r2_opt_denied(self):
        with self.assertRaisesRegex(ConfigError, "MIPS32r2"):
            check_config(valid_config().replace("-mips32r2", "-mips32"))

    def test_compiler_version_and_target_pass(self):
        with patch("telemt_mipsle_entware_config_gate.subprocess.run",
                   side_effect=[CompletedProcess([], 0, "8.4.0\n", ""),
                                CompletedProcess([], 0, "mipsel-openwrt-linux-gnu\n", "")]):
            self.assertEqual(check_compiler("/opt/sdk/bin/mipsel-linux-gnu-gcc")["version"], "8.4.0")

    def test_debian_gcc12_denied(self):
        with patch("telemt_mipsle_entware_config_gate.subprocess.run",
                   side_effect=[CompletedProcess([], 0, "12.2.0\n", ""),
                                CompletedProcess([], 0, "mipsel-linux-gnu\n", "")]):
            with self.assertRaisesRegex(ConfigError, "compiler mismatch"):
                check_compiler("/usr/bin/mipsel-linux-gnu-gcc")


if __name__ == "__main__":
    unittest.main()
