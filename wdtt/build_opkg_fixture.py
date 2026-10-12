#!/usr/bin/env python3
"""Build pinned native Entware-patched opkg for offline-root tests only."""
import argparse,base64,hashlib,json,pathlib,subprocess
HERE=pathlib.Path(__file__).resolve().parent

def build(work):
 work=pathlib.Path(work).resolve();work.mkdir(parents=True,exist_ok=True)
 pins=json.loads((HERE/'opkg-fixture/pins.json').read_text());prefix=work/'prefix'
 def run(args,cwd=None):subprocess.run([str(x) for x in args],cwd=cwd,check=True)
 for name in ['libubox','opkg']:
  src=work/name
  if not src.exists():
   src.mkdir();run(['git','init','-q',src]);run(['git','-C',src,'fetch','--depth=1','https://github.com/openwrt/'+('opkg-lede' if name=='opkg' else name)+'.git',pins[name]]);run(['git','-C',src,'checkout','-q','--detach','FETCH_HEAD'])
  assert subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'],text=True).strip()==pins[name]
  if name=='opkg' and not (work/'patches-applied').exists():
   for patch,sha in sorted(pins['patch_sha256'].items()):
    raw=base64.b64decode(pins['patch_base64'][patch]);assert hashlib.sha256(raw).hexdigest()==sha
    patch_dir=work/'patch-inputs';patch_dir.mkdir(exist_ok=True)
    p=patch_dir/patch;p.write_bytes(raw)
    run(['git','apply',p],src)
   (work/'patches-applied').write_text(json.dumps(pins,sort_keys=True))
  options=['-DBUILD_TESTS=OFF','-DCMAKE_INSTALL_PREFIX='+str(prefix)]
  if name=='libubox':options+=['-DBUILD_LUA=OFF','-DBUILD_EXAMPLES=OFF']
  else:options+=['-DSTATIC_UBOX=ON','-DENABLE_USIGN=ON','-DLOCK_FILE=/opt/tmp/opkg.lock','-DCMAKE_PREFIX_PATH='+str(prefix),'-DCMAKE_C_FLAGS=-I'+str(prefix/'include'),'-DVERSION='+pins[name]]
  run(['cmake','-S',src,'-B',work/(name+'-build'),*options]);run(['cmake','--build',work/(name+'-build'),'-j','2'])
  if name=='libubox':run(['cmake','--install',work/(name+'-build')])
 binary=work/'opkg-build/src/opkg-cl';assert binary.is_file()
 (work/'fixture-provenance.json').write_text(json.dumps(dict(pins,binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),scope='native host/offline-root only, not router opkg acceptance'),indent=2)+'\n')
 print('FIXTURE_OPKG='+str(binary));return binary
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('work');build(p.parse_args().work)
