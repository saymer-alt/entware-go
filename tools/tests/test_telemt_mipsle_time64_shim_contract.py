"""Host-only contract tests for Entware MIPS O32 time32/time64 shim layout.

The GitHub Actions toolchain glibc headers may represent struct timespec as
16 bytes, but Entware glibc-2.27 time32 ABI always expects 8 bytes.
These tests do NOT run a guest or pretend to prove TeleMT runtime.
"""
from pathlib import Path
import re
import unittest

SCRIPT = (Path(__file__).resolve().parents[2]
          / "docs/research/telemt-mipsle-ipk-3517/scripts/build-telemt-core.sh")


def shim_source():
    s = SCRIPT.read_text(encoding="utf-8")
    a = 'cat > "$EB/shim/shim.c" <<\\'EOF\\'\n'
    return s.split(a, 1)[1].split("\nEOF\n", 1)[0]


class Time64AbiContract(unittest.TestCase):
    def test_entware_time32_explicit_fixed_width_layout(self):
        s = shim_source()
        self.assertIn("struct entware_timespec32 { int32_t tv_sec; int32_t tv_nsec; };", s)
        self.assertIn("sizeof(struct entware_timespec32) == 8", s)
        self.assertIn("offsetof(struct entware_timespec32, tv_nsec) == 4", s)
        self.assertIn("sizeof(struct ts64) == 16", s)
        self.assertIn("offsetof(struct ts64, tv_nsec) == 8", s)
        self.assertNotRegex(s, r"\bstruct timespec\b")
        self.assertIn("tp->_padding = 0", s)

    def test_time32_external_calls_only(self):
        s = shim_source()
        self.assertRegex(s, r"entware_clock_gettime32\(clockid_t, struct entware_timespec32 \*\)")
        self.assertRegex(s, r"entware_nanosleep32\(const struct entware_timespec32 \*, struct entware_timespec32 \*\)")
        self.assertIn(' __asm__("clock_gettime")', s)
        self.assertIn(' __asm__("nanosleep")', s)

    def test_nanosleep_overflow_fails_closed(self):
        s = shim_source()
        self.assertIn("req->tv_sec < INT32_MIN || req->tv_sec > INT32_MAX", s)
        self.assertIn("errno = EOVERFLOW", s)
        self.assertIn("rem->_padding = 0", s)


if __name__ == "__main__":
    unittest.main()
