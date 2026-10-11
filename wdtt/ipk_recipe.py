#!/usr/bin/env python3
"""Deterministic, versioned IPK recipe. Admission is closed; no publishing code."""
import argparse,gzip,hashlib,io,json,pathlib,sys,tarfile
HERE=pathlib.Path(__file__).parent
ARCH={'arm64':'aarch64-3.10','mipsle':'mipsel-3.4','mips':'mips-3.4'}
def tar_gz(files):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w',format=tarfile.USTAR_FORMAT) as tar:
        for name,(data,mode) in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=mode;info.mtime=0;info.uid=info.gid=0;info.uname=info.gname='root'
            tar.addfile(info,io.BytesIO(data))
    return gzip.compress(out.getvalue(),mtime=0)
def ar(files):
    out=b'!<arch>\n'
    for name,data in files:
        header=f'{name+"/":<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(data):<10}`\n'.encode('ascii')
        assert len(header)==60
        out+=header+data+(b'\n' if len(data)%2 else b'')
    return out
def package(binary,arch,source,notices,provenance):
    version='0.0.0+git'+source[:12]
    control=f'Package: wt-client-lab\nVersion: {version}-1\nArchitecture: {ARCH[arch]}\nMaintainer: saymer-alt\nSection: net\nPriority: optional\nDepends: ca-bundle\nInstalled-Size: {(len(binary)+1023)//1024}\nDescription: Experimental standalone WDTT; manual start only\n'
    root=f'./opt/libexec/wdtt-lab/{version}'
    data={root+'/wt-client':(binary,0o755),root+'/NOTICES':(notices,0o644),root+'/provenance.json':(json.dumps(provenance,sort_keys=True).encode(),0o644)}
    return ar([('debian-binary',b'2.0\n'),('control.tar.gz',tar_gz({'./control':(control.encode(),0o644)})),('data.tar.gz',tar_gz(data))])
def main():
    p=argparse.ArgumentParser();p.add_argument('report');p.add_argument('binary');p.add_argument('notices');p.add_argument('output');p.add_argument('--arch',choices=ARCH,required=True);a=p.parse_args()
    gate=json.loads((HERE/'release-gates.json').read_text())
    failed=[k for k,v in gate.items() if v is not True]
    if failed:sys.exit('WDTT IPK withheld: '+', '.join(failed))
    report=json.loads(pathlib.Path(a.report).read_text())
    binary=pathlib.Path(a.binary).read_bytes();record=next(r for r in report['builds'] if r['arch']==a.arch)
    assert hashlib.sha256(binary).hexdigest()==record['sha256']
    assert report['install_ready'] is True and report['license_gate']=='APPROVED'
    notices=pathlib.Path(a.notices).read_bytes();assert notices
    with pathlib.Path(a.output).open('xb') as f:f.write(package(binary,a.arch,report['source'],notices,report))
if __name__=='__main__':main()
