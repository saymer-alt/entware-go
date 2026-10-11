#!/usr/bin/env python3
"""Prepare installable *manual-only* WDTT laboratory IPKs. Never publish to feeds.

Deliberately separate from ipk_recipe.main() production admission:
- artifact is a file-only package without init scripts or postinst
- package is marked as experimental; no claim of runtime readiness
- this is not permission or a substitute for license compliance
"""
import argparse
import hashlib
import json
from pathlib import Path
from ipk_recipe import ARCH, package

HERE = Path(__file__).resolve().parent
TARGETS = ("arm64", "mipsle")

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def make_lab_packages(report, binary_dir, output_dir):
    report = Path(report)
    binary_dir = Path(binary_dir)
    output_dir = Path(output_dir)
    data = json.loads(report.read_text())
    if data.get("install_ready") is True or data.get("license_gate") == "APPROVED":
        raise ValueError("owner-test wrapper is only for a laboratory build report")
    source = data["source"]
    if not isinstance(source, str) or len(source) != 40 or not all(c in "0123456789abcdef" for c in source):
        raise ValueError("invalid pinned source SHA")
    records = {item["arch"]: item for item in data["builds"]}
    warning = (HERE / "EXPERIMENTAL-DOWNLOAD-WARNING.md").read_bytes()
    if not warning.startswith("# ⚠️⚠️⚠️".encode()):
        raise ValueError("prominent experiment warning missing")
    notices = b"\n\n".join((
        warning,
        b"--- UPSTREAM GPL NOTICE (separate component) ---\n" + (HERE / "licenses/UPSTREAM-GPL-3.0.txt").read_bytes(),
        b"--- AWGMPROTO MIT NOTICE (separate component) ---\n" + (HERE / "licenses/awgmproto-MIT.txt").read_bytes(),
        b"--- DEPENDENCY INVENTORY (NOT LEGAL CLEARANCE) ---\n" + (HERE / "licenses/PHASE1-dependency-inventory.json").read_bytes()
    ))
    if not output_dir.is_dir() or list(output_dir.iterdir()):
        raise ValueError("pass a pre-created empty output directory")
    summary = []
    for arch in TARGETS:
        binary_path = binary_dir / ("wt-client-linux-" + arch)
        rec = records[arch]
        binary = binary_path.read_bytes()
        checksum = hashlib.sha256(binary).hexdigest()
        if checksum != rec["sha256"]:
            raise ValueError(f"binary mismatch for {arch}")
        provenance = {
            "source": source,
            "architecture": arch,
            "entware_architecture": ARCH[arch],
            "binary_sha256": checksum,
            "EXPERIMENTAL_ONLY": True,
            "MANUAL_ONLY_NO_AUTOSTART": True,
            "license_review": "NOT_COMPLETE",
            "hardware_acceptance": "NOT_PERFORMED",
            "server_production_approval": "NOT_PERFORMED",
            "source_build_report_sha256": digest(report),
        }
        name = f"wt-client-lab_0.0.0+git{source[:12]}-1_{ARCH[arch]}.ipk"
        target = output_dir / name
        with target.open("xb") as f:
            f.write(package(binary, arch, source, notices, provenance))
        summary.append((digest(target), name, checksum))
    (output_dir / "SHA256SUMS").write_text("".join(f"{pkg}  {name}\n" for pkg, name, _ in summary))
    (output_dir / "README-FIRST.md").write_bytes(warning)
    (output_dir / "MANIFEST.json").write_text(json.dumps([
        {"file": name, "ipk_sha256": pkg, "binary_sha256": binary, "status": "EXPERIMENTAL_ONLY"}
        for pkg, name, binary in summary
    ], indent=2) + "\n")
    print("LAB-ONLY IPK files generated; manual installation is NOT approved for unverified hardware.")
    for pkg, name, _ in summary:
        print(pkg, name)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--report", required=True)
    p.add_argument("--binary-dir", required=True)
    p.add_argument("--output-dir", required=True)
    a = p.parse_args()
    make_lab_packages(a.report, a.binary_dir, a.output_dir)

if __name__ == "__main__":
    main()
