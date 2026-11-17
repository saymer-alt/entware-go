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
    69: "BusyBox timeout applet unavailable",
    70: "foreground Linux syscall unsupported",
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
        all_codes = re.findall(r"\bexit (4[1-9]|5[0-9]|6[0-9]|70)\b", text)
        # Group 41..70 exclusively belongs to the new startup stages.
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
        for code in (46, *range(55, 71)):
            self.assertIn(f"exit {code}", command)
        self.assertTrue(command.endswith("exit 46"))
        self.assertIn("/opt/bin/busybox timeout -k 2 12 ", command)
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

    def test_foreground_classifier_uses_only_pinned_disposable_config(self):
        step = next(s for s in self.plan["steps"]
                    if s.get("expect") == "IPC_PIDFILE_READY")
        command = step["send"]
        self.assertIn(self.module.BIN + " start --foreground", command)
        self.assertIn(self.module.CONF + " >/opt/lab/ipc-fg.out", command)
        self.assertIn("grep -qx timeout || exit 69", command)
        self.assertNotIn("--run-as-user", command)
        self.assertNotIn("kill -9 ", command)
        self.assertNotIn("pkill ", command)
        # Parsed by a real /bin/sh; no foreground binary is run by host tests.

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
