import gzip,io,tarfile
from ipk_recipe import package
data=package(b'SYNTHETIC-NOT-AN-ELF','arm64','1'*40,b'SYNTHETIC NOTICE',{'fixture':True})
assert data==package(b'SYNTHETIC-NOT-AN-ELF','arm64','1'*40,b'SYNTHETIC NOTICE',{'fixture':True})
assert data[:8]==b'!<arch>\n'
offset=8;members={}
while offset<len(data):
    header=data[offset:offset+60];offset+=60;size=int(header[48:58]);name=header[:16].decode().strip().rstrip('/')
    members[name]=data[offset:offset+size];offset+=size+size%2
assert set(members)=={'debian-binary','control.tar.gz','data.tar.gz'}
with tarfile.open(fileobj=io.BytesIO(gzip.decompress(members['data.tar.gz']))) as t:
    assert len(t.getmembers())==3 and all(x.name.startswith('./opt/libexec/wdtt-lab/') for x in t)
    assert not any('init.d' in x.name for x in t)
print('PASS: deterministic ar/IPK synthetic payload, versioned paths, no init scripts; no real IPK emitted')
