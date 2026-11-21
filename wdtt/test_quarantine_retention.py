#!/usr/bin/env python3
"""Private retention regression; tests metadata/permissions without real IPKs."""
import hashlib
import json
import tempfile
from pathlib import Path
from verify_quarantine import preserve_owner_local

with tempfile.TemporaryDirectory(prefix='wdtt-retention-test-') as tmp:
    root=Path(tmp)
    private=root/'private'
    private.mkdir(mode=0o700)
    test_data=[('arm64','aarch64-3.10'),('mipsle','mipsel-3.4')]
    records=[]
    for arch,entware_arch in test_data:
        data=('synthetic-private-quarantine-'+arch).encode()
        path=private/('wt-client-quarantine_'+entware_arch+'.ipk')
        path.write_bytes(data)
        records.append({'arch':arch,'entware_arch':entware_arch,
                        'ipk_sha256':hashlib.sha256(data).hexdigest()})
    dest=root/'wdtt-private-retained'
    assert preserve_owner_local(private,str(dest),records)==2
    assert dest.is_dir() and dest.stat().st_mode & 0o777 == 0o700
    manifest=json.loads((dest/'PRIVATE-QUARANTINE-MANIFEST.json').read_text())
    assert len(manifest)==2
    for r in manifest:
        path=dest/r['file']
        assert path.stat().st_mode & 0o777 == 0o600
        assert hashlib.sha256(path.read_bytes()).hexdigest()==r['sha256']
        assert r['install_ready'] is False
    try:
        preserve_owner_local(private,str(dest),records)
    except ValueError:
        pass
    else:
        raise AssertionError('Must not overwrite existing retention target')
    outside=root/'outputs'
    outside.mkdir()
    try:
        preserve_owner_local(private,str(outside/'wdtt-private-bad'),records)
    except ValueError:
        pass
    else:
        raise AssertionError('Must refuse outputs location')
    link=root/'wdtt-private-link'
    link.symlink_to(dest)
    try:
        preserve_owner_local(private,str(link),records)
    except ValueError:
        pass
    else:
        raise AssertionError('Must refuse symlink destination')
print('PASS: explicit local-only retention, private 0700/0600, SHA, no overwrites or public outputs')
