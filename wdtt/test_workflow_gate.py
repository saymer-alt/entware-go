#!/usr/bin/env python3
"""Publication policy regression: exactly one evidence-only upload, no feed writer.

This is a source contract; final CI artifact listing is independently inspected.
"""
import pathlib,re
p=pathlib.Path(__file__).resolve().parents[1]/'.github/workflows/build-wdtt-lab.yml'
text=p.read_text()
assert 'contents: read' in text and 'contents: write' not in text
assert not any(s in text for s in ['AGGREGATOR_PAT','publish_ipks','gh release','owner-download','owner-test-ipks/'])
steps=re.split(r'^      - ',text,flags=re.M)
uploads=[s for s in steps if 'uses: actions/upload-artifact@' in s]
assert len(uploads)==1,'new binary uploads need licensing/distribution review'
match=re.search(r'^          path: \|\n((?:            [^\n]+\n)+)',uploads[0],re.M)
assert match
paths={line.strip() for line in match[1].splitlines()}
assert paths=={
 'wdtt-build/owner-opkg-report.json','wdtt-build/production-guard-report.json',
 'wdtt-build/build-report.json','wdtt-build/local-pair-report.json','wdtt-build/server-auth-baseline.txt',
 'wdtt-build/quarantine-ipk-report.json','wdtt-build/license-evidence/dependency-source-audit.json',
 'wdtt-build/license-evidence/NOTICE-COLLECTION.txt','wdtt-build/test-deps/mihomo-test-digest.json'}
print('PASS: single exact evidence-only upload, no release/feed/legacy binary publisher')
