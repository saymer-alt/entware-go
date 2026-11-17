#!/usr/bin/env python3
"""Pinned TeleMT IPC candidate: one real QEMU-system MT7621 kernel-4.9 cycle.

Uses router-emulator's unchanged boot/Entware fixture, then ONLY new IPC
acceptance tests. The accepted Core/Panel IPKs and their 93-step suite are
not rebuilt or substituted. This is an offline disposable research run.
"""
import argparse
import base64
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

CORE_NAME = "telemt-ipc-lab_3.5.17-1ipc1_mipsel-3.4.ipk"
CORE_SHA = "5079390d513ebf118292323a8eb8f0e1beb663d0348147d7cea9f4d0d0865da9"
ELF_SHA = "0d3dcce3b9922d5dbffc748045168def7420c770ed6b4336e5e67d418c6f7e66"
# Variant A reference: the already accepted Core binary from the 74/74 guest
# suite. Its frozen bytes are re-verified here; nothing about them changes.
CORE_IPK_NAME = "telemt_3.5.17-2fb1_mipsel-3.4.ipk"
CORE_IPK_SHA = "2c8a84fb93535303eeb4bb8a0a5057370f4e625b1cdf0e102f04e33e28c85d8d"
CORE_ELF_SHA = "d4ba43815883dd1ce9aa57349602598127781e8966d51dab97616dbdb35b216f"
CORE_BIN = "/opt/bin/telemt"
EMU_SHA = "64a446deaacb0bca10d6053781ff1f7ad4a29552"
MIRROR_HOST = "192.168.1.100"
PID = "/opt/var/run/telemt-ipc-lab.pid"
CTL = "/opt/var/run/telemt-ipc-lab/ctl.sock"
CONF = "/opt/etc/telemt-lab.toml"
BIN = "/opt/bin/telemt-ipc-lab"
LOG = "/opt/var/log/telemt-ipc-lab.log"
# A/B/C foreground diagnosis: separate disposable PID/log/output paths, one
# variant at a time, never two instances on the same ports simultaneously.
FG_SOCK = "/opt/var/run/telemt-ipc-lab/ctl-fg.sock"
# Listener presence inside /proc/net/tcp: 127.0.0.1:3443 and 127.0.0.1:9091
# in LISTEN state, same expression family as the accepted 74/74 scenario.
TCP_LISTEN3443 = "0100007F:0D73 +[0-9A-F]{8}:[0-9A-F]{4} +0A "
TCP_LISTEN9091 = "0100007F:2383 +[0-9A-F]{8}:[0-9A-F]{4} +0A "


def guest_ssh(command, marker, timeout=120):
    # The regex must match only an explicit marker from an executed command.
    assert marker.isupper() and marker.replace("_", "").isalnum()
    return {"action": "ssh", "port": 8022, "send": command,
            "expect": marker, "timeout_sec": timeout}


def guest_ssh_regex(command, pattern, timeout=120):
    # The emulator's validator permits regex answer markers; the echoed
    # command must not itself match the pattern (checked by load_scenario).
    assert pattern.startswith("IPC_") and "\n" not in pattern
    assert "\n" not in command and "\r" not in command
    return {"action": "ssh", "port": 8022, "send": command,
            "expect": pattern, "timeout_sec": timeout}


def audit_lab_ipk(emulator_root, ipk):
    sys.path.insert(0, str(emulator_root))
    from lab.mt7621 import telemt_lab as audit
    if not ipk.is_file() or ipk.stat().st_size > audit.MAX_IPK:
        raise ValueError("missing/oversize lab IPK")
    raw = ipk.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CORE_SHA:
        raise ValueError("MIPSLE IPC IPK SHA-256 mismatch (fail closed)")
    metadata, data = audit.ipk_parts(raw)
    if metadata != {"Package": "telemt-ipc-lab",
                    "Version": "3.5.17-1ipc1",
                    "Architecture": "mipsel-3.4"}:
        raise ValueError("unexpected lab control metadata")
    if set(data) != {"opt/bin/telemt-ipc-lab"}:
        raise ValueError("package would replace unrelated payload")
    elf = data["opt/bin/telemt-ipc-lab"]
    if hashlib.sha256(elf).hexdigest() != ELF_SHA:
        raise ValueError("MIPSLE IPC ELF SHA-256 mismatch (fail closed)")
    info = audit.elf_mips_info(elf)
    if (info["fp_abi"] != 3 or info["interp"] != "/opt/lib/ld.so.1"
            or not info["dynamic"]):
        raise ValueError("Entware MIPSLE glibc softfloat ABI mismatch")
    return {"package": CORE_NAME, "ipk_sha256": CORE_SHA,
            "elf_sha256": ELF_SHA, "elf": info}


def audit_core_ipk(emulator_root, ipk):
    """Audit the immutable accepted Core IPK used as the variant A reference."""
    sys.path.insert(0, str(emulator_root))
    from lab.mt7621 import telemt_lab as audit
    if not ipk.is_file() or ipk.stat().st_size > audit.MAX_IPK:
        raise ValueError("missing/oversize accepted Core IPK")
    raw = ipk.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CORE_IPK_SHA:
        raise ValueError("accepted Core IPK SHA-256 mismatch (fail closed)")
    metadata, data = audit.ipk_parts(raw)
    if metadata != {"Package": "telemt",
                    "Version": "3.5.17-2fb1",
                    "Architecture": "mipsel-3.4"}:
        raise ValueError("unexpected accepted Core metadata")
    if set(data) != {"opt/bin/telemt"}:
        raise ValueError("accepted Core package would replace unrelated payload")
    elf = data["opt/bin/telemt"]
    if hashlib.sha256(elf).hexdigest() != CORE_ELF_SHA:
        raise ValueError("accepted Core ELF SHA-256 mismatch (fail closed)")
    info = audit.elf_mips_info(elf)
    if (info["fp_abi"] != 3 or info["interp"] != "/opt/lib/ld.so.1"
            or not info["dynamic"]):
        raise ValueError("accepted Core Entware MIPSLE glibc softfloat ABI mismatch")
    return {"package": CORE_IPK_NAME, "ipk_sha256": CORE_IPK_SHA,
            "elf_sha256": CORE_ELF_SHA, "elf": info}


