#!/usr/bin/env python3
"""Private CI test dependency only; no repack/publication."""
import argparse,gzip,hashlib,json,pathlib,urllib.request
p=argparse.ArgumentParser();p.add_argument('directory');a=p.parse_args()
directory=pathlib.Path(a.directory);directory.mkdir(parents=True,exist_ok=True)
target=directory/'mihomo-compatible'
assert not target.exists()
digest='ba3ce607747a07f948fc35780e108a4a7c7f552a38b9bd4d115f313ebcb89c20'
url='https://github.com/MetaCubeX/mihomo/releases/download/v1.19.32/mihomo-linux-amd64-compatible-v1.19.32.gz'
raw=urllib.request.urlopen(url,timeout=60).read()
assert hashlib.sha256(raw).hexdigest()==digest
target.write_bytes(gzip.decompress(raw));target.chmod(0o700)
(directory/'mihomo-test-digest.json').write_text(json.dumps({'uncompressed_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'gzip_sha256':digest,'url':url})+'\n')
print('Verified private test Mihomo v1.19.32 compatible AMD64')
