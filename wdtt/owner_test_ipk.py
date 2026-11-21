#!/usr/bin/env python3
"""Legacy entry point: owner-test labels never waive licensing/install gates.

Private format testing is verify_quarantine.py. Future approved owner packages
delegate to the exact same validation/notice recipe as normal IPKs.
"""
import argparse, json, pathlib, subprocess, sys
from ipk_recipe import ARCH
HERE=pathlib.Path(__file__).resolve().parent

def make_lab_packages(report,binary_dir,output_dir):
    gates=json.loads((HERE/'release-gates.json').read_text())
    if not gates or any(v is not True for v in gates.values()):
        raise ValueError('WDTT_OWNER_TEST_IPK_BLOCKED: license/security/install gates; warning labels are not permission')
    data=json.loads(pathlib.Path(report).read_text())
    if data.get('install_ready') is not True or data.get('license_gate')!='APPROVED':
        raise ValueError('WDTT_OWNER_TEST_IPK_BLOCKED: approved provenance required')
    binary_dir=pathlib.Path(binary_dir);output_dir=pathlib.Path(output_dir)
    if not output_dir.is_dir() or list(output_dir.iterdir()):raise ValueError('empty output directory required')
    for arch in ['arm64','mipsle']:
        record=next(r for r in data['builds'] if r['arch']==arch)
        version='0.0.0+git'+data['source'][:12]+'.'+record['sha256'][:12]
        output=output_dir/f'wt-client-lab_{version}-1_{ARCH[arch]}.ipk'
        subprocess.run([sys.executable,str(HERE/'ipk_recipe.py'),str(report),str(binary_dir/('wt-client-linux-'+arch)),str(binary_dir/'license-evidence/NOTICE-COLLECTION.txt'),str(output),'--arch',arch],check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',required=True);p.add_argument('--binary-dir',required=True);p.add_argument('--output-dir',required=True);a=p.parse_args()
    make_lab_packages(a.report,a.binary_dir,a.output_dir)
