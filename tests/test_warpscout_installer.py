"""Run the product installer with only fixture paths and mocked machine tools."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]

ASSET_VERSION = '0.16.0-1'
ASSET_NAME = f'warpscout_{ASSET_VERSION}_aarch64-3.10.ipk'
ASSET_URL = f'https://github.com/saymer-alt/entware-go/releases/download/latest/{ASSET_NAME}'


def make_release_json(digest=None):
    """Compact GitHub release metadata like the REST API returns."""
    asset = {'name': ASSET_NAME, 'uploader': {'login': 'system'},
             'browser_download_url': ASSET_URL}
    if digest is not None:
        asset['digest'] = 'sha256:' + digest
    return json.dumps({'name': 'latest', 'assets': [asset]}, separators=(',', ':'))


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root/'bin'; self.bin.mkdir()
        self.downloads = self.root/'tmp'; self.downloads.mkdir()
        self.opt = self.root/'opt'; (self.opt/'bin').mkdir(parents=True)
        # The download mock writes exactly this payload; keep the release
        # digest matched so the default flow installs after verification.
        self.payload_digest = hashlib.sha256(b'fixture').hexdigest()
        self.tool('uname', 'echo aarch64')
        self.tool('opkg', '''case "$1" in
print-architecture) echo 'arch aarch64-3.10 100';;
update) exit 0;;
install) [ "$2" != warpscout ] || exit 1; [ "${FAIL_INSTALL:-0}" = 0 ];;
esac''')
        self.tool('curl', '''case "$*" in
*api.github.com*)
    [ "${API_FAIL:-0}" = 0 ] || exit 22
    [ "${API_TIMEOUT:-0}" = 0 ] || exit 28
    dest=""
    while [ "$#" -gt 0 ]; do if [ "$1" = -o ]; then shift; dest=$1; fi; shift; done
    printf '%s' "$RELEASE_JSON" > "$dest";;
*) while [ "$#" -gt 0 ]; do if [ "$1" = -o ]; then shift; target=$1; fi; shift; done
printf '%s\\n' "$target" >> "$CALLS"
printf fixture > "$target"
[ "${PAUSE:-0}" = 0 ] || sleep 10
;; esac''')
        warpscout = self.opt/'bin/warpscout'
        warpscout.write_text('#!/bin/sh\n[ "$1" = version ] && echo fixture\nexit 0\n'); warpscout.chmod(0o755)
        source = (ROOT/'warpscout/install.sh').read_text().replace('/opt',str(self.opt))
        # BusyBox ash may prefer its builtin uname over PATH; keep the
        # architecture observation explicitly injected on the x86 test host.
        source = source.replace('uname -m', str(self.bin/'uname')+' -m')
        self.script = self.root/'installer.sh'; self.script.write_text(source)
        self.env = dict(os.environ, PATH=str(self.bin)+':'+os.environ['PATH'], TMPDIR=str(self.downloads), CALLS=str(self.root/'calls'),
                        RELEASE_JSON=make_release_json(self.payload_digest))
        self.shell = ['busybox', 'ash'] if os.environ.get('INSTALL_TEST_SHELL') == 'busybox' else ['sh']

    def no_jq_env(self):
        """PATH with the system tools the installer needs but deliberately
        without jq, to exercise the unverified-download fallback that must
        print an explicit warning. Mocked tools stay in self.bin."""
        nojq = self.root/'nojq-bin'; nojq.mkdir()
        needed = ['sh', 'grep', 'head', 'sed', 'awk', 'mktemp', 'chmod',
                  'rm', 'basename', 'sha256sum', 'mkdir']
        if os.environ.get('INSTALL_TEST_SHELL') == 'busybox':
            needed.append('busybox')
        for name in needed:
            source = shutil.which(name)
            if source:
                os.symlink(source, nojq/name)
        return dict(self.env, PATH=str(nojq)+':'+str(self.bin))

    def run_install(self, extra=None, env=None):
        return subprocess.run(self.shell+[str(self.script)],env=env or dict(self.env,**(extra or {})),capture_output=True,timeout=15)

    def tool(self, name, code):
        path = self.bin/name; path.write_text('#!/bin/sh\n'+code+'\n'); path.chmod(0o755)

    def test_symlink_repeat_and_parallel(self):
        victim = self.root/'victim'; victim.write_text('keep')
        symlink = self.downloads/'warpscout_0.16.0-1_aarch64-3.10.ipk'; symlink.symlink_to(victim)
        self.assertEqual(self.run_install().returncode,0)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:self.run_install(),range(2)))
        self.assertTrue(all(r.returncode == 0 for r in results))
        self.assertEqual(victim.read_text(),'keep')
        self.assertTrue(symlink.is_symlink())
        calls=(self.root/'calls').read_text().splitlines()
        self.assertEqual(len(set(calls)),3)
        self.assertFalse(list(self.downloads.glob('warpscout-install.*')))

    def test_install_failure_cleanup(self):
        self.assertNotEqual(self.run_install({'FAIL_INSTALL':'1'}).returncode,0)
        self.assertFalse(list(self.downloads.glob('warpscout-install.*')))

    def test_fallback_digest_mismatch_refuses_install(self):
        result = self.run_install({'RELEASE_JSON': make_release_json('0'*64)})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'SHA-256 mismatch', result.stderr)
        self.assertFalse(list(self.downloads.glob('warpscout-install.*')))

    def test_fallback_http_404_refuses_download(self):
        result = self.run_install({'API_FAIL': '1'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'HTTP error or timeout', result.stderr)
        self.assertFalse((self.root/'calls').exists())

    def test_fallback_timeout_refuses_download(self):
        result = self.run_install({'API_TIMEOUT': '1'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'HTTP error or timeout', result.stderr)
        self.assertFalse((self.root/'calls').exists())

    def test_fallback_without_digest_warns_and_installs(self):
        result = self.run_install({'RELEASE_JSON': make_release_json(None)})
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(b'without checksum verification', result.stdout)

    def test_fallback_broken_jq_fails_closed(self):
        self.tool('jq', 'exit 1')
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(list(self.downloads.glob('warpscout-install.*')))

    def test_fallback_without_jq_warns_and_installs_unverified(self):
        result = self.run_install(env=self.no_jq_env())
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(b'jq is not available', result.stdout)
        # The grep fallback still resolved the asset and installed it.
        self.assertTrue((self.root/'calls').exists())

    def test_feed_install_prints_freshness_note(self):
        # Force the feed branch to succeed so its advisory note is printed.
        self.tool('opkg', '''case "$1" in
print-architecture) echo 'arch aarch64-3.10 100';;
update) exit 0;;
install) [ "${FAIL_INSTALL:-0}" = 0 ];;
esac''')
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(b'from Entware feed', result.stdout)
        self.assertIn(b'update.sh', result.stdout)
        self.assertFalse((self.root/'calls').exists())

    def test_signal_cleanup(self):
        proc=subprocess.Popen(self.shell+[str(self.script)],env=dict(self.env,PAUSE='1'),start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            end=time.monotonic()+5
            while not (self.root/'calls').exists() and time.monotonic()<end: time.sleep(.02)
            self.assertTrue((self.root/'calls').exists())
            stages=list(self.downloads.glob('warpscout-install.*'))
            self.assertEqual(len(stages),1)
            self.assertEqual(stages[0].stat().st_mode & 0o777,0o700)
            os.killpg(proc.pid,signal.SIGTERM)
            self.assertNotEqual(proc.wait(timeout=5),0)
            self.assertFalse(list(self.downloads.glob('warpscout-install.*')))
        finally:
            if proc.poll() is None: os.killpg(proc.pid,signal.SIGKILL); proc.wait()


if __name__ == '__main__': unittest.main()
