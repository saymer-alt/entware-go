#!/usr/bin/env python3
"""Deterministic, versioned IPK recipe. Admission is closed; no publishing code."""
import argparse,gzip,hashlib,io,json,pathlib,struct,sys,tarfile
HERE=pathlib.Path(__file__).parent
ARCH={'arm64':'aarch64-3.10','mipsle':'mipsel-3.4','mips':'mips-3.4'}
def tar_gz(files,include_dirs=False,directory_floor=None):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w',format=tarfile.USTAR_FORMAT) as tar:
        if include_dirs:
            directories=set()
            for name in files:
                parts=name.split('/')
                directories.update('/'.join(parts[:n]) for n in range(2,len(parts)))
            for name in sorted(directories):
                if directory_floor and not (name==directory_floor or name.startswith(directory_floor+'/')):continue
                info=tarfile.TarInfo(name+'/');info.type=tarfile.DIRTYPE;info.mode=0o755
                info.mtime=0;info.uid=info.gid=0;info.uname=info.gname='root';tar.addfile(info)
        for name,(data,mode) in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=mode;info.mtime=0;info.uid=info.gid=0;info.uname=info.gname='root'
            tar.addfile(info,io.BytesIO(data))
    compressed=bytearray(gzip.compress(out.getvalue(),compresslevel=9,mtime=0))
    # Python 3.11/3.12 delegate mtime=0 to zlib (OS=3); newer Python uses
    # OS=255. Canonicalize every gzip layer, independent of host OS header.
    compressed[9]=255
    return bytes(compressed)
def package(binary,arch,source,notices,provenance,quarantine=False,owner_test=False,extra_files=None):
    version='0.0.0+git'+source[:12]+'.'+hashlib.sha256(binary).hexdigest()[:12]
    if provenance.get('fork_source'):version+='.'+provenance['fork_source'][:12]
    assert not (quarantine and owner_test)
    name='wt-client-quarantine' if quarantine else ('wt-client-owner-test' if owner_test else 'wt-client-lab')
    if owner_test:version+='.'+provenance['kas_commit'][:12]
    root=(f'./opt/lib/wdtt-owner-test/{version}' if owner_test else f'./opt/libexec/wdtt-lab/{version}')
    data={root+'/wt-client':(binary,0o755),root+'/NOTICES':(notices,0o644),root+'/provenance.json':(json.dumps(provenance,sort_keys=True).encode(),0o644)}
    if extra_files:
        assert owner_test and set(extra_files)=={'service.sh','init.d','install.sh'}
        data.update({root+'/'+name:(value,0o755) for name,value in extra_files.items()})
    data_archive=tar_gz(data,include_dirs=True,directory_floor='./opt/lib/wdtt-owner-test' if owner_test else None)
    # Pinned Entware SDK ipkg-build: bytes of the uncompressed data tar.
    installed_size=len(gzip.decompress(data_archive))
    control=f'Package: {name}\nVersion: {version}-1\nArchitecture: {ARCH[arch]}\nMaintainer: saymer-alt\nSection: net\nPriority: optional\nDepends: ca-bundle\nInstalled-Size: {installed_size}\nDescription: Experimental standalone WDTT; manual start only\n'
    ctl={'./control':(control.encode(),0o644)}
    if owner_test:
        preinst='#!/bin/sh\nset -f\nexport LC_ALL=C\nfail() { printf \'%s\\n\' WDTT_OWNER_PAYLOAD_CONFLICT >&2; exit 78; }\nprefix=${IPKG_INSTROOT-}; prefix=${prefix%/}\nif [ -n "$prefix" ]; then\n    [ -d "$prefix" ] && [ ! -L "$prefix" ] && [ "$(cd -P "$prefix" && pwd)" = "$prefix" ] || fail\nfi\ncommand -v sha256sum >/dev/null 2>&1 || fail\nuid=$(id -u)\n'
        target=root.removeprefix('.')
        preinst+='dest="$prefix'+target+'"\n'
        preinst+='[ -d "$prefix/opt/lib" ] && [ ! -L "$prefix/opt/lib" ] || fail\n'
        preinst+='for parent in "$prefix/opt" "$prefix/opt/lib" "$prefix/opt/lib/wdtt-owner-test" "$dest"; do\n'
        preinst+='  if [ -e "$parent" ] || [ -L "$parent" ]; then\n'
        preinst+='    [ -d "$parent" ] && [ ! -L "$parent" ] || fail\n'
        preinst+="    ls -ldn \"$parent\" | awk -v uid=\"$uid\" '$3==uid && substr($1,6,1)!=\"w\" && substr($1,9,1)!=\"w\" {ok=1} END {exit !ok}' || fail\n"
        preinst+='  fi\ndone\n'
        for name,(value,mode) in sorted(data.items()):
            relative=name.removeprefix(root+'/')
            preinst+='file="$dest/'+relative+'"\n'
            preinst+='if [ -e "$file" ] || [ -L "$file" ]; then\n'
            preinst+='  [ -f "$file" ] && [ ! -L "$file" ] || fail\n'
            preinst+="  ls -ln \"$file\" | awk -v uid=\"$uid\" '$2==1 && $3==uid {ok=1} END {exit !ok}' || fail\n"
            preinst+='  [ "$(sha256sum "$file" | awk \'{print $1}\')" = "'+hashlib.sha256(value).hexdigest()+'" ] || fail\nfi\n'
        ctl['./preinst']=(preinst.encode(),0o755)
    if quarantine:
        ctl['./preinst']=(b'#!/bin/sh\nprintf "%s\\n" "WDTT_QUARANTINE_INSTALL_BLOCKED" >&2\nexit 78\n',0o755)
    return tar_gz({'./debian-binary':(b'2.0\n',0o644),'./control.tar.gz':(tar_gz(ctl),0o644),'./data.tar.gz':(data_archive,0o644)})

