"""Exercise actual publication helpers with server-side failed uploads."""
import copy
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from publish_ipks import GitHub, PublicationError, complete_candidate, expected_variants, publish
from test_publish_ipks import API, asset


class Server(API):
    def __init__(self, package):
        super().__init__()
        self.package = package
        self.version = '1.19.33' if package == 'mihomo' else '0.18.8'
        old = '1.19.32' if package == 'mihomo' else '0.18.7'
        self.assets = [asset(self.filename(old, arch), identity=i+1)
                       for i, arch in enumerate(sorted(expected_variants(package)))]
        self.assets += [asset('foreign_1.0.0-1_x64-3.2.ipk', identity=90)]
        self.fault = None
        self.object_change = None

    def filename(self, version, arch):
        return f'{self.package}_{"nohf_" if arch.startswith("nohf/") else ""}{version}-1_{arch.split("/")[-1]}.ipk'

    def upload(self, file):
        if self.fault == 'starter':
            self.assets.append(dict(id=99, name=file.name, size=0, state='starter', digest=None))
            raise PublicationError('HTTP 502 after starter created')
        super().upload(file)
        if self.fault == 'ack':
            raise PublicationError('response lost after healthy server commit')

    def asset(self, identity):
        if self.object_change:
            target = next(a for a in self.assets if a['id'] == identity)
            target.update(self.object_change)
            return copy.deepcopy(target)
        return super().asset(identity)