def fg_probe_step(tag, binary, control_socket):
    """One bounded foreground run of one variant (A, B or C), fail closed.

    The sanitized report cannot carry matched marker text, so the verdict is
    exported through the SSH exit status (the only free-form channel in the
    report). A healthy variant exits 0 with marker `IPC_FG<tag>_HEALTHY`;
    every unhealthy outcome exits with a dedicated per-variant code:

      base = 120 (A, accepted Core), 136 (B, lab binary without the flag),
             152 (C, lab binary with --control-socket); +0..+15:

      +0 early exit; captured output mentions the control socket (Rust
         custom IPC validation message from the research patch);
      +1 early exit; permission/ownership wording (incl. the Rust kind
         spelling PermissionDenied and the trusted-directory message);
      +2 early exit; missing path wording;
      +3 early exit; address already in use;
      +4 early exit; panic wording;
      +5 early exit; unsupported syscall/argument wording;
      +6 early exit; an `Error:` line with none of the above classes;
      +7 early exit; empty captured output but a nonempty tracing log;
      +8 early exit; fully silent, wait status < 128 (orderly exit);
      +9 early exit; fully silent, wait status >= 128 (fatal signal);
      +10 alive at 12 s but the control socket is missing (C only);
      +11 alive at 12 s but a listener is not in LISTEN state;
      +12 alive at 12 s but both missing;
      +13 alive but TERM did not terminate within the bounded grace
          (verified direct child is then KILLed to keep the lab clean);
      +14 alive, TERMed, exited nonzero;
      +15 early exit with nonempty unclassified captured output.

    The child is a direct shell child ($!); its identity is verified through
    /proc/$fgp/exe before any TERM. Terminating (and if wedged, KILLing)
    only that verified direct child never signals any PID read from a file.
    A stale control socket of an already-dead previous attempt is removed
    first so attempts stay independent; nothing unlinks a live socket.
    """
    upper = tag.upper()
    base = {"a": 120, "b": 136, "c": 152}[tag]
    marker = f"IPC_FG{upper}_HEALTHY"
    pid = f"/opt/var/run/abc-fg-{tag}.pid"
    log = f"/opt/var/log/abc-fg-{tag}.log"
    out = f"/opt/lab/abc-fg-{tag}.out"
    rm_paths = f"{pid} {log} {out}"
    ctl_arg = ""
    sock_check = ""
    sock_cleanup = ""
    if control_socket is not None:
        ctl_arg = f" --control-socket {control_socket}"
        rm_paths += f" {control_socket}"
        sock_check = f"[ -S {control_socket} ] || d=$((d+1)); "
        sock_cleanup = (
            f"[ -r /proc/$fgp/exe ] || "
            f"/opt/bin/busybox rm -f {control_socket}; ")
    command = (
        f"/opt/bin/busybox rm -f {rm_paths}; "
        f"HOME=/opt/lab TMPDIR=/opt/lab {binary} start --foreground "
        f"--log-file {log} --pid-file {pid}{ctl_arg} {CONF} >{out} 2>&1 "
        "& fgp=$!; "
        "/opt/bin/busybox sleep 12; "
        "fg_exe=$(/opt/bin/busybox readlink /proc/$fgp/exe 2>/dev/null); "
        f"if [ \"$fg_exe\" != '{binary}' ]; then "
        "wait \"$fgp\"; frc=$?; "
        f"/opt/bin/busybox grep -q 'control socket' {out} 2>/dev/null && "
        f"exit {base + 0}; "
        f"/opt/bin/busybox grep -Eiq 'permission denied|permissiondenied|"
        f"not owned and protected|operation not permitted' {out} 2>/dev/null "
        f"&& exit {base + 1}; "
        f"/opt/bin/busybox grep -Eiq 'no such file|not a directory|not found' "
        f"{out} 2>/dev/null && exit {base + 2}; "
        f"/opt/bin/busybox grep -Eiq 'address already in use' {out} "
        f"2>/dev/null && exit {base + 3}; "
        f"/opt/bin/busybox grep -Eiq 'panic|panicked' {out} 2>/dev/null && "
        f"exit {base + 4}; "
        f"/opt/bin/busybox grep -Eiq 'invalid argument|not supported|"
        f"function not implemented|enosys' {out} 2>/dev/null && "
        f"exit {base + 5}; "
        f"/opt/bin/busybox grep -q 'Error:' {out} 2>/dev/null && "
        f"exit {base + 6}; "
        f"[ -s {out} ] && exit {base + 15}; "
        f"/opt/bin/busybox grep -q 'Log level:' {log} 2>/dev/null && "
        f"exit {base + 7}; "
        f"[ -s {log} ] && exit {base + 7}; "
        f"[ \"$frc\" -ge 128 ] && exit {base + 9}; "
        f"exit {base + 8}; fi; "
        "lst=1; "
        f"/opt/bin/busybox grep -Eq '{TCP_LISTEN3443}' /proc/net/tcp 2>/dev/null "
        "|| lst=0; "
        f"/opt/bin/busybox grep -Eq '{TCP_LISTEN9091}' /proc/net/tcp 2>/dev/null "
        "|| lst=0; "
        "d=0; [ \"$lst\" = 1 ] || d=$((d+2)); "
        f"{sock_check}"
        "kill -TERM \"$fgp\" 2>/dev/null; "
        "i=0; while [ \"$i\" -lt 10 ] && [ -r /proc/$fgp/exe ]; do "
        "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
        "if [ -r /proc/$fgp/exe ]; then "
        "kill -TERM \"$fgp\" 2>/dev/null; "
        "j=0; while [ \"$j\" -lt 5 ] && [ -r /proc/$fgp/exe ]; do "
        "/opt/bin/busybox sleep 1; j=$((j+1)); done; "
        "if [ -r /proc/$fgp/exe ]; then "
        f"kill -KILL \"$fgp\" 2>/dev/null; fi; wait \"$fgp\"; "
        f"[ \"$d\" -ne 0 ] && exit $(({base} + 9 + d)) || exit {base + 13}; fi; "
        f"{sock_cleanup}"
        "wait \"$fgp\"; frc=$?; "
        f"[ \"$d\" -ne 0 ] && exit $(({base} + 9 + d)) || "
        f"{{ [ \"$frc\" = 0 ] && printf 'IPC_%s\\n' FG{upper}_HEALTHY && "
        f"exit 0 || exit {base + 14}; }}"
    )
    return guest_ssh_regex(command, marker, 180)