def validate_elf(binary,arch):
    expected={'arm64':(2,1,183),'mipsle':(1,1,8),'mips':(1,2,8)}[arch]
    assert len(binary)>64 and binary[:4]==b'\x7fELF'
    endian='<' if expected[1]==1 else '>'
    assert (binary[4],binary[5],struct.unpack_from(endian+'H',binary,18)[0])==expected
    if binary[4]==2: offset=struct.unpack_from(endian+'Q',binary,32)[0]; size,count=struct.unpack_from(endian+'HH',binary,54)
    else: offset=struct.unpack_from(endian+'I',binary,28)[0]; size,count=struct.unpack_from(endian+'HH',binary,42)
    assert count>0 and all(struct.unpack_from(endian+'I',binary,offset+i*size)[0]!=3 for i in range(count))

def package_provenance(report,record,quarantine):
    # Test elapsed time and host build paths are evidence, not package inputs.
    keys=['source','toolchain','sdk_sha256','patch_sha256','go_sum_sha256','overlay',
          'notice_collection_sha256','dependency_source_audit_sha256','license_gate']
    p={key:report[key] for key in keys}
    r=dict(record);r['go_metadata']='\n'.join(record['go_metadata'].splitlines()[1:])
    p.update(builds=[r],quarantine=quarantine,install_ready=not quarantine and report['install_ready'])
    if 'fork_source' in report:
        p.update({key:report[key] for key in ['fork_source','source_repository','fork_tree_verified','fork_source_lock_sha256']})
        p['source_url']=report['source_repository'].removesuffix('.git')+'/tree/'+report['fork_source']
        p['upstream_base']=report['source']
    else:p['source_url']='https://github.com/hoaxisr/proxy-turn-vk-android/tree/'+report['source']
    return p
def main():
    p=argparse.ArgumentParser();p.add_argument('report');p.add_argument('binary');p.add_argument('notices');p.add_argument('output');p.add_argument('--arch',choices=ARCH,required=True);p.add_argument('--private-quarantine',action='store_true');a=p.parse_args()
    gate=json.loads((HERE/'release-gates.json').read_text())
    failed=[k for k,v in gate.items() if v is not True]
    if failed and not a.private_quarantine:sys.exit('WDTT IPK withheld: '+', '.join(failed))
    if a.private_quarantine:
        dest=pathlib.Path(a.output).resolve()
        assert 'work' in dest.parts or (str(dest).startswith('/tmp/wdtt-')),'Quarantine requires private work directory, never outputs/release'
        assert 'outputs' not in dest.parts
        dest.parent.mkdir(parents=True,exist_ok=True);dest.parent.chmod(0o700)
    report=json.loads(pathlib.Path(a.report).read_text())
    binary=pathlib.Path(a.binary).read_bytes();record=next(r for r in report['builds'] if r['arch']==a.arch)
    assert hashlib.sha256(binary).hexdigest()==record['sha256']
    validate_elf(binary,a.arch)
    if a.arch.startswith('mips'):assert 'GOMIPS=softfloat' in record['go_metadata']
    assert report['source']=='1110a75f76e42c23149b8e24f9182c1ff179e515'
    if not a.private_quarantine:assert report['install_ready'] is True and report['license_gate']=='APPROVED'
    notices=pathlib.Path(a.notices).read_bytes();assert notices
    assert hashlib.sha256(notices).hexdigest()==report['notice_collection_sha256']
    provenance=package_provenance(report,record,a.private_quarantine)
    with pathlib.Path(a.output).open('xb') as f:
        f.write(package(binary,a.arch,report['source'],notices,provenance,a.private_quarantine))
    pathlib.Path(a.output).chmod(0o600)
if __name__=='__main__':main()
