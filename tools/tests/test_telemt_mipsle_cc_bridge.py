"""Fast host-only tests: fail closed on unsafe cc-rs flags and invalid object output."""
from __future__ import annotations
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import telemt_mipsle_cc_bridge as bridge


class ParseTests(unittest.TestCase):
    def test_ring_style_flags_are_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "mem.c"
            src.write_text("int x;")
            out = Path(td) / "mem.o"
            got = bridge.parse_command(["-c", str(src), "-o", str(out),
                "-fPIC", "-O3", "-g3", "-DNDEBUG", "-std=c1x",
                "-Wall", "-Wbad-function-cast", "-ffunction-sections",
                "-I", str(Path(td)), "-fvisibility=hidden"])
            self.assertEqual(got[0], src)
            self.assertEqual(got[1], out)
            self.assertIn("-O3", got[2])

    def test_missing_compile_or_link_only_is_denied(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "a.c"
            src.write_text("int x;")
            for args in ([str(src), "-o", str(Path(td) / "bin")],
                         ["-c", str(src)], ["-c", str(src), "-o"]):
                with self.subTest(args=args):
                    with self.assertRaises(bridge.ProbeError):
                        bridge.parse_command(args)

    def test_hardfloat_and_native_arch_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "test.c"
            src.write_text("int x;")
            for arg in ("-mhard-float", "-march=native", "-march=mips64",
                        "-fplugin=/tmp/hack.so", "-shared", "-Wl,-z,execstack",
                        "-fsanitize=address"):
                with self.subTest(flag=arg):
                    with self.assertRaisesRegex(bridge.ProbeError, "unsupported"):
                        bridge.parse_command(["-c", str(src), "-o", str(Path(td) / "o"), arg])

    def test_multiple_sources_denied(self):
        with tempfile.TemporaryDirectory() as td:
            files = [Path(td) / f"{i}.c" for i in range(2)]
            for f in files: f.write_text("int x;")
            with self.assertRaisesRegex(bridge.ProbeError, "multiple input"):
                bridge.parse_command(["-c", *map(str,files), "-o", str(Path(td) / "a.o")])

    def test_wrong_source_type_denied(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "bad.rs"
            f.write_text("x")
            with self.assertRaisesRegex(bridge.ProbeError, "extension"):
                bridge.parse_command(["-c", str(f), "-o", str(Path(td) / "a.o")])

    def test_safe_assembler_cpp_flag(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "test.S"
            f.write_text(".text\n")
            src, dst, opts = bridge.parse_command(["-D", "ABC=1", "-c", str(f),
                                                 "-o", str(Path(td) / "test.o")])
            self.assertEqual(src.suffix, ".S")
            self.assertEqual(opts, ["-D", "ABC=1"])

class BridgeTests(unittest.TestCase):
    def simulated(self, kind: str, abi: int, fail: bool = False):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "root"
            root.mkdir()
            src = Path(td) / ("a." + kind)
            src.write_text("int x;" if kind == "c" else ".text\nnop\n")
            out = Path(td) / "a.o"
            def fake(cmd, seconds, **_kwargs):
                if fail:
                    raise bridge.ProbeError("simulated compiler failure")
                if "-o" in cmd:
                    Path(cmd[cmd.index("-o") + 1]).write_bytes(b"object" if "mipsel-linux-gnu-as" in " ".join(cmd) else b"asm")
            with patch.object(bridge, "check_root"), \
                 patch.object(bridge.shutil, "which", side_effect=lambda name: "/usr/bin/" + name), \
                 patch.object(bridge, "exec_bounded", side_effect=fake), \
                 patch.object(bridge, "inspect_elf", return_value={"fp_abi": abi,
                       "softfloat_abi_ok": abi == 3}):
                if fail or abi != 3:
                    out.write_bytes(b"original")
                    with self.assertRaises(bridge.ProbeError):
                        bridge.assemble(root, src, out, [])
                    self.assertEqual(out.read_bytes(), b"original")
                else:
                    value = bridge.assemble(root, src, out, [])
                    self.assertEqual(value["fp_abi"], 3)
                    self.assertEqual(out.read_bytes(), b"object")

    def test_c_success(self):
        self.simulated("c", 3)

    def test_uppercase_S_success(self):
        self.simulated("S", 3)

    def test_lowercase_s_success(self):
        self.simulated("s", 3)

    def test_hardfloat_object_never_written(self):
        self.simulated("c", 5)

    def test_compiler_error_preserves_old_file(self):
        self.simulated("c", 3, fail=True)

    def test_missing_guestroot_fails(self):
        with patch.dict("os.environ", {"ENTWARE_MIPSEL_GUESTROOT": ""}):
            self.assertEqual(bridge.main(), 2)

    def test_bounded_subprocess_failure(self):
        with patch.object(bridge.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 1, b"", b"error")):
            with self.assertRaisesRegex(bridge.ProbeError, "exit=1"):
                bridge.exec_bounded(["test"], 3)

    def test_bounded_subprocess_success(self):
        with patch.object(bridge.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, b"", b"")):
            bridge.exec_bounded(["test"], 3)


if __name__ == "__main__":
    unittest.main()
