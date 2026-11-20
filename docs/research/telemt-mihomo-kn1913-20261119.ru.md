# KN-1913, TeleMT/Mihomo и релизный handoff — 19.11.2026

Статус: **аппаратная исследовательская приёмка выполнена частично; production/stable MIPSel TeleMT НЕ принят**. Документ предназначен для передачи Z AI и консолидации PR. Не является разрешением на изменения живых роутеров, merge либо публикацию пакетов. Личные MTProxy-секреты, конфигурации и приватные адреса не включаются.

## 1. Цель и реальная среда

- Устройство: **Keenetic Viva KN-1913, объект «124»**, KeeneticOS 5.1.9, Linux 4.9-ndm-5, Entware `mipsel-3.4` во внутренней UBIFS/NAND (`/opt`).
- Общая физическая RAM около 256 МиБ, zRAM swap около 256 МиБ; `/opt/tmp` = tmpfs 20 МиБ, `/opt/var/log` = tmpfs 10 МиБ, `/opt/var/run` = tmpfs 1 МиБ (S00ubifs/KAS).
- KAS Core и KAS Web beta.9 оставлены без переустановки. Рабочие Mihomo, MagiTrickle, DNS-прокси и прокси-маршрутизация не должны быть нарушены.
- Задача: проверить Mihomo init `S28`, сжатый MIPSel TeleMT UPX из внутренней NAND и совместную работу с MagiTrickle без USB.
- Исключения: это НЕ подтверждение публичной доступности MTProxy/WAN, подключения Telegram-клиента, устойчивости после перезагрузки, ресурса под нагрузкой или совместимости на других платформах.

## 2. Подтверждённая аппаратная последовательность (логи владельца)

