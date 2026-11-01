"""Safety regression for the on-demand WARPSCOUT GitHub IPK updater."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'warpscout/update.sh'


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        self.opt = self.home / 'opt'
        (self.opt / 'bin').mkdir(parents=True)
        exe = self.opt / 'bin' / 'warpscout'
        exe.write_text('#!/bin/sh\necho 0.16.1\n')
        exe.chmod(0o755)
        self.state = self.opt / 'etc' / 'warpscout'
        self.state.mkdir(parents=True)
        (self.state / 'warpscout-account.json').write_text('KEEP ACCOUNT\n')
        (self.state / 'warp-awg.conf').write_text('KEEP CONFIG\n')
        self.temp = self.home / 'tmp'
        self.temp.mkdir()
        self.version = self.home / 'installed'
        self.version.write_text('0.16.0-1')
        self.calls = self.home / 'calls'
        self.payload = self.home / 'package.ipk'
        self.payload.write_bytes(b'EXAMPLE IPK FOR TEST ONLY\n')
        self.metadata = self.home / 'release.json'
        self.make_release()
        self.tool('uname', 'echo "${MOCK_ARCH:-aarch64}"')
        self.tool('opkg', '''
case "$1" in
    print-architecture) echo 'arch aarch64-3.10 100';;
    status) [ -s "$VERSION_FILE" ] && printf 'Package: warpscout\\nStatus: install ok installed\\nVersion: %s\\n' "$(cat "$VERSION_FILE")";;
    compare-versions)
        [ "${COMPARE_FAIL:-0}" != 1 ] || exit 2
        # Tests cover numeric version and package release combinations.
        comparison="$3"
        left="$(printf '%s' "$2" | tr '.-' '  ' )"
        right="$(printf '%s' "$4" | tr '.-' '  ' )"
        set -- $left
        a="$(printf '%03d%03d%03d%03d' "$1" "$2" "$3" "${4:-0}")"
        set -- $right
        b="$(printf '%03d%03d%03d%03d' "$1" "$2" "$3" "${4:-0}")"
        case "$comparison" in
            =) [ "$a" = "$b" ];;
            '<') [ "$a" -lt "$b" ];;
            '>') [ "$a" -gt "$b" ];;
        esac;;
    install)
        printf 'install\\n' >> "$CALLS"
        [ "${INSTALL_FAIL:-0}" != 1 ] || exit 1
        if [ "${KEEP_OLD:-0}" != 1 ]; then printf '%s' '0.16.1-1' > "$VERSION_FILE"; fi;;
esac''')
        self.tool('curl', '''
case "$*" in
    *api.github.com*)
        [ "${API_FAIL:-0}" != 1 ] || exit 22
        file="$API_FIXTURE" ;;
    *)
        printf 'download\\n' >> "$CALLS"
        file="$PACKAGE_FIXTURE" ;;
esac
while [ "$#" -gt 0 ]; do
    if [ "$1" = -o ]; then shift; dest="$1"; fi
    shift
done
cp "$file" "$dest"
''')
        script = SCRIPT.read_text().replace('/opt', str(self.opt))
        script = script.replace('uname -m', str(self.bin / 'uname') + ' -m')
        self.script = self.home / 'update.sh'
        self.script.write_text(script)
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'], TMPDIR=str(self.temp),
                        VERSION_FILE=str(self.version), CALLS=str(self.calls), API_FIXTURE=str(self.metadata),
                        PACKAGE_FIXTURE=str(self.payload))
        self.shell = ['busybox', 'ash'] if os.environ.get('INSTALL_TEST_SHELL') == 'busybox' else ['sh']

    def tool(self, name, body):
        tool = self.bin / name
        tool.write_text('#!/bin/sh\n' + body + '\n')
        tool.chmod(0o755)

    def make_release(self, digest=None, version='0.16.1-1', count=1):
        name = f'warpscout_{version}_aarch64-3.10.ipk'
        digest = digest if digest is not None else hashlib.sha256(self.payload.read_bytes()).hexdigest()
        self.metadata.write_text(json.dumps({'name': 'latest', 'assets': [
            {'name': name, 'uploader': {'login': 'system'}, 'digest': 'sha256:' + digest,
             'browser_download_url': 'https://github.com/saymer-alt/entware-go/releases/download/latest/' + name}
            for _ in range(count)]}, indent=2))

    def run_update(self, **extra):
        result = subprocess.run(self.shell + [str(self.script)], capture_output=True,
                                env=dict(self.env, **{k: str(v) for k, v in extra.items()}), timeout=10)
        self.assertEqual((self.state / 'warpscout-account.json').read_text(), 'KEEP ACCOUNT\n')
        self.assertEqual((self.state / 'warp-awg.conf').read_text(), 'KEEP CONFIG\n')
        self.assertFalse(list(self.temp.glob('warpscout-update.*')), result.stderr.decode())
        return result

    def test_upgrade(self):
        r = self.run_update()
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertEqual(self.version.read_text(), '0.16.1-1')
        self.assertEqual(self.calls.read_text().splitlines(), ['download', 'install'])

    def test_same_version_is_noop(self):
        self.version.write_text('0.16.1-1')
        r = self.run_update()
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertFalse(self.calls.exists())

    def test_no_downgrade(self):
        self.version.write_text('0.17.0-1')
        r = self.run_update()
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertFalse(self.calls.exists())

    def test_bad_checksum_never_installs(self):
        self.make_release(digest='0' * 64)
        r = self.run_update()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.calls.read_text().splitlines(), ['download'])
        self.assertEqual(self.version.read_text(), '0.16.0-1')

    def test_missing_digest_never_installs(self):
        self.make_release(digest='invalid')
        r = self.run_update()
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_multiple_candidates_rejected(self):
        self.make_release(count=2)
        r = self.run_update()
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_missing_installed_is_rejected(self):
        self.version.unlink()
        r = self.run_update()
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_network_error_and_wrong_arch_rejected(self):
        for args in [dict(API_FAIL=1), dict(MOCK_ARCH='mips')]:
            with self.subTest(args=args):
                r = self.run_update(**args)
                self.assertNotEqual(r.returncode, 0)
                self.assertFalse(self.calls.exists())

    def test_opkg_failure_is_reported(self):
        r = self.run_update(INSTALL_FAIL=1)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.version.read_text(), '0.16.0-1')

    def test_post_install_mismatch_is_detected(self):
        r = self.run_update(KEEP_OLD=1)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(b'installed package version does not match', r.stderr)


if __name__ == '__main__':
    unittest.main()
