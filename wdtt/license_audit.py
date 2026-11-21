#!/usr/bin/env python3
"""Pinned, actually selected source inventory and notices; never grants rights."""
import argparse, hashlib, json, os, pathlib, subprocess

def digest(data): return hashlib.sha256(data).hexdigest()
def objects(text):
    decoder=json.JSONDecoder()
    while text.strip():
        obj,n=decoder.raw_decode(text.lstrip());text=text.lstrip()[n:];yield obj

def audit(go,module,out,env=None):
    go=pathlib.Path(go).resolve();module=pathlib.Path(module).resolve();out=pathlib.Path(out)
    out.mkdir(parents=True,exist_ok=True)
    env=dict(env or os.environ,GOENV='off',GOTOOLCHAIN='local',GOWORK='off',CGO_ENABLED='0',GOOS='linux')
    modules={}; sources={}; packages={}; scanned=set()
    for arch in ['arm64','mipsle']:
        env.update(GOARCH=arch,GOMIPS='softfloat')
        raw=subprocess.check_output([str(go),'list','-mod=readonly','-deps','-json','.'],cwd=module,env=env,text=True)
        for p in objects(raw):
            m=p.get('Module');mid=(m['Path']+'@'+m.get('Version','LOCAL')) if m else 'Go-stdlib'
            if mid not in modules:
                root=pathlib.Path(m['Dir']) if m else go.parent.parent
                if m and m.get('Main') and (root.parent/'LICENSE').is_file():root=root.parent
                modules[mid]={'root':root,'licenses':{},'packages':set(),'version':m.get('Version') if m else 'go1.26.1','sum':m.get('Sum') if m else None}
            rec=modules[mid];rec['packages'].add(p['ImportPath']);packages.setdefault(arch,[]).append(p['ImportPath'])
            directory=pathlib.Path(p['Dir'])
            for name in p.get('GoFiles',[])+p.get('SFiles',[])+p.get('EmbedFiles',[]):
                file=directory/name
                if not file.is_file():continue
                rel=file.relative_to(rec['root']).as_posix()
                if mid+'/'+rel in sources:continue
                data=file.read_bytes()
                sources[mid+'/'+rel]={'sha256':digest(data),'header':data[:1024].decode('utf-8',errors='replace').split('\n\n')[0][:600]}
            parent=directory
            while parent.is_relative_to(rec['root']):
                if (mid,parent) in scanned:break
                scanned.add((mid,parent))
                for file in parent.iterdir():
                    if file.is_file() and file.name.lower().startswith(('license','copying','notice','patents')):
                        rel=file.relative_to(rec['root']).as_posix();data=file.read_bytes()
                        rec['licenses'][rel]={'sha256':digest(data),'data':data}
                if parent==rec['root']:break
                parent=parent.parent
    notices=[];records=[]
    for mid,rec in sorted(modules.items()):
        notices.append('\n===== '+mid+' =====\n')
        files=[]
        for name,info in sorted(rec['licenses'].items()):
            notices.append('\n--- '+name+' SHA256 '+info['sha256']+' ---\n')
            notices.append(info['data'].decode('utf-8',errors='strict'))
            files.append({'path':name,'sha256':info['sha256']})
        if not files:notices.append('UNRESOLVED: no applicable license text found. This is NOT permission to redistribute.\n')
        records.append({'module':mid,'version':rec['version'],'sum':rec['sum'],'packages':sorted(rec['packages']),'license_files':files,'scope_review':'PENDING; collection is not approval'})
    notices.append('\n===== SELECTED SOURCE COPYRIGHT HEADERS =====\n')
    for path,rec in sorted(sources.items()):
        if 'copyright' in rec['header'].lower() or 'SPDX-License-Identifier' in rec['header']:
            notices.append('\n--- '+path+' ---\n'+rec['header']+'\n')
    report={'scope':'Go selected Go/S/embedded files for actual ARM64 and MIPSel CGO0 builds; tests excluded; compiler runtime notices included',
            'targets':['arm64','mipsle'],'modules':records,'sources':sources,'packages':packages,
            'missing_license_modules':[r['module'] for r in records if not r['license_files']],
            'redistribution_approved':False,'install_ready':False}
    (out/'NOTICE-COLLECTION.txt').write_text(''.join(notices),encoding='utf-8',newline='\n')
    (out/'dependency-source-audit.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--go',required=True);p.add_argument('--module',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    r=audit(a.go,a.module,a.output)
    print(json.dumps({'modules':len(r['modules']),'selected_files':len(r['sources']),'missing':r['missing_license_modules'],'redistribution_approved':False}))
