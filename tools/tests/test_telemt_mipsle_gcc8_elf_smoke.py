"""Offline, no-network tests for real Entware MIPSLE dynamic link/runtime smoke."""
from __future__ import annotations

from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import telemt_mipsle_gcc8_elf_smoke as smoke


def fake_elf_with_interp(interp: bytes | None = smoke.INTERP) -> bytes:
    blob = bytearray(180)
    blob[:6] = b"\x7fELF\x01\x01"
    struct.pack_into("<I", blob, 28, 52)
    struct.pack_into("<HH", blob, 42, 32, 1)
    if interp is not None:
        struct.pack_into("<IIIII", blob, 52, 3, 100, 0, 0, len(interp) + 1)
        blob[100:100 + len(interp) + 1] = interp + b"\0"
    return bytes(blob)


class LinkSmokeTests(unittest.TestCase):
    def test_expected_pt_interp_accept(self):
        self.assertEqual(smoke.elf_interp(fake_elf_with_interp()), smoke.INTERP)

    def test_no_pt_interp_rejected(self):
        with self.assertRaisesRegex(smoke.ProbeError, "exactly one"):
            smoke.elf_interp(fake_elf_with_interp(None))

    def test_invalid_pt_interp_rejected(self):
        blob = bytearray(fake_elf_with_interp())
        blob[100 + len(smoke.INTERP)] = 1  # non-NUL terminator
        with self.assertRaisesRegex(smoke.ProbeError, "invalid PT_INTERP"):
            smoke.elf_interp(bytes(blob))

    def test_oversized_header_table_rejected(self):
        blob = bytearray(fake_elf_with_interp())
        struct.pack_into("<I", blob, 28, 5000)
        with self.assertRaisesRegex(smoke.ProbeError, "invalid program table"):
            smoke.elf_interp(bytes(blob))

    def test_missing_native_crt_refused_before_link(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(smoke.ProbeError, "missing genuine"):
                smoke.link_and_run(Path(td))

    def _with_mock_toolchain(self, temp: str, exit_code: int, interp: bytes, fp_abi: int):
        root = Path(temp)
        lib = root / smoke.GCC8_LIB
        lib.mkdir(parents=True)
        for name in ("crt1.o", "crti.o", "crtbegin.o", "crtend.o", "crtn.o",
                     "libc.so", "libc_nonshared.a"):
            (lib / name).write_bytes(b"fixture")
        def emit_fake_elf(args, timeout):
            Path(args[args.index("-o") + 1]).write_bytes(fake_elf_with_interp())
        runner = subprocess.CompletedProcess([], exit_code, b"", b"")
        return (
            patch.object(smoke.shutil, "which", side_effect=lambda n: "/usr/bin/" + n),
            patch.object(smoke, "compile_source"),
            patch.object(smoke, "run_cmd", side_effect=emit_fake_elf),
            patch.object(smoke, "inspect_elf", return_value={
                "softfloat_abi_ok": fp_abi == 3, "fp_abi": fp_abi}),
            patch.object(smoke, "elf_interp", return_value=interp),
            patch.object(smoke.subprocess, "run", return_value=runner),
        )

    def test_linked_non_softfloat_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            patches = self._with_mock_toolchain(td, 17, smoke.INTERP, 5)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as call:
                with self.assertRaisesRegex(smoke.ProbeError, "not softfloat"):
                    smoke.link_and_run(Path(td))
                call.assert_not_called()

    def test_wrong_loader_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            patches = self._with_mock_toolchain(td, 17, b"/lib/ld.so.1", 3)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as call:
                with self.assertRaisesRegex(smoke.ProbeError, "unexpected PT_INTERP"):
                    smoke.link_and_run(Path(td))
                call.assert_not_called()

    def test_exit_zero_is_not_false_success(self):
        with tempfile.TemporaryDirectory() as td:
            patches = self._with_mock_toolchain(td, 0, smoke.INTERP, 3)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
                with self.assertRaisesRegex(smoke.ProbeError, "exit=0"):
                    smoke.link_and_run(Path(td))

    def test_expected_runtime_exit_pass(self):
        with tempfile.TemporaryDirectory() as td:
            patches = self._with_mock_toolchain(td, 17, smoke.INTERP, 3)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as process:
                got = smoke.link_and_run(Path(td))
                self.assertEqual(got["main_exit"], 17)
                self.assertEqual(got["status"], "DYNAMIC_ENTWARE_GCC8_GLIBC227_QEMU_USER_PASS")
                process.assert_called_once()
                argv = process.call_args.args[0]
                self.assertEqual(argv[:5], [
                    "/usr/bin/unshare", "--user", "--map-root-user", "--net", "--"])


if __name__ == "__main__":
    unittest.main()