def classification_step():
    """Classify each variant's captured foreground output by fixed markers.

    Emits one sanitized numeric mask per variant: `IPC_CLS_<a>_<b>_<c>`.
    Bits: 1 past tracing banner, 2 main returned an Error, 4 panic text,
    8 raw os-error text, 16 permission text, 32 control-socket text,
    64 tracing log initialised, 128 graceful shutdown logged,
    256 shutdown signal logged, 512 address-in-use, 1024 missing-file text,
    2048 foreground output nonempty. No raw log or config leaves the guest.
    """
    greps = [
        (1, "-q 'Telemt MTProxy v'", "o"),
        (2, "-q 'Error:'", "o"),
        (4, "-Eiq 'panic|panicked'", "ol"),
        (8, "-q 'os error'", "o"),
        (16, "-Eiq 'permission denied|operation not permitted'", "ol"),
        (32, "-q 'control socket'", "o"),
        (64, "-q 'Log level:'", "l"),
        (128, "-q 'Shutting down'", "l"),
        (256, "-q 'Received shutdown signal'", "l"),
        (512, "-Eiq 'address already in use'", "ol"),
        (1024, "-Eiq 'no such file|not found'", "ol"),
    ]
    body = "[ -s \"$o\" ] && m=$((m+2048)); "
    for bit, pattern, files in greps:
        tests = []
        if "o" in files:
            tests.append(f"/opt/bin/busybox grep {pattern} \"$o\" 2>/dev/null")
        if "l" in files:
            tests.append(f"/opt/bin/busybox grep {pattern} \"$l\" 2>/dev/null")
        if len(tests) == 1:
            body += f"{tests[0]} && m=$((m+{bit})); "
        else:
            body += "{ " + " || ".join(tests) + f"; }} && m=$((m+{bit})); "
    command = (
        "cm() { m=0; "
        "o=/opt/lab/abc-fg-$1.out; l=/opt/var/log/abc-fg-$1.log; "
        "[ -f \"$o\" ] || o=/dev/null; [ -f \"$l\" ] || l=/dev/null; "
        f"{body}"
        "eval \"$2=$m\"; }; "
        "cm a ma; cm b mb; cm c mc; "
        "printf 'IPC_%s\\n' \"CLS_${ma}_${mb}_${mc}\"; exit 0"
    )
    return guest_ssh_regex(command, "IPC_CLS_[0-9]+_[0-9]+_[0-9]+", 120)


def daemon_log_step():
    """Sanitized milestone mask of the detached daemon's own log.

    Emits `IPC_DLOG_<mask>` after the detached start attempt: 1 log nonempty,
    2 tracing initialised, 4 buffer-budget stage, 8 shutdown signal logged,
    16 graceful shutdown logged, 32 panic text, 64 no-listeners error,
    128 address-in-use, 256 permission text, 512 unsupported-syscall text,
    1024 SIGHUP reload observed. No raw content leaves the guest.
    """
    greps = [
        (2, "-q 'Log level:'"),
        (4, "-q 'Direct relay buffer budget initialized'"),
        (8, "-q 'Received shutdown signal'"),
        (16, "-q 'Shutting down'"),
        (32, "-Eiq 'panic|panicked'"),
        (64, "-q 'No listeners'"),
        (128, "-Eiq 'address already in use'"),
        (256, "-Eiq 'permission denied|operation not permitted'"),
        (512, "-Eiq 'function not implemented|not supported|enosys'"),
        (1024, "-q 'SIGHUP received'"),
    ]
    body = "[ -s \"$l\" ] && m=$((m+1)); "
    for bit, pattern in greps:
        body += f"/opt/bin/busybox grep {pattern} \"$l\" 2>/dev/null && " \
                f"m=$((m+{bit})); "
    command = (
        f"m=0; l={LOG}; [ -f \"$l\" ] || l=/dev/null; "
        f"{body}"
        "printf 'IPC_%s\\n' \"DLOG_$m\"; exit 0"
    )
    return guest_ssh_regex(command, "IPC_DLOG_[0-9]+", 120)


def synthetic_file_step(config, secret):
    # No real Telegram credentials: both inputs come from pinned offline
    # router-emulator synthetic lab fixtures.
    # The runtime-path ancestors are normalized to the same modes the
    # opt-ndmsv2 package ships on real Entware installations (0755 root):
    # local_control's trusted-parent validation runs in the guest and must
    # see a standard, non-group/world-writable chain. This is lab
    # environment repair, not a weakening of any Rust security check.
    b64_config = base64.b64encode(config).decode("ascii")
    b64_secret = base64.b64encode(secret).decode("ascii")
    return guest_ssh(
        "/opt/bin/busybox mkdir -p /opt/lab /opt/var/run/telemt-ipc-lab "
        "/opt/var/log /opt/etc && "
        "/opt/bin/busybox chmod 755 /opt/lab /opt/var /opt/var/run "
        "/opt/var/log /opt/etc && "
        "/opt/bin/busybox chmod 700 /opt/var/run/telemt-ipc-lab && "
        "printf '%s' '" + b64_config +
        "' | /opt/bin/busybox base64 -d > " + CONF + " && "
        "printf '%s' '" + b64_secret +
        "' | /opt/bin/busybox base64 -d > /opt/etc/telemt-lab.secret && "
        "/opt/bin/busybox chmod 600 " + CONF + " /opt/etc/telemt-lab.secret && "
        "printf 'IPC_%s\\n' SYNTHETIC_CONFIG",
        "IPC_SYNTHETIC_CONFIG")


