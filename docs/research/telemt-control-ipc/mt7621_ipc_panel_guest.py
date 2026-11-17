#!/usr/bin/env python3
"""Joint MT7621 kernel-4.9 acceptance: pinned TeleMT IPC 3.5.17-1ipc2 +
Panel Lite 1.0.0-rc.4, one real QEMU-system cycle.

The already accepted pieces are reused, never rebuilt:
  - the boot/Entware fixture and the accepted native reboot bootstrap come
    from the pinned router-emulator scenario (drift-checked);
  - the Panel Lite RC4 disposable init wrapper is extracted byte-identical
    from the pinned 93/93 panel scenario JSON;
  - both IPKs are the frozen SHA-pinned artifacts (IPC lab from the 1ipc2
    build, Panel Lite RC4 from the mipsel experimental build).

The accepted Core binary is deliberately NOT installed: the only TeleMT
daemon in the guest is /opt/bin/telemt-ipc-lab, and several steps assert
/opt/bin/telemt is absent, so the panel can only be observing the IPC lab
daemon on 127.0.0.1:9091.

GUI daemon-control probe: the frozen panel ELF and upstream docs define
host.service_manager = "custom" with all four commands (telemt start/stop/
restart + panel restart) executed as direct argv (no shell), and
POST /api/telemt/stop|start returning 202 on success. The probe reconfigures
the running panel, checks GET /api/telemt/service caps, drives the IPC lab
daemon through the panel's own control endpoint and verifies the ground
truth process/socket state, then restores the proven service_manager="none"
configuration. The probe is bounded and isolated: a failure here is a
separate finding and cannot mask the joint lifecycle results that ran
before it.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from types import SimpleNamespace

IPC_NAME = "telemt-ipc-lab_3.5.17-1ipc2_mipsel-3.4.ipk"
IPC_SHA = "fbf5ef4c2cad4a564483c29a584986623181574b798ec5b787cdc93c27e15daa"
IPC_ELF_SHA = "a83caf105dd77248de43c9e096f8248ce3851b322dfe6dd59a934801344d9506"
PANEL_NAME = "telemt-panel-lite_1.0.0.rc.4-1_mipsel-3.4.ipk"
PANEL_SHA = "0236dfb076b14b129a6392de49f287838a11aebe7681e092084d4ce87e771e68"
PANEL_ELF_SHA = "380cb5112b58538eafec9ae9fab27fb22c994fd36ce3130c541c5e11b29a40c8"
PANEL_ARTIFACT_RUN = "43624729371"
IPC_ARTIFACT_RUN = "44139876820"
EMU_SHA = "64a446deaacb0bca10d6053781ff1f7ad4a29552"
MIRROR_HOST = "192.168.1.100"

IPC_BIN = "/opt/bin/telemt-ipc-lab"
PANEL_BIN = "/opt/bin/telemt-panel"
ACCEPTED_CORE_BIN = "/opt/bin/telemt"  # must never exist in this guest
PID = "/opt/var/run/telemt-ipc-lab.pid"
CTL = "/opt/var/run/telemt-ipc-lab/ctl.sock"
CONF = "/opt/etc/telemt-lab.toml"
LOG = "/opt/var/log/telemt-ipc-lab.log"
PANEL_PID = "/opt/var/run/telemt-panel-lab.pid"
PANEL_GEN = "/opt/var/run/telemt-panel-lab.gen"
PANEL_CONF = "/opt/etc/telemt-panel/config.toml"
PANEL_COOKIE = "/opt/lab/panel-cookie"
PANEL_WRAPPER = "/opt/lab/S99telemtlab-panel"
GUI_START = "/opt/lab/telemt-ipc-gui-start"
GUI_STOP = "/opt/lab/telemt-ipc-gui-stop"
GUI_RESTART = "/opt/lab/telemt-ipc-gui-restart"
PANEL_GUI_RESTART = "/opt/lab/telemt-panel-gui-restart"
PANEL_PASS = "telemt-lab-panel-synthetic-pass-01"
PANEL_URL = "http://127.0.0.1:8080"
CORE_URL = "http://127.0.0.1:9091"
LISTEN_PANEL = "0100007F:1F90 +[0-9A-F]{8}:[0-9A-F]{4} +0A "
LISTEN_CORE_API = "0100007F:2383 +[0-9A-F]{8}:[0-9A-F]{4} +0A "
LISTEN_MTPROTO = "(0100007F|00000000):0D73 +[0-9A-F]{8}:[0-9A-F]{4} +0A "


def guest_ssh(command, marker, timeout=120):
    assert marker.isupper() and marker.replace("_", "").isalnum()
    assert "\n" not in command and "\r" not in command
    # The literal marker must never appear in the echoed command itself.
    assert marker not in command
    return {"action": "ssh", "port": 8022, "send": command,
            "expect": re.escape(marker), "timeout_sec": timeout}


def marker_printf(name):
    return "printf 'IPCP_%s\\n' " + name


def gui_scripts():
    """Four direct-argv custom service commands for the panel (upstream
    schema: absolute executable, no shell, all four required)."""
    header = ("# Disposable MT7621 Entware-only custom service command for the\n"
              "# synthetic TeleMT IPC lab panel probe. Never installed on real\n"
              "# routers. Runs the pinned IPC client against the pinned control\n"
              "# socket only; no PID from any file is ever signalled.\n")
    start = header + (
        "HOME=/opt/lab /opt/bin/telemt-ipc-lab start --log-file " + LOG +
        " --pid-file " + PID + " --control-socket " + CTL + " " + CONF + "\n")
    stop = header + (
        "HOME=/opt/lab /opt/bin/telemt-ipc-lab stop --control-socket " +
        CTL + "\n")
    restart = header + (
        "/opt/lab/telemt-ipc-gui-stop || exit 1\n"
        "exec /opt/lab/telemt-ipc-gui-start\n")
    panel_restart = header + (
        "exec /opt/lab/S99telemtlab-panel restart\n")
    return {"start": start, "stop": stop, "restart": restart,
            "panel_restart": panel_restart}


def b64(text):
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def panel_config_command(service_manager_block):
    """Seed /opt/etc/telemt-panel/config.toml. service_manager_block is the
    exact [host] section body (proven "none" or the custom commands probe)."""
    return (
        "/opt/bin/busybox mkdir -p /opt/etc/telemt-panel "
        "/opt/var/lib/telemt-panel && "
        "h=$(/opt/bin/busybox printf '%s\\n' '" + PANEL_PASS +
        "' | /opt/bin/telemt-panel hash-password) && "
        "[ ${#h} -ge 50 ] && /opt/bin/busybox printf "
        "'listen = \"127.0.0.1:8080\"\\n"
        "data_dir = \"/opt/var/lib/telemt-panel\"\\n\\n"
        "[tls]\\nmode = \"http\"\\n\\n"
        "[telemt]\\nurl = \"http://127.0.0.1:9091\"\\n"
        "auth_header = \"\"\\n\\n"
        "[auth]\\nusername = \"labadmin\"\\npassword_hash = \"%s\"\\n\\n"
        "[store]\\ndriver = \"memory\"\\n\\n"
        "[host]\\n" + service_manager_block + "\\n' \"$h\" > " + PANEL_CONF +
        " && /opt/bin/busybox chmod 600 " + PANEL_CONF + " && "
        "printf 'IPCP_%s\\n' PANEL_CFG")


PANEL_HOST_NONE = 'service_manager = "none"'
# The \n sequences here are printf escapes inside the one-line guest command,
# not Python newlines.
PANEL_HOST_CUSTOM = (
    'service_manager = "custom"\\n\\n'
    '[host.commands.telemt]\\n'
    'start = ["' + GUI_START + '"]\\n'
    'stop = ["' + GUI_STOP + '"]\\n'
    'restart = ["' + GUI_RESTART + '"]\\n\\n'
    '[host.commands.panel]\\n'
    'restart = ["' + PANEL_GUI_RESTART + '"]')


def panel_wrapper_base64(panel_scenario):
    """Extract the disposable panel wrapper byte-identical from the pinned
    93/93 scenario instead of retyping it."""
    blob = None
    for step in panel_scenario.get("steps", []):
        send = step.get("send")
        if not isinstance(send, str) or "S99telemtlab-panel" not in send:
            continue
        m = re.search(r"printf '%s' '([A-Za-z0-9+/=]{200,})' \| base64 -d > "
                      r"/opt/etc/init\.d/S99telemtlab-panel", send)
        if m:
            blob = m.group(1)
            break
    if not blob:
        raise ValueError("panel wrapper not found in pinned scenario")
    text = base64.b64decode(blob).decode("utf-8")
    for needle in ("#!/bin/sh", "/opt/bin/telemt-panel",
                   "telemt-panel-lab.pid", "telemt-panel-lab.gen",
                   "panellab_main \"$@\""):
        if needle not in text:
            raise ValueError("unexpected panel wrapper content")
    return blob


def audit_ipc_ipk(emulator_root, ipk):
    sys.path.insert(0, str(emulator_root))
    from lab.mt7621 import telemt_lab as audit
    if not ipk.is_file() or ipk.stat().st_size > audit.MAX_IPK:
        raise ValueError("missing/oversize IPC lab IPK")
    raw = ipk.read_bytes()
    if hashlib.sha256(raw).hexdigest() != IPC_SHA:
        raise ValueError("MIPSLE IPC IPK SHA-256 mismatch (fail closed)")
    metadata, data = audit.ipk_parts(raw)
    if metadata != {"Package": "telemt-ipc-lab",
                    "Version": "3.5.17-1ipc2",
                    "Architecture": "mipsel-3.4"}:
        raise ValueError("unexpected lab control metadata")
    if set(data) != {"opt/bin/telemt-ipc-lab"}:
        raise ValueError("package would replace unrelated payload")
    elf = data["opt/bin/telemt-ipc-lab"]
    if hashlib.sha256(elf).hexdigest() != IPC_ELF_SHA:
        raise ValueError("MIPSLE IPC ELF SHA-256 mismatch (fail closed)")
    info = audit.elf_mips_info(elf)
    if (info["fp_abi"] != 3 or info["interp"] != "/opt/lib/ld.so.1"
            or not info["dynamic"]):
        raise ValueError("Entware MIPSLE glibc softfloat ABI mismatch")
    return {"ipk_sha256": IPC_SHA, "elf_sha256": IPC_ELF_SHA}


def audit_panel_ipk(emulator_root, ipk):
    sys.path.insert(0, str(emulator_root))
    from lab.mt7621 import telemt_lab as audit
    if not ipk.is_file() or ipk.stat().st_size > audit.MAX_IPK:
        raise ValueError("missing/oversize panel IPK")
    raw = ipk.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PANEL_SHA:
        raise ValueError("panel IPK SHA-256 mismatch (fail closed)")
    metadata, data = audit.ipk_parts(raw)
    if metadata != {"Package": "telemt-panel-lite",
                    "Version": "1.0.0~rc.4-1",
                    "Architecture": "mipsel-3.4"}:
        raise ValueError("unexpected panel metadata")
    if set(data) != {"opt/bin/telemt-panel"}:
        raise ValueError("panel package would replace unrelated payload")
    elf = data["opt/bin/telemt-panel"]
    if hashlib.sha256(elf).hexdigest() != PANEL_ELF_SHA:
        raise ValueError("panel ELF SHA-256 mismatch (fail closed)")
    return {"ipk_sha256": PANEL_SHA, "elf_sha256": PANEL_ELF_SHA}


def synthetic_file_step(config, secret):
    # No real Telegram credentials: both inputs come from pinned offline
    # router-emulator synthetic lab fixtures (proven in the 63/63 IPC run).
    # BusyBox applets used by the whole joint plan are verified here once.
    b64_config = base64.b64encode(config).decode("ascii")
    b64_secret = base64.b64encode(secret).decode("ascii")
    bb = "/opt/bin/busybox"
    applets = "base64 readlink wget sha256sum sed tr grep ls wc"
    guard = ""
    for applet in applets.split():
        guard += f"{bb} --list | {bb} grep -qx {applet} || exit 90; "
    command = (
        guard +
        f"{bb} mkdir -m 755 -p /opt/lab /opt/var/run/telemt-ipc-lab "
        "/opt/var/log /opt/etc && "
        f"{bb} chmod 700 /opt/var/run/telemt-ipc-lab && "
        f"printf '%s' '{b64_config}' | {bb} base64 -d > {CONF} && "
        f"printf '%s' '{b64_secret}' | {bb} base64 -d > "
        "/opt/etc/telemt-lab.secret && "
        f"{bb} chmod 600 {CONF} /opt/etc/telemt-lab.secret && "
        "printf 'IPCP_%s\\n' FILES_READY")
    return guest_ssh(command, "IPCP_FILES_READY")


def start_command():
    return ("HOME=/opt/lab TMPDIR=/opt/lab " + IPC_BIN +
            " start --log-file " + LOG + " --pid-file " + PID +
            " --control-socket " + CTL + " " + CONF)


def core_ready_command():
    # Detached start followed by one consolidated readiness contract: numeric
    # PID, pinned live /proc/exe identity, control socket, 2s stability.
    return (
        start_command() + " >/opt/lab/ipc-start.out 2>&1 || exit 45; "
        "i=0; seen=0; while [ \"$i\" -lt 30 ]; do "
        "[ -e " + PID + " ] && seen=1; "
        "if [ -r " + PID + " ]; then "
        "p=$(/opt/bin/busybox cat " + PID + " 2>/dev/null); "
        "case \"$p\" in ''|*[!0-9]*) ;; *) "
        "if [ -r /proc/$p/cmdline ] && "
        "[ \"$(/opt/bin/busybox readlink /proc/$p/exe 2>/dev/null)\" = '" +
        IPC_BIN + "' ] && [ -S " + CTL + " ]; then "
        "/opt/bin/busybox sleep 2; "
        "if [ -r " + PID + " ] && "
        "[ \"$(/opt/bin/busybox cat " + PID + " 2>/dev/null)\" = \"$p\" ] && "
        "[ \"$(/opt/bin/busybox readlink /proc/$p/exe 2>/dev/null)\" = '" +
        IPC_BIN + "' ]; then "
        "printf 'IPCP_%s\\n' CORE_READY; exit 0; "
        "fi; fi;; esac; fi; "
        "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
        "n=0; for d in /proc/[0-9]*; do "
        "e=$(/opt/bin/busybox readlink \"$d/exe\" 2>/dev/null); "
        "[ \"$e\" = '" + IPC_BIN + "' ] && n=$((n+1)); done; "
        "[ \"$n\" = 0 ] || exit 56; "
        "if [ -s " + LOG + " ]; then "
        "/opt/bin/busybox grep -Eqi 'panic|panicked' " + LOG + " && exit 58; "
        "/opt/bin/busybox grep -Eqi "
        "'permission denied|operation not permitted|failed to bind|"
        "address already in use' " + LOG + " && exit 59; fi; "
        "[ \"$seen\" = 0 ] || exit 57; exit 46")


def login_command(cookie_file):
    # Proven 93/93 login: extract the panel_session cookie value.
    return (
        "c=$(/opt/bin/busybox wget -qO- -S --post-data "
        "'{\"username\":\"labadmin\",\"password\":\"" + PANEL_PASS + "\"}' "
        "--header 'Content-Type: application/json' " + PANEL_URL +
        "/api/auth/login 2>&1 | /opt/bin/busybox sed -n "
        "'s/.*[Ss]et-[Cc]ookie: panel_session=\\([^;]*\\).*/\\1/p' | "
        "/opt/bin/busybox head -n 1); [ -n \"$c\" ] || exit 40; "
        "printf '%s' \"$c\" > " + cookie_file + " && "
        "/opt/bin/busybox chmod 600 " + cookie_file)


def ip_exe_count(binary):
    return ("n=0; for d in /proc/[0-9]*; do "
            "e=$(/opt/bin/busybox readlink \"$d/exe\" 2>/dev/null); "
            "[ \"$e\" = '" + binary + "' ] && n=$((n+1)); done")


def gui_probe_steps():
    """Bounded isolated GUI-control probe. Every failure exit code is
    distinct and the probe never touches the joint lifecycle steps that
    already ran before it."""
    scripts = gui_scripts()
    write_scripts = (
        "".join(f"printf '%s' '{b64(scripts[name])}' | /opt/bin/busybox "
                f"base64 -d > {path} && /opt/bin/busybox chmod 700 {path} && "
                for name, path in (("start", GUI_START), ("stop", GUI_STOP),
                                   ("restart", GUI_RESTART),
                                   ("panel_restart", PANEL_GUI_RESTART))))
    fg_validate = (
        "HOME=/opt/lab /opt/bin/telemt-panel -config " + PANEL_CONF +
        " >/opt/lab/panel-fg.out 2>&1 & fgp=$!; "
        "/opt/bin/busybox sleep 3; "
        "fg_exe=$(/opt/bin/busybox readlink /proc/$fgp/exe 2>/dev/null); "
        "if [ \"$fg_exe\" = '" + PANEL_BIN + "' ]; then "
        "kill -TERM \"$fgp\" 2>/dev/null; "
        "i=0; while [ \"$i\" -lt 5 ] && [ -r /proc/$fgp/exe ]; do "
        "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
        "kill -KILL \"$fgp\" 2>/dev/null; wait \"$fgp\"; "
        "else wait \"$fgp\"; "
        "/opt/bin/busybox grep -qi 'unknown configuration field' "
        "/opt/lab/panel-fg.out 2>/dev/null && exit 60; "
        "/opt/bin/busybox grep -Eiq 'service_manager|commands' "
        "/opt/lab/panel-fg.out 2>/dev/null && exit 61; "
        "exit 62; fi")
    gui_config = (
        write_scripts + panel_config_command(PANEL_HOST_CUSTOM)
        .replace("&& printf 'IPCP_%s\\n' PANEL_CFG", " && ") +
        "/opt/lab/S99telemtlab-panel stop || exit 63; "
        "/opt/bin/busybox rm -f " + PANEL_PID + "; " +
        fg_validate + "; " +
        "out=$(/opt/lab/S99telemtlab-panel start) || exit 63; "
        "printf '%s\\n' \"$out\"")
    gui_caps = (
        login_command(PANEL_COOKIE) + "; "
        "svc=$(/opt/bin/busybox wget -qO- --header "
        "\"Cookie: panel_session=$c\" " + PANEL_URL +
        "/api/telemt/service 2>/dev/null) || exit 64; "
        "printf '%s' \"$svc\" | /opt/bin/busybox grep -q "
        "'\"manager\":\"custom\"' || exit 65; "
        "printf '%s' \"$svc\" | /opt/bin/busybox grep -q '\"stop\":true' "
        "&& printf '%s' \"$svc\" | /opt/bin/busybox grep -q '\"start\":true' "
        "&& printf 'IPCP_%s\\n' GUI_CAPS_OK || exit 66")
    # GUI stop: POST /api/telemt/stop; 202 accepted -> daemon gone.
    gui_stop = (
        login_command(PANEL_COOKIE) + "; "
        "out=$(/opt/bin/busybox wget -qO- -S --post-data '{}' "
        "--header 'Content-Type: application/json' --header "
        "\"Cookie: panel_session=$c\" " + PANEL_URL +
        "/api/telemt/stop 2>&1); rc=$?; "
        "[ \"$rc\" = 0 ] || { "
        "printf '%s' \"$out\" | /opt/bin/busybox grep -q "
        "'manual_service_control_required' && exit 67; "
        "printf '%s' \"$out\" | /opt/bin/busybox grep -q "
        "'service_action_unconfirmed' && exit 68; "
        "printf '%s' \"$out\" | /opt/bin/busybox grep -q 'update_locked' "
        "&& exit 69; exit 70; }; "
        "ok=0; i=0; while [ \"$i\" -lt 15 ]; do "
        "[ -S " + CTL + " ] || { ok=1; break; }; "
        "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
        "[ \"$ok\" = 1 ] || exit 71; " +
        ip_exe_count(IPC_BIN) + "; [ \"$n\" = 0 ] || exit 71; "
        "pp=$(/opt/bin/busybox cat " + PANEL_PID + " 2>/dev/null); "
        "[ -n \"$pp\" ] && [ \"$(/opt/bin/busybox readlink "
        "/proc/$pp/exe 2>/dev/null)\" = '" + PANEL_BIN + "' ] || exit 72; "
        "/opt/bin/busybox wget -qO- " + PANEL_URL + "/api/health >/dev/null "
        "2>&1 || exit 72; "
        "printf 'IPCP_%s\\n' GUI_STOP_OK")
    # GUI start: POST /api/telemt/start; 202 -> pinned daemon back, panel
    # worker untouched.
    gui_start = (
        login_command(PANEL_COOKIE) + "; "
        "pp0=$(/opt/bin/busybox cat " + PANEL_PID + " 2>/dev/null); "
        "[ -n \"$pp0\" ] || exit 72; "
        "out=$(/opt/bin/busybox wget -qO- -S --post-data '{}' "
        "--header 'Content-Type: application/json' --header "
        "\"Cookie: panel_session=$c\" " + PANEL_URL +
        "/api/telemt/start 2>&1); rc=$?; "
        "[ \"$rc\" = 0 ] || { "
        "printf '%s' \"$out\" | /opt/bin/busybox grep -q "
        "'manual_service_control_required' && exit 67; "
        "printf '%s' \"$out\" | /opt/bin/busybox grep -q "
        "'service_action_unconfirmed' && exit 68; "
        "printf '%s' \"$out\" | /opt/bin/busybox grep -q 'update_locked' "
        "&& exit 69; exit 70; }; "
        "ok=0; i=0; while [ \"$i\" -lt 20 ]; do "
        "if [ -r " + PID + " ]; then "
        "p=$(/opt/bin/busybox cat " + PID + " 2>/dev/null); "
        "case \"$p\" in ''|*[!0-9]*) ;; *) "
        "[ \"$(/opt/bin/busybox readlink /proc/$p/exe 2>/dev/null)\" = '" +
        IPC_BIN + "' ] && [ -S " + CTL + " ] && { ok=1; break; };; esac; fi; "
        "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
        "[ \"$ok\" = 1 ] || exit 71; "
        "pp=$(/opt/bin/busybox cat " + PANEL_PID + " 2>/dev/null); "
        "[ \"$pp\" = \"$pp0\" ] && "
        "[ \"$(/opt/bin/busybox readlink /proc/$pp/exe 2>/dev/null)\" = '" +
        PANEL_BIN + "' ] || exit 72; "
        "/opt/bin/busybox wget -qO- " + PANEL_URL + "/api/health >/dev/null "
        "2>&1 || exit 72; "
        "printf 'IPCP_%s\\n' GUI_START_OK")
    # Restore the proven service_manager="none" configuration; the daemon
    # started through the GUI must keep running untouched. The wrapper must
    # be stopped first: an idempotent start on a live worker prints no
    # generation marker at all.
    gui_restore = (
        panel_config_command(PANEL_HOST_NONE)
        .replace("&& printf 'IPCP_%s\\n' PANEL_CFG", " && ") +
        "/opt/lab/S99telemtlab-panel stop || exit 73; "
        "out=$(/opt/lab/S99telemtlab-panel start) || exit 73; "
        "printf '%s\\n' \"$out\"; " +
        ip_exe_count(IPC_BIN) + "; [ \"$n\" = 1 ] || exit 74; "
        "[ -S " + CTL + " ] && [ -r " + PID + " ] || exit 74")
    return [
        guest_ssh_regex(gui_config, "telemtlab-panel-start gen=2 pid=[0-9]+",
                        180),
        guest_ssh(gui_caps, "IPCP_GUI_CAPS_OK", 120),
        guest_ssh(gui_stop, "IPCP_GUI_STOP_OK", 180),
        guest_ssh(gui_start, "IPCP_GUI_START_OK", 180),
        guest_ssh_regex(gui_restore,
                        "telemtlab-panel-start gen=3 pid=[0-9]+", 180),
    ]


def guest_ssh_regex(command, pattern, timeout=120):
    assert "\n" not in command and "\r" not in command
    # The echoed command must not itself match the answer pattern (checked
    # again by the emulator validator before any QEMU).
    return {"action": "ssh", "port": 8022, "send": command,
            "expect": pattern, "timeout_sec": timeout}


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
    lock = json.loads((emulator_root / "lab/entware-mipselsf.lock.json").read_text())
    found = [p for p in lock["packages"] if p.get("Package") == "busybox"]
    if (len(found) != 1 or found[0].get("Filename") !=
            "busybox_1.38.0-5_mipsel-3.4.ipk"
            or found[0].get("SHA256sum") !=
            "0ba41200b8fdd51c2b606fc92c141059350cd3da7a45233eb0174aeaea1bfa32"
            or found[0].get("Architecture") != "mipsel-3.4"):
        raise ValueError("BusyBox pin in isolated Entware mirror drifted")
    panel_path = emulator_root / "lab/scenarios/ported-mt7621-telemt-panel.json"
    panel_scenario = json.loads(panel_path.read_text(encoding="utf-8"))
    wrapper_blob = panel_wrapper_base64(panel_scenario)
    panel_text = json.dumps(panel_scenario)
    if (PANEL_NAME not in panel_text
            or "0236dfb076b14b129a6392de49f287838a11aebe7681e092084d4ce87e771e68"
            not in panel_text):
        raise ValueError("panel scenario pins drifted from frozen artifacts")

    steps = list(prefix)
    bb = "/opt/bin/busybox"
    steps.extend([
        # Self-diagnosing mirror delivery: every failure path carries a
        # distinct fixed exit code (82 HTTP 404, 83 connection failure,
        # 84 other wget failure, 85 implausible size, 86 SHA mismatch),
        # because an ssh answer mismatch with exit 0 is structurally
        # undiagnosable from the sanitized report alone.
        guest_ssh(bb + " mkdir -p /opt/lab || exit 81; "
                  bb + " rm -f /opt/lab/ipc.ipk /opt/lab/ipc.wget.err; "
                  bb + " wget -qO /opt/lab/ipc.ipk "
                  "http://" + MIRROR_HOST + "/entware/" + IPC_NAME +
                  " 2>/opt/lab/ipc.wget.err || { "
                  bb + " grep -q 404 /opt/lab/ipc.wget.err && exit 82; "
                  bb + " grep -Eqi 'refused|unreachable|timed out|"
                  "no route|network is down' /opt/lab/ipc.wget.err && "
                  "exit 83; exit 84; }; "
                  "sz=$(" + bb + " wc -c < /opt/lab/ipc.ipk | " + bb +
                  " tr -d ' '); "
                  "[ \"$sz\" -ge 1000000 ] 2>/dev/null || exit 85; "
                  "printf '%s  %s\\n' '" + IPC_SHA +
                  "' /opt/lab/ipc.ipk > /opt/lab/ipc.sha && "
                  bb + " sha256sum -c /opt/lab/ipc.sha >/dev/null || "
                  "exit 86; "
                  "printf 'IPCP_%s\\n' IPC_IPK_DELIVERED",
                  "IPCP_IPK_DELIVERED", 300),
        guest_ssh("/opt/bin/opkg install /opt/lab/ipc.ipk "
                  ">/opt/lab/ipc-opkg.log 2>&1 && "
                  "/opt/bin/opkg status telemt-ipc-lab | "
                  "/opt/bin/busybox grep -q 'Version: 3.5.17-1ipc2' && "
                  "test -x " + IPC_BIN + " && "
                  "test ! -e " + ACCEPTED_CORE_BIN + " && "
                  "printf 'IPCP_%s\\n' OPKG_SEPARATE",
                  "IPCP_OPKG_SEPARATE", 300),
        guest_ssh("printf '%s  %s\\n' '" + IPC_ELF_SHA + "' " + IPC_BIN +
                  " > /opt/lab/ipc-elf.sha && "
                  "/opt/bin/busybox sha256sum -c /opt/lab/ipc-elf.sha >/dev/null "
                  "&& printf 'IPCP_%s\\n' IPC_ELF_PINNED",
                  "IPCP_ELF_PINNED"),
        synthetic_file_step(config, secret),
        guest_ssh(core_ready_command(), "IPCP_CORE_READY", 150),
        guest_ssh(bb + " rm -f /opt/lab/panel.ipk /opt/lab/panel.wget.err; "
                  bb + " wget -qO /opt/lab/panel.ipk "
                  "http://" + MIRROR_HOST + "/entware/" + PANEL_NAME +
                  " 2>/opt/lab/panel.wget.err || { "
                  bb + " grep -q 404 /opt/lab/panel.wget.err && exit 87; "
                  bb + " grep -Eqi 'refused|unreachable|timed out|"
                  "no route|network is down' /opt/lab/panel.wget.err && "
                  "exit 88; exit 89; }; "
                  "sz=$(" + bb + " wc -c < /opt/lab/panel.ipk | " + bb +
                  " tr -d ' '); "
                  "[ \"$sz\" -ge 1000000 ] 2>/dev/null || exit 90; "
                  "printf '%s  %s\\n' '" + PANEL_SHA +
                  "' /opt/lab/panel.ipk > /opt/lab/panel.sha && "
                  bb + " sha256sum -c /opt/lab/panel.sha >/dev/null || "
                  "exit 91; "
                  "printf 'IPCP_%s\\n' PANEL_IPK_DELIVERED",
                  "IPCP_PANEL_IPK_DELIVERED", 300),
        guest_ssh("/opt/bin/opkg install /opt/lab/panel.ipk "
                  ">/opt/lab/panel-opkg.log 2>&1 && "
                  "/opt/bin/opkg status telemt-panel-lite | "
                  "/opt/bin/busybox grep -q 'Version: 1.0.0~rc.4-1' && "
                  "test -x " + PANEL_BIN + " && "
                  "test ! -e " + ACCEPTED_CORE_BIN + " && "
                  "printf 'IPCP_%s\\n' PANEL_OPKG",
                  "IPCP_PANEL_OPKG", 300),
        guest_ssh("printf '%s  %s\\n' '" + PANEL_ELF_SHA + "' " + PANEL_BIN +
                  " > /opt/lab/panel-elf.sha && cd / && "
                  "/opt/bin/busybox sha256sum -c /opt/lab/panel-elf.sha "
                  ">/dev/null && printf 'IPCP_%s\\n' PANEL_ELF_PINNED",
                  "IPCP_PANEL_ELF_PINNED"),
        guest_ssh("/opt/bin/telemt-panel version > /opt/lab/panel-version.out "
                  "2>&1; rc=$?; [ \"$rc\" = 0 ] && "
                  "/opt/bin/busybox grep -q "
                  "'telemt-panel 1.0.0-rc.4 (lite: memory)' "
                  "/opt/lab/panel-version.out && "
                  "printf 'IPCP_%s\\n' PANEL_VERSION_RC4",
                  "IPCP_PANEL_VERSION_RC4"),
        guest_ssh(panel_config_command(PANEL_HOST_NONE), "IPCP_PANEL_CFG"),
        guest_ssh_regex("printf '%s' '" + wrapper_blob + "' | /opt/bin/busybox "
                        "base64 -d > " + PANEL_WRAPPER + " && "
                        "/opt/bin/busybox chmod 700 " + PANEL_WRAPPER + " && "
                        "out=$(" + PANEL_WRAPPER + " start) || exit 1; "
                        "printf '%s\\n' \"$out\"",
                        "telemtlab-panel-start gen=1 pid=[0-9]+", 120),
        guest_ssh("pid=$(/opt/bin/busybox cat " + PANEL_PID + " 2>/dev/null); "
                  "if [ -n \"$pid\" ] && [ -r /proc/$pid/cmdline ] && "
                  "[ \"$(/opt/bin/busybox readlink /proc/$pid/exe "
                  "2>/dev/null)\" = '" + PANEL_BIN + "' ]; then "
                  "printf 'IPCP_%s\\n' PANEL_PROC_ALIVE; else exit 1; fi",
                  "IPCP_PANEL_PROC_ALIVE"),
        guest_ssh("ok=0; i=0; while [ \"$i\" -lt 15 ]; do "
                  "body=$(/opt/bin/busybox wget -qO- " + PANEL_URL +
                  "/api/health 2>/dev/null) && ok=1 && break; "
                  "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
                  "[ \"$ok\" = 1 ] || exit 1; "
                  "printf '%s\\n' \"$body\" | /opt/bin/busybox grep -q "
                  "'\"status\":\"ok\"' && printf '%s\\n' \"$body\" | "
                  "/opt/bin/busybox grep -q '\"version\":\"1.0.0-rc.4\"' && "
                  "printf '%s\\n' \"$body\" | /opt/bin/busybox grep -q "
                  "'\"variant\":\"lite\"' && "
                  "printf 'IPCP_%s\\n' PANEL_HEALTH_OK",
                  "IPCP_PANEL_HEALTH_OK", 120),
        guest_ssh("/opt/bin/busybox grep -Eq '" + LISTEN_PANEL +
                  "' /proc/net/tcp && printf 'IPCP_%s\\n' PANEL_LISTENING",
                  "IPCP_PANEL_LISTENING"),
        guest_ssh(login_command(PANEL_COOKIE) + "; "
                  "me=$(/opt/bin/busybox wget -qO- --header "
                  "\"Cookie: panel_session=$c\" " + PANEL_URL +
                  "/api/auth/me 2>/dev/null); "
                  "printf '%s\\n' \"$me\" | /opt/bin/busybox grep -q "
                  "'\"username\":\"labadmin\"' && "
                  "printf 'IPCP_%s\\n' AUTH_OK",
                  "IPCP_AUTH_OK", 120),
        guest_ssh("/opt/bin/busybox wget -qO- -S --post-data "
                  "'{\"username\":\"labadmin\",\"password\":"
                  "\"telemt-lab-panel-wrong-pass\"}' --header "
                  "'Content-Type: application/json' " + PANEL_URL +
                  "/api/auth/login > /opt/lab/panel-401.out 2>&1; rc=$?; "
                  "[ \"$rc\" != 0 ] && /opt/bin/busybox grep -q '401' "
                  "/opt/lab/panel-401.out && "
                  "printf 'IPCP_%s\\n' AUTH_NEGATIVE",
                  "IPCP_AUTH_NEGATIVE"),
        # The panel must observe the IPC lab daemon: pinned Core API on
        # 127.0.0.1:9091, daemon PID verified by /proc/exe in the same step,
        # accepted Core binary still absent.
        guest_ssh("c=$(/opt/bin/busybox cat " + PANEL_COOKIE + "); "
                  "[ -n \"$c\" ] || exit 40; "
                  "info=$(/opt/bin/busybox wget -qO- --header "
                  "\"Cookie: panel_session=$c\" " + PANEL_URL +
                  "/api/telemt/info 2>/dev/null); "
                  "printf '%s\\n' \"$info\" | /opt/bin/busybox grep -q "
                  "'\"reachable\":true' && printf '%s\\n' \"$info\" | "
                  "/opt/bin/busybox grep -q '\"version\":\"3.5.17' || exit 80; "
                  "p=$(/opt/bin/busybox cat " + PID + "); "
                  "[ \"$(/opt/bin/busybox readlink /proc/$p/exe "
                  "2>/dev/null)\" = '" + IPC_BIN + "' ] || exit 81; "
                  "test ! -e " + ACCEPTED_CORE_BIN + " || exit 82; "
                  "printf 'IPCP_%s\\n' INTEGRATION_OK",
                  "IPCP_INTEGRATION_OK"),
        # IPC reload through the control socket while the panel is serving.
        guest_ssh("p=$(/opt/bin/busybox cat " + PID + "); "
                  "HOME=/opt/lab " + IPC_BIN + " reload --control-socket " +
                  CTL + " >/opt/lab/ipc-reload.out 2>&1 || exit 1; "
                  "/opt/bin/busybox sleep 3; "
                  "[ \"$(/opt/bin/busybox cat " + PID + ")\" = \"$p\" ] && "
                  "[ -r /proc/$p/cmdline ] && "
                  "/opt/bin/busybox grep -q 'SIGHUP received' " + LOG +
                  " || exit 83; "
                  "c=$(/opt/bin/busybox cat " + PANEL_COOKIE + "); "
                  "info=$(/opt/bin/busybox wget -qO- --header "
                  "\"Cookie: panel_session=$c\" " + PANEL_URL +
                  "/api/telemt/info 2>/dev/null); "
                  "printf '%s\\n' \"$info\" | /opt/bin/busybox grep -q "
                  "'\"reachable\":true' || exit 84; "
                  "printf 'IPCP_%s\\n' RELOAD_SAME_PID",
                  "IPCP_RELOAD_SAME_PID", 150),
        # IPC stop: the panel itself must stay healthy and report the loss.
        guest_ssh("HOME=/opt/lab " + IPC_BIN + " stop --control-socket " +
                  CTL + " >/opt/lab/ipc-stop.out 2>&1 || exit 1; "
                  "i=0; while [ \"$i\" -lt 15 ]; do "
                  "test ! -S " + CTL + " && break; "
                  "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
                  "test ! -e " + CTL + " || exit 85; " +
                  ip_exe_count(IPC_BIN) + "; [ \"$n\" = 0 ] || exit 85; "
                  "pp=$(/opt/bin/busybox cat " + PANEL_PID + " 2>/dev/null); "
                  "[ \"$(/opt/bin/busybox readlink /proc/$pp/exe "
                  "2>/dev/null)\" = '" + PANEL_BIN + "' ] || exit 86; "
                  "/opt/bin/busybox wget -qO- " + PANEL_URL +
                  "/api/health >/dev/null 2>&1 || exit 86; "
                  "c=$(/opt/bin/busybox cat " + PANEL_COOKIE + "); "
                  "info=$(/opt/bin/busybox wget -qO- --header "
                  "\"Cookie: panel_session=$c\" " + PANEL_URL +
                  "/api/telemt/info 2>/dev/null); "
                  "printf '%s\\n' \"$info\" | /opt/bin/busybox grep -q "
                  "'\"reachable\":true' && exit 87; "
                  "printf 'IPCP_%s\\n' CORE_LOSS",
                  "IPCP_CORE_LOSS", 150),
        # Manual Core restart restores reachability without a panel restart.
        guest_ssh("pp0=$(/opt/bin/busybox cat " + PANEL_PID + "); " +
                  start_command() + " >/opt/lab/ipc-restart.out 2>&1 || exit 1; "
                  "i=0; while [ \"$i\" -lt 30 ]; do "
                  "test -S " + CTL + " && test -r " + PID + " && break; "
                  "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
                  "test -S " + CTL + " || exit 88; "
                  "c=$(/opt/bin/busybox cat " + PANEL_COOKIE + "); "
                  "info=$(/opt/bin/busybox wget -qO- --header "
                  "\"Cookie: panel_session=$c\" " + PANEL_URL +
                  "/api/telemt/info 2>/dev/null); "
                  "printf '%s\\n' \"$info\" | /opt/bin/busybox grep -q "
                  "'\"reachable\":true' || exit 88; "
                  "[ \"$(/opt/bin/busybox cat " + PANEL_PID + ")\" = \"$pp0\" ] "
                  "|| exit 89; "
                  "printf 'IPCP_%s\\n' CORE_RECOVERY",
                  "IPCP_CORE_RECOVERY", 150),
    ])
    steps.extend(gui_probe_steps())
    steps.extend([
        guest_ssh("HOME=/opt/lab " + IPC_BIN + " stop --control-socket " +
                  CTL + " >/opt/lab/ipc-preboot.out 2>&1 || exit 1; "
                  "i=0; while [ \"$i\" -lt 15 ]; do "
                  "test ! -S " + CTL + " && break; "
                  "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
                  "test ! -e " + CTL + " || exit 90; "
                  "/opt/lab/S99telemtlab-panel stop || exit 91; "
                  "ok=0; i=0; while [ \"$i\" -lt 5 ]; do "
                  "/opt/bin/busybox wget -qO- " + PANEL_URL +
                  "/api/health >/dev/null 2>&1 || { ok=1; break; }; "
                  "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
                  "[ \"$ok\" = 1 ] || exit 91; " +
                  ip_exe_count(IPC_BIN) + "; a=$n; " +
                  ip_exe_count(PANEL_BIN) + "; "
                  "[ \"$a\" = 0 ] && [ \"$n\" = 0 ] && "
                  "/opt/bin/busybox grep -Eq '" + LISTEN_PANEL +
                  "' /proc/net/tcp && exit 92; "
                  "/opt/bin/busybox grep -Eq '" + LISTEN_CORE_API +
                  "' /proc/net/tcp && exit 92; "
                  "/opt/bin/busybox grep -Eq '" + LISTEN_MTPROTO +
                  "' /proc/net/tcp && exit 92; "
                  "printf 'IPCP_%s\\n' PRE_REBOOT_CLEAN",
                  "IPCP_PRE_REBOOT_CLEAN", 150),
    ])
    # Reuse only the already accepted native KeeneticOS reboot bootstrap.
    reboot = baseline["steps"][21:33]
    if (len(reboot) != 12 or reboot[0]["action"] != "telnet"
            or reboot[-1].get("expect") != "MARK42"):
        raise ValueError("reboot/Entware prefix drift (fail closed)")
    steps.extend(reboot)
    steps.extend([
        guest_ssh("/opt/bin/opkg status telemt-ipc-lab | "
                  "/opt/bin/busybox grep -q 'Version: 3.5.17-1ipc2' && "
                  "/opt/bin/opkg status telemt-panel-lite | "
                  "/opt/bin/busybox grep -q 'Version: 1.0.0~rc.4-1' && "
                  "test -x " + IPC_BIN + " && test -x " + PANEL_BIN + " && "
                  "test ! -e " + CTL + " && "
                  "[ \"$(/opt/bin/busybox cat " + PANEL_GEN + " 2>/dev/null)\" "
                  "= 3 ] && "
                  "n=0; for f in /opt/etc/init.d/*; do "
                  "case \"$f\" in *telemt*) n=$((n+1));; esac; done; "
                  "[ \"$n\" = 0 ] && " +
                  ip_exe_count(IPC_BIN) + "; a=$n; " +
                  ip_exe_count(PANEL_BIN) + "; "
                  "[ \"$a\" = 0 ] && [ \"$n\" = 0 ] && "
                  "printf 'IPCP_%s\\n' REBOOT_NO_AUTOSTART",
                  "IPCP_REBOOT_NO_AUTOSTART", 180),
        guest_ssh(start_command() + " >/opt/lab/ipc-reboot-start.out 2>&1 "
                  "|| exit 1; "
                  "i=0; while [ \"$i\" -lt 30 ]; do "
                  "test -S " + CTL + " && test -r " + PID + " && break; "
                  "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
                  "test -S " + CTL + " && "
                  "printf 'IPCP_%s\\n' REBOOT_CORE_START",
                  "IPCP_REBOOT_CORE_START", 150),
        guest_ssh_regex("out=$(" + PANEL_WRAPPER + " start) || exit 1; "
                        "printf '%s\\n' \"$out\"",
                        "telemtlab-panel-start gen=4 pid=[0-9]+", 120),
        guest_ssh("c=$(/opt/bin/busybox wget -qO- -S --post-data "
                  "'{\"username\":\"labadmin\",\"password\":\"" + PANEL_PASS +
                  "\"}' --header 'Content-Type: application/json' " +
                  PANEL_URL + "/api/auth/login 2>&1 | /opt/bin/busybox sed -n "
                  "'s/.*[Ss]et-[Cc]ookie: panel_session=\\([^;]*\\).*/\\1/p' | "
                  "/opt/bin/busybox head -n 1); [ -n \"$c\" ] || exit 40; "
                  "info=$(/opt/bin/busybox wget -qO- --header "
                  "\"Cookie: panel_session=$c\" " + PANEL_URL +
                  "/api/telemt/info 2>/dev/null); "
                  "printf '%s\\n' \"$info\" | /opt/bin/busybox grep -q "
                  "'\"reachable\":true' || exit 93; "
                  "p=$(/opt/bin/busybox cat " + PID + "); "
                  "[ \"$(/opt/bin/busybox readlink /proc/$p/exe "
                  "2>/dev/null)\" = '" + IPC_BIN + "' ] || exit 94; "
                  "pp=$(/opt/bin/busybox cat " + PANEL_PID + "); "
                  "[ \"$(/opt/bin/busybox readlink /proc/$pp/exe "
                  "2>/dev/null)\" = '" + PANEL_BIN + "' ] || exit 94; "
                  "printf 'IPCP_%s\\n' REBOOT_INTEGRATION",
                  "IPCP_REBOOT_INTEGRATION", 150),
        guest_ssh("HOME=/opt/lab " + IPC_BIN + " stop --control-socket " +
                  CTL + " >/opt/lab/ipc-reboot-stop.out 2>&1 || exit 1; "
                  "i=0; while [ \"$i\" -lt 15 ]; do "
                  "test ! -S " + CTL + " && break; "
                  "/opt/bin/busybox sleep 1; i=$((i+1)); done; "
                  "test ! -e " + CTL + " || exit 95; "
                  "/opt/lab/S99telemtlab-panel stop || exit 95; " +
                  ip_exe_count(IPC_BIN) + "; a=$n; " +
                  ip_exe_count(PANEL_BIN) + "; "
                  "[ \"$a\" = 0 ] && [ \"$n\" = 0 ] && "
                  "printf 'IPCP_%s\\n' REBOOT_STOP_CLEAN",
                  "IPCP_REBOOT_STOP_CLEAN", 150),
        guest_ssh("/opt/bin/opkg remove telemt-ipc-lab "
                  ">/opt/lab/ipc-remove.out 2>&1 && "
                  "/opt/bin/opkg remove telemt-panel-lite "
                  ">/opt/lab/panel-remove.out 2>&1 && "
                  "test ! -e " + IPC_BIN + " && test ! -e " + PANEL_BIN + " && "
                  "test ! -e " + ACCEPTED_CORE_BIN + " && "
                  "test ! -e " + CTL + " && "
                  "/opt/bin/busybox rm -rf /opt/etc/telemt-panel "
                  "/opt/var/lib/telemt-panel /opt/var/run/telemt-ipc-lab "
                  "/opt/lab && "
                  "printf 'IPCP_%s\\n' ROLLBACK_OK",
                  "IPCP_ROLLBACK_OK", 150),
    ])
    return {"name": "Ported MT7621 joint TeleMT IPC 3.5.17-1ipc2 + Panel Lite "
                    "1.0.0-rc.4 acceptance (SHA-pinned frozen artifacts only)",
            "evidence": "KEENETIC_PORTED_EXPERIMENTAL", "steps": steps}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emulator-root", required=True)
    ap.add_argument("--ipk-dir", required=True)
    ap.add_argument("--panel-ipk-dir", required=True,
                    help="directory holding the frozen Panel Lite RC4 IPK")
    ap.add_argument("--workspace", help="fresh private workspace")
    ap.add_argument("--entware-cache", help="verified cache outside fresh private workspace")
    ap.add_argument("--nand-dir")
    ap.add_argument("--credentials-file")
    ap.add_argument("--max-seconds", type=int, default=2400)
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args()
    root = Path(args.emulator_root).resolve()
    ipc_ipk = Path(args.ipk_dir) / IPC_NAME
    panel_ipk = Path(args.panel_ipk_dir) / PANEL_NAME
    ipc_summary = audit_ipc_ipk(root, ipc_ipk)
    panel_summary = audit_panel_ipk(root, panel_ipk)
    plan = scenario_for(root)
    steps = plan["steps"]
    if not 60 <= len(steps) <= 75:
        raise ValueError("joint scenario step count drifted")
    labels = [s.get("expect") for s in steps]
    required = [
        "IPCP_IPK_DELIVERED", "IPCP_OPKG_SEPARATE", "IPCP_ELF_PINNED",
        "IPCP_FILES_READY", "IPCP_CORE_READY", "IPCP_PANEL_IPK_DELIVERED",
        "IPCP_PANEL_OPKG", "IPCP_PANEL_ELF_PINNED", "IPCP_PANEL_VERSION_RC4",
        "IPCP_PANEL_CFG", "IPCP_PANEL_PROC_ALIVE", "IPCP_PANEL_HEALTH_OK",
        "IPCP_PANEL_LISTENING", "IPCP_AUTH_OK", "IPCP_AUTH_NEGATIVE",
        "IPCP_INTEGRATION_OK", "IPCP_RELOAD_SAME_PID", "IPCP_CORE_LOSS",
        "IPCP_CORE_RECOVERY", "IPCP_GUI_CAPS_OK", "IPCP_GUI_STOP_OK",
        "IPCP_GUI_START_OK", "IPCP_PRE_REBOOT_CLEAN",
        "IPCP_REBOOT_NO_AUTOSTART", "IPCP_REBOOT_CORE_START",
        "IPCP_REBOOT_INTEGRATION", "IPCP_REBOOT_STOP_CLEAN",
        "IPCP_ROLLBACK_OK",
    ]
    if not all(labels.count(marker) == 1 for marker in required):
        raise ValueError("joint lifecycle probes must appear exactly once each")
    order = [labels.index(m) for m in required]
    if order != sorted(order):
        raise ValueError("joint lifecycle probes are out of order")
    gen_labels = [m for m in labels
                  if m and m.startswith("telemtlab-panel-start gen=")]
    if gen_labels != ["telemtlab-panel-start gen=%d pid=[0-9]+" % g
                      for g in (1, 2, 3, 4)]:
        raise ValueError("panel wrapper generations drifted")
    sends = [s.get("send", "") for s in steps]
    if sum("test ! -e " + ACCEPTED_CORE_BIN in s for s in sends) < 3:
        raise ValueError("accepted-Core absence must be asserted repeatedly")
    for s in sends:
        if "kill" in s and "telemt-ipc-lab.pid" in s:
            raise ValueError("the IPC daemon is never signalled via a PID file")
    # The emulator's real scenario validator must run *before* any QEMU.
    import tempfile
    from lab.run import load_scenario
    with tempfile.TemporaryDirectory(prefix="telemt-ipc-panel-scenario-") as td:
        candidate = Path(td) / "scenario.json"
        candidate.write_text(json.dumps(plan), encoding="utf-8")
        load_scenario(candidate)
    if args.plan_only:
        print(json.dumps({"status": "PINNED_JOINT_GUEST_PLAN_PASS",
                          "step_count": len(steps),
                          "ipc_ipk_sha256": ipc_summary["ipk_sha256"],
                          "ipc_elf_sha256": ipc_summary["elf_sha256"],
                          "panel_ipk_sha256": panel_summary["ipk_sha256"],
                          "panel_elf_sha256": panel_summary["elf_sha256"]},
                         sort_keys=True))
        return 0
    if not (args.workspace and args.nand_dir and args.credentials_file):
        ap.error("guest run requires --workspace, --nand-dir, --credentials-file")
    workspace = Path(args.workspace)
    workspace.mkdir(mode=0o700, exist_ok=False)
    credentials = json.loads(Path(args.credentials_file).read_text(encoding="utf8"))
    if credentials.get("username") != "root":
        raise ValueError("root-only disposable guest SSH credential contract")
    scenario_file = workspace / "joint-scenario.json"
    scenario_file.write_text(json.dumps(plan), encoding="utf8")
    sys.path.insert(0, str(root))
    from lab.build_entware import build
    from lab.mirror import Mirror
    from lab.run import run
    lock = root / "lab/entware-mipselsf.lock.json"
    image, mirror = workspace / "opt.img", workspace / "mirror"
    if args.entware_cache:
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
    shutil.copyfile(ipc_ipk, mirror / "entware" / IPC_NAME)
    shutil.copyfile(panel_ipk, mirror / "entware" / PANEL_NAME)
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
