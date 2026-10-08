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


def package_key(name, package):
    match = re.fullmatch(re.escape(package) + r'_(\d+)\.(\d+)\.(\d+)-(\d+)_([a-z0-9]+-[0-9.]+)\.ipk', name)
    if not match:
        raise PublicationError(f'Invalid package filename: {name}')
    return tuple(int(match[i]) for i in range(1, 5)), match[5]


def scoped(release, package):
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
        package_key(name, package)
        if (name in result or type(asset.get('id')) is not int or type(asset.get('size')) is not int
                or asset['size'] <= 0 or asset.get('state') != 'uploaded'
                or not re.fullmatch(r'sha256:[0-9a-f]{64}', asset.get('digest', ''))):
            raise PublicationError(f'Invalid or duplicate asset: {name}')
        result[name] = asset
    return result


def publish(api, directory, version):
    package = 'beszel-agent'
    expected = {'aarch64-3.10', 'mips-3.4', 'mipsel-3.4'}
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
        if any(old[name][field] != desired[name][field] for field in ('size', 'digest')):
            raise PublicationError('Existing candidate differs; refusing overwrite')
    # Optimistic admission supplements Actions' shared publication lock.
    check = api.release()
    if check['id'] != baseline['id'] or scoped(check, package) != old:
        raise PublicationError('Concurrent package publication before upload')
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
    for name, asset in old.items():
        if name not in desired:
            # Recheck the complete desired set and exact old identity before each deletion.
            live = api.release()
            live_assets = scoped(live, package)
            if live['id'] != baseline['id'] or live_assets != actual:
                raise PublicationError('Concurrent publication during pruning')
            api.delete(asset['id'])
            del actual[name]
    final = api.release()
    if final['id'] != baseline['id'] or scoped(final, package) != actual:
        raise PublicationError('Final publication verification failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('version')
    args = parser.parse_args()
    try:
        publish(GitHub(), args.directory, args.version)
    except (PublicationError, OSError, KeyError) as error:
        parser.exit(2, f'Publication stopped: {error}\n')
