# Joint MT7621 acceptance: TeleMT IPC 3.5.17-1ipc2 + Panel Lite 1.0.0-rc.4

Research document for Draft PR #59 (`research/telemt-ipc-panel-joint-20261117`).
Timezone of every timestamp: Europe/Moscow (UTC+3), grounded in GitHub
Actions timestamps. Session of 17.11.2026, ~22:15 → (closing time below).

## 1. Question

The two frozen artifacts were each accepted separately on the guest:

- TeleMT IPC lab `telemt-ipc-lab_3.5.17-1ipc2` — 63/63 PASS, run
  [44154378735](https://github.com/saymer-alt/entware-go/actions/runs/44154378735)
  (17.11.2026, 22:03–22:11 МСК, PR #58);
- Panel Lite RC4 `telemt-panel-lite_1.0.0.rc.4-1` — 93/93 PASS against the
  accepted Core 3.5.17-2fb1, router-emulator PR #96 scenario
  `lab/scenarios/ported-mt7621-telemt-panel.json`.

Nothing had proven that the panel works against the **IPC lab daemon**
instead of the accepted Core, that the IPC reload/stop/restart lifecycle
survives with a live panel client, or whether Panel Lite RC4 can actually
*control* the daemon from its GUI. This document closes exactly those gaps
with one bounded QEMU-system MT7621 (kernel 4.9) cycle.

## 2. Frozen artifacts (read-only, nothing rebuilt)

| Artifact | Value |
|---|---|
| IPC IPK | `telemt-ipc-lab_3.5.17-1ipc2_mipsel-3.4.ipk`, SHA-256 `fbf5ef4c2cad4a564483c29a584986623181574b798ec5b787cdc93c27e15daa`, artifact run 44139876820 |
| IPC ELF | SHA-256 `a83caf105dd77248de43c9e096f8248ce3851b322dfe6dd59a934801344d9506` |
| Panel IPK | `telemt-panel-lite_1.0.0.rc.4-1_mipsel-3.4.ipk`, SHA-256 `0236dfb076b14b129a6392de49f287838a11aebe7681e092084d4ce87e771e68`, artifact run 43624729371 |
| Panel ELF | SHA-256 `380cb5112b58538eafec9ae9fab27fb22c994fd36ce3130c541c5e11b29a40c8` |
| Emulator | router-emulator `64a446deaacb0bca10d6053781ff1f7ad4a29552` (unchanged checkout, identity asserted in CI) |

Both IPKs are downloaded in CI from the existing successful runs
(`actions/download-artifact@v4`) and re-verified by SHA before use. The
host-side auditor (`mt7621_ipc_panel_guest.py`) additionally parses each
IPK (metadata + payload set + ELF SHA), fail-closed.

**Attribution guard:** the accepted Core binary `/opt/bin/telemt` is never
installed; several steps assert `test ! -e /opt/bin/telemt`, so the only
TeleMT daemon in the guest is `/opt/bin/telemt-ipc-lab` on 127.0.0.1:9091,
and the panel's `[telemt] url` can only be observing it. The daemon PID is
re-verified through `/proc/<pid>/exe` in the same steps that read
`/api/telemt/info`.

## 3. Scenario shape (65 steps)

`mt7621_ipc_panel_guest.py` builds the plan at run time:

1. **Boot/Entware prefix (steps 0–20):** copied unchanged from the pinned
   emulator scenario `lab/scenarios/ported-mt7621-telemt.json` with a
   drift check (boot serial probes, MARK42, `opkg disk KASOPT:/`).
2. **IPC lab (21–25):** IPK download + SHA, opkg install (`3.5.17-1ipc2`,
   `test ! -e /opt/bin/telemt`), ELF SHA, synthetic loopback config +
   secret from the pinned fixtures (`telemt-lab.toml`, `telemt-lab.secret`,
   BusyBox applet guard), detached start with the proven opt-in
   `--control-socket` and one consolidated readiness contract (numeric PID,
   pinned `/proc/exe`, control socket, 2 s stability).
3. **Panel Lite RC4 (26–34):** IPK download + SHA, opkg install
   (`1.0.0~rc.4-1`, accepted Core re-checked absent), ELF SHA, `version`
   banner (`telemt-panel 1.0.0-rc.4 (lite: memory)`), config seeding
   (`service_manager = "none"`, memory store, synthetic bcrypt auth,
   `url = "http://127.0.0.1:9091"`), wrapper start.
4. **Joint HTTP integration (35–40):** wrapper start gen=1 (the disposable
   init wrapper is extracted **byte-identical** from the pinned 93/93 panel
   scenario JSON — no retyping), worker exe check, `/api/health`
   (`status/ok`, `1.0.0-rc.4`, `variant/lite`), 8080 LISTEN check, login +
   `/api/auth/me`, wrong-password 401, `/api/telemt/info`
   (`reachable:true`, `version 3.5.17…`, daemon exe re-verified).
5. **Joint lifecycle (38–40):** IPC `reload` via control socket → same PID,
   `SIGHUP received` in the log, panel still sees `reachable:true`; IPC
   `stop` → daemon gone, panel stays healthy and stops reporting
   `reachable:true`; manual restart → `reachable:true` restored with the
   panel worker PID unchanged.
6. **GUI-control probe (41–45):** isolated, bounded, always restores the
   proven configuration afterwards (see §4).
7. **Pre-reboot clean stop (46):** client stop + wrapper stop, no
   `telemt-ipc-lab` / `telemt-panel` processes, no listeners on
   8080/9091/3443.
8. **Native reboot (47–58):** the already accepted KeeneticOS reboot
   bootstrap (12 steps, telnet + serial, drift-checked) — Entware persists.
9. **After reboot (59–64):** both packages present with pinned versions, no
   processes/sockets, no `/opt/etc/init.d/S99*telemt*` scripts, wrapper
   generation still 3 (proves nothing auto-started); separate manual starts
   of the daemon (socket ready) and the panel (gen=4); fresh login +
   `reachable:true`; clean stop of both; `opkg remove` of both packages +
   lab cleanup (binaries, socket, lab directories gone).

The sanitized report exports only `{action, outcome, elapsed_seconds}` per
step; every failure path uses a distinct fixed SSH exit code; no raw logs,
configs, or secrets leave the guest; the daemon is never signalled via any
PID file (host-side plan check).

## 4. GUI daemon control from Panel Lite RC4 (research)

**Static evidence from the frozen RC4 ELF** (`opt/bin/telemt-panel`,
strings) plus upstream docs (`docs/CONFIG.md`, `docs/SERVICE_CONTROL.md`,
`internal/httpapi/service_control.go` of the unmodified upstream binary):

- `host.service_manager` enum: `auto | systemd | openrc | procd | sysvinit
  | docker | custom | none` (error string in the binary; `none` disables
  managed operations — the 93/93 scenario used `none`).
- Control endpoints exist in RC4: `POST /api/telemt/start`,
  `POST /api/telemt/stop`, `POST /api/telemt/reload`,
  `POST /api/telemt/restart`, `GET /api/telemt/service` (caps +
  `manual_commands` + `busy`).
- Custom mode requires **all four** commands as direct argv (no shell):
  `[host.commands.telemt] start/stop/restart` + `[host.commands.panel]
  restart`; first element absolute executable; up to 64 elements × 4096 B;
  `service restart requires host.service_manager = custom`;
  `host.commands: cannot be used with host.service_manager %q`;
  `host.panel_service: must differ from host.telemt_service for custom
  commands` (defaults `telemt` / `telemt-panel` already differ).
- POST semantics (upstream `service_control.go`): success = **202 Accepted**
  (empty body, no confirm token); failures: 502
  `service_action_unconfirmed` (the command ran and exited non-zero), 503
  `manual_service_control_required` (caps disabled), 409 `update_locked`.
  The audit codes `telemt.stop.unconfirmed` / `telemt.start.unconfirmed`
  in the binary are failure-path codes, not a confirm protocol.
- Start/stop caps additionally require the telemt and panel service
  bindings to differ and a `ServiceController` manager (custom qualifies);
  privileges `auto` resolves to direct as root.

**Guest probe (bounded, isolated):** the panel is reconfigured with
`service_manager = "custom"` and four wrapper scripts
(`/opt/lab/telemt-ipc-gui-{start,stop,restart}`,
`/opt/lab/telemt-panel-gui-restart`) that only drive the pinned IPC client
against the pinned control socket. The step sequence: config v2 seeded →
wrapper stopped → bounded foreground validation of the new config (direct
child, verified exe, TERM after 3 s; distinct exit codes for config
rejection classes) → wrapper start (gen=2) → fresh login →
`GET /api/telemt/service` must show `"manager":"custom"` and
`"stop":true`/`"start":true` caps → `POST /api/telemt/stop` → ground truth
(exe count 0, socket gone, panel worker untouched and healthy) →
`POST /api/telemt/start` → ground truth (pinned exe, socket, panel PID
unchanged) → config restored to the proven `service_manager = "none"`,
wrapper restarted (gen=3), daemon — the one the GUI started — still alive.
Every probe failure is a distinct fixed exit code and cannot mask the
lifecycle results that ran before it.

## 5. Result: **BLOCKED** — the joint guest lifecycle was not reached

Both authorized guest cycles failed deterministically at the **first
mirror-delivery step** (plan index 21, `IPCP_IPK_DELIVERED`), before any
joint step executed. Everything before it passed identically twice:

| Plan step | Main run | Corrective run |
|---|---|---|
| 0–14 boot serial/telnet | PASS | PASS |
| 15–20 Entware baseline (`opkg`, `bash`, `MARK42`) | PASS (0.32–1.91 s) | PASS (0.34–1.22 s) |
| **21 first IPK delivery (mirror wget + SHA)** | **FAIL `ssh_answer_mismatch`, 1.0 s** | **FAIL `ssh_answer_mismatch`, 0.87 s** |

The signature — SSH exit status **0** with **no marker in the output** —
is structurally impossible for any in-guest execution of the step's
command: every internal failure mode is mapped to a fixed nonzero exit
(81 mkdir, 82 HTTP 404, 83 connection failure, 84 other wget failure,
85 implausible size, 86 SHA mismatch), so a guest-side failure would
have surfaced as `ssh_exit_nonzero_N`. An early `&&`-chain break cannot
yield exit 0, and a full successful delivery was measurably too fast
(1.0/0.87 s vs 2.16 s for the same step shape in the accepted run 16).
Therefore the guest shell did not execute the step's command.

### Evidence-based exclusion

- **Mirror 404 — excluded:** `lab/mirror.py` builds its file table from
  the actual mirror directory *after* both IPKs are copied and raises on
  anything irregular; the requested file name is byte-identical to the
  one served in the accepted run 16.
- **wget failure classes — excluded:** all are classified (82/83/84) and
  nonzero; a hung connection would end in `TimeoutError`, not mismatch.
- **In-guest command semantics — excluded:** identical constructs
  (`&&` chains, `|| { … }`, `$()`, pipes, two-space `printf` formats)
  passed 63 times in run 16 and six times in each new run's baseline.
- **Runner code, emulator code, image build process, Entware inputs
  (SHA-verified), firmware assets (SHA-pinned), credentials mechanism —
  identical** to the accepted run lineage (emulator pinned at
  `64a446d`, plan validated by the same `load_scenario`).

### Remaining hypothesis (primary suspect)

The only component **not** pinned across the two lineages is the
**QEMU-system-mipsel binary**. The guest workflow caches it under a
branch-scoped key: the run-15/16 binary (used by the accepted 63/63 run)
was saved on the PR #58 branch and is **not visible** to the PR #59
branch, so the main run rebuilt QEMU from source (the corrective run
reused that rebuilt binary via the now-populated cache, reproducing the
failure deterministically). A build-time difference in this QEMU — not
in any pinned input — is the leading hypothesis for a step whose command
never reached the guest shell; the mechanism (why the exec channel
reports exit 0 with no output instead of a transport error) requires
UART-level visibility to resolve.

## 6. Run record

| Run | Head | МСК (GitHub timestamps) | Result |
|---|---|---|---|
| [44166116031](https://github.com/saymer-alt/entware-go/actions/runs/44166116031) | `ccd505d` | 23:08:33 → 23:17:12 | FAIL 21/22 recorded steps — first mirror-delivery step |
| [44170228781](https://github.com/saymer-alt/entware-go/actions/runs/44170228781) | `6eb7494` | 23:31:40 → 23:37:45 | FAIL, identical signature, at the same step |

- Scenario SHA: entware-go `6eb7494` (PR #59 head; plan builder
  `docs/research/telemt-control-ipc/mt7621_ipc_panel_guest.py`, 65 steps,
  validated by the pinned emulator's `load_scenario` + host-side audits).
- Emulator: `64a446deaacb0bca10d6053781ff1f7ad4a29552` (asserted in CI).
- IPK hashes: both artifact downloads re-verified host-side against the
  frozen pins before every run (`PINNED_FROZEN_IPKS: PASS`); the
  guest-side `sha256sum` step never executed (blocked at step 21).
- Both runs' sanitized evidence: artifact
  `telemt-ipc-panel-mt7621-guest-evidence` (report.json + junit.xml).
- Budget discipline: 2/2 authorized QEMU cycles used; per the task rules
  no further guest runs were started; the one-shot label was removed
  after each run.

### Guest-side statuses (all NOT_TESTED — blocked at step 21)

панель HTTP: NOT_TESTED · авторизация: NOT_TESTED · Core API через
панель: NOT_TESTED · IPC reload/stop: NOT_TESTED · восстановление связи:
NOT_TESTED · reboot: NOT_TESTED · rollback: NOT_TESTED · GUI-управление
Core: **static research complete (§4), guest probe NOT_TESTED**.

## 7. KN-1010 instruction addendum (static part only)

Until the joint guest acceptance completes, do **not** install both lab
packages together on KN-1010. The static findings that are already
actionable:

1. Panel Lite RC4 can drive the IPC lab daemon through its **existing**
   interface — no panel rewrite is needed:
   - `[host] service_manager = "custom"` with all four commands
     (`[host.commands.telemt] start/stop/restart` +
     `[host.commands.panel] restart`), each an argv array whose first
     element is an absolute executable; no shell features.
   - For the IPC lab the start/stop/restart commands are simply the
     pinned client invocations
     (`/opt/bin/telemt-ipc-lab start --log-file … --pid-file …
     --control-socket <ctl> /opt/etc/telemt-lab.toml`,
     `… stop --control-socket <ctl>`), which is exactly what the blocked
     guest probe would have verified.
   - GUI buttons hit `POST /api/telemt/stop|start|restart` → **202** on
     success; 502 `service_action_unconfirmed` = the command exited
     non-zero; 503 `manual_service_control_required` = the four commands
     are not configured; 409 `update_locked` = another operation in
     flight. Status stays "unknown" (no status command is defined for
     custom managers) — the panel still shows Core reachability via
     `/api/telemt/info`.
2. The panel must point at the IPC lab daemon's API
   (`[telemt] url = "http://127.0.0.1:9091"`); with the IPC lab installed
   there is no `/opt/bin/telemt`, so there is nothing else to bind 9091.
3. GUI control is a *capability*, not yet an *accepted fact*: the guest
   probe that would have proven stop/start ground truth is NOT_TESTED
   (§5). Treat GUI-based daemon control as unverified until a guest run
   (or a KN-1010 trial by the owner) confirms it.

**Recommended next step for the owner:** make the verified QEMU binary
from the run-15/16 lineage visible to this branch (e.g., re-tag a one-shot
run from the PR #58 branch scope, or pin the QEMU binary SHA-256 produced
by `lab/mt7621/build_qemu_mipsel.sh` as an explicit CI gate), then spend
one corrective cycle on PR #59. The self-diagnosing delivery steps (81–91)
will either pass through or pinpoint the layer.
