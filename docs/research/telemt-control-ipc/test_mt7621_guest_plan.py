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
        self.assertLess(positions[-1], labels.index("IPC_RELOAD_SAME_PID"))
        self.assertLess(labels.index("IPC_STOP_CLEAN"), labels.index("IPC_REBOOT_NO_AUTOSTART"))
        self.assertLess(labels.index("IPC_REBOOT_NO_AUTOSTART"),
                        labels.index("IPC_ROLLBACK_OK"))

    def test_codes_are_reserved_only_for_start_diagnosis(self):
        text = "\n".join(s.get("send", "") for s in self.plan["steps"]
                         if isinstance(s.get("send"), str))
        all_codes = re.findall(r"\bexit (4[1-9]|50|51)\b", text)
        # Group 41..51 exclusively belongs to the new startup stages.
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

    def test_findutils_in_exact_emulator_lock(self):
        lock_path = self.root / "lab/entware-mipselsf.lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        found = [p for p in lock["packages"] if p["Package"] == "findutils"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["Architecture"], "mipsel-3.4")
        self.assertRegex(found[0]["SHA256sum"], r"^[a-f0-9]{64}$")
        step = next(x for x in self.plan["steps"]
                    if x.get("expect") == "IPC_PARENT_OWNER_MODE")
        self.assertIn("test -x /opt/bin/find", step["send"])
        self.assertIn("-printf %m", step["send"])
        self.assertIn("-printf %U", step["send"])
        self.assertNotIn("busybox stat", step["send"])

    def test_gnu_findutils_mode_and_numeric_uid_from_private_dir(self):
        # The host test checks GNU find syntax and semantics only. It does
        # not claim that the remote mipsel executable has run.
        with tempfile.TemporaryDirectory(prefix="ipc-mode-") as root:
            private = Path(root) / "private"
            private.mkdir(mode=0o700)
            os.chmod(private, 0o700)
            observed = subprocess.run(
                ["find", str(private), "-maxdepth", "0",
                 "-printf", "%m:%U"],
                capture_output=True, text=True, check=True)
            self.assertEqual(observed.stdout, f"700:{os.getuid()}")

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
