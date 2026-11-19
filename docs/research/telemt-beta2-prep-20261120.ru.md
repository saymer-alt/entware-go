# TeleMT MIPSel beta.2 — подготовка (ночная сессия 19–20.11.2026)

Статус: **подготовка, не публикация**. Ни один шаг этого документа не выполняется без отдельного owner GO (beta.1 остаётся последней опубликованной версией MIPSel-канала; `latest` production-фид не затрагивается).

## 1. Поддерживаемые профили и матрица

| Профиль | Пакет / артефакт | Init-скрипты | Порты | Ветвь/PR | Назначение |
|---|---|---|---|---|---|
| Core-only UPX2 | `telemt-ipc-upx` `3.5.17-1ipc2upx2` | `S99telemt-ipc-upx` (non-exec до enable) | Mihomo-ready `:::7890` readiness-регрессия | `research/telemt-compact-core-only-mipsel-20261119` → **PR #68** | минимальный Core, UPX2, без Panel |
| Core+Panel managed | installer `telemt-mipsel-install.sh` + `telemt-mipsel-service.sh` | `S98telemt-mipsel` + `S99telemt-mipsel-panel` (генерируются установщиком) | proxy 13443, panel 18082, Core API 19091 (только 127.0.0.1) | `research/telemt-mipsel-managed-preflight-20261119` → **PR #70** (⊃ #60) | полный профиль с панелью и секретами |
| Compact/RAM | `telemt-ipc-compact` / `*-ram` | `S98telemt-ipc-compact(-ram)`, `S99telemt-ipc-compact-ram` | см. конфигуратор | тот же бранч #68 (ram/, scripts/) | RAM-исполнение, отдельный профиль |

