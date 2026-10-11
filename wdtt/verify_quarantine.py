#!/usr/bin/env python3
"""Real ELF/IPK format probes, private local storage; never opkg install/upload."""
import argparse, gzip, hashlib, io, json, os, pathlib, shutil, subprocess, sys, tarfile, tempfile, zlib
from ipk_recipe import ARCH, package, validate_elf

def members(data):
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:
        files=tar.getmembers()
        assert len(files)==3 and all(m.isfile() for m in files)
        out={m.name.removeprefix('./'):tar.extractfile(m).read() for m in files}
    assert set(out)=={'debian-binary','control.tar.gz','data.tar.gz'}
    assert out['debian-binary']==b'2.0\n';return out

def preserve_owner_local(private, requested, records, kind="quarantine"):
    """Retain verified install-blocked IPKs *only* in an explicit private local directory.

    This is not a public artifact/release path and does not produce install-ready packages.
    """
    if os.name!="posix":raise ValueError("Private retention requires POSIX permissions, e.g. owner WSL ext4")
    assert kind in ("quarantine","owner-test")
    dest=pathlib.Path(requested).expanduser()
    if not dest.is_absolute() or dest.exists() or not dest.parent.is_dir():
        raise ValueError('Retention needs a new absolute local directory (parent must exist)')
    if not dest.name.startswith('wdtt-private-') or any(x in ('outputs','artifacts','.git') for x in dest.parts):
        raise ValueError('Use a separate wdtt-private-* directory outside outputs/repository artifacts')
    if any(part.is_symlink() for part in [dest,*dest.parents]):
        raise ValueError('Symlink in retention destination')
    if pathlib.Path.cwd().resolve() in dest.parents:
        raise ValueError('Do not keep binary IPKs within the Git checkout')
    dest.mkdir(mode=0o700)
    dest.chmod(0o700)
    if dest.stat().st_mode & 0o777 != 0o700 or dest.stat().st_uid!=os.geteuid():
        raise ValueError("Private directory permissions not enforced; use WSL ext4, not /mnt/c")
    manifest=[]
    for r in records:
        src=private/('wt-client-'+kind+'_'+r['entware_arch']+'.ipk')
        target=dest/src.name
        if target.exists():
            raise FileExistsError(target)
        shutil.copyfile(src,target)
        target.chmod(0o600)
        assert target.stat().st_mode & 0o777 == 0o600
        digest=hashlib.sha256(target.read_bytes()).hexdigest()
        assert digest==r['ipk_sha256'],'retained file checksum mismatch'
        manifest.append({'file':target.name,'sha256':digest,'status':'QUARANTINED_PREINST_BLOCKS_INSTALL' if kind=='quarantine' else 'OWNER_LOCAL_INSTALL_CANDIDATE','install_ready':False,'owner_install_candidate':kind=='owner-test'})
    manifest_file=dest/('PRIVATE-QUARANTINE-MANIFEST.json' if kind=='quarantine' else 'PRIVATE-OWNER-TEST-MANIFEST.json')
    with manifest_file.open('x') as h:
        json.dump(manifest,h,indent=2)
        h.write('\n')
    manifest_file.chmod(0o600)
    print('PRESERVED PRIVATE '+kind+':',dest)
    return len(manifest)

def verify(build,output,retain_private_dir=None):
    build=pathlib.Path(build).resolve();report=json.loads((build/'build-report.json').read_text());records=[]
    notices=build/'license-evidence/NOTICE-COLLECTION.txt'
    with tempfile.TemporaryDirectory(prefix='wdtt-quarantine-') as tmp:
        private=pathlib.Path(tmp);private.chmod(0o700)
        for arch in ['arm64','mipsle']:
            elf=(build/('wt-client-linux-'+arch)).read_bytes();validate_elf(elf,arch)
            dest=private/('wt-client-quarantine_'+ARCH[arch]+'.ipk')
            cmd=[sys.executable,str(pathlib.Path(__file__).with_name('ipk_recipe.py')),str(build/'build-report.json'),str(build/('wt-client-linux-'+arch)),str(notices),str(dest),'--arch',arch]
            blocked=subprocess.run(cmd,capture_output=True)
            assert blocked.returncode!=0 and not dest.exists()
            subprocess.run(cmd+['--private-quarantine'],check=True)
            data=dest.read_bytes();ars=members(data)
            with tarfile.open(fileobj=io.BytesIO(gzip.decompress(ars['control.tar.gz']))) as tar:
                assert set(tar.getnames())=={'./control','./preinst'}
                control=tar.extractfile('./control').read();preinst=tar.extractfile('./preinst').read()
                assert b'Package: wt-client-quarantine\n' in control and ('Architecture: '+ARCH[arch]).encode() in control
                assert ('Installed-Size: '+str(len(gzip.decompress(ars['data.tar.gz'])))+'\n').encode() in control
                assert tar.getmember('./preinst').mode==0o755
                for shell in [['sh'],['busybox','ash']]:
                    p=subprocess.run(shell,input=preinst,capture_output=True)
                    assert p.returncode==78 and b'INSTALL_BLOCKED' in p.stderr
            with tarfile.open(fileobj=io.BytesIO(gzip.decompress(ars['data.tar.gz']))) as tar:
                all_members=tar.getmembers();assert all(m.isdir() or m.isfile() for m in all_members)
                assert all(m.uid==0 and m.gid==0 and (not m.isdir() or m.mode==0o755) for m in all_members)
                files=[m for m in all_members if m.isfile()];assert len(files)==3
                assert all(m.isfile() and m.uid==0 and m.gid==0 and '..' not in pathlib.PurePosixPath(m.name).parts and m.name.startswith('./opt/libexec/wdtt-lab/') for m in files)
                binary=next(m for m in files if m.name.endswith('/wt-client'));assert binary.mode==0o755
                assert tar.extractfile(binary).read()==elf
                prov=json.loads(tar.extractfile(next(m for m in files if m.name.endswith('/provenance.json'))).read())
                assert prov['quarantine'] is True and prov['install_ready'] is False
                assert data==package(elf,arch,report['source'],notices.read_bytes(),prov,True)
            records.append({'arch':arch,'entware_arch':ARCH[arch],'binary_sha256':hashlib.sha256(elf).hexdigest(),'ipk_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'format':'Entware outer tar.gz','installed_size_bytes_verified':True,'reproducible_same_host':True,'preinst_blocks_dash_and_busybox':True,'opkg_install_tested':False,'hardware_tested':False})
        # Preserve an owner-requested copy before temporary verification cleanup.
        # No CI upload, feed publication or installation is enabled by this option.
        saved=preserve_owner_local(private,retain_private_dir,records) if retain_private_dir else 0
    result={'quarantine_ipks_built':True,'ipks_retained':bool(saved),'install_ready':False,'redistribution_approved':False,'public_binary_upload':False,'compression_runtime':{'python':sys.version.split()[0],'zlib':zlib.ZLIB_RUNTIME_VERSION,'level':9,'mtime':0,'gzip_os':255},'packages':records}
    pathlib.Path(output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--build',required=True);p.add_argument('--report',required=True);p.add_argument('--retain-private-dir',help='new absolute local wdtt-private-* directory outside Git checkout; packages still refuse installation');a=p.parse_args();verify(a.build,a.report,a.retain_private_dir)
