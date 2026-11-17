#!/usr/bin/env python3
"""Host-only contract tests: never launch QEMU, SSH, or actual TeleMT.

Requires a pinned router-emulator checkout (public repo SHA specified in
mt7621_guest.py). Uses only the synthetic fixture and its scenario parser.
"""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

EXPECTED = [
    "IPC_PARENT_COMPONENTS_SAFE",
    "IPC_PARENT_OWNER_MODE",
    "IPC_START_RETURNED",
    "IPC_PIDFILE_READY",
    "IPC_CHILD_EXE_CONFIRMED",
    "IPC_CONTROL_SOCKET_READY",
    "IPC_DAEMON_ALIVE",
]
FAIL_CODES = {
    41: "ancestor symlink",
    42: "missing or nondirectory ancestor",
    43: "private control parent mode",
    44: "private control parent owner",
    45: "start parent rejected",
    46: "pidfile did not appear",
    47: "invalid pidfile contents",
    48: "daemon child not alive",
    49: "wrong live executable",
    50: "Unix control socket did not appear",
    51: "readiness race or inconsistency",
    52: "BusyBox find applet unavailable",
    53: "BusyBox find -perm invocation failed",
    54: "BusyBox find -user invocation failed",
    55: "Unix socket exists without readable PID file",
    56: "pinned daemon executable alive without PID file",
    57: "PID file appeared transiently, then disappeared",
    58: "on-guest daemon log has panic marker; content not exported",
    59: "on-guest daemon log has permission or bind marker; content not exported",
    60: "other nonempty on-guest daemon log; content not exported",
    61: "sibling PID lock persists without PID file or readable log",
    62: "foreground process survived until bounded SIGTERM",
    63: "foreground process exited cleanly before bounded timeout",
    64: "foreground process failed, no allowlisted classification",
    65: "foreground crash/panic marker",
    66: "foreground permission/bind error",
    67: "foreground config parse error",
    68: "foreground missing file/path",
    70: "foreground Linux syscall unsupported",
    71: "direct foreground child executable identity mismatch",
    72: "direct foreground child TERM failed or did not exit",
    73: "foreground exited with fatal signal-like status",
    74: "foreground launcher/exec status 126 or 127",
    75: "foreground stdout/stderr nonempty without known diagnostic marker",
    76: "foreground log nonempty without known diagnostic marker",
}


class ResearchPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(ROOT)
        spec = importlib.util.spec_from_file_location(
            "pinned_telemt_ipc_guest_plan",
            Path(__file__).resolve().with_name("mt7621_guest.py"))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
        cls.plan = cls.module.scenario_for(cls.root)
        sys.path.insert(0, str(cls.root))
        from lab.run import load_scenario
        cls.load_scenario = staticmethod(load_scenario)

    def test_pinned_entware_prefetch_manifest_and_fail_closed_cache(self):
        spec = importlib.util.spec_from_file_location(
            "telemt_mipsel_entware_prefetch",
            Path(__file__).resolve().with_name("prefetch_entware_assets.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = module.assets(self.root)
        self.assertGreater(len(rows), 20)
        self.assertEqual(rows[0], ("installer.tar.gz",
                                 module.INSTALLER_URL, module.INSTALLER_SHA))
        self.assertEqual(len({x[0] for x in rows}), len(rows))
        for name, url, digest in rows:
            self.assertTrue(url.startswith("https://bin.entware.net/mipselsf-k3.4/"))
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
        with tempfile.TemporaryDirectory(prefix="ipc-cache-test-") as d:
            with self.assertRaises(ValueError):
                module.verify_cache(Path(d), rows)
            (Path(d) / rows[0][0]).write_bytes(b"incorrect installer")
            with self.assertRaises(ValueError):
                module.verify_cache(Path(d), [rows[0]])

    def test_entware_cache_preserves_guest_freshness(self):
        code = Path(__file__).resolve().with_name("mt7621_guest.py").read_text()
        self.assertIn('workspace.mkdir(mode=0o700, exist_ok=False)', code)
        self.assertIn('if args.entware_cache:', code)
        self.assertIn('verify_cache(source_cache, rows)', code)
        self.assertIn('verify_cache(internal_cache, rows)', code)
        self.assertIn('shutil.copyfile(source_cache / name, internal_cache / name)', code)
        workflow = (Path(__file__).resolve().parents[3] /
                    ".github/workflows/telemt-control-ipc-mt7621-guest.yml").read_text()
        self.assertLess(
            workflow.index("Save verified Entware cache before QEMU"),
            workflow.index("One QEMU-system kernel-4.9 IPC cycle"))
        self.assertIn('--entware-cache "$RUNNER_TEMP/mt7621-entware-cache"', workflow)

    def test_emulator_sha_is_immutable(self):
        self.assertEqual(
            self.module.EMU_SHA,
            "64a446deaacb0bca10d6053781ff1f7ad4a29552")

    def test_actual_emulator_parser_accepts_full_plan(self):
        with tempfile.TemporaryDirectory(prefix="telemt-ipc-plan-only-") as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps(self.plan), encoding="utf-8")
            parsed = self.load_scenario(path)
        self.assertEqual(len(parsed["steps"]), len(self.plan["steps"]))
        self.assertLess(len(parsed["steps"]), 74)

    def test_readiness_probes_are_isolated_and_before_ipc_operations(self):
        labels = [step.get("expect") for step in self.plan["steps"]]
        for label in EXPECTED:
            self.assertEqual(labels.count(label), 1, label)
        positions = [labels.index(label) for label in EXPECTED]
        self.assertEqual(positions, list(range(positions[0], positions[0] + len(positions))))
        self.assertLess(labels.index("IPC_ABSENT_REJECTED"), positions[0])
        self.assertNotIn("IPC_FINDUTILS_INSTALLED", labels)
        self.assertLess(positions[-1], labels.index("IPC_RELOAD_SAME_PID"))
        self.assertLess(labels.index("IPC_STOP_CLEAN"), labels.index("IPC_REBOOT_NO_AUTOSTART"))
        self.assertLess(labels.index("IPC_REBOOT_NO_AUTOSTART"),
                        labels.index("IPC_ROLLBACK_OK"))

    def test_codes_are_reserved_only_for_start_diagnosis(self):
        text = "\n".join(s.get("send", "") for s in self.plan["steps"]
                         if isinstance(s.get("send"), str))
        all_codes = re.findall(r"\bexit (4[1-9]|5[0-9]|6[0-8]|7[0-6])\b", text)
        # Group 41..68 and 70..76 covers startup diagnostics (legacy 69 removed).
        self.assertEqual(sorted({int(c) for c in all_codes}), sorted(FAIL_CODES))
        # One code may guard multiple conditions within its error category.
        self.assertGreaterEqual(len(all_codes), len(FAIL_CODES))
        for code in FAIL_CODES:
            self.assertIn(f"exit {code}", text)

    def test_all_new_ssh_steps_one_line_and_no_pidfile_kill(self):
        labels = [step.get("expect") for step in self.plan["steps"]]
        for step in self.plan["steps"][labels.index("IPC_IPK_PINNED"):]:
            if step["action"] == "ssh":
                command = step["send"]
                self.assertNotIn("\n", command)
                self.assertNotIn("\r", command)
                self.assertNotIn("/opt/bin/busybox kill ", command)
                self.assertNotIn("kill -9 ", command)
                self.assertNotIn("pkill ", command)
        self.assertTrue(self.module.start_command().startswith("HOME=/opt/lab"))
        self.assertIn("--control-socket " + self.module.CTL,
                      self.module.start_command())

    def test_busybox_find_in_exact_emulator_lock_and_probe(self):
        lock_path = self.root / "lab/entware-mipselsf.lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        found = [p for p in lock["packages"] if p["Package"] == "busybox"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["Version"], "1.38.0-5")
        self.assertEqual(found[0]["Architecture"], "mipsel-3.4")
        self.assertEqual(
            found[0]["SHA256sum"],
            "0ba41200b8fdd51c2b606fc92c141059350cd3da7a45233eb0174aeaea1bfa32")
        labels = [step.get("expect") for step in self.plan["steps"]]
        self.assertNotIn("IPC_FINDUTILS_INSTALLED", labels)
        step = next(x for x in self.plan["steps"]
                    if x.get("expect") == "IPC_PARENT_OWNER_MODE")
        self.assertIn("/opt/bin/busybox --list", step["send"])
        self.assertIn("/opt/bin/busybox find", step["send"])
        self.assertIn("-maxdepth 0 -type d -perm 700 -print", step["send"])
        self.assertIn('-maxdepth 0 -type d -user "$uid" -print', step["send"])
        self.assertNotIn("/opt/bin/find", step["send"])
        self.assertNotIn("findutils.ipk", step["send"])

    def test_busybox_find_mode_and_owner_negative_controls(self):
        # Optional runner-local executable test, never runs any guest binary.
        import shutil
        binary = shutil.which("busybox")
        if binary is None:
            self.skipTest("busybox not installed on host runner (guest plan statically checked)")
        with tempfile.TemporaryDirectory(prefix="ipc-bb-find-") as root:
            private = Path(root) / "private"
            private.mkdir(mode=0o700)
            os.chmod(private, 0o700)
            def matched(extra):
                args = [binary, "find", str(private), "-maxdepth", "0",
                        "-type", "d", *extra, "-print"]
                result = subprocess.run(args, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr[:300])
                return result.stdout.strip() == str(private)
            self.assertTrue(matched(["-perm", "700"]))
            self.assertTrue(matched(["-user", str(os.getuid())]))
            os.chmod(private, 0o755)
            self.assertFalse(matched(["-perm", "700"]))
            os.chmod(private, 0o700)
            wrong_uid = 1 if os.getuid() == 0 else 0
            self.assertFalse(matched(["-user", str(wrong_uid)]))

    def test_missing_pid_classifier_sanitized_and_fail_closed(self):
        step = next(s for s in self.plan["steps"]
                    if s.get("expect") == "IPC_PIDFILE_READY")
        command = step["send"]
        self.assertIn("seen=0;", command)
        self.assertIn("readlink", command)
        self.assertIn("grep -Eqi", command)
        for code in (46, *range(55, 69), *range(70, 77)):
            self.assertIn(f"exit {code}", command)
        self.assertNotIn("exit 69", command)
        self.assertTrue(command.endswith("exit 46"))
        self.assertNotIn("/opt/bin/busybox timeout", command)
        self.assertIn("fg_pid=$!;", command)
        self.assertIn("/opt/bin/busybox sleep 12;", command)
        self.assertIn("kill -TERM \"$fg_pid\" || exit 72", command)
        self.assertIn('wait "$fg_pid"; frc=$?', command)
        self.assertLess(command.index("fg_exe=$("),
                        command.index('kill -TERM "$fg_pid"'))
        self.assertIn("start --foreground", command)
        self.assertIn("/opt/var/run/telemt-ipc-fg.pid", command)
        self.assertIn("/opt/var/run/telemt-ipc-lab/ctl-fg.sock", command)
        self.assertIn(">/opt/lab/ipc-fg.out 2>&1", command)
        self.assertIn("frc=$?", command)
        self.assertNotIn("/opt/bin/busybox kill ", command)
        self.assertNotIn("rm -f", command)
        self.assertLess(command.index('n=0;'), command.index('start --foreground'))
        self.assertNotIn("cat " + self.module.LOG, command)
        self.assertNotIn("cat /proc/", command)
        self.assertNotIn("echo $e", command)

    def test_pid_readiness_requires_stable_live_executable(self):
        labels = [s.get("expect") for s in self.plan["steps"]]
        probe = self.plan["steps"][labels.index("IPC_PIDFILE_READY")]["send"]
        self.assertIn('case "$p" in', probe)
        self.assertIn('/proc/$p/cmdline', probe)
        self.assertIn('busybox readlink /proc/$p/exe', probe)
        self.assertIn('/opt/bin/busybox sleep 2;', probe)
        self.assertLess(probe.index("sleep 2;"),
                        probe.index("printf 'IPC_%s\\n' PIDFILE_READY"))
        self.assertGreaterEqual(probe.count("readlink /proc/$p/exe"), 2)
        self.assertGreaterEqual(probe.count("busybox cat " + self.module.PID), 2)
        exe = self.plan["steps"][labels.index("IPC_CHILD_EXE_CONFIRMED")]["send"]
        self.assertTrue(exe.startswith("[ -r " + self.module.PID + " ] || exit 57;"))
        self.assertIn("|| exit 57;", exe)

    def test_foreground_evidence_precedes_generic_main_log(self):
        step = next(s for s in self.plan["steps"]
                    if s.get("expect") == "IPC_PIDFILE_READY")
        command = step["send"]
        self.assertIn('case "$frc" in 132|134|137|139) exit 73;', command)
        self.assertIn('126|127) exit 74;', command)
        self.assertIn('[ -s /opt/lab/ipc-fg.out ] && exit 75;', command)
        self.assertIn('[ -s /opt/var/log/telemt-ipc-fg.log ] && exit 76;', command)
        self.assertLess(command.index("exit 73"),
                        command.index("[ -s " + self.module.LOG + " ] && exit 60"))
        self.assertLess(command.index("exit 75"),
                        command.index("[ -s " + self.module.LOG + " ] && exit 60"))
        self.assertLess(command.index("exit 76"),
                        command.index("[ -s " + self.module.LOG + " ] && exit 60"))
        # No log lines or process arguments are ever emitted to SSH.
        self.assertNotIn("cat /opt/lab/ipc-fg.out", command)
        self.assertNotIn("cat /opt/var/log/telemt-ipc-fg.log", command)
        self.assertNotIn("tr '\\0'", command)

    def test_foreground_classifier_uses_only_pinned_disposable_config(self):
        step = next(s for s in self.plan["steps"]
                    if s.get("expect") == "IPC_PIDFILE_READY")
        command = step["send"]
        self.assertIn(self.module.BIN + " start --foreground", command)
        self.assertIn(self.module.CONF + " >/opt/lab/ipc-fg.out", command)
        self.assertIn("fg_timed=0;", command)
        self.assertIn('fg_exe=$(/opt/bin/busybox readlink /proc/$fg_pid/exe', command)
        self.assertIn('elif [ -n "$fg_exe" ]; then exit 71', command)
        self.assertNotIn('kill -TERM "$p"', command)
        self.assertNotIn('kill -TERM "$pid"', command)
        self.assertNotIn("--run-as-user", command)
        self.assertNotIn("kill -9 ", command)
        self.assertNotIn("pkill ", command)
        # Parsed by a real /bin/sh; no foreground binary is run by host tests.

    def test_direct_child_term_is_bounded_and_not_pidfile_based(self):
        # Local POSIX-shell exercise: only the child spawned via $! may be
        # signalled. This never starts TeleMT or reads any guest files.
        executable = str(Path("/bin/sleep").resolve())
        with tempfile.TemporaryDirectory(prefix="ipc-direct-child-") as tmp:
            command = (
                "sleep 20 >/dev/null 2>&1 & fg_pid=$!; "
                "sleep 0.1; fg_exe=$(readlink /proc/$fg_pid/exe 2>/dev/null); "
                "[ \"$fg_exe\" = '" + executable + "' ] || exit 71; "
                "kill -TERM \"$fg_pid\" || exit 72; "
                "sleep 0.1; "
                "[ \"$(readlink /proc/$fg_pid/exe 2>/dev/null)\" != '" +
                executable + "' ] || exit 72; "
                "wait \"$fg_pid\"; frc=$?; "
                "[ \"$frc\" != 0 ]")
            actual = subprocess.run(["/bin/sh", "-c", command], cwd=tmp,
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(actual.returncode, 0, actual.stderr[:300])

    def test_ssh_command_posix_shell_parse_without_execution(self):
        labels = [step.get("expect") for step in self.plan["steps"]]
        for step in self.plan["steps"][labels.index("IPC_IPK_PINNED"):]:
            if step["action"] != "ssh":
                continue
            with self.subTest(marker=step["expect"]):
                # -n parses but never executes any command, never opens
                # sockets, and never starts the lab binary.
                parsed = subprocess.run(
                    ["/bin/sh", "-n", "-c", step["send"]],
                    capture_output=True, text=True, check=False)
                self.assertEqual(parsed.returncode, 0, parsed.stderr[:300])

    def test_negative_parser_mutations_reject_late_echo_or_newlines(self):
        for change in ("newline", "echo_collision"):
            with self.subTest(change=change):
                mutated = copy.deepcopy(self.plan)
                target = next(s for s in mutated["steps"]
                              if s.get("expect") == "IPC_START_RETURNED")
                if change == "newline":
                    target["send"] += "\ntrue"
                else:
                    target["send"] += "; echo IPC_START_RETURNED"
                with tempfile.TemporaryDirectory(prefix="ipc-bad-scenario-") as d:
                    p = Path(d) / "bad.json"
                    p.write_text(json.dumps(mutated), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        self.load_scenario(p)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emulator-root", type=Path, required=True)
    args, rest = parser.parse_known_args()
    ROOT = args.emulator_root.resolve()
    sys.argv = [sys.argv[0], *rest]
    unittest.main(verbosity=2)
