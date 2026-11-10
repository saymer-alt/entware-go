#!/usr/bin/env python3
"""Owner-local install candidate. Public release gates remain unchanged/closed."""
import argparse,hashlib,json,pathlib,subprocess,tempfile
from ipk_recipe import ARCH,package,package_provenance,validate_elf
from verify_quarantine import preserve_owner_local
from build_lab import SOURCE,SDK_SHA,HERE,FORK,SOURCE_REVISION

def sha(data):return hashlib.sha256(data).hexdigest()
def make_owner_packages(report,binary_dir,kas,output_dir,acceptance_report=None):
 report=pathlib.Path(report);binary_dir=pathlib.Path(binary_dir);kas=pathlib.Path(kas)
 r=json.loads(report.read_text());assert r['source']==SOURCE and r['sdk_sha256']==SDK_SHA
 assert r['fork_source']==SOURCE_REVISION and r['source_repository']==FORK['repository'] and r['fork_tree_verified'] is True
 assert r['fork_source_lock_sha256']==sha((HERE/'fork-source-lock.json').read_bytes().replace(b'\r\n',b'\n'))
 assert r['go_sum_sha256']==json.loads((HERE/'source-lock.json').read_text())['go.sum']
 assert r['toolchain']=='go version go1.26.1 linux/amd64'
 assert r['patch_sha256']==sha((HERE/'patches/010-laboratory-security.patch').read_bytes())
 assert all(r['overlay'][name]==sha((HERE/'lab'/name).read_bytes()) for name in r['overlay'])
 notices=(binary_dir/'license-evidence/NOTICE-COLLECTION.txt').read_bytes();assert sha(notices)==r['notice_collection_sha256']
 commit=subprocess.check_output(['git','-C',str(kas),'rev-parse','HEAD'],text=True).strip()
 scripts={name:subprocess.check_output(['git','-C',str(kas),'show','HEAD:experimental/wdtt/'+name]) for name in ['service.sh','init.d','install.sh']}
 assert b'--install-owner-test' in scripts['install.sh'],'use Phase4 KAS owner-test commit'
 records=[]; retained={}
 with tempfile.TemporaryDirectory(prefix='wdtt-owner-package-') as tmp:
  private=pathlib.Path(tmp);private.chmod(0o700)
  for arch in ['arm64','mipsle']:
   rec=next(x for x in r['builds'] if x['arch']==arch);binary=(binary_dir/('wt-client-linux-'+arch)).read_bytes()
   assert sha(binary)==rec['sha256'];validate_elf(binary,arch)
   assert 'CGO_ENABLED=0' in rec['go_metadata'] and 'GOARCH='+arch in rec['go_metadata']
   if arch=='mipsle':assert 'GOMIPS=softfloat' in rec['go_metadata']
   p=package_provenance(r,rec,False)
   # Neither legal approval nor public install/release readiness is asserted.
   p.update(install_ready=False,quarantine=False,owner_local=True,owner_install_candidate=True,public_distribution_approved=False,kas_commit=commit,lifecycle_sha256={n:sha(v) for n,v in scripts.items()},recipe_sha256={n:sha((HERE/n).read_bytes().replace(b"\r\n",b"\n")) for n in ["owner_local_ipk.py","ipk_recipe.py","verify_quarantine.py","source-lock.json","fork-source-lock.json"]})
   data=package(binary,arch,r['source'],notices,p,owner_test=True,extra_files=scripts)
   file=private/('wt-client-owner-test_'+ARCH[arch]+'.ipk');file.write_bytes(data);file.chmod(0o600)
   retained['wt-client-linux-'+arch]=(binary,0o700)
   retained['provenance-'+arch+'.json']=((json.dumps(p,indent=2,sort_keys=True)+'\n').encode(),0o600)
   records.append({'payload':'/opt/lib/wdtt-owner-test/0.0.0+git'+r['source'][:12]+'.'+rec['sha256'][:12]+'.'+r['fork_source'][:12]+'.'+commit[:12],'arch':arch,'entware_arch':ARCH[arch],'ipk_sha256':sha(data),'binary_sha256':sha(binary),'bytes':len(data),'kas_commit':commit})
  preserve_owner_local(private,str(output_dir),records,kind='owner-test')
 dest=pathlib.Path(output_dir)
 for name,data in [('build-report.json',report.read_bytes()),('NOTICE-COLLECTION.txt',notices),('dependency-source-audit.json',(binary_dir/'license-evidence/dependency-source-audit.json').read_bytes()),('OWNER-TEST-BUILD.json',(json.dumps({'public_distribution_approved':False,'install_ready':False,'owner_install_candidate':True,'packages':records},indent=2)+'\n').encode())]:
  p=dest/name
  with p.open('xb') as f:f.write(data)
  p.chmod(0o600)
 for name,(data,mode) in retained.items():
  file=dest/name
  with file.open('xb') as f:f.write(data)
  file.chmod(mode)
 if acceptance_report:
  acceptance=pathlib.Path(acceptance_report);accepted=json.loads(acceptance.read_text())
  assert accepted['passed'] is True
  for record in records:
   check=next(x for x in accepted['packages'] if x['arch']==record['arch'])
   assert check['ipk_sha256']==record['ipk_sha256'] and check['real_opkg_install_remove'] is True
  with (dest/'owner-opkg-report.json').open('xb') as f:f.write(acceptance.read_bytes())
  (dest/'owner-opkg-report.json').chmod(0o600)
 manifest=[]
 for file in sorted(dest.iterdir()):
  manifest.append(sha(file.read_bytes())+'  '+file.name)
 with (dest/'SHA256SUMS').open('x') as f:f.write('\n'.join(manifest)+'\n')
 (dest/'SHA256SUMS').chmod(0o600)
 return records
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report',required=True);p.add_argument('--binary-dir',required=True);p.add_argument('--kas',required=True);p.add_argument('--retain-private-dir',required=True);p.add_argument('--acceptance-report');a=p.parse_args()
 print(json.dumps(make_owner_packages(a.report,a.binary_dir,a.kas,a.retain_private_dir,a.acceptance_report),indent=2))
