#!/usr/bin/env python3
"""Publish a complete package set to latest before pruning its older versions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


class PublicationError(RuntimeError):
    pass


class GitHub:
    def __init__(self):
        self.repo = os.environ['GH_REPO']

    def api(self, endpoint, method='GET'):
        result = subprocess.run(['gh', 'api', '-X', method,
                                 f'repos/{self.repo}/{endpoint}'], capture_output=True, text=True)
        if result.returncode:
            raise PublicationError(result.stderr)
        if method == 'DELETE':
            return None
        try:
            return json.loads(result.stdout)
        except ValueError as exc:
            raise PublicationError('Invalid GitHub JSON') from exc

    def release(self):
        release = self.api('releases/tags/latest')
        if (not isinstance(release, dict) or release.get('tag_name') != 'latest'
                or release.get('draft') is not False or release.get('prerelease') is not False
                or type(release.get('id')) is not int):
            raise PublicationError('Invalid latest release metadata')
        assets = []
        page = 1
        while True:
            batch = self.api(f"releases/{release['id']}/assets?per_page=100&page={page}")
            if not isinstance(batch, list):
                raise PublicationError('Invalid assets response')
            assets.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        release['assets'] = assets
        return release

    def upload(self, file):
        result = subprocess.run(['gh', 'release', 'upload', 'latest', str(file),
                                 '--repo', self.repo], capture_output=True, text=True)
        if result.returncode:
            raise PublicationError(result.stderr)

    def delete(self, asset_id):
        self.api(f'releases/assets/{asset_id}', 'DELETE')

    def asset(self, asset_id):
        return self.api(f'releases/assets/{asset_id}')


def package_key(name, package):
    variant = ''
    if package == 'mihomo' and name.startswith('mihomo_nohf_'):
        name = name.replace('mihomo_nohf_', 'mihomo_', 1)
        variant = 'nohf/'
    match = re.fullmatch(re.escape(package) + r'_(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-([1-9][0-9]*)_([a-z0-9]+-[0-9.]+)\.ipk', name)
    if not match:
        raise PublicationError(f'Invalid package filename: {name}')
    return tuple(int(match[i]) for i in range(1, 5)), variant + match[5]


def expected_variants(package):
    if package == 'beszel-agent':
        return {'aarch64-3.10', 'mips-3.4', 'mipsel-3.4'}
    if package == 'mihomo':
        return {'aarch64-3.10', 'armv7-3.2', 'mips-3.4', 'mipsel-3.4', 'x64-3.2', 'nohf/armv7-3.2'}
    raise PublicationError('Unsupported package scope')


def starter(asset):
    return (asset.get('state') == 'starter' and type(asset.get('size')) is int
            and asset['size'] == 0 and asset.get('digest') is None)


def scoped(release, package):
    if (not isinstance(release, dict) or release.get('tag_name') != 'latest'
            or release.get('draft') is not False or release.get('prerelease') is not False
            or type(release.get('id')) is not int or release['id'] <= 0):
        raise PublicationError('Invalid latest release identity')
    result = {}
    assets = release.get('assets')
    if not isinstance(assets, list):
        raise PublicationError('Invalid asset list')
    for asset in assets:
        if not isinstance(asset, dict) or not isinstance(asset.get('name'), str):
            raise PublicationError('Invalid asset metadata')
        name = asset['name']
        if not (name.startswith(package + '_') and name.endswith('.ipk')):
            continue
        _, variant = package_key(name, package)
        healthy = (type(asset.get('size')) is int and asset['size'] > 0
                   and asset.get('state') == 'uploaded' and isinstance(asset.get('digest'), str)
                   and re.fullmatch(r'sha256:[0-9a-f]{64}', asset['digest']))
        if (name in result or type(asset.get('id')) is not int or asset['id'] <= 0
                or sum(a.get('id') == asset['id'] for a in assets if isinstance(a, dict)) != 1
                or variant not in expected_variants(package) or not (healthy or starter(asset))):
            raise PublicationError(f'Invalid or duplicate asset: {name}')
        result[name] = asset
    return result


def publish(api, directory, version, package='beszel-agent', keep_old=False):
    expected = expected_variants(package)
    files = sorted(Path(directory).rglob(package + '_*.ipk'))
    desired, architectures, keys = {}, set(), set()
    for file in files:
        key, arch = package_key(file.name, package)
        if '.'.join(map(str, key[:3])) != version or arch not in expected or arch in architectures:
            raise PublicationError('Unexpected version, architecture or duplicate local package')
        if file.is_symlink() or not file.is_file() or file.stat().st_size <= 0:
            raise PublicationError('Empty/unsafe local package')
        architectures.add(arch)
        keys.add(key)
        desired[file.name] = {'size': file.stat().st_size,
                              'digest': 'sha256:' + hashlib.sha256(file.read_bytes()).hexdigest()}
    if architectures != expected or len(keys) != 1:
        raise PublicationError('Incomplete or inconsistent package set')
    candidate = next(iter(keys))
    baseline = api.release()
    old = scoped(baseline, package)
    if any(package_key(name, package)[0] > candidate for name in old):
        raise PublicationError('Refusing publication over a newer package set')
    for name in desired.keys() & old.keys():
        if not starter(old[name]) and any(old[name][field] != desired[name][field] for field in ('size', 'digest')):
            raise PublicationError('Existing candidate differs; refusing overwrite')
    # Optimistic admission supplements Actions' shared publication lock.
    check = api.release()
    if check['id'] != baseline['id'] or scoped(check, package) != old:
        raise PublicationError('Concurrent package publication before upload')
    for name in desired.keys() & old.keys():
        if starter(old[name]):
            # Exact local candidate only. Re-read the release and the object before DELETE.
            live = api.release()
            if (live['id'] != baseline['id'] or scoped(live, package) != old
                    or api.asset(old[name]['id']) != old[name]):
                raise PublicationError('Concurrent starter recovery')
            api.delete(old[name]['id'])
            del old[name]
    check = api.release()
    if check['id'] != baseline['id'] or scoped(check, package) != old:
        raise PublicationError('Concurrent package publication after recovery')
    for file in files:
        if file.name not in old:
            api.upload(file)
    current = api.release()
    actual = scoped(current, package)
    if current['id'] != baseline['id']:
        raise PublicationError('Target release changed')
    for name, wanted in desired.items():
        if name not in actual or any(actual[name][field] != wanted[field] for field in ('size', 'digest')):
            raise PublicationError('Uploaded set not verified; preserving old packages')
    if {n: a for n, a in actual.items() if n not in desired} != {n: a for n, a in old.items() if n not in desired}:
        raise PublicationError('Concurrent publication; refusing pruning')
    if keep_old:
        # The workflow notifies its existing aggregator before cleanup. A failed
        # notification leaves overlap as the durable signal for a cleanup retry.
        return
    prune_verified(api, baseline['id'], old, actual, desired, package)


def prune_verified(api, release_id, old, actual, desired, package):
    for name, asset in old.items():
        if name not in desired:
            # Recheck the complete desired set and exact old identity before each deletion.
            live = api.release()
            live_assets = scoped(live, package)
            if live['id'] != release_id or live_assets != actual:
                raise PublicationError('Concurrent publication during pruning')
            if starter(asset) and api.asset(asset['id']) != asset:
                raise PublicationError('Concurrent starter change during pruning')
            api.delete(asset['id'])
            del actual[name]
    final = api.release()
    if final['id'] != release_id or scoped(final, package) != actual:
        raise PublicationError('Final publication verification failed')


def complete_candidate(release, version, package):
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version):
        raise PublicationError('Invalid stable upstream version')
    target = tuple(map(int, version.split('.')))
    groups = {}
    for name, asset in scoped(release, package).items():
        key, variant = package_key(name, package)
        if key[:3] > target:
            raise PublicationError('Refusing to prune a newer upstream version')
        if key[:3] == target:
            groups.setdefault(key, {})[name] = asset
    # Never prune a partially published newer package release in favour of an older one.
    if not groups:
        return {}
    candidate = groups[max(groups)]
    variants = {package_key(name, package)[1] for name in candidate}
    return candidate if variants == expected_variants(package) and not any(starter(a) for a in candidate.values()) else {}


def prune_complete(api, version, package='mihomo'):
    baseline = api.release()
    desired = complete_candidate(baseline, version, package)
    if not desired:
        raise PublicationError('No complete verified candidate for cleanup-only retry')
    old = scoped(baseline, package)
    prune_verified(api, baseline['id'], old, old.copy(), desired, package)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('version')
    parser.add_argument('--package', choices=('beszel-agent', 'mihomo'), default='beszel-agent')
    parser.add_argument('--prune-only', action='store_true')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--keep-old', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    try:
        if args.plan:
            release = GitHub().release()
            candidate = complete_candidate(release, args.version, args.package)
            complete = bool(candidate)
            cleanup = complete and bool(scoped(release, args.package).keys() - candidate.keys())
            with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                output.write('update=' + ('false' if complete else 'true') + '\n')
                output.write('prune=' + ('true' if cleanup else 'false') + '\n')
        elif args.verify_only:
            if not complete_candidate(GitHub().release(), args.version, args.package):
                raise PublicationError('No complete verified candidate')
        elif args.prune_only:
            prune_complete(GitHub(), args.version, args.package)
        else:
            publish(GitHub(), args.directory, args.version, args.package, args.keep_old)
    except (PublicationError, OSError, KeyError) as error:
        parser.exit(2, f'Publication stopped: {error}\n')
