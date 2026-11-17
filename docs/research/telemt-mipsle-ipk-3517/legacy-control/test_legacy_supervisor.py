"""Host-only, disposable experiments; no TeleMT or router binaries touched."""
import os
import socket
import stat
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

SOURCE = Path(__file__).with_name("legacy-supervisor.c")

CHILD = """
import os, signal, sys, time
from pathlib import Path
root = Path(sys.argv[1])
def reload(signum, frame):
    (root/'reloaded').write_text('yes')
def terminate(signum, frame):
    (root/'terminated').write_text('yes')
    sys.exit(0)
signal.signal(signal.SIGHUP, reload)
signal.signal(signal.SIGTERM, terminate)
(root/'ready').write_text(str(os.getpid()))
while True: time.sleep(.05)
"""


class LegacySupervisorHostProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._binary_dir = tempfile.TemporaryDirectory()
        cls.binary = str(Path(cls._binary_dir.name) / "legacy-supervisor")
        compiled = subprocess.run([shutil.which("cc") or "cc", "-std=c11", "-Wall",
                                   "-Wextra", "-Werror", "-O2", str(SOURCE), "-o", cls.binary],
                                  capture_output=True, text=True)
        if compiled.returncode != 0:
            raise AssertionError(f"host C compiler failed:\n{compiled.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls._binary_dir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sock = str(self.root / "control.sock")
        self.child = None

    def tearDown(self):
        if self.child and self.child.poll() is None:
            self.child.terminate()
            try:
                self.child.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait(timeout=4)
        if self.child and self.child.stderr:
            self.child.stderr.close()

    def wait_path(self, name):
        target = self.root / name
        for _ in range(200):
            if target.exists():
                return target
            time.sleep(.025)
        self.fail(f"not created: {name}")

    def invoke(self, verb):
        return subprocess.run([self.binary, verb, self.sock], capture_output=True,
                              timeout=5).returncode

    def start(self):
        self.child = subprocess.Popen([self.binary, "serve", self.sock, "--",
                                       sys.executable, "-u", "-c", CHILD, str(self.root)],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.wait_path("ready")
        self.wait_path("control.sock")

    def test_daemon_owned_reload_stop_and_reap(self):
        self.start()
        self.assertEqual(self.invoke("status"), 0)
        self.assertEqual(self.invoke("reload"), 0)
        self.wait_path("reloaded")
        self.assertEqual(self.invoke("stop"), 0)
        self.wait_path("terminated")
        self.assertEqual(self.child.wait(timeout=5), 0)
        self.assertFalse(Path(self.sock).exists())
        self.assertEqual(self.invoke("stop"), 1)

    def test_invalid_or_absent_socket_fails_closed(self):
        self.assertEqual(self.invoke("stop"), 1)
        self.assertEqual(self.invoke("reload"), 1)
        self.assertEqual(self.invoke("status"), 1)
        self.assertEqual(subprocess.run([self.binary, "serve", self.sock, "--",
                                         "/bin/true"], capture_output=True).returncode, 0)
        self.assertEqual(self.invoke("stop"), 1)

    def test_insecure_parent_and_preexisting_endpoint_rejected(self):
        os.chmod(self.root, 0o777)
        result = subprocess.run([self.binary, "serve", self.sock, "--", "/bin/true"],
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        os.chmod(self.root, 0o700)
        Path(self.sock).write_text("not-a-socket")
        result = subprocess.run([self.binary, "serve", self.sock, "--", "/bin/true"],
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(Path(self.sock).read_text(), "not-a-socket")

    def test_child_exits_before_command_without_pid_signals(self):
        self.child = subprocess.Popen([self.binary, "serve", self.sock, "--", "/bin/true"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.assertEqual(self.child.wait(timeout=5), 0)
        self.assertFalse(Path(self.sock).exists())
        self.assertEqual(self.invoke("reload"), 1)

    def test_early_disconnect_cannot_kill_supervisor(self):
        self.start()
        self.assertTrue(stat.S_ISSOCK(os.stat(self.sock).st_mode))
        self.assertEqual(stat.S_IMODE(os.stat(self.sock).st_mode) & 0o077, 0)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.connect(self.sock)
            peer.sendall(b"P")
            peer.shutdown(socket.SHUT_RDWR)
        time.sleep(0.2)
        self.assertIsNone(self.child.poll(), "peer disconnect must not terminate owner")
        self.assertEqual(self.invoke("status"), 0)
        self.assertEqual(self.invoke("stop"), 0)
        self.assertEqual(self.child.wait(timeout=5), 0)

    def test_replaced_socket_path_is_not_unlinked_on_exit(self):
        self.start()
        os.unlink(self.sock)
        Path(self.sock).write_text("replacement-must-survive")
        self.child.terminate()
        self.wait_path("terminated")
        self.assertEqual(self.child.wait(timeout=5), 0)
        self.assertEqual(Path(self.sock).read_text(), "replacement-must-survive")