def start_command():
    return ("HOME=/opt/lab TMPDIR=/opt/lab " + BIN +
            " start --log-file " + LOG + " --pid-file " + PID +
            " --control-socket " + CTL + " " + CONF)


def scenario_for(emulator_root):
    baseline_path = emulator_root / "lab/scenarios/ported-mt7621-telemt.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    prefix = baseline["steps"][:21]
    if (len(prefix) != 21 or prefix[0]["action"] != "wait_serial"
            or prefix[-1].get("expect") != "MARK42"
            or not any("opkg disk KASOPT:/" in str(s.get("send"))
                       for s in prefix)):
        raise ValueError("boot/Entware prefix drift (fail closed)")
    config = (emulator_root / "lab/mt7621/fixtures/telemt-lab.toml").read_bytes()
    secret = (emulator_root / "lab/mt7621/fixtures/telemt-lab.secret").read_bytes()
    if (b'use_middle_proxy = false' not in config
            or b'127.0.0.1' not in config
            or b'mask = false' not in config
            or len(secret) != 32):
        raise ValueError("non-synthetic or unexpected lab config")

    # BusyBox find is part of the already-installed pinned Entware bootstrap.
    # The mipsel-3.4 BusyBox configuration includes FIND, MAXDEPTH, PERM,
    # TYPE and USER. Verify the exact locked BusyBox package identity here.
    lock = json.loads((emulator_root / "lab/entware-mipselsf.lock.json").read_text())
    found = [p for p in lock["packages"] if p.get("Package") == "busybox"]
    if (len(found) != 1 or found[0].get("Filename") !=
            "busybox_1.38.0-5_mipsel-3.4.ipk"
            or found[0].get("SHA256sum") !=
            "0ba41200b8fdd51c2b606fc92c141059350cd3da7a45233eb0174aeaea1bfa32"
            or found[0].get("Architecture") != "mipsel-3.4"):
        raise ValueError("BusyBox pin in isolated Entware mirror drifted")

    steps = list(prefix)
    steps.extend([
        guest_ssh("/opt/bin/busybox mkdir -p /opt/lab && "
                  "/opt/bin/busybox wget -qO /opt/lab/ipc.ipk "
                  "http://" + MIRROR_HOST + "/entware/" + CORE_NAME +
                  " && printf '%s  %s\\n' '" + CORE_SHA +
                  "' /opt/lab/ipc.ipk > /opt/lab/ipc.sha && "
                  "/opt/bin/busybox sha256sum -c /opt/lab/ipc.sha >/dev/null && "
                  "printf 'IPC_%s\\n' IPK_PINNED", "IPC_IPK_PINNED", 300),
        guest_ssh("/opt/bin/opkg install /opt/lab/ipc.ipk "
                  ">/opt/lab/ipc-opkg.log 2>&1 && "
                  "/opt/bin/opkg status telemt-ipc-lab | "
                  "/opt/bin/busybox grep -q 'Version: 3.5.17-1ipc1' && "
                  "test -x " + BIN + " && "
                  "test ! -e /opt/bin/telemt && "
                  "printf 'IPC_%s\\n' OPKG_SEPARATE",
                  "IPC_OPKG_SEPARATE", 300),
        guest_ssh("printf '%s  %s\\n' '" + ELF_SHA + "' " + BIN +
                  " > /opt/lab/ipc-elf.sha && "
                  "/opt/bin/busybox sha256sum -c /opt/lab/ipc-elf.sha >/dev/null "
                  "&& printf 'IPC_%s\\n' ELF_PINNED", "IPC_ELF_PINNED"),
        synthetic_file_step(config, secret),
        guest_ssh("HOME=/opt/lab " + BIN +
                  " stop --control-socket " + CTL +
                  " >/opt/lab/ipc-absent.out 2>&1; rc=$?; "
                  "[ \"$rc\" -ne 0 ] && "
                  "printf 'IPC_%s\\n' ABSENT_REJECTED",
                  "IPC_ABSENT_REJECTED"),
        # Probe the exact parent trust conditions from local_control::private_parent.
        # Distinct nonzero SSH codes are preserved in the sanitized JSON report:
        # 41 symlink ancestor, 42 missing/non-directory, 43 parent mode,
        # 44 parent UID, 45 start(1) CLI rejected, 46 no PID file,
        # 47 malformed PID, 48 dead child, 49 wrong executable,
        # 50 no Unix control socket, 51 final consistency failed.
        guest_ssh("for d in /opt /opt/var /opt/var/run "
                  "/opt/var/run/telemt-ipc-lab; do "
                  "[ ! -L \"$d\" ] || exit 41; "
                  "[ -d \"$d\" ] || exit 42; done; "
                  "printf 'IPC_%s\\n' PARENT_COMPONENTS_SAFE",
                  "IPC_PARENT_COMPONENTS_SAFE"),
        # BusyBox FIND with -maxdepth 0 -type d -perm 700 and -user N
        # tests the *exact* private directory, not children or ancestors.
        # Capture -print because BusyBox find returns 0 on no match.
        # 52 = no built-in find; 53/54 = invocation error; 43/44 =
        # actual permission/owner mismatch; preserve Rust strict checks.
        guest_ssh("/opt/bin/busybox --list | "
                  "/opt/bin/busybox grep -qx find || exit 52; "
                  "uid=$(/opt/bin/busybox id -u) || exit 44; "
                  "mode=$(/opt/bin/busybox find "
                  "/opt/var/run/telemt-ipc-lab "
                  "-maxdepth 0 -type d -perm 700 -print "
                  "2>/dev/null) || exit 53; "
                  "[ \"$mode\" = /opt/var/run/telemt-ipc-lab ] || exit 43; "
                  "owner=$(/opt/bin/busybox find "
                  "/opt/var/run/telemt-ipc-lab "
                  "-maxdepth 0 -type d -user \"$uid\" -print "
                  "2>/dev/null) || exit 54; "
                  "[ \"$owner\" = /opt/var/run/telemt-ipc-lab ] || exit 44; "
                  "printf 'IPC_%s\\n' PARENT_OWNER_MODE",
                  "IPC_PARENT_OWNER_MODE"),
        # Comparative diagnosis (task A/B/C): the same lab environment runs
        # the accepted Core (A), the lab binary without the opt-in flag (B)
        # and the lab binary with it (C), strictly one at a time in bounded
        # foreground mode with separate disposable paths. Variant A re-proves
        # the frozen accepted bytes; B isolates a candidate-build regression;
        # C isolates the opt-in IPC integration. The detached readiness
        # probes below then repeat the original daemonized contract.
        guest_ssh("/opt/bin/busybox mkdir -p /opt/lab && "
                  "/opt/bin/busybox wget -qO /opt/lab/core.ipk "
                  "http://" + MIRROR_HOST + "/entware/" + CORE_IPK_NAME +
                  " && printf '%s  %s\\n' '" + CORE_IPK_SHA +
                  "' /opt/lab/core.ipk > /opt/lab/core.sha && "
                  "/opt/bin/busybox sha256sum -c /opt/lab/core.sha >/dev/null && "
                  "/opt/bin/opkg install /opt/lab/core.ipk "
                  ">/opt/lab/core-opkg.log 2>&1 && "
                  "/opt/bin/opkg status telemt | "
                  "/opt/bin/busybox grep -q 'Version: 3.5.17-2fb1' && "
                  "test -x " + CORE_BIN + " && "
                  "printf 'IPC_%s\\n' CORE_OPKG",
                  "IPC_CORE_OPKG", 300),
        fg_probe_step("a", CORE_BIN, None),
        fg_probe_step("b", BIN, None),
        fg_probe_step("c", BIN, FG_SOCK),
        classification_step(),
        guest_ssh(start_command() + " >/opt/lab/ipc-start.out 2>&1; "
                  "rc=$?; [ \"$rc\" = 0 ] || exit 45; "
                  "printf 'IPC_%s\\n' START_RETURNED",
                  "IPC_START_RETURNED", 120),
        daemon_log_step(),
        # A detached child can fail after start(1) parent exits 0 and
        # release its PID via RAII. Do not accept mere readability as READY:
        # verify numeric PID, pinned live /proc/exe identity and stability
        # across 2s in the same SSH session. Then, if not stable, attempt
        # one short, isolated foreground run.
        # The pinned MIPSel BusyBox *lacks* the timeout applet (native run 10).
        # Run foreground binary as a direct shell child ($!), not via a PID
        # file. Keep it unreaped until wait: this blocks PID reuse. Verify
        # /proc/$fg_pid/exe is the exact pinned executable BEFORE sending
        # TERM to that direct child only. Never signal PID-file contents.
        # The foreground PID, socket and log use separate disposable paths.
        # SSH returns only fixed codes, no raw log/config/process arguments.
        # 62 alive for bounded window and terminated, 63 exited 0 early;
        # 64 other failure; 65 panic; 66 permission/bind; 67 config;
        # 68 missing file; 70 unsupported syscall; 71 unexpected child
        # executable; 72 direct-child TERM failed or it did not exit.
        # 73 common fatal signal-like exit status, 74 launcher 126/127,
        # 75 unclassified foreground stderr/stdout, 76 unclassified
        # foreground file log. Old main daemon's routine logging must
        # NOT mask a foreground diagnostic's own result.
        guest_ssh("i=0; seen=0; while [ \"$i\" -lt 30 ]; do "
                  "[ -e " + PID + " ] && seen=1; "
                  "if [ -r " + PID + " ]; then "
                  "p=$(/opt/bin/busybox cat " + PID + " 2>/dev/null); "
                  "case \"$p\" in ''|*[!0-9]*) ;; *) "
                  "if [ -r /proc/$p/cmdline ] && "
                  "[ \"$(/opt/bin/busybox readlink /proc/$p/exe 2>/dev/null)\" = '" +
                  BIN + "' ]; then "
                  "/opt/bin/busybox sleep 2; "
                  "if [ -r " + PID + " ] && "
                  "[ \"$(/opt/bin/busybox cat " + PID + " 2>/dev/null)\" = \"$p\" ] && "
                  "[ -r /proc/$p/cmdline ] && "
                  "[ \"$(/opt/bin/busybox readlink /proc/$p/exe 2>/dev/null)\" = '" +
                  BIN + "' ]; then "
                  "printf 'IPC_%s\\n' PIDFILE_READY; exit 0; "
                  "fi; fi;; esac; fi; "
                  "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
                  "[ -S " + CTL + " ] && exit 55; "
                  "n=0; for d in /proc/[0-9]*; do "
                  "e=$(/opt/bin/busybox readlink \"$d/exe\" 2>/dev/null); "
                  "[ \"$e\" = '" + BIN + "' ] && n=$((n+1)); done; "
                  "[ \"$n\" = 0 ] || exit 56; "
                  "if [ -s " + LOG + " ]; then "
                  "/opt/bin/busybox grep -Eqi 'panic|panicked' " + LOG +
                  " && exit 58; "
                  "/opt/bin/busybox grep -Eqi "
                  "'permission denied|operation not permitted|failed to bind|address already in use' " +
                  LOG + " && exit 59; fi; "
                  "fg_timed=0; HOME=/opt/lab TMPDIR=/opt/lab " + BIN +
                  " start --foreground "
                  "--log-file /opt/var/log/telemt-ipc-fg.log "
                  "--pid-file /opt/var/run/telemt-ipc-fg.pid "
                  "--control-socket /opt/var/run/telemt-ipc-lab/ctl-fg.sock " +
                  CONF + " >/opt/lab/ipc-fg.out 2>&1 & fg_pid=$!; "
                  "/opt/bin/busybox sleep 12; "
                  "fg_exe=$(/opt/bin/busybox readlink /proc/$fg_pid/exe "
                  "2>/dev/null); "
                  "if [ \"$fg_exe\" = '" + BIN + "' ]; then "
                  "kill -TERM \"$fg_pid\" || exit 72; "
                  "/opt/bin/busybox sleep 2; "
                  "[ \"$(/opt/bin/busybox readlink /proc/$fg_pid/exe "
                  "2>/dev/null)\" != '" + BIN + "' ] || exit 72; "
                  "fg_timed=1; "
                  "elif [ -n \"$fg_exe\" ]; then exit 71; fi; "
                  "wait \"$fg_pid\"; frc=$?; "
                  "[ \"$fg_timed\" = 1 ] && exit 62; "
                  "/opt/bin/busybox grep -Eqi 'panic|panicked' "
                  "/opt/lab/ipc-fg.out /opt/var/log/telemt-ipc-fg.log "
                  "2>/dev/null && exit 65; "
                  "/opt/bin/busybox grep -Eqi "
                  "'permission denied|operation not permitted|failed to bind|address already in use' "
                  "/opt/lab/ipc-fg.out /opt/var/log/telemt-ipc-fg.log "
                  "2>/dev/null && exit 66; "
                  "/opt/bin/busybox grep -Eqi "
                  "'invalid.*config|parse error|toml|unclosed table' "
                  "/opt/lab/ipc-fg.out /opt/var/log/telemt-ipc-fg.log "
                  "2>/dev/null && exit 67; "
                  "/opt/bin/busybox grep -Eqi "
                  "'no such file|not found|cannot open.*file' "
                  "/opt/lab/ipc-fg.out /opt/var/log/telemt-ipc-fg.log "
                  "2>/dev/null && exit 68; "
                  "/opt/bin/busybox grep -Eqi "
                  "'function not implemented|operation not supported|enosys' "
                  "/opt/lab/ipc-fg.out /opt/var/log/telemt-ipc-fg.log "
                  "2>/dev/null && exit 70; "
                  "[ \"$frc\" = 0 ] && exit 63; "
                  "case \"$frc\" in 132|134|137|139) exit 73;; "
                  "126|127) exit 74;; esac; "
                  "[ -s /opt/lab/ipc-fg.out ] && exit 75; "
                  "[ -s /opt/var/log/telemt-ipc-fg.log ] && exit 76; "
                  "[ \"$seen\" = 0 ] || exit 57; "
                  "[ -s " + LOG + " ] && exit 60; "
                  "[ -e " + PID + ".lock ] && exit 61; "
                  "[ \"$frc\" != 0 ] && exit 64; "
                  "exit 46",
                  "IPC_PIDFILE_READY", 120),
        guest_ssh("[ -r " + PID + " ] || exit 57; "
                  "p=$(/opt/bin/busybox cat " + PID + " 2>/dev/null) || exit 57; "
                  "case \"$p\" in ''|*[!0-9]*) exit 47;; esac; "
                  "[ -r /proc/$p/cmdline ] || exit 48; "
                  "exe=$(/opt/bin/busybox readlink /proc/$p/exe 2>/dev/null); "
                  "[ \"$exe\" = '" + BIN + "' ] || exit 49; "
                  "printf 'IPC_%s\\n' CHILD_EXE_CONFIRMED",
                  "IPC_CHILD_EXE_CONFIRMED"),
        guest_ssh("i=0; while [ \"$i\" -lt 30 ]; do "
                  "[ -S " + CTL + " ] && break; "
                  "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
                  "[ -S " + CTL + " ] || exit 50; "
                  "printf 'IPC_%s\\n' CONTROL_SOCKET_READY",
                  "IPC_CONTROL_SOCKET_READY", 120),
        guest_ssh("p=$(/opt/bin/busybox cat " + PID + "); "
                  "[ -r /proc/$p/cmdline ] && "
                  "[ \"$(/opt/bin/busybox readlink /proc/$p/exe)\" = '" + BIN +
                  "' ] && [ -S " + CTL + " ] || exit 51; "
                  "printf 'IPC_%s\\n' DAEMON_ALIVE",
                  "IPC_DAEMON_ALIVE"),

        guest_ssh("p=$(/opt/bin/busybox cat " + PID + "); "
                  "HOME=/opt/lab " + BIN + " reload --control-socket " + CTL +
                  " >/opt/lab/ipc-reload.out 2>&1 || exit 1; "
                  "/opt/bin/busybox sleep 3; "
                  "[ \"$(/opt/bin/busybox cat " + PID + ")\" = \"$p\" ] && "
                  "[ -r /proc/$p/cmdline ] && "
                  "/opt/bin/busybox grep -q 'SIGHUP received' " + LOG +
                  " && printf 'IPC_%s\\n' RELOAD_SAME_PID",
                  "IPC_RELOAD_SAME_PID", 150),
        guest_ssh("p=$(/opt/bin/busybox cat " + PID + "); "
                  "/opt/bin/busybox chmod 777 /opt/var/run/telemt-ipc-lab; "
                  "HOME=/opt/lab " + BIN + " stop --control-socket " + CTL +
                  " >/opt/lab/ipc-unsafe.out 2>&1; rc=$?; "
                  "/opt/bin/busybox chmod 700 /opt/var/run/telemt-ipc-lab; "
                  "[ \"$rc\" -ne 0 ] && [ -r /proc/$p/cmdline ] && "
                  "printf 'IPC_%s\\n' UNSAFE_PARENT_REJECTED",
                  "IPC_UNSAFE_PARENT_REJECTED"),
        guest_ssh("p=$(/opt/bin/busybox cat " + PID + "); "
                  "HOME=/opt/lab " + BIN +
                  " reload --pid-file " + PID +
                  " >/opt/lab/ipc-pidfd.out 2>&1; rc=$?; "
                  "[ \"$rc\" -ne 0 ] && [ -r /proc/$p/cmdline ] && "
                  "printf 'IPC_%s\\n' NO_IMPLICIT_PIDFD_FALLBACK",
                  "IPC_NO_IMPLICIT_PIDFD_FALLBACK"),
        guest_ssh("p=$(/opt/bin/busybox cat " + PID + "); "
                  "HOME=/opt/lab " + BIN +
                  " stop --control-socket >/opt/lab/ipc-empty.out 2>&1; rc=$?; "
                  "[ \"$rc\" -ne 0 ] && [ -r /proc/$p/cmdline ] && "
                  "printf 'IPC_%s\\n' EMPTY_PATH_REJECTED",
                  "IPC_EMPTY_PATH_REJECTED"),
        guest_ssh("p=$(/opt/bin/busybox cat " + PID + "); "
                  "HOME=/opt/lab " + BIN + " stop --control-socket " + CTL +
                  " >/opt/lab/ipc-stop.out 2>&1 || exit 1; "
                  "i=0; while [ \"$i\" -lt 30 ]; do "
                  "test ! -S " + CTL +
                  " && test ! -r /proc/$p/cmdline && break; "
                  "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
                  "test ! -e " + CTL + " && "
                  "test ! -r /proc/$p/cmdline && "
                  "n=0; for d in /proc/[0-9]*; do "
                  "e=$(/opt/bin/busybox readlink \"$d/exe\" 2>/dev/null); "
                  "[ \"$e\" = '" + BIN + "' ] && n=$((n+1)); done; "
                  "[ \"$n\" = 0 ] && "
                  "printf 'IPC_%s\\n' STOP_CLEAN",
                  "IPC_STOP_CLEAN", 150),
        guest_ssh("HOME=/opt/lab " + BIN + " stop --control-socket " + CTL +
                  " >/dev/null 2>&1; [ \"$?\" -ne 0 ] && "
                  "test ! -e " + CTL + " && "
                  "printf 'IPC_%s\\n' SECOND_STOP_REJECTED",
                  "IPC_SECOND_STOP_REJECTED"),
    ])
    # Reuse only the already accepted native KeeneticOS reboot bootstrap
    # assertions, not the old 74/93-step TeleMT product test.
    reboot = baseline["steps"][21:33]
    if (len(reboot) != 12 or reboot[0]["action"] != "telnet"
            or reboot[-1].get("expect") != "MARK42"):
        raise ValueError("reboot/Entware prefix drift (fail closed)")
    steps.extend(reboot)
    steps.extend([
        guest_ssh("/opt/bin/opkg status telemt-ipc-lab | "
                  "/opt/bin/busybox grep -q 'Version: 3.5.17-1ipc1' "
                  "&& test -x " + BIN + " && "
                  "test ! -e " + CTL + " && "
                  "test ! -e /opt/etc/init.d/S99telemt-ipc-lab && "
                  "n=0; for d in /proc/[0-9]*; do "
                  "e=$(/opt/bin/busybox readlink \"$d/exe\" 2>/dev/null); "
                  "[ \"$e\" = '" + BIN + "' ] && n=$((n+1)); done; "
                  "[ \"$n\" = 0 ] && "
                  "printf 'IPC_%s\\n' REBOOT_NO_AUTOSTART",
                  "IPC_REBOOT_NO_AUTOSTART"),
        guest_ssh("HOME=/opt/lab " + BIN +
                  " reload --control-socket " + CTL +
                  " >/dev/null 2>&1; [ \"$?\" -ne 0 ] && "
                  "printf 'IPC_%s\\n' REBOOT_ABSENT_REJECTED",
                  "IPC_REBOOT_ABSENT_REJECTED"),
        guest_ssh(start_command() + " >/opt/lab/ipc-restart.out 2>&1 || exit 1; "
                  "i=0; while [ \"$i\" -lt 30 ]; do "
                  "test -S " + CTL + " && test -r " + PID +
                  " && break; /opt/bin/busybox sleep 1; i=$((i+1)); done; "
                  "test -S " + CTL + " && "
                  "printf 'IPC_%s\\n' REBOOT_MANUAL_START",
                  "IPC_REBOOT_MANUAL_START", 150),
        guest_ssh("p=$(/opt/bin/busybox cat " + PID + "); "
                  "HOME=/opt/lab " + BIN + " stop --control-socket " + CTL +
                  " >/dev/null 2>&1 || exit 1; "
                  "i=0; while [ \"$i\" -lt 30 ]; do "
                  "test ! -e " + CTL +
                  " && test ! -r /proc/$p/cmdline && break; "
                  "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
                  "test ! -e " + CTL +
                  " && test ! -r /proc/$p/cmdline && "
                  "printf 'IPC_%s\\n' REBOOT_STOP_CLEAN",
                  "IPC_REBOOT_STOP_CLEAN", 150),
        guest_ssh("/opt/bin/opkg remove telemt-ipc-lab "
                  ">/opt/lab/ipc-remove.out 2>&1 && "
                  "test ! -e " + BIN + " && "
                  "test ! -e " + CTL + " && "
                  "printf 'IPC_%s\\n' ROLLBACK_OK",
                  "IPC_ROLLBACK_OK", 150),
    ])
    return {"name": "Ported MT7621 native TeleMT in-daemon IPC acceptance "
                    "(new SHA-pinned lab binary only)",
            "evidence": "KEENETIC_PORTED_EXPERIMENTAL", "steps": steps}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emulator-root", required=True)
    ap.add_argument("--ipk-dir", required=True)
    ap.add_argument("--core-ipk-dir", required=True,
                    help="directory holding the frozen accepted Core IPK (variant A)")
    ap.add_argument("--workspace", help="fresh private workspace")
    ap.add_argument("--entware-cache", help="verified cache outside fresh private workspace")
    ap.add_argument("--nand-dir")
    ap.add_argument("--credentials-file")
    ap.add_argument("--max-seconds", type=int, default=2400)
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args()
    root = Path(args.emulator_root).resolve()
    ipk = Path(args.ipk_dir) / CORE_NAME
    summary = audit_lab_ipk(root, ipk)
    core_ipk = Path(args.core_ipk_dir) / CORE_IPK_NAME
    core_summary = audit_core_ipk(root, core_ipk)
    plan = scenario_for(root)
    steps = plan["steps"]
    if len(steps) >= 74 or not any(
            s.get("expect") == "IPC_STOP_CLEAN" for s in steps):
        raise ValueError("narrow IPC scenario contract was violated")
    # The emulator's real scenario validator must run *before* any QEMU,
    # not only on execution. This catches literal newlines in guest shell
    # commands and echo-unsafe markers at the cheap preflight boundary.
    import tempfile
    from lab.run import load_scenario
    with tempfile.TemporaryDirectory(prefix="telemt-ipc-scenario-") as temp_dir:
        candidate_path = Path(temp_dir) / "scenario.json"
        candidate_path.write_text(json.dumps(plan), encoding="utf-8")
        load_scenario(candidate_path)
    download_step = next(s for s in steps if s.get("expect") == "IPC_IPK_PINNED")
    if not download_step["send"].startswith(
            "/opt/bin/busybox mkdir -p /opt/lab && "):
        raise ValueError("lab directory must exist before the IPK download")
    expected_readiness = [
        "IPC_PARENT_COMPONENTS_SAFE", "IPC_PARENT_OWNER_MODE",
        "IPC_CORE_OPKG", "IPC_FGA_*", "IPC_FGB_*", "IPC_FGC_*",
        "IPC_CLS_*", "IPC_START_RETURNED", "IPC_DLOG_*",
        "IPC_PIDFILE_READY", "IPC_CHILD_EXE_CONFIRMED",
        "IPC_CONTROL_SOCKET_READY", "IPC_DAEMON_ALIVE",
    ]
    labels = [s.get("expect") for s in steps]

    def label_matches(marker):
        return sum(1 for label in labels
                   if label is not None and fnmatch.fnmatchcase(label, marker))

    if not all(label_matches(marker) == 1 for marker in expected_readiness):
        raise ValueError("IPC startup readiness must have exactly one probe each")
    exact_labels = [m for m in expected_readiness if "*" not in m]
    positions = [labels.index(marker) for marker in exact_labels]
    if positions != sorted(positions):
        raise ValueError("IPC startup probes are out of order")
    # Contiguity across the whole readiness family, regex members included.
    first = min(labels.index(m) for m in exact_labels)
    family = [i for i, label in enumerate(labels)
              if label is not None and any(fnmatch.fnmatchcase(label, m)
                                           for m in expected_readiness)]
    if family != list(range(first, first + len(family))):
        raise ValueError("IPC startup probes are not contiguous")
    if args.plan_only:
        print(json.dumps({"status": "PINNED_IPC_GUEST_PLAN_PASS",
                          "step_count": len(steps),
                          "ipk_sha256": summary["ipk_sha256"],
                          "elf_sha256": summary["elf_sha256"],
                          "core_ipk_sha256": core_summary["ipk_sha256"],
                          "core_elf_sha256": core_summary["elf_sha256"]},
                         sort_keys=True))
        return 0

    if not (args.workspace and args.nand_dir and args.credentials_file):
        ap.error("guest run requires --workspace, --nand-dir, --credentials-file")
    workspace = Path(args.workspace)
    workspace.mkdir(mode=0o700, exist_ok=False)
    credentials = json.loads(Path(args.credentials_file).read_text(encoding="utf8"))
    if credentials.get("username") != "root":
        raise ValueError("root-only disposable guest SSH credential contract")
    scenario_file = workspace / "ipc-scenario.json"
    scenario_file.write_text(json.dumps(plan), encoding="utf8")
    sys.path.insert(0, str(root))
    from lab.build_entware import build
    from lab.mirror import Mirror
    from lab.run import run
    lock = root / "lab/entware-mipselsf.lock.json"
    image, mirror = workspace / "opt.img", workspace / "mirror"
    if args.entware_cache:
        # The workspace MUST remain fresh. Copy only verified public assets
        # into it after the existing exist_ok=False safety boundary.
        from prefetch_entware_assets import assets, verify_cache
        rows = assets(root)
        source_cache = Path(args.entware_cache)
        verify_cache(source_cache, rows)
        internal_cache = workspace / "cache"
        internal_cache.mkdir(mode=0o700)
        for name, _, _ in rows:
            shutil.copyfile(source_cache / name, internal_cache / name)
        verify_cache(internal_cache, rows)
    build(str(image), str(mirror), workspace / "cache",
          args.credentials_file, arch="mipsel", lock_path=str(lock))
    shutil.copyfile(ipk, mirror / "entware" / CORE_NAME)
    shutil.copyfile(core_ipk, mirror / "entware" / CORE_IPK_NAME)
    with Mirror(mirror) as port:
        return run(SimpleNamespace(
            scenario=str(scenario_file), emulator_root=str(root),
            nand_dir=args.nand_dir, output_dir=workspace / "report",
            max_seconds=args.max_seconds, preset="xiaomi-mi-router-3g-breed",
            lan_forwards="8080:80;8022:222;8023:23", opt_image=str(image),
            archive_image=None, mirror_port=port,
            credentials_file=args.credentials_file))


if __name__ == "__main__":
    sys.exit(main())
