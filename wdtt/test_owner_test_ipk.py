#!/usr/bin/env python3
"""Regression: explicit owner-test wording must not bypass closed source gates."""
import json,pathlib,tempfile
from owner_test_ipk import make_lab_packages
with tempfile.TemporaryDirectory(prefix='wdtt-owner-gate-') as tmp:
    root=pathlib.Path(tmp);out=root/'out';out.mkdir();report=root/'report.json'
    for ready in [False,True]:
        report.write_text(json.dumps({'install_ready':ready,'license_gate':'APPROVED' if ready else 'BLOCKED'}))
        try:make_lab_packages(report,root,out)
        except ValueError as e:assert 'BLOCKED' in str(e)
        else:raise AssertionError('owner-test wrapper bypassed source gates')
        assert not list(out.iterdir())
print('PASS: owner-test wrapper fails closed even with forged ready report; no package writes')
