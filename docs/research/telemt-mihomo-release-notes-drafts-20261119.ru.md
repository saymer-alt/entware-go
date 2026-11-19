# Подготовка релизов: support matrix, инструкции, черновики notes — 19.11.2026

Статус: **черновики для owner GO**. Публикация любого из нижеперечисленного требует отдельного явного owner GO (AGENTS.md). Файл не является разрешением; фактические SHA указаны на момент подготовки.

## 1. Support matrix

| Канал | Пакет/профиль | Архитектура | Статус приёмки | Ограничения |
|---|---|---|---|---|
| `latest` (shared feed) | `telemt_3.5.17-1` | aarch64-3.10 | стабильно работает; официальные ELF + license; без init/Panel | не трогать |
| `latest` (shared feed) | `telemt-panel-lite_1.0.0.rc.4-1` | aarch64-3.10 | стабильно работает | не трогать |
| архив | `mihomo_1.19.34-2` (6 вариантов, S99) | все | исправный предыдущий комплект; вычищен из `latest` после публикации `-3` (keep-old flow); полный комплект + SHA256SUMS сохранены в релизе **mihomo-1.19.34-2** для отката | ссылка на тег, не на `/releases/latest` |
| `latest` (shared feed) — **опубликовано 19.11.2026** | `mihomo_1.19.34-3` (6 вариантов, S28) | все | SDK-матрица PASS (run 44565066188 = байты релиза, run 44587763950 публикация), статика 6/6 PASS против опубликованных байтов, digest'ы совпали с лидом GitHub; KN-1913 физический upgrade PASS — для **LAB repackage**, байты которого отличаются от SDK-комплекта | QEMU-гостевая приёмка: BLOCKED (см. раздел 2.1); plan после публикации `update=false` |
| prerelease `telemt-mipsel-v3.5.17-beta.1` | Core IPC + Panel Lite + kit | mipsel-3.4 | Core IPC/Panel — PR #58/#62 QEMU 66/66; beta.1 published 18.11 | KN-1913 NAND недостаточно; universal kit не для KN-1913 |
| канал UPX (PR #68) | `telemt-ipc-upx_3.5.17-1ipc2upx2` | mipsel-3.4 | CI pass; хост-регрессии :::7890 — 10/10 кейсов (`test_socks5_listener.py`); **на железо не ставился** | beta-канал, не `latest` |
| managed kit (PR #60 + PR #70) | installer + service | mipsel-3.4 | сценарная приёмка IPC/Panel есть; preflight NAND/RAM добавлены в #70, не испытаны | свежие установки / `--reuse-config` |
| ARM64 updater (PR #33) | `telemt/entware-manager.sh` | aarch64-3.10 | не интегрирован, 74 коммита позади | отдельный шаг |

Границы стендов: MT7621 QEMU (Ported 5.1.8) — MIPSel ABI/Entware, НЕ замена физического WAN/USB/Wi-Fi/Telegram-клиента; Filogic/MT7981 (WR3000P) — aarch64 Ported 5.1.8, НЕ идентичен железу KN-3811.

## 2. Инструкции обновления и отката

### 2.1 Mihomo (S28, все архитектуры)

Обновление `-2` → `-3` (механика upgrade физически проверена на KN-1913 с **LAB repackage** `-3` mipsel; опубликованный SDK `-3` имеет другие байты — аппаратный тест одного комплекта не переносится на другой):

```
opkg update не требуется: ставим локальный проверенный IPK
sha256sum mihomo_1.19.34-3_<arch>.ipk   # сверить с SHA256SUMS релиза
opkg install /path/mihomo_1.19.34-3_<arch>.ipk
# opkg сам: удалит устаревший S99mihomo (владелец - старый пакет),
# поставит один S28mihomo, сохранит изменённый config.yaml,
# пакетный образец появится как config.yaml-opkg
/etc/init.d/S28mihomo restart
```

Откат `-3` → `-2` (механика `--force-downgrade` стандартна; QEMU-сценарий с шагом ROLLBACK_V2_OK подготовлен, гостевой прогон **BLOCKED**: в эмулируемом MT7621 процесс mihomo завершается до открытия порта — классифицировано диагностикой run 44606829890, подозрение UPX-распаковка под TCG; физический откат на железе — NOT_TESTED):

```
opkg install --force-downgrade /path/mihomo_1.19.34-2_<arch>.ipk
# конфигурация сохраняется (conffiles), init-имя возвращается к S99
```

Инварианты после любой операции: ровно один init-скрипт `S*mihomo*`; `config.yaml` пользователя не теряется; порт 7890 слушается (возможна форма `:::7890`).

### 2.2 TeleMT MIPSel Core-only UPX (KN-1913-профиль)

- Fresh: `opkg install telemt-ipc-upx_3.5.17-1ipc2upx2_mipsel-3.4.ipk` — preinst гвард требует ≈14598 KiB свободных; при отказе НЕ обходить гвард (см. Issue #64).
- UPX1 → UPX2 на устройстве с установленным UPX1 (13100 KiB свободных): штатный `opkg upgrade` БЛОКИРОВАН гвардом by design. Путь: (1) остановить службу, (2) корневая резервная копия `/opt/etc/telemt-compact-ram/core.toml` + секрет, (3) `opkg remove telemt-ipc-upx` (конфиг-каталог не принадлежит пакету и сохраняется), (4) `opkg install` UPX2, (5) `sh /opt/etc/init.d/S99telemt-ipc-upx start`, (6) только после клиентских тестов `enable-boot`.
- Откат: обратная последовательность с UPX1 IPK (sha256 `d02b5116…`).
- Автозапуск на KN-1913 остаётся выключенным (AUTOSTART_DISABLED) до owner GO.

### 2.3 TeleMT MIPSel Core+Panel (managed kit)

- Fresh: `sh telemt-mipsel-install.sh CORE.ipk PANEL.ipk SOCKS5_IP:PORT PUBLIC_HOST PANEL_BIND_IP` (включает NAND/RAM preflight PR #70).
- Обновление с сохранением конфигурации: `service.sh uninstall` → `sh telemt-mipsel-install.sh … --reuse-config` (PR #70; секреты/TOML не пересоздаются).
- Откат/удаление: `service.sh uninstall` — пакеты снимаются, конфиги/секреты сохраняются (0700) для rollback-инспекции; повторная установка — с `--reuse-config`.

## 3. Черновик тела релиза: обновление `latest` (mihomo -3)

> Profile B (RELEASE-STANDARD.md): компактное техническое тело, без H1-повтора имени.

```markdown
Rebuilt complete mihomo package set: S28 init migration and package revision bump.

## Build

Entware SDK, six-package complete set, PKG_RELEASE 3 (upstream 1.19.34 unchanged).
Init script renamed S99mihomo -> S28mihomo (byte-identical payload, Entware
start-order policy, upstream ee4b689). UPX compression preserved.

## Assets

mihomo_1.19.34-3_{aarch64-3.10,armv7-3.2,mips-3.4,mipsel-3.4,x64-3.2}.ipk
mihomo_nohf_1.19.34-3_armv7-3.2.ipk
SHA256SUMS in the release notes / commit message. The previous complete
1.19.34-2 set was pruned from `latest` by the standard keep-old flow after
this set was verified; the full -2 kit + SHA256SUMS stay available in the
`mihomo-1.19.34-2` archive release for --force-downgrade rollback.

## Install / Usage

opkg install /path/mihomo_1.19.34-3_<arch>.ipk — removes stale package-owned
S99mihomo, installs one S28mihomo, preserves user config.yaml (package sample
as config.yaml-opkg). Rollback: opkg install --force-downgrade <1.19.34-2 ipk>.

## Verification / Compatibility

Full SDK matrix PASS (run 44565066188; published bytes are byte-identical
to that validation set). Static acceptance 6/6 against the published
assets: S28 present, no S99, ELF arch/endianness per variant, UPX marker,
byte-identical init. Physical MIPSel upgrade -2 -> -3 verified on KN-1913
with the LAB repackage (PR #66 docs); QEMU guest acceptance BLOCKED —
emulated startup exits before bind (router-emulator PR #112).
```

Публикация — только штатным `build-mihomo.yml` после merge PR #67 (revision-aware plan сам увидит `update=true`); набор/verify/prune — существующими механизмами `publish_ipks.py`.

## 4. Черновик тела релиза: telemt-mipsel beta.2 (при готовности)

> Профиль prerelease; name `vX.Y.Z — …` по Profile A; в `latest` не попадает.

```markdown
TeleMT MIPSel beta.2 — Core-only UPX2 channel and managed-kit preflight

## Главное

- Новый компактный профиль Core-only UPX2 (`telemt-ipc-upx`): ELF в NAND без
  распаковки 23 МиБ в /tmp; исправлена проверка готовности SOCKS5 при
  dual-stack `:::7890` (KN-1913); 8 host-регрессий; preinst гвард NAND.
- Managed kit: preflight NAND/RAM, `--reuse-config` для обновления с
  сохранением секретов, локальный readiness-wait SOCKS5 upstream.

## Проверено

- UPX2: CI 10/10; хост-регрессии 8/8; MT7621 QEMU приёмка нового SHA — см.
  матрицу статусов (BLOCKED/NOT_TESTED честно указываются).
- Managed kit: скрипт-приёмка IPC/Panel из beta.1; новые preflight-гварды
  host-проверены (sh -n, Installed-Size extraction), на железе не испытаны.

## Совместимость и границы

- KN-1913: UPX2 требует ≈14598 KiB свободных; с установленным UPX1 путь —
  remove→install (инструкция в docs). Universal kit beta.1 на KN-1913 не
  помещается. Автозапуск везде выключен до owner GO.
- Не подтверждены: реальный Telegram-клиент, WAN, reboot x2, длительная
  нагрузка (критерии Issue #61 не выполнены).
```

## 5. Точные оставшиеся owner-действия

1. **GO/NO-GO merge** PR #67 (+ #65) — после зелёной CI; затем штатная публикация `-3` через `build-mihomo.yml` (второй GO: только что merged workflow сам решает `update=true`; publish-шаг выполняется при `inputs.publish=true` — дефолт).
2. **Секрет `TELEMT_IPK_TOKEN`** (actions:read на entware-go) в router-emulator → dispatch `mt7621-telemt-lab.yml -f scenario=mihomo-s28` (рецепт в PR #112) → QEMU-приёмка S28 mipsel IPK.
3. **GO/NO-GO** PR #68 (UPX2) и PR #70 (managed preflight) после ревью; re-pin SHA скриптов в PR #63 при консолидации beta.1 → beta.2.
4. **Закрытие superseded** (#40, #41, #42, #43, #57; #46/#47 → #48; #60 после мержа #63) — отдельным механическим шагом по матрице (PR #69).
5. KN-1913: контролируемая установка UPX2 по инструкции 2.2 (не автоматическая), реальный Telegram/WAN/reboot-цикл — критерии Issue #61.
6. ARM64: ничего не меняется; PR #33 rebase — отдельным шагом при желании.