class StarterRecovery(unittest.TestCase):
    def scenario(self, package):
        api = Server(package)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for arch in expected_variants(package):
            Path(temp.name, api.filename(api.version, arch)).write_bytes(b'new-'+arch.encode())
        return api, lambda: publish(api, temp.name, api.version, package, keep_old=True)

    def test_server_starter_retry_twice_preserves_healthy_and_foreign(self):
        for package in ('beszel-agent', 'mihomo'):
            with self.subTest(package=package):
                api, run = self.scenario(package)
                healthy = copy.deepcopy(api.assets)
                api.fault = 'starter'
                with self.assertRaises(PublicationError): run()
                self.assertEqual(api.deleted, [])
                self.assertFalse(complete_candidate(api.release(), api.version, package))
                api.fault = None
                run()
                self.assertEqual(api.deleted, [99])
                self.assertTrue(all(a in api.assets for a in healthy))
                snapshot = copy.deepcopy(api.assets)
                run()
                self.assertEqual(snapshot, api.assets)
                self.assertEqual(api.deleted, [99])
                self.assertEqual(len(complete_candidate(api.release(), api.version, package)), len(expected_variants(package)))

    def test_failed_delete_can_be_retried_without_healthy_deletions(self):
        for package in ('beszel-agent', 'mihomo'):
            api, run = self.scenario(package)
            api.fault = 'starter'
            with self.assertRaises(PublicationError): run()
            api.fault = None
            before = copy.deepcopy(api.assets)
            api.fail_delete = 0
            with self.assertRaises(PublicationError): run()
            self.assertEqual(api.assets, before)
            api.fail_delete = None
            run(); run()
            self.assertEqual(api.deleted, [99])

    def test_lost_response_after_healthy_commit_reuses_asset_identity(self):
        for package in ('beszel-agent', 'mihomo'):
            api, run = self.scenario(package)
            api.fault = 'ack'
            with self.assertRaises(PublicationError): run()
            committed = copy.deepcopy(api.assets[-1])
            api.fault = None
            run(); run()
            self.assertIn(committed, api.assets)
            self.assertEqual(api.deleted, [])

    def test_changed_object_before_delete_is_never_deleted(self):
        for mutation in (dict(state='uploaded', size=3, digest='sha256' + ':' + 'a'*64),
                         dict(id=199), dict(name='foreign.ipk'), dict(size=1)):
            for package in ('beszel-agent', 'mihomo'):
                api, run = self.scenario(package)
                api.fault = 'starter'
                with self.assertRaises(PublicationError): run()
                api.fault = None
                api.object_change = mutation
                with self.assertRaises(PublicationError): run()
                self.assertEqual(api.deleted, [])

    def test_release_or_snapshot_change_before_delete_fails_closed(self):
        for package in ('beszel-agent', 'mihomo'):
            for change in ('id', 'tag', 'candidate'):
                api, run = self.scenario(package)
                api.fault = 'starter'
                with self.assertRaises(PublicationError): run()
                api.fault = None
                original = api.release
                reads = 0
                def release():
                    nonlocal reads
                    reads += 1
                    result = original()
                    if reads == 3:  # per-starter re-fetch, after admission
                        if change == 'id': result['id'] = 142
                        elif change == 'tag': result['tag_name'] = 'foreign'
                        else: result['assets'][-1] = asset(result['assets'][-1]['name'], identity=199)
                    return result
                api.release = release
                with self.assertRaises(PublicationError): run()
                self.assertEqual(api.deleted, [])

    def test_damaged_starters_are_not_repair_authority(self):
        for package in ('beszel-agent', 'mihomo'):
            for mutation in (dict(id=0), dict(id=True), dict(size=1), dict(size=False),
                             dict(state='unknown'), dict(digest='sha256:'+'a'*64),
                             dict(name='not-owned.ipk', id=1)):
                api, run = self.scenario(package)
                api.fault = 'starter'
                with self.assertRaises(PublicationError): run()
                api.fault = None
                api.assets[-1].update(mutation)
                with self.assertRaises(PublicationError): run()
                self.assertEqual(api.deleted, [])

    def test_duplicate_starter_name_or_id_fails_closed(self):
        for package in ('beszel-agent', 'mihomo'):
            for duplicate in ('name', 'id'):
                api, run = self.scenario(package)
                api.fault = 'starter'
                with self.assertRaises(PublicationError): run()
                api.fault = None
                if duplicate == 'name': api.assets.append(dict(api.assets[-1], id=199))
                else: api.assets.append(dict(api.assets[-1], name='foreign.ipk'))
                with self.assertRaises(PublicationError): run()
                self.assertEqual(api.deleted, [])

    def test_object_api_error_preserves_starter_and_healthy_assets(self):
        for package in ('beszel-agent', 'mihomo'):
            api, run = self.scenario(package)
            api.fault = 'starter'
            with self.assertRaises(PublicationError): run()
            api.fault = None
            before = copy.deepcopy(api.assets)
            def unavailable(identity): raise PublicationError('HTTP 503 object GET')
            api.asset = unavailable
            with self.assertRaises(PublicationError): run()
            self.assertEqual(api.assets, before)
            self.assertEqual(api.deleted, [])

    def test_api_transport_and_json_errors_fail_closed(self):
        with patch.dict('os.environ', {'GH_REPO': 'owner/repo'}):
            for status in (429, 500, 502, 503):
                result = subprocess.CompletedProcess([], 1, '', f'HTTP {status}')
                with patch('subprocess.run', return_value=result):
                    with self.assertRaises(PublicationError): GitHub().asset(99)
                    with self.assertRaises(PublicationError): GitHub().delete(99)
            with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'not JSON', '')):
                with self.assertRaises(PublicationError): GitHub().asset(99)

    def test_foreign_starter_is_preserved(self):
        for package in ('beszel-agent', 'mihomo'):
            api, run = self.scenario(package)
            foreign = dict(id=199,name='foreign_0.0.1-1_x64-3.2.ipk',state='starter',size=0,digest=None)
            api.assets.append(foreign)
            run(); run()
            self.assertIn(foreign,api.assets)
            self.assertNotIn(199,api.deleted)

    def test_lost_delete_ack_resumes_without_deleting_healthy_assets(self):
        for package in ('beszel-agent', 'mihomo'):
            api, run = self.scenario(package)
            api.fault = 'starter'
            with self.assertRaises(PublicationError): run()
            api.fault = None
            delete = api.delete
            def lost_ack(identity):
                delete(identity)
                raise PublicationError('DELETE committed, response lost')
            api.delete = lost_ack
            with self.assertRaises(PublicationError): run()
            api.delete = delete
            run(); run()
            self.assertEqual(api.deleted,[99])
