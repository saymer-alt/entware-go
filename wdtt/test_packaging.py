import gzip,io,tarfile
from ipk_recipe import package
data=package(b'SYNTHETIC-NOT-AN-ELF','arm64','1'*40,b'SYNTHETIC NOTICE',{'fixture':True})
assert data==package(b'SYNTHETIC-NOT-AN-ELF','arm64','1'*40,b'SYNTHETIC NOTICE',{'fixture':True})
with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as outer:
    assert len(outer.getmembers())==3
    members={m.name.removeprefix('./'):outer.extractfile(m).read() for m in outer}
assert data[9]==255 and all(members[n][9]==255 for n in ['control.tar.gz','data.tar.gz'])
assert set(members)=={'debian-binary','control.tar.gz','data.tar.gz'}
with tarfile.open(fileobj=io.BytesIO(gzip.decompress(members['data.tar.gz']))) as t:
    payload=[x for x in t if x.isfile()];assert len(payload)==3 and all(x.name.startswith('./opt/libexec/wdtt-lab/') for x in payload)
    assert all(x.isdir() or x.isfile() for x in t)
    assert t.getmember('./opt/libexec/wdtt-lab').isdir()
    assert not any('init.d' in x.name for x in t)
print('PASS: deterministic Entware tar.gz IPK synthetic payload, versioned paths, no init scripts; no real IPK emitted')
with tarfile.open(fileobj=io.BytesIO(members['control.tar.gz']),mode='r:gz') as ctl:
    assert ('Installed-Size: '+str(len(gzip.decompress(members['data.tar.gz'])))+'\n').encode() in ctl.extractfile('./control').read()
