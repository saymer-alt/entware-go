#!/usr/bin/env python3
"""Read-only production source and shared-latest regression for WDTT CI."""
import argparse,hashlib,json,pathlib,subprocess
HERE=pathlib.Path(__file__).resolve().parent

def observe():
 pins=json.loads((HERE/'production-baseline.json').read_text())
 for name,expected in pins['sha256'].items():
  actual=(HERE.parent/name).read_bytes().replace(b'\r\n',b'\n')
  assert hashlib.sha256(actual).hexdigest()==expected,'PRODUCTION_SOURCE_CHANGED: '+name
 release=json.loads(subprocess.check_output(['gh','api','repos/saymer-alt/entware-go/releases/tags/latest'],text=True))
 keys=['id','name','size','digest','updated_at']
 return {'production_files':len(pins['sha256']),'baseline':pins['baseline'],'release_id':release['id'],'assets':sorted([{k:x.get(k) for k in keys} for x in release['assets']],key=lambda x:x['id'])}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--capture');p.add_argument('--verify');p.add_argument('--report');a=p.parse_args();now=observe()
 if a.capture:pathlib.Path(a.capture).write_text(json.dumps(now,indent=2)+'\n')
 else:
  before=json.loads(pathlib.Path(a.verify).read_text());assert before==now,'LATEST_CHANGED_DURING_TEST: investigate independent publisher; WDTT must not publish'
  pathlib.Path(a.report).write_text(json.dumps({'passed':True,'no_latest_asset_change':True,**now},indent=2)+'\n')
 print('PASS production boundary: unchanged protected source; read-only latest snapshot')
