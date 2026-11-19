#!/usr/bin/env python3
"""Regression: KN-1913 dual-stack Mihomo :::7890 must pass TeleMT readiness.

Tests the actual grep -E pattern embedded in S99telemt-ipc-upx. No router,
Telegram credentials, WAN connectivity or root permissions are required.
"""
import re
import subprocess
from pathlib import Path

script = Path(__file__).with_name("S99telemt-ipc-upx").read_text()
idx = script.find("while ! netstat -lnt")
assert idx >= 0, "readiness loop missing"
match = re.search(r"grep -Eq\s*\\\s*\n\s*'([^']+)'", script[idx:])
assert match, "cannot extract actual listener grep regex"
pattern = match.group(1)

cases = {
    "IPv4 loopback": ("tcp 0 0 127.0.0.1:7890 0.0.0.0:* LISTEN\n", True),
    "IPv4 wildcard": ("tcp 0 0 0.0.0.0:7890 0.0.0.0:* LISTEN\n", True),
    "KN-1913 observed dual-stack": ("tcp 0 0 :::7890 :::* LISTEN\n", True),
    "netstat tcp6 variant": ("tcp6 0 0 :::7890 :::* LISTEN\n", True),
    "unrelated port": ("tcp 0 0 :::7891 :::* LISTEN\n", False),
    "port prefix": ("tcp 0 0 :::78900 :::* LISTEN\n", False),
    "port suffix": ("tcp 0 0 :::17890 :::* LISTEN\n", False),
    "IPv6 loopback only, not IPv4": ("tcp6 0 0 ::1:7890 :::* LISTEN\n", False),
    "not listening": ("", False),
    "mixed output": ("tcp 0 0 :::19091 :::* LISTEN\ntcp 0 0 :::7890 :::* LISTEN\n", True),
}
for label, (output, expected) in cases.items():
    p = subprocess.run(["grep", "-Eq", pattern], input=output, text=True, capture_output=True)
    assert p.returncode in (0, 1), f"{label}: grep error: {p.stderr}"
    actual = p.returncode == 0
    assert actual == expected, f"{label}: expected={expected} actual={actual}"
print("TELEMT_UPX_SOCKS5_NETSTAT_DUALSTACK_REGRESSION_PASS", len(cases))
