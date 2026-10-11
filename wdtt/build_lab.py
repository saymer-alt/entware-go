#!/usr/bin/env python3
"""Build-only laboratory recipe; no feed, webhook, release, or binary uploads."""
import argparse, hashlib, io, json, os, pathlib, shutil, struct, subprocess, tarfile

HERE=pathlib.Path(__file__).resolve().parent
SOURCE='1110a75f76e42c23149b8e24f9182c1ff179e515'
SDK_SHA='d51f30c126425ebff203b107a1a0aa9d3a5844f6c481bc6ff4c117cadc208674'

def run(args,**kwargs):
    return subprocess.check_output([str(x) for x in args],text=True,**kwargs).strip()
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--go',required=True);p.add_argument('--sdk-archive',required=True);p.add_argument('--work',required=True);p.add_argument('--source');p.add_argument('--cache');p.add_argument('--modules');a=p.parse_args()
    assert sha(a.sdk_archive)==SDK_SHA,'SDK digest mismatch'
    go=pathlib.Path(a.go).resolve();work=pathlib.Path(a.work).resolve();work.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env.update(GOTOOLCHAIN='local',GOENV='off',GOWORK='off',GOTELEMETRY='off',CGO_ENABLED='0',GOOS='linux',GOARCH='amd64',GOPATH=str(work/'gopath'),GOCACHE=str(work/'gocache'),GOSUMDB='sum.golang.org',GOPROXY='https://proxy.golang.org')
    env.pop('GOROOT',None)
    if a.cache:env['GOCACHE']=str(pathlib.Path(a.cache).resolve())
    if a.modules:env['GOPATH']=str(pathlib.Path(a.modules).resolve())
    version=run([go,'version'],env=env);assert version=='go version go1.26.1 linux/amd64',version
    src=work/'source'
    assert not src.exists(),'Use a fresh work directory; never overwrite an existing checkout'
    if a.source:
        origin=pathlib.Path(a.source).resolve()
        assert run(['git','-C',origin,'rev-parse','HEAD'])==SOURCE
        assert not run(['git','-C',origin,'status','--porcelain'])
        raw=subprocess.check_output(['git','-C',str(origin),'archive','--format=tar','HEAD'])
        src.mkdir()
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:archive.extractall(src,filter='data')
    else:
        run(['git','init',src]);run(['git','-C',src,'remote','add','origin','https://github.com/hoaxisr/proxy-turn-vk-android.git'])
        run(['git','-C',src,'fetch','--depth=1','origin',SOURCE]);run(['git','-C',src,'checkout','--detach','FETCH_HEAD'])
        assert run(['git','-C',src,'rev-parse','HEAD'])==SOURCE
    module=src/'go_client'
    locked=json.loads((HERE/'source-lock.json').read_text())
    for name in ['go.mod','go.sum']:assert sha(module/name)==locked[name],name+' changed'
    patch=HERE/'patches/010-laboratory-security.patch'
    run(['git','apply','--check',patch],cwd=src);run(['git','apply',patch],cwd=src)
    for source,dst in [('security.go','lab_security.go'),('security_test.go','lab_security_test.go')]:shutil.copy(HERE/'lab'/source,module/dst)
    # All auxiliary profile writes are contained by a private, ephemeral CWD.
    tests=run([go,'test','-mod=readonly','-count=1','-run','^Test(AllDiagnosticSinks|PrivateFilesAtomicAndSymlink|EndpointExclusive|GETCONFAndAUTHWireFixture)$','.'],cwd=module,env=env)
    server=work/'server-fixture';server.mkdir()
    shutil.copy(src/'server.go',server/'server.go')
    # Harness intentionally uses the pinned CLIENT module graph (includes TURN
    # and netstack), not a claim about the production server's module lock.
    for name in ['go.mod','go.sum']:shutil.copy(module/name,server/name)
    shutil.copy(HERE/'lab/server_auth_test.go',server/'server_auth_test.go')
    baseline=subprocess.run([go,'test','-mod=readonly','-count=1','-run','^Test(RejectWrongAUTH|AcceptKnownAUTH|RejectUnknownDevice|RejectNoAUTH)$','.'],cwd=server,env=env,capture_output=True,text=True)
    assert baseline.returncode!=0 and baseline.stdout.count('AUTH boundary forwarding=true want=false')==3, 'unexpected baseline auth result'
    (work/'server-auth-baseline.txt').write_text(baseline.stdout)
    server_patch=HERE/'patches/020-server-auth-lab.patch'
    run(['git','apply',server_patch],cwd=server)
    auth_tests=run([go,'test','-mod=readonly','-count=1','-run','^Test(RejectWrongAUTH|AcceptKnownAUTH|RejectUnknownDevice|RejectNoAUTH)$','.'],cwd=server,env=env)
    shutil.copy(HERE/'lab/server_pair_fixture_test.go',server/'server_pair_fixture_test.go')
    run([go,'test','-mod=readonly','-c','-o',work/'server-pair.test','.'],cwd=server,env=env)
    records=[]
    for arch,machine,endian,runner in [('amd64',62,1,[]),('arm64',183,1,['qemu-aarch64']),('mipsle',8,1,['qemu-mipsel']),('mips',8,2,['qemu-mips'])]:
        env.update(GOARCH=arch,GOMIPS='softfloat')
        out=work/('wt-client-linux-'+arch)
        args=[go,'build','-mod=readonly','-trimpath','-buildvcs=false','-ldflags=-s -w -buildid=','-o',out,'.']
        run(args,cwd=module,env=env)
        b=out.read_bytes();assert b[:4]==b'\x7fELF' and b[5]==endian
        byteorder='<' if endian==1 else '>'
        assert struct.unpack_from(byteorder+'H',b,18)[0]==machine
        # No dynamic loader; parse every program header, rather than grep text.
        if b[4]==2:offset=struct.unpack_from(byteorder+'Q',b,32)[0];size,count=struct.unpack_from(byteorder+'HH',b,54)
        else:offset=struct.unpack_from(byteorder+'I',b,28)[0];size,count=struct.unpack_from(byteorder+'HH',b,42)
        assert all(struct.unpack_from(byteorder+'I',b,offset+i*size)[0]!=3 for i in range(count)),'PT_INTERP'
        metadata=run([go,'version','-m',out],env=env)
        if arch.startswith('mips'):assert 'GOMIPS=softfloat' in metadata
        helpout=run([*runner,out,'-h'],env=env);assert 'no AWG daemon' in helpout
        records.append(dict(arch=arch,bytes=len(b),sha256=sha(out),machine=machine,endian=endian,pt_interp=False,go_metadata=metadata,cli_startup='native' if not runner else 'QEMU ONLY'))
    report=dict(source=SOURCE,toolchain=version,sdk_sha256=SDK_SHA,patch_sha256=sha(patch),server_auth_patch_sha256=sha(server_patch),server_auth_tests=auth_tests,overlay={n:sha(HERE/'lab'/n) for n in ['security.go','security_test.go','server_auth_test.go','server_pair_fixture_test.go']},go_sum_sha256=sha(module/'go.sum'),tests=tests,builds=records,server_pair='same upstream SHA; GETCONF/AUTH fixture; local TURN/DTLS/WG harness compiled separately, consult local-pair report; full VK acceptance NOT RUN',license_gate='BLOCKED: fhttp notice/scope audit incomplete',install_ready=False,ipk_created=False,production_mutation=False)
    (work/'build-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
