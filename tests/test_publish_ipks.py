import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from publish_ipks import PublicationError, publish


def asset(name, data=b'old', identity=1):
    return dict(id=identity, name=name, size=len(data), state='uploaded',
                digest='sha256:' + hashlib.sha256(data).hexdigest())


class API:
    def __init__(self):
        self.assets = [asset('beszel-agent_0.18.7-1_' + arch + '.ipk', identity=i)
                       for i, arch in enumerate(('aarch64-3.10', 'mips-3.4', 'mipsel-3.4'), 1)]
        self.assets += [asset('mihomo_1.19.32-2_mips-3.4.ipk', identity=10),
                        asset('warpscout_0.16.0-1_aarch64-3.10.ipk', identity=11)]
        self.deleted, self.uploads, self.reads = [], [], 0
        self.fail_upload = self.fail_delete = None
        self.mutate_at = None

    def release(self):
        self.reads += 1
        if self.reads == self.mutate_at:
            self.assets.append(asset('beszel-agent_0.19.0-1_mips-3.4.ipk', identity=99))
        return dict(id=42, assets=copy.deepcopy(self.assets))

    def upload(self, file):
        if len(self.uploads) == self.fail_upload:
            raise PublicationError('HTTP 503 upload failure')
        self.uploads.append(file.name)
        self.assets.append(asset(file.name, file.read_bytes(), 100 + len(self.uploads)))

    def delete(self, identity):
        if len(self.deleted) == self.fail_delete:
            raise PublicationError('HTTP 429 pruning failure')
        self.deleted.append(identity)
        self.assets = [a for a in self.assets if a['id'] != identity]


class PublicationTests(unittest.TestCase):
    def test_workflow_checkout_precedes_artifact_download(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/build-beszel.yml').read_text()
        publication = workflow.split('  publish-latest-release:')[1]
        self.assertLess(publication.index('actions/checkout@'), publication.index('actions/download-artifact@'))
        self.assertIn('expected stable X.Y.Z', workflow)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for arch in ('aarch64-3.10', 'mips-3.4', 'mipsel-3.4'):
            (self.root / f'beszel-agent_0.18.8-1_{arch}.ipk').write_bytes(b'new-' + arch.encode())
        self.api = API()
        self.foreign = copy.deepcopy(self.api.assets[-2:])

    def run_publish(self):
        publish(self.api, self.root, '0.18.8')

    def test_complete_set_then_prune_and_idempotent_rerun(self):
        self.run_publish()
        self.assertEqual(self.api.deleted, [1, 2, 3])
        self.assertTrue(all(a in self.api.assets for a in self.foreign))
        ids = [a['id'] for a in self.api.assets]
        self.run_publish()
        self.assertEqual(ids, [a['id'] for a in self.api.assets])

    def test_missing_architecture_admits_no_mutation(self):
        next(self.root.glob('*mips-*.ipk')).unlink()
        with self.assertRaises(PublicationError):
            self.run_publish()
        self.assertEqual(self.api.uploads + self.api.deleted, [])

    def test_failed_and_partial_upload_preserve_old_then_resume(self):
        for fail_at in (0, 1, 2):
            self.api = API()
            self.api.fail_upload = fail_at
            with self.assertRaises(PublicationError):
                self.run_publish()
            self.assertEqual(self.api.deleted, [])
            self.assertTrue({1, 2, 3}.issubset({a['id'] for a in self.api.assets}))
            self.api.fail_upload = None
            self.run_publish()
            self.assertEqual(len(self.api.uploads), 3)

    def test_pruning_failure_retries_without_overwrite(self):
        self.api.fail_delete = 1
        with self.assertRaises(PublicationError):
            self.run_publish()
        new_ids = [a['id'] for a in self.api.assets if a['id'] >= 100]
        self.api.fail_delete = None
        self.run_publish()
        self.assertEqual(new_ids, [a['id'] for a in self.api.assets if a['id'] >= 100])

    def test_concurrent_publisher_before_upload_and_before_prune(self):
        for barrier in (2, 3, 4):
            self.api = API()
            self.api.mutate_at = barrier
            with self.assertRaises(PublicationError):
                self.run_publish()
            self.assertEqual(self.api.deleted, [])
            self.assertTrue(any(a['id'] == 99 for a in self.api.assets))

    def test_mismatched_digest_and_duplicate_metadata_fail_closed(self):
        file = next(self.root.glob('*.ipk'))
        for bad in (asset(file.name, b'wrong', 30), self.api.assets[0]):
            self.api = API()
            self.api.assets.append(copy.deepcopy(bad))
            with self.assertRaises(PublicationError):
                self.run_publish()
            self.assertEqual(self.api.uploads + self.api.deleted, [])

    def test_verification_failure_keeps_old_set(self):
        upload = self.api.upload
        def corrupt(file):
            upload(file)
            self.api.assets[-1]['digest'] = 'sha256:' + '0' * 64
        self.api.upload = corrupt
        with self.assertRaises(PublicationError):
            self.run_publish()
        self.assertEqual(self.api.deleted, [])

    def test_api_failure_preserves_everything(self):
        def failed():
            raise PublicationError('HTTP 500')
        self.api.release = failed
        with self.assertRaises(PublicationError):
            self.run_publish()
        self.assertEqual(self.api.uploads + self.api.deleted, [])


if __name__ == '__main__':
    unittest.main()