1. Сохранён `/opt/etc/telemt-compact-ram/core.toml` в отдельную root-only резервную копию, остановлен и удалён ранее работавший пакет `telemt-ipc-compact-ram 3.5.17-1ipc2ram2`.
2. Установлен **Mihomo 1.19.34-3 MIPSel LAB** из SHA256-проверенного IPK `5b90cd9a86eef07a3cc7a509352b631adc166197f388a36c18610a34d29f4744`. `opkg` корректно удалил устаревший `S99mihomo`, поставил один `S28mihomo`, сохранил изменённый `config.yaml` и поместил пакетный образец отдельно как `config.yaml-opkg`. PID Mihomo 2563, порт 7890 слушает. Эта лабораторная сборка — перепакованный проверенный `1.19.34-2` с тем же ELF (в нём UPX уже был), а не полноценный SDK rebuild всех архитектур. Основа — Draft PR [#65](https://github.com/saymer-alt/entware-go/pull/65).
3. Установлен **TeleMT 3.5.17-1ipc2upx1 MIPSel** из SHA256-проверенного IPK `d02b5116dca92f7a7b9d877ae9571eba5410c837085974d96ee1638d9d794f33`. Исполняемый ELF `/opt/bin/telemt-ipc-upx` после `strip` ~23 028 440 Б и после UPX 5.3.0 ~7 072 700 Б; бинарник запускается из NAND, без предварительной распаковки полного 23-МБ ELF в `/tmp`. После установки `df -k /opt`: всего 56 424 KiB, свободно 13 100 KiB (76% used).
4. Первоначальный старт TeleMT ошибочно блокировался строкой `SOCKS5 127.0.0.1:7890 not listening after 60s`. Причина — `netstat -lnt` показывал `:::7890 LISTEN`; TCP IPv4-mapped loopback существовал, а `curl -4 --socks5-hostname 127.0.0.1:7890` достиг GitHub и получил HTTP 403 по исчерпанному API rate-limit. 403 не означает отказ SOCKS5.
5. В установленном `S99telemt-ipc-upx` локально добавлен `:::7890` в выражение готовности SOCKS5; `sh -n` PASS. TeleMT отчитался **CORE_READY**, **PROFILE_CONFIGURED**, **AUTOSTART_DISABLED**. Прослушивание `0.0.0.0:13443` подтверждено. Путь исходящего подключения — `socks5://127.0.0.1:7890`. Startup DC1–DC5 и DC203 — 6/6 PASS (время 3–6 мс), инициализация ~12 с.
6. В журнале присутствует `Failed to update runtime log filter error=subscriber no longer exists`; после него Core привязал TCP-порт и запустил watchers. Сообщение пока не блокирует старт, но причину/влияние под нагрузкой нужно проверить отдельно.
7. `/opt/tmp` действительно содержал два установленных IPK общим объёмом 18,9 МиБ. После удаления ТОЛЬКО подтверждённых ненужных файлов `/opt/tmp` стал 4 KiB; `MemAvailable` вырос с 18 700 до **37 792 KiB**, `Shmem` снизился с 51 748 до **32 456 KiB**, `SwapFree` не изменился. **Не включать автоматическое удаление произвольных файлов из /opt/tmp!** Только собственные проверенные staged IPK после успешной установки.
8. После возврата `magitrickled` `MemAvailable` снизился с 37 252 до 21 756 KiB (дельта всей системы -15 496 KiB), swap без изменения; все три сервиса остались активны.
9. Через ~20 минут совместной работы выполнены шесть 30-секундных замеров 17:19–17:21 МСК:

| MSK | MemAvailable, KiB | SwapFree, KiB |
|---|---:|---:|
| 17:19:20 | 23184 | 223848 |
| 17:19:50 | 19848 | 222384 |
| 17:20:20 | 19488 | 222384 |
| 17:20:50 | 20452 | 222428 |
| 17:21:20 | 20984 | 222432 |
| 17:21:50 | 20996 | 222432 |

Процессы остались с прежними PID; проверка последних 150 строк `dmesg` не выявила OOM (это НЕ аудит полного журнала). Конечные показания:

| Процесс | RSS, KiB | HWM, KiB | VmSwap, KiB | Потоки |
|---|---:|---:|---:|---:|
| mihomo (PID 2563) | 80912 | 95424 | 1708 | 12 |
| magitrickled (PID 3920) | 14384 | 14412 | 0 | 10 |
| telemt-ipc-upx (PID 3034) | 16996 | 17016 | 0 | 17 |

**Интерпретация:** совместный запуск и кратковременная стабильность PASS; физическая память уже близка к критически малому запасу. Не заявлять долгосрочный PASS, отсутствие утечки или пригодность для большого числа клиентов. UPX уменьшает NAND-образ, но не гарантирует меньший RSS.

## 3. Исправление и артефакты

- Исходный SOCKS5/netstat дефект исправлен в research-ветке коммитом [9b1f0ed](https://github.com/saymer-alt/entware-go/commit/9b1f0ed426717f08b34433d595100e8ff43f9152). Добавлены **10 регрессионных кейсов** и hook в CI.
- [UPX2 workflow CI PASS](https://github.com/saymer-alt/entware-go/actions/runs/44536287656), artifact [14536036695](https://github.com/saymer-alt/entware-go/actions/runs/44536287656/artifacts/14536036695): `telemt-ipc-upx_3.5.17-1ipc2upx2_mipsel-3.4.ipk`, SHA256 `4000cf36700f119e1a716d38cfdba8dc83506d7594761152dfbe34bee95f8849`, 6 886 437 Б. **UPX2 пока НЕ ставили на реальный роутер.**
- Preinstall guard для нового IPK требует минимум 14 598 KiB NAND, а с установленным UPX1 на KN-1913 было 13 100 KiB. Нельзя игнорировать guard или пытаться заменить без плана освобождения места/отката. Можно использовать hotfix UPX1 на лабораторном устройстве до следующей контролируемой установки.
- Аппаратные подробности записаны в [Issue #64](https://github.com/saymer-alt/entware-go/issues/64). Beta/stable exit criteria — [Issue #61](https://github.com/saymer-alt/entware-go/issues/61).

## 4. Фактическое состояние публикаций (19.11.2026)

### TeleMT ARM64 — существующий механизм, не переписывать

- Основная ветка Entware fork: `gh-action-build`; [`build-telemt.yml`](https://github.com/saymer-alt/entware-go/blob/gh-action-build/.github/workflows/build-telemt.yml) уже проверяет официальные upstream stable releases каждые 6 часов, проверяет SHA256/license/binary identity, собирает SDK IPK для `aarch64-3.10` и публикует **только** `telemt_*.ipk` в общий `latest`.
- Текущий `latest` содержит `telemt_3.5.17-1_aarch64-3.10.ipk`. ARM64 пакет — неизменённый официально распространяемый ELF с лицензией; он намеренно **не содержит Panel, личный TOML, секреты или init/autostart**. Не заменять его непроверенным MIPSel IPC-форком.
- Panel Lite ARM64 — отдельная семья `telemt-panel-lite_*.ipk`.

### TeleMT MIPSel — отделить от официального ARM64 канала

- Уже существует опубликованный **неофициальный публичный prerelease** [`telemt-mipsel-v3.5.17-beta.1`](https://github.com/saymer-alt/entware-go/releases/tag/telemt-mipsel-v3.5.17-beta.1), от 18.11.2026. Core IPC + Panel Lite RC4 и universal kit — **не UPX Core-only**, а другой пакетный профиль. Его универсальный установщик на KN-1913 с текущей NAND недостаточен по размеру; [PR #63](https://github.com/saymer-alt/entware-go/pull/63) ещё открыт.
- Принятое исследование IPC — PR #58, QEMU joint acceptance — [PR #62](https://github.com/saymer-alt/entware-go/pull/62), уже интегрирован; managed kit [Draft PR #60](https://github.com/saymer-alt/entware-go/pull/60) ещё требует приёмки. Есть исторические/конкурирующие ветки — не объединять все механически.
- Для MIPSel выбрать поддерживаемые **раздельные профили**: (a) Core + Panel при достаточной RAM/NAND или USB EXT4; (b) Core-only UPX для очень малого NAND. Не выдавать их за эквивалентные.
- Нельзя публиковать MIPSel «stable» только по CORE_READY/DC probes: нужны real Telegram client/WAN, reboot/autostart x2, load/stability, clean install/upgrade/uninstall/rollback, ресурсы на заявленных моделях, лицензии/хэши и owner sign-off. В иных случаях выпускать `beta.2`/RC с честными ограничениями; `latest` ARM64 не трогать.

### Mihomo — S28 на все будущие сборки

- [Draft PR #65](https://github.com/saymer-alt/entware-go/pull/65): `mihomo/Makefile` должен устанавливать `S28mihomo` (файлы S28/S99 byte-identical, KAS уже знает S28), package revision `-3`.
- Физический MIPSel upgrade `1.19.34-2` -> `1.19.34-3` с удалением `S99`, сохранением изменённой конфигурации и работающим SOCKS5 **PASS**. Это LAB repackage одного IPK; не evidence для полного кросс-архитектурного SDK.
- В `latest` пока шесть вариантов `mihomo_1.19.34-2`: `aarch64-3.10`, `armv7-3.2`, `mips-3.4`, `mipsel-3.4`, `x64-3.2`, `mihomo_nohf` для `armv7-3.2`.
- [`build-mihomo.yml`](https://github.com/saymer-alt/entware-go/blob/gh-action-build/.github/workflows/build-mihomo.yml) сейчас решает пересборку по наличию версии upstream; одно изменение `PKG_RELEASE`/init без нового upstream tag может пропускаться. Нужен revision-aware check и полный, проверенный шестипакетный SDK build до выпуска. Не терять `GOTOOLCHAIN=local`, требование tagged `go.mod`, архитектуры и возможность prune-only.
- [`scripts/publish_ipks.py`](https://github.com/saymer-alt/entware-go/blob/gh-action-build/scripts/publish_ipks.py) уже требует полный набор, отказывает при конфликте checksums и не должен стирать чужие assets. Сохранить `entware-latest-publication`; новая `-3` должна пройти всю матрицу без overwrite непроверенного существующего asset. Rollback `-2` должен быть доступен и проверен.
- Скрипты init являются частью пакета Entware; никаких ad-hoc `mv S99 S28` в KAS, двойных исполняемых S28/S99 или принудительной переустановки KAS.

## 5. Эмуляторная база и ограничение доказательств

- [`saymer-alt/router-emulator`](https://github.com/saymer-alt/router-emulator) имеет QEMU-машины семейства Filogic (`mt7981-router` и др., например WR3000P-подобная лаборатория) и **отдельную `mt7621-router` / `qemu-system-mipsel`**. Физический KN-1913 относится к MT7621, поэтому именно второй стенд релевантен MIPSel ABI и Entware. Filogic/3811-подобный стенд не является идентичной аппаратурой KN-3811.
- В router-emulator есть реальные Ported MT7621 guest acceptance по Core/Panel: [PR #93](https://github.com/saymer-alt/router-emulator/pull/93) зафиксировал отрицательный baseline `getrandom(2)` на прежней версии; [PR #96](https://github.com/saymer-alt/router-emulator/pull/96) описывает 93/93 PASS для исправленного исследовательского комплекта с Panel. Не повторять без причины уже успешные тяжёлые тесты.
- Для финальных EXACT IPK/SHA (TeleMT UPX2 и Mihomo S28 всех архитектур) нужны отдельные provenance и гостевые проверки: ELF/ABI, package ownership, `opkg` clean install/update, `S28` и `S99` collision negative case, `rc.unslung`, real daemon/IPC, proxy `:::7890` matcher, memory profile `256M`, reboot/restart/rollback. Достаточность QEMU не равна физическому Telegram/WAN acceptance.
- Не смешивать MIPSel mipsel-3.4 с aarch64-3.10; на Filogic стенде проверять ARM64 пакет, на MT7621 — MIPSel. Отдельно явно помечать `PASS/FAIL/BLOCKED/NOT_TESTED`.

## 6. Предлагаемые шаги Z AI

1. **Инвентаризация:** прочитать `AGENTS.md`, exact base SHA, Issues #61/#64, PRs #60/#63/#65 и смежные исследования в обоих репозиториях; представить матрицу `готово / перенести / закрыть как superseded / блокер`. Не сливать все research branches целиком.
2. **Mihomo S28:** довести рецепт + revision-aware workflow, официальную SDK матрицу всех шести вариантов, host CI и MIPSel/ARM64 guest compatibility. PR отдельно; release-publish только после проверки пакетов/комплекта/сохранения конфига/наличия отката и явного owner GO.
3. **TeleMT каналы:** сохранить текущую ARM64 авто-сборку без изменений; для MIPSel выбрать канонические Core IPC, Panel Lite и UPX Core-only, пересмотреть preflight полного installed size, отдельные пакетные имена, credentials/paths, safe upgrade, reserve NAND/RAM, live service ownership; подготовить воспроизводимый пакетный источник и automation без истекающих Actions artifacts. Не подменять modified IPC именем официального бинарника.
4. **Эмуляторы:** host/regression дешёвые тесты в первую очередь, затем точечные реальные QEMU Ported MT7621 и Filogic проверки на новых SHA. Не тратить токены на повтор неизменных PASS.
5. **Релиз:** если не выполнены критерии Issue #61, сделать только RC/beta и матрицу оставшихся hardware acceptance; stable — только после набора реальных evidence и отдельного согласованного решения. Never publish MIPSel to shared `latest` silently; preserve unrelated `mihomo_*`/`warpscout_*`/`beszel-agent_*`/`telemt-panel-lite_*`.
6. **Документы/отчёт:** PR diff, package manifest/sha256, run links, supported devices, logs sanitized, fail-safe/uninstall rollback, explicit no-op on routers. Экспериментальный KN-1913 оставить как есть, TeleMT AUTOSTART_DISABLED.

## 7. Правила экономии и STOP

Обязательны `AGENTS.md`, [релизный стандарт](../../RELEASE-STANDARD.md), [Issue #61](https://github.com/saymer-alt/entware-go/issues/61), правила доказательств router-emulator. 2 одинаковых FAIL -> новая гипотеза/BLOCKED; 3 изменения или 3 полных тяжёлых прогона на одну проблему -> STOP + owner GO. Не повторять одинаковые уже успешные тесты. Не менять живые Keenetic, фиды, токены, ветку `gh-action-build`, общий `latest` и не запускать регулярные публикации без отдельно явно подтверждённого допуска.

**Финальный результат агента до релизного GO:** Draft PR(ы), готовые воспроизводимые CI, аудит конфликтующих веток, точные IPK/SHA при сборке, матрица ограничений, версия Release Notes и конкретный список требований для безопасного merge/publish.
