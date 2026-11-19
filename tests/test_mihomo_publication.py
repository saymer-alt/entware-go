import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from publish_ipks import PublicationError, complete_candidate, expected_variants, package_key, publish, prune_complete
from test_publish_ipks import API, asset


def filename(version, variant):
    package = 'mihomo_nohf' if variant.startswith('nohf/') else 'mihomo'
    return f'{package}_{version}_{variant.removeprefix("nohf/")}.ipk'


class MihomoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.api = API()
        self.api.assets = [a for a in self.api.assets if not a['name'].startswith('mihomo_')]
        self.foreign = copy.deepcopy(self.api.assets)
        for index, variant in enumerate(sorted(expected_variants('mihomo'))):
            self.api.assets.append(asset(filename('1.19.31-2', variant), identity=20+index))
            (self.root / filename('1.19.32-2', variant)).write_bytes(b'new-' + variant.encode())

    def publish(self):
        publish(self.api, self.root, '1.19.32', 'mihomo')

    def test_complete_mixed_float_set_then_cleanup(self):
        self.publish()
        self.assertEqual(len(self.api.uploads), 6)
        self.assertEqual(len(self.api.deleted), 6)
        self.assertTrue(all(a in self.api.assets for a in self.foreign))
        self.assertEqual(len(complete_candidate(self.api.release(), '1.19.32', 'mihomo')), 6)

    def test_incomplete_nohf_or_wrong_abi_cannot_prune(self):
        for replacement in (None, 'armv7-5.10'):
            soft = next(self.root.glob('mihomo_nohf*'))
            payload = soft.read_bytes()
            soft.unlink()
            wrong = self.root / filename('1.19.32-2', 'nohf/' + replacement) if replacement else None
            if wrong:
                wrong.write_bytes(payload)
            with self.assertRaises(PublicationError):
                self.publish()
            self.assertEqual(self.api.uploads + self.api.deleted, [])
            if wrong:
                wrong.unlink()
            soft.write_bytes(payload)

    def test_prune_failure_cleanup_only_never_uploads(self):
        self.api.fail_delete = 2
        with self.assertRaises(PublicationError):
            self.publish()
        wanted = copy.deepcopy([a for a in self.api.assets if a['id'] >= 100])
        self.api.fail_delete = None
        prune_complete(self.api, '1.19.32')
        self.assertEqual(wanted, [a for a in self.api.assets if a['id'] >= 100])
        self.assertEqual(len(self.api.uploads), 6)
        prune_complete(self.api, '1.19.32')
        self.assertEqual(len(self.api.uploads), 6)
        self.assertTrue(all(a in self.api.assets for a in self.foreign))

    def test_notification_failure_leaves_overlap_for_recovery_without_upload(self):
        publish(self.api, self.root, '1.19.32', 'mihomo', keep_old=True)
        self.assertEqual(self.api.deleted, [])
        self.assertTrue(complete_candidate(self.api.release(), '1.19.32', 'mihomo'))
        old_ids = {a['id'] for a in self.api.assets if 20 <= a['id'] < 100}
        self.assertEqual(len(old_ids), 6)
        # Failed notification ends the workflow before pruning; the next run
        # verifies/notifies this complete set and retries cleanup only.
        ids = {a['id'] for a in self.api.assets if a['id'] >= 100}
        prune_complete(self.api, '1.19.32')
        self.assertEqual(ids, {a['id'] for a in self.api.assets if a['id'] >= 100})
        self.assertEqual(len(self.api.uploads), 6)

    def test_partial_upload_preserves_old_and_retry_reuses_uploaded_ids(self):
        self.api.fail_upload = 3
        with self.assertRaises(PublicationError):
            self.publish()
        ids = [a['id'] for a in self.api.assets if a['id'] >= 100]
        self.assertFalse(complete_candidate(self.api.release(), '1.19.32', 'mihomo'))
        self.assertEqual(self.api.deleted, [])
        with self.assertRaises(PublicationError):
            prune_complete(self.api, '1.19.32')
        self.api.fail_upload = None
        self.publish()
        self.assertTrue(set(ids).issubset(a['id'] for a in self.api.assets))

    def test_newer_partial_release_not_deleted_in_favour_of_complete_older_release(self):
        self.publish()
        self.api.assets.append(asset(filename('1.19.32-3', 'mipsel-3.4'), identity=200))
        self.assertFalse(complete_candidate(self.api.release(), '1.19.32', 'mihomo'))
        deletes = self.api.deleted.copy()
        with self.assertRaises(PublicationError):
            prune_complete(self.api, '1.19.32')
        self.assertEqual(deletes, self.api.deleted)

    def test_foreign_newer_version_blocks_cleanup(self):
        self.publish()
        self.api.assets.append(asset(filename('1.20.0-1', 'mipsel-3.4'), identity=200))
        with self.assertRaises(PublicationError):
            prune_complete(self.api, '1.19.32')

    def test_noncanonical_versions_rejected_as_by_consumer(self):
        for version in ('01.19.32-2', '1.19.32-0', '1.19.32-02', '1.bad-2'):
            with self.assertRaises(PublicationError):
                package_key(filename(version, 'mipsel-3.4'), 'mihomo')

    def test_workflow_contract(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('build-beszel.yml', 'build-mihomo.yml', 'build-warpscout.yml'):
            workflow = (root / '.github/workflows' / name).read_text()
            publication = workflow.split('  publish-latest-release:')[1]
            self.assertIn('group: entware-latest-publication', publication)
        workflow = (root / '.github/workflows/build-mihomo.yml').read_text()
        self.assertIn('--prune-only', workflow)
        self.assertIn('--plan', workflow)
        self.assertNotIn('--clobber', workflow)
        self.assertNotIn('steps.target-release', workflow)
        self.assertNotIn('- .github/workflows/build-mihomo.yml', workflow)
        for name in ('prune-complete', 'publish-latest-release'):
            job = workflow.split('  '+name+':')[1].split('\n  preflight:')[0]
            self.assertLess(job.index('Dispatch to feedly'), job.index('--prune-only'))
        self.assertIn('curl -fsS -X POST', workflow)
        self.assertIn("needs.check-version.outputs.prune == 'true'", workflow)
        self.assertIn('--keep-old', workflow)

    def test_workflow_revision_aware_plan_contract(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / '.github/workflows/build-mihomo.yml').read_text()
        self.assertIn('--expected-release "$RELEASE"', workflow)
        self.assertIn('PKG_RELEASE', workflow)
        # No-publish dispatch guard must only ever *skip* feed mutation; the
        # build matrix itself must stay unconditional so validation dispatches
        # still produce the full six-package artifact set.
        build = workflow.split('  build:')[1].split('\n  publish-latest-release:')[0]
        self.assertNotIn('inputs.publish', build)

    def test_workflow_publish_gate_by_event_type(self):
        # GitHub loose equality coerces null and boolean false to 0, so a
        # guard comparing the (undefined) push/schedule input against false
        # would skip publication on every automatic run. The correct gate
        # short-circuits on the event name first and only then demands an
        # explicit publish=true from a manual dispatch.
        root = Path(__file__).resolve().parents[1]
        workflow = (root / '.github/workflows/build-mihomo.yml').read_text()
        gate = "(github.event_name != 'workflow_dispatch' || inputs.publish == true)"
        for name in ('prune-complete', 'publish-latest-release'):
            job = workflow.split('  '+name+':')[1].split('\n  preflight:')[0]
            self.assertIn(gate, job)
        self.assertNotIn('inputs.publish != false', workflow)
        # pull_request never appears as a trigger, so a PR can neither build
        # nor publish; push/schedule must remain the automatic channels.
        triggers = workflow.split('jobs:')[0]
        self.assertNotIn('pull_request', triggers)
        self.assertIn('workflow_dispatch:', triggers)
        self.assertIn('push:', triggers)
        self.assertIn('schedule:', triggers)
        # The dispatch input defaults to true and is a real boolean, so
        # `inputs.publish == true` compares payload booleans, not strings.
        input_block = triggers.split('publish:')[1].split('push:')[0]
        self.assertIn('type: boolean', input_block)
        self.assertIn('default: true', input_block)


class ExpectedReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.api = API()
        self.api.assets = [a for a in self.api.assets if not a['name'].startswith('mihomo_')]
        for index, variant in enumerate(sorted(expected_variants('mihomo'))):
            self.api.assets.append(asset(filename('1.19.32-2', variant), identity=20+index))

    def test_complete_stale_release_is_not_a_candidate(self):
        self.assertEqual(len(complete_candidate(self.api.release(), '1.19.32', 'mihomo', 2)), 6)
        self.assertFalse(complete_candidate(self.api.release(), '1.19.32', 'mihomo', 3))

    def test_matching_release_with_partial_newer_still_not_candidate(self):
        self.api.assets.append(asset(filename('1.19.32-3', 'mipsel-3.4'), identity=90))
        self.assertFalse(complete_candidate(self.api.release(), '1.19.32', 'mihomo', 3))

    def test_matching_release_complete_and_cleanup_only_older_revisions(self):
        for variant in expected_variants('mihomo'):
            (self.root / filename('1.19.32-3', variant)).write_bytes(b'new-' + variant.encode())
        self.assertFalse(complete_candidate(self.api.release(), '1.19.32', 'mihomo', 3))
        publish(self.api, self.root, '1.19.32', 'mihomo', keep_old=True)
        self.assertEqual(self.api.deleted, [])
        self.assertEqual(len(complete_candidate(self.api.release(), '1.19.32', 'mihomo', 3)), 6)
        prune_complete(self.api, '1.19.32')
        self.assertEqual([a['name'] for a in self.api.assets if a['name'].startswith('mihomo_')],
                         sorted(filename('1.19.32-3', v) for v in expected_variants('mihomo')))

    def test_invalid_expected_release_rejected(self):
        for bad in (0, -1, '2', 2.0):
            with self.assertRaises(PublicationError):
                complete_candidate(self.api.release(), '1.19.32', 'mihomo', bad)


if __name__ == '__main__':
    unittest.main()