Разделение профилей подтверждено фактическими именами (пакеты, init'ы, порты не пересекаются; установщик сам гейтит 13443/18082/19091 через `available()`). Механически объединять init-скрипты запрещено (см. матрицу консолидации, раздел 2.4).

## 2. Архитектура/устройства

- **Целевая архитектура**: MIPSel (Entware `mipsel-3.4`, GCC8 softfloat, динамический C ELF — gate из ветки softfloat-sdk-gate/ccrs-gcc8, производство не затрагивает).
- **Пилотное устройство**: KN-1913 (MT7621, 128 MiB NAND / 256 MiB RAM).
- **Известные аппаратные ограничители**: NAND preinst UPX2 требует ≈14598 KiB свободных (при живом UPX1 доступно ≈13100 KiB → upgrade-путь UPX1→UPX2 требует плана освобождения, Issue #64; guard не обходить); RAM ≈19–23 МиБ в совместном режиме — не 24/7 (Issue #61).

## 3. Схема объединения веток (уточнена merge-base сверкой 20.11.2026)

Фактическая топология (git merge-base, проверено):

- `research/telemt-mipsel-managed-service-20261118` (head PR #60) **целиком содержится** в `research/telemt-mipsel-managed-preflight-20261119` (head PR #70) → мерж #70 привносит всё содержимое #60; после мержа #60 закрывается как включённый.
- PR #63 (`release/telemt-mipsel-3.5.17-beta.1`) и #60/#70 **разошлись**: head #60 НЕ является предком #63. «#63 — superset #60» из матрицы относился к состоянию до развития managed-service ветки.
- `research/telemt-ring-cc-bridge-20261115` ⊂ `research/telemt-ccrs-gcc8-bridge-20261115` (подтверждено) — при консолидации toolchain-gate использовать tip ccrs-ветки.

Порядок (каждый шаг — отдельный owner GO):

1. **PR #63** (beta.1 vehicle) — merge с текущим tip `gh-action-build` (сейчас он отстал от main после интеграции S28, merge тривиален, файлы не пересекаются).
2. **PR #70** (managed kit + preflight + reuse/update-with-error контракты) — merge следующим; затем **закрыть #60** как включённый (ссылка на merge-commit #70).
3. **PR #68** (Core-only UPX2) — независимо; перед merge требуется QEMU-гостевая приёмка нового SHA (router-emulator MT7621, pinned-artifact паттерн) и решение по NAND-плану UPX1→UPX2 (Issue #64).
4. **PR #66** (handoff docs) — в любой момент после GO (docs-only).
5. beta.2 vehicle — см. раздел 4; сборка кандидата возможна в любой момент, публикация — только по GO-флагу.

## 4. beta.2 vehicle: сборка кандидата и публикация (паттерн beta.1)

Готовая механика из PR #63 переиспользуется без переписывания:

- **Сборка кандидата без публикации**: workflow `telemt-mipsel-kn1913-pilot-bundle.yml` — собирает bundle и кладёт его **только в artifact** (`upload-artifact`, явный «no release»), с пинами IPK/кита и пометкой «untested on KN-1913». Этого достаточно для «CI собирает beta-кандидатов, но не публикует».
- **Публикация**: workflow `telemt-mipsel-publish-beta1.yml` срабатывает **только** на push файла-маркера (`GO-BETA1.flag` с константным содержимым) в релизную ветку; перед публикацией верифицирует git-hashObject-пины исходников/патчей/скриптов, лицензии (`LICENSE.TELEMT.txt` GPL 3.3, `LICENSE.PANEL.txt` MIT), release notes («Не официальный релиз»), и скачивает **зафиксированные по run-id** артефакты принятых сборок. В `latest` и production-фид не пишет никогда.
- Для beta.2: копия пары workflow с `GO-BETA2.flag` (иное константное содержимое), пинами SHA/артефактов приёмки beta.2 и release notes beta.2. Создавать только после того, как приёмочные прогоны beta.2 зафиксированы (нужны run-id для пинов).

Проверка целостности beta.1 (выполнена 20.11.2026): `telemt-mipsel-v3.5.17-beta.1.zip` sha256 `854c6f0d…` — совпадает с опубликованным манифестом `.sha256` (OK). Тот же `sha256sum -c` шаг входит в vehicle.

## 5. Офлайн-регрессии beta.2 (готовность)

| Контракт | Где | Статус |
|---|---|---|
| `--reuse-config` не трогает секреты/TOML/ссылки | `tests/test_telemt_mipsel_managed_contract.py::ReuseConfigContractTests` (PR #70) | PASS (5 кейсов) |
| update-with-error: preflight до первой мутации; retry после частичной установки отказывает («abort to avoid overwriting»); конфиг-каталог создаётся только после верификации обоих ELF | тот же файл, `UpdateWithErrorContractTests` (3 кейса, добавлены 20.11.2026, commit `ff74f08`) | PASS |
| ARGS_IGNORED_IN_REUSE (SOCKS5/PUBLIC_HOST/PANEL_BIND валидируются, но не применяются) | установщик + контракт-тест | PASS |
| SOCKS5-формы прослушивания Mihomo 127.0.0.1 / 0.0.0.0 / ::: (dual-stack KN-1913) | `docs/research/telemt-compact-core/upx/test_socks5_listener.py` (PR #68), 10 кейсов | PASS |
| NAND/RAM preflight | установщик `nand_check`/`ram_check` + контракт-тест | PASS (гостевая приёмка NOT_TESTED) |
| Разделение профилей по пакетам/init/портам | данный документ, раздел 1 (фактические имена из веток) | задокументировано |

## 6. Чего не хватает для beta.2 (честные статусы)

- **NOT_TESTED**: QEMU-гостевая приёмка UPX2 SHA (PR #68) и managed-kit на свежем SHA (PR #70) — блокированы общим эмуляторным вопросом UPX-vs-TCG (router-emulator PR #112, классификация в матрице); физический прогон managed-kit на KN-1913 с новым установщиком; физический откат -3→-2 и UPX2-install на KN-1913 (инструкции в PR #69, раздел 2).
- **BLOCKED**: NAND upgrade-путь UPX1→UPX2 (место на KN-1913, Issue #64) — требует owner-плана освобождения.
- **Не требуется для beta.2**: изменения ARM64 upstream-канала (`build-telemt.yml` не переписывать), UPX для других архитектур не применять.

## 7. Release Notes beta.2 (каркас)

- Заголовок: «Unofficial TeleMT IPC 3.5.17 + Panel Lite for Entware MIPSel — beta.2» (пометка «Не официальный релиз» обязательна, grep-гейт vehicle).
- Разделы: что изменилось с beta.1 (пины SHA/артефактов, update-with-error контракты, reuse-config гарантии, разделение профилей), известные ограничения (NAND/RAM), инструкции установки/обновления/отката (только через управляемый установщик, `--reuse-config` для сохранения секретов), лицензии.
- Заполняется фактическими SHA после приёмочных прогонов beta.2; черновик хранится рядом с vehicle в релизной ветке beta.2.
