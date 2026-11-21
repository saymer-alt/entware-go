#!/usr/bin/env python3
"""Real pinned opkg/offline-root installation. No target ELF execution, no force flags."""
import argparse,gzip,hashlib,io,json,os,pathlib,subprocess,tarfile,tempfile
from ipk_recipe import tar_gz
from owner_local_ipk import make_owner_packages

def sha(data):return hashlib.sha256(data).hexdigest()
def checked_install(opkg,conf,root,path,wanted):
 if sha(path.read_bytes())!=wanted:raise ValueError('PACKAGE_SHA_REJECTED')
 return subprocess.run([str(opkg),'-f',str(conf),'-o',str(root),'install',str(path)],capture_output=True,text=True)
def main(opkg,build,kas,report):
 opkg=pathlib.Path(opkg).resolve();build=pathlib.Path(build).resolve();checks=[]
 with tempfile.TemporaryDirectory(prefix='wdtt-opkg-acceptance-') as temp:
  d=pathlib.Path(temp);d.chmod(0o700)
  saved=d/'wdtt-private-owner-candidates';records=make_owner_packages(build/'build-report.json',build,kas,saved)
  again=d/'wdtt-private-owner-repeat';second=make_owner_packages(build/'build-report.json',build,kas,again)
  assert [r['ipk_sha256'] for r in records]==[r['ipk_sha256'] for r in second]
  for rec in records:
   arch=rec['entware_arch'];root=d/arch;root.mkdir();(root/'tmp').mkdir();(root/'opt/tmp').mkdir(parents=True)
   config=root/'opkg.conf';config.write_text(f'dest root /\narch all 1\narch {arch} 10\noption tmp_dir {root}/tmp\n')
   ownroot=root/'opt/wdtt-experimental';ownroot.mkdir(parents=True)
   sentinel=ownroot/'config.json';sentinel.write_bytes(b'SYNTHETIC_PRIVATE_CONFIG_KEEP');sentinel.chmod(0o600)
   foreign=root/'opt/etc/mihomo-baseline';foreign.parent.mkdir(parents=True);foreign.write_bytes(b'KEEP')
   ca=d/'ca-bundle.ipk';ca.write_bytes(tar_gz({'./debian-binary':(b'2.0\n',0o644),'./control.tar.gz':(tar_gz({'./control':(b'Package: ca-bundle\nVersion: 1\nArchitecture: all\nDescription: fixture dependency only\n',0o644)}),0o644),'./data.tar.gz':(tar_gz({}),0o644)}))
   p=checked_install(opkg,config,root,ca,sha(ca.read_bytes()));assert p.returncode==0,p.stdout+p.stderr
   pkg=saved/('wt-client-owner-test_'+arch+'.ipk')
   with tarfile.open(pkg,'r:gz') as outer:
    parts={m.name:outer.extractfile(m).read() for m in outer}
   with tarfile.open(fileobj=io.BytesIO(parts['./control.tar.gz']),mode='r:gz') as ctl:
    assert set(ctl.getnames())=={'./control','./preinst'}
    preinst=ctl.extractfile('./preinst').read()
   def guard(ok):
    for shell in [['sh'],['busybox','ash']]:
     p=subprocess.run(shell,input=preinst,capture_output=True,env=dict(os.environ,IPKG_INSTROOT=str(root)))
     assert (p.returncode==0)==ok,(shell,p.stderr)
   # Offline opkg skips maintainer scripts; execute the exact read-only guard
   # explicitly under both shells, without --force-postinstall.
   guard(True)
   libexec=root/'opt/lib/wdtt-owner-test';outside=d/('foreign-'+arch);outside.mkdir();libexec.symlink_to(outside)
   guard(False);assert not list(outside.iterdir());libexec.unlink()
   target=root/rec['payload'].lstrip('/');target.mkdir(parents=True)
   fake=target/'wt-client';fake.write_bytes(b'FOREIGN_KEEP');guard(False)
   assert fake.read_bytes()==b'FOREIGN_KEEP';fake.unlink();target.rmdir()
   (root/'opt').chmod(0o711);(root/'opt/lib').chmod(0o711)
   p=checked_install(opkg,config,root,pkg,rec['ipk_sha256']);assert p.returncode==0,p.stdout+p.stderr
   payloads=list((root/'opt/lib/wdtt-owner-test').glob('*/wt-client'));assert len(payloads)==1,(p.stdout,p.stderr,[str(f.relative_to(root)) for f in root.rglob("*")])
   payload=payloads[0];assert sha(payload.read_bytes())==rec['binary_sha256']
   assert (root/'opt').stat().st_mode&0o777==0o711 and (root/'opt/lib').stat().st_mode&0o777==0o711
   guard(True)
   original=payload.stat().st_mtime_ns
   p=checked_install(opkg,config,root,pkg,rec['ipk_sha256']);assert p.returncode==0,p.stdout+p.stderr
   assert payload.stat().st_mtime_ns==original
   with tarfile.open(pkg,'r:gz') as outer:
    parts={m.name:outer.extractfile(m).read() for m in outer}
   with tarfile.open(fileobj=io.BytesIO(parts['./control.tar.gz']),mode='r:gz') as ctl:
    assert set(ctl.getnames())=={'./control','./preinst'},'no startup/postinst/removal scripts'
   # Wrong SHA must fail before opkg; matching-digest corrupt archive must fail opkg.
   try:checked_install(opkg,config,root,pkg,'0'*64)
   except ValueError:pass
   else:raise AssertionError('wrong SHA accepted')
   bad=d/('bad-'+arch+'.ipk');bad.write_bytes(b'CORRUPT'+pkg.read_bytes()[7:])
   p=checked_install(opkg,config,root,bad,sha(bad.read_bytes()));assert p.returncode!=0
   assert sha(payload.read_bytes())==rec['binary_sha256']
   # Actual opkg architecture refusal, without --force-architecture/depends.
   other=next(x for x in records if x['arch']!=rec['arch'])
   wrongroot=d/('wrong-arch-'+arch);(wrongroot/'opt/tmp').mkdir(parents=True);(wrongroot/'tmp').mkdir()
   wrongconf=wrongroot/'opkg.conf';wrongconf.write_text(f'dest root /\narch all 1\narch {arch} 10\noption tmp_dir {wrongroot}/tmp\n')
   p=checked_install(opkg,wrongconf,wrongroot,ca,sha(ca.read_bytes()));assert p.returncode==0
   p=checked_install(opkg,wrongconf,wrongroot,saved/('wt-client-owner-test_'+other['entware_arch']+'.ipk'),other['ipk_sha256'])
   assert p.returncode!=0 and not list(wrongroot.rglob('wt-client')),p.stdout+p.stderr
   # Test real opkg upgrade paths with the exact payload and a higher fixture revision.
   with tarfile.open(fileobj=io.BytesIO(parts['./control.tar.gz']),mode='r:gz') as ctl:
    ctl_files={m.name:(ctl.extractfile(m).read(),m.mode) for m in ctl};control=ctl_files['./control'][0]
   version=next(line for line in control.splitlines() if line.startswith(b'Version: '))
   ctl_files['./control']=(control.replace(version,version[:-1]+b'2'),0o644)
   parts['./control.tar.gz']=tar_gz(ctl_files)
   update=d/('update-'+arch+'.ipk');update.write_bytes(tar_gz({name:(value,0o644) for name,value in parts.items()}))
   p=checked_install(opkg,config,root,update,sha(update.read_bytes()));assert p.returncode==0,p.stdout+p.stderr
   assert sha(payload.read_bytes())==rec['binary_sha256'] and sentinel.read_bytes()==b'SYNTHETIC_PRIVATE_CONFIG_KEEP'
   p=subprocess.run([str(opkg),'-f',str(config),'-o',str(root),'remove','wt-client-owner-test'],capture_output=True,text=True)
   assert p.returncode==0 and not payload.exists(),p.stdout+p.stderr
   assert sentinel.read_bytes()==b'SYNTHETIC_PRIVATE_CONFIG_KEEP' and foreign.read_bytes()==b'KEEP'
   assert not (root/'opt/etc/init.d/S98wdtt-lab').exists()
   checks.append(dict(rec,real_opkg_install_remove=True,repeat_install_noop=True,upgrade=True,wrong_sha_rejected=True,corrupt_archive_rejected=True,wrong_architecture_rejected=True,secrets_and_foreign_files_preserved=True,auto_execution=False,read_only_preinst_dash_busybox=True,symlink_foreign_payload_rejected=True,shared_directory_mode_preserved=True,hardware=False))
 pins=json.loads((opkg.parents[2]/'fixture-provenance.json').read_text())
 result={'passed':True,'scope':'native Entware-patched opkg offline-root; target ELFs not executed; lifecycle native fixtures separate','public_distribution_approved':False,'hardware_acceptance':False,'opkg':pins,'packages':checks}
 pathlib.Path(report).write_text(json.dumps(result,indent=2)+'\n');print('PASS real opkg: both target packages install/repeat/upgrade/remove, corruption/SHA/arch rejection, read-only preinst separately tested, no autostart, secrets/foreign files preserved')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--opkg',required=True);p.add_argument('--build',required=True);p.add_argument('--kas',required=True);p.add_argument('--report',required=True);a=p.parse_args();main(a.opkg,a.build,a.kas,a.report)
