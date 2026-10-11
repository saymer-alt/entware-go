# WDTT standalone laboratory build

## ⚠️⚠️⚠️ ЛИЧНЫЙ НЕКОММЕРЧЕСКИЙ ПРОЕКТ / ПУБЛИЧНЫЙ ТЕСТ ⚠️⚠️⚠️

**Проект владелец ведёт прежде всего для себя, на некоммерческой основе. Репозиторий открыт публично. Лабораторные сборки и IPK для РУЧНОГО тестирования можно скачать, но они НЕ ГОТОВЫ К РАБОТЕ В PRODUCTION.**

Некоммерческое назначение проекта **не отменяет** лицензии upstream и зависимостей; неизвестный объём разрешений не считается автоматически разрешённым. Лицензионная атрибуция требует отдельной проверки. Все существующие сборки/релизы Mihomo, WARPSCOUT и Beszel Agent работают по своим независимым правилам и не должны останавливаются из-за WDTT. В WDTT нет разрешения на автопубликацию пакетов в общий `latest`.

Development base: `gh-action-build`. This directory is the only WDTT build location; no new repository, no use of retired mihomo-auto-build.

Source: [hoaxisr/proxy-turn-vk-android](https://github.com/hoaxisr/proxy-turn-vk-android/tree/1110a75f76e42c23149b8e24f9182c1ff179e515), exact SHA `1110a75f76e42c23149b8e24f9182c1ff179e515`, go_client plus maintained patches and lab overlay. Client go.mod/go.sum hashes are locked. The fixture server uses the **client module graph** to include Pion TURN and netstack; this is not a production server module lock.

Compiler: unmodified Go1.26.1 from existing [Entware SDK v2026.07.04](https://github.com/ownik/entware-sdk/releases/tag/v2026.07.04), archive SHA256 `d51f30c126425ebff203b107a1a0aa9d3a5844f6c481bc6ff4c117cadc208674`. No setup-go, SDK/toolchain upgrade, GOTOOLCHAIN=auto, dynamic upstream tag or upstream install script. CGO=0; GOMIPS=softfloat; readonly modules + sum.golang.org; trimpath and empty buildid. Extraction uses SDK compiler directly for this gated static-binary experiment; an SDK feed Makefile and installable package are not claimed.

## Build-only CI

[build-wdtt-lab.yml](../.github/workflows/build-wdtt-lab.yml) supports workflow_dispatch and PRs to gh-action-build. Contents permission is read-only. It uploads reproducibility evidence and an **explicitly experimental, downloadable tar.gz containing the four lab ELF binaries**, SHA256SUMS, warning README, preliminary upstream notices and dependency inventory. It **does not** create IPKs, GitHub Releases, publish to `latest` or submit to the Entware feed. A new workflow may not be manually dispatchable until present on the default branch; use the PR run while merge is forbidden. Do not change the default branch or merge to work around this restriction.

```sh
# Download and SHA256-verify the SDK as shown in the workflow, extract host/go.
python3 wdtt/build_lab.py --go /absolute/sdk/staging_dir/host/go/bin/go \
  --sdk-archive /absolute/sdk.tar.zst --work /absolute/fresh-build-directory
python3 wdtt/test_packaging.py
```

Builds Linux AMD64 (local functional tests), AArch64, MIPSel and MIPS BE. ELF machine/endian and absence of PT_INTERP are checked. MIPS Go build metadata must say softfloat. Native/QEMU -h checks verify startup and the narrow standalone CLI, **not target hardware, kernel support, RAM or full ABI acceptance**. All build and overlay/source/lock digests are recorded in build-report.json. Reproducibility across independent hosts is still an acceptance item.

## ⚠️⚠️⚠️ СКАЧИВАЕМЫЕ ЛАБОРАТОРНЫЕ СБОРКИ — НЕ ДЛЯ PRODUCTION ⚠️⚠️⚠️

**СКАЧАТЬ МОЖНО. ЭТО НЕ ГОТОВЫЙ УСТАНОВЩИК И НЕ ПРОЙДЕННЫЙ ДОПУСК НА KEENETIC.**

После успешного PR-run: экспериментальные бинарники в `WDTT-EXPERIMENTAL-NOT-FOR-PRODUCTION`; IPK ARM64/MIPSel в **`WDTT-OWNER-TEST-IPK-NOT-PRODUCTION`**. Оба скачиваются из Artifacts, не из Releases и не из Entware feed. Не запускать opkg install, пока preflight не подтвердил ABI и владелец не согласовал эксперимент. Дальше: после успешного PR-run откройте [PR #10](https://github.com/saymer-alt/entware-go/pull/10) → **Checks / Actions → завершённый запуск → Artifacts** и скачайте `WDTT-EXPERIMENTAL-NOT-FOR-PRODUCTION`. Внутри находится `wdtt-EXPERIMENTAL-OWNER-TEST-BINARIES.tar.gz`; прочитайте `README-FIRST-EXPERIMENTAL.md` до извлечения и запуска ELF. При необходимости скачивание Actions artifacts требует входа в GitHub. Каждый архив содержит `SHA256SUMS`, исходный build-report, имеющиеся upstream notices и инвентаризацию зависимостей.

Порядок проверки: сначала read-only preflight KAS #125, затем проверка совпадения SHA256 и ABI; запускать только на согласованном **изолированном** тестовом устройстве. Для KN-1010 нужен бинарник `wt-client-linux-mipsle`, но лишь если реальный preflight подтвердит Entware little-endian softfloat. Для KN-4210 не предполагать ARM64 без проверки. Не запускать из CI-архива неизвестные конфиги, не вводить реальные секреты и не менять работающие службы.

**Юридический статус не подтверждён:** отсутствие корневого LICENSE у pinned `fhttp@v0.6.8` и неполнота notice/scope review не означают технической ошибки компиляции, но крупное предупреждение **не заменяет** реальные разрешения и обязательные copyright/license notices. Не представлять этот архив как одобренный для публичного распространения. См. [EXPERIMENTAL-DOWNLOAD-WARNING.md](EXPERIMENTAL-DOWNLOAD-WARNING.md). Выполнить review параллельно с тестированием.

**Production IPK emission остаётся заблокированным** `release-gates.json`; но отдельная упаковка **доступных для скачивания owner-test IPK ARM64/MIPSel** разрешена как лабораторная функция, без init.d/postinst/автозапуска, с предупреждениями и SHA256. В рабочих пакетных лентах и общем `latest` изменений нет. Entware init, reboot/rollback и реальный VK TURN пока не приняты. Возможность скачать ELF для предварительного аппаратного CLI-теста не означает разрешения на установку/IPK или эксплуатацию VPN.

## Security boundary

The lab entry point accepts only `-config-file /absolute/private/client.json` and help. Legacy secret argv flags, AWGM socket/log/protocol, RAW, socks, hash-check and interactive STDIN are unavailable. Password, call hash and account credentials come from owner-only regular 0600 files in non-symlink 0700 directories; wrong mode/UID/hardlink/symlink is rejected. Parent ancestors and privileged same-UID/root attackers are outside this file-permission boundary. Do not put secrets in filenames, environment or shell history; the program does not consume secret environment variables.

Upstream stdout, stderr, STDIN and core dumps are disabled before execution. This also suppresses HTTP error bodies, cookies, captcha protocol and vendor loggers; it deliberately removes upstream diagnostics rather than claiming a universal redactor. Only fixed status codes are written. Received WG config and captcha profiles use atomic 0600 writes within the private runtime directory. No plaintext config event or private key is printed. Account credential refresh is not unattended-ready; sessions are capped at 30 minutes. Treat runtime directory as private volatile storage, never a public report directory.

UDP bind is exclusive (upstream SO_REUSEADDR removed). Port/config/auth failures terminate with78; temporary worker failures have exponential backoff and a five-attempt bound, exit75 when exhausted. No router TUN or AWG Manager daemon is required for vpn mode. The linked awgmproto library remains MIT, with notice retained; control sockets are never initialized in this profile.

`CONFIG_READY` is only a file event. The local test also waits for `WORKER_REGISTERED`, emitted after UDP dispatcher registration, before starting the application. Neither event proves WG connectivity: the test separately requires handshake/counters and successful TCP/UDP. First CI run38146507134 built every architecture but failed the first TCP request with curl52 after GETCONF. Startup timing was a hypothesis; the explicit registration gate and separate literal-IP/DNS probes preserve that distinction rather than treating a config file as readiness.

Server patch020 requires AUTH password + known/bound device, and rejects unapproved first packets/failed GETCONF before UDP forwarding. The unchanged upstream fails three local negative tests; patched handler passes those plus the positive test. WRAP key to credential binding, revocation of already-active connections, persistent server files, TCP API, Telegram and startup side effects still need production review. A local AUTH test is not a complete server security audit.

## Local functional PoC

`lab/server_pair_fixture_test.go` is opt-in, loopback-only: Pion TURN, actual patched upstream WRAP/DTLS/GETCONF/AUTH handler, userspace WG netstack and private synthetic keys. It never invokes server main, OS TUN, routes, NAT, sysctl, Telegram or control API. `local_pair.py` connects the actual standalone client and Mihomo v1.19.32, then checks tunnel DNS, HTTP/TCP, SOCKS5 UDP echo 64/512/1000/1200/1400, WG handshake/counters, argv/log canaries and application failure after transport stop.

This passed locally with synthetic TURN credentials. **No VK, router, VPS, WAN packet capture, NAT traversal, real-provider MTU or reboot acceptance is claimed.** The test Mihomo is a digest-verified official compatible AMD64 asset used privately; it is not redistributed by this workflow. The ordinary AMD64 asset requires v3 CPU features on the local host and could not start; compatible asset was used explicitly.

## IPK / rollback / release gates

`ipk_recipe.py` implements deterministic ar + control.tar.gz + data.tar.gz with versioned `/opt/libexec/wdtt-lab/<source-version>/` payload, notices and provenance. It has no init script/maintainer script/autostart. Synthetic archive/path tests pass. **Production admission remains closed**: its normal CLI refuses without approved `release-gates.json` and `build-report.install_ready=true`. A **separate** `owner_test_ipk.py` deliberately produces only experimental manually operated CLI IPKs for ARM64 and MIPSel and embeds big warning, currently known GPL/MIT notices, dependency inventory, SHA256 and provenance. It does **not** install services, bypass owner hardware preflight, edit Mihomo, publish a release, notify the feed or claim legal clearance. CI packages these as a distinct Actions artifact; no WDTT IPKs are placed in `latest`.

Dependency gate: main GPL-3.0-or-later; awgmproto v0.1.1 MIT. The retained Phase1 inventory covers 31 actually imported modules, root license texts only, not a complete scope approval. `fhttp@v0.6.8` refers to a BSD-style Go license but lacks LICENSE/COPYING/NOTICE at pinned tree `ecfe905c2db9d1ec769a16a14191ec84553dd235`; exact Go-derived and fork-specific notices/scopes remain unresolved. No incompatible-license conclusion is invented. Experimental Actions artifacts are now downloadable; **warnings are not legal permissions**, and the legal implications of public redistribution remain under review.

Future rollback keeps previous own version/provenance and atomically selects it after verified stop. KAS contains a separately tested local sandbox lifecycle; live Entware installation/uninstall/reboot admission remains closed pending hardware and safety gates. See [KAS experimental branch](https://github.com/saymer-alt/keenetic-auto-setup/tree/feature/wdtt-experimental-poc-20261011/experimental/wdtt).

## Existing publication safety

Existing Mihomo/Beszel/WARPSCOUT workflows and scripts are unchanged. Their shared latest release writer lock is `entware-latest-publication`; each owns only its package glob, validates/uploads/verifies before old-set prune, notifies feedly with AGGREGATOR_PAT, then prunes. This workflow never invokes publish_ipks.py, references that secret, sends a package-built dispatch or writes to latest. Record release asset IDs/digests before/after; independent scheduled workflows may change latest while this experiment is running.

WG-obfuscator remains next after WDTT readiness; no new workflow/IPK here. CSQTT patch/results/PolyForm notices remain in the separate KAS research PR; no CSQTT package is created.
