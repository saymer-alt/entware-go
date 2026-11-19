# TeleMT/Mihomo: матрица консолидации веток и PR — 19.11.2026

Статус: **инвентаризация выполнена агентом Z AI по фактическим SHA и diff** (не по названиям PR). Документ — вход для консолидации; сам по себе не является разрешением на merge, публикацию или изменения живых роутеров. База: `gh-action-build` @ `5e3940c` (совпадает с интеграцией joint IPC+Panel приёмки, PR #62).

## 1. Канонические реализации (единый источник для каждого артефакта)

| Артефакт | Каноническая реализация | Где живёт | Статус |
|---|---|---|---|
| TeleMT ARM64 Core IPK (`telemt_*` aarch64-3.10) | `build-telemt.yml` + `telemt/Makefile` | `gh-action-build` | INTEGRATED, не переписывать |
| TeleMT Panel Lite ARM64 IPK | `build-telemt-panel.yml` + `telemt-panel-lite/Makefile` | `gh-action-build` | INTEGRATED, не переписывать |
| MIPSel Core IPC (source + патчи: atomic64, daemon-control, getrandom-фолбэк) | `docs/research/telemt-control-ipc/` + `docs/research/telemt-mipsle-ipk-3517/` | `gh-action-build` (PR #44, #50, #56, #58, #62) | INTEGRATED |
| MIPSel IPK preflight-инструмент | `tools/telemt_mipsle_ipk_preflight.py` + тесты | `gh-action-build` | INTEGRATED |
| MIPSel Core-only UPX (`telemt-ipc-upx`, исправление `:::7890`, UPX2) | `docs/research/telemt-compact-core/upx/` | ветка `research/telemt-compact-core-only-mipsel-20261119` @ `9b1f0ed` → **Draft PR #68** | КАНДИДАТ, ждёт приёмки |
| MIPSel managed service kit (installer, service, pilot-скрипты) | PR #60 (`scripts/telemt-mipsel-install.sh`, `telemt-mipsel-service.sh`) | ветка `research/telemt-mipsel-managed-service-20261118` | КАНДИДАТ |
| MIPSel beta.1 release vehicle (superset #60 + publish workflow + release notes) | PR #63 (`release/telemt-mipsel-beta.1/`) | ветка `release/telemt-mipsel-3.5.17-beta.1` @ `b9a98f3` | КАНДИДАТ, 1 коммит позади (тривиально) |
| Generic ARM64 Entware installer/updater | PR #33 (`telemt/entware-manager.sh`) | ветка `feature/telemt-entware-package-manager-20261113` @ `8a1b13d` | КАНДИДАТ, 74 коммита позади |
| Mihomo S28 + revision-aware автосборка | PR #65 + PR #67 | ветки `fix/mihomo-s28-upx-package-20261119`, `fix/mihomo-s28-revision-aware-20261119` | В РАБОТЕ, CI-приёмка идёт |

## 2. Ветки/PR: решение по каждому

### 2.1 INTEGRATED — ветки можно удалить, содержимое уже в `gh-action-build`

- **PR #26, #27** (ARM64 Core/Panel IPK) — ветки удалены, содержимое в `gh-action-build` (эволюционировало только в основной ветке).
- **PR #44** (`research/telemt-mipsle-ipk-3517`) — ветка удалена; rc4 workflow, atomic64-патч, preflight-инструмент в основной ветке.
- **PR #50** (getrandom-фолбэк) — интегрирован, `2fb1`-сборка выпущена как experimental.
- **PR #56** (nightly reproducibility) — интегрирован.
- **PR #58** (daemon IPC) — squash `231429c` в основной ветке.
- **PR #59** (closed) — все 4 файла byte-identical присутствуют в `gh-action-build` (завершён через #58+#62).
- **PR #62** (joint acceptance) — squash `5e3940c` в основной ветке, 66/66 PASS.

### 2.2 SUPERSEDED — закрыть со ссылками, не сливать

- **PR #40** (`telemt-mipsle-poc`) — рецепт Go cross-build влит в merged rc4 workflow; standalone-файл не нужен.
- **PR #41** (`telemt-mipsle-core-3517`) — поглощён цепочкой PR #44.
- **PR #42** (`telemt-mipsle-panel-acceptance`) — логика folded в `tools/telemt_mipsle_ipk_preflight.py` (заголовок это фиксирует); standalone-версия не нужна.
- **PR #43** (`telemt-mipsle-compat`) — atomic64-патч byte-identical с копией в основной ветке (`5773ddd2`); workflow/README не переносить.
- **PR #57** (`telemt-legacy-supervisor`, закрыт) — отвергнутое решение (C-supervisor); его собственный `decision.md` фиксирует выбор in-daemon AF_UNIX IPC. Ссылку сохранить.
- **PR #46 ⊂ #47 ⊂ #48** (softfloat/ring/ccrs gates) — строгая вложенность; если toolchain-gate исследования ещё нужны — консолидировать в #48, иначе закрыть все три. Отдельно от production-канала; в `latest` не попадают.

### 2.3 КАНИДАТЫ — переносить целенаправленно, не всё сразу

- **PR #68 (новый, из `research/telemt-compact-core-only-mipsel-20261119`)** — единственное место с UPX/XZ-упаковкой TeleMT, `S98/S99` init-скриптами, NAND preinst-гвами и исправлением `:::7890` + 8 регрессионных кейсов. Нулевое отставание от tip. Требуется: QEMU-гостевая приёмка нового SHA (router-emulator MT7621, pinned-artifact паттерн), затем owner GO.
- **PR #63 → #60**: PR #63 — строгий superset PR #60 (+publish-beta1 workflow, лицензии, release notes). Мержить #63 после тривиального merge с `5e3940c`; #60 закрывать как включённый (или merge #60 и обновлять #63 — но двойная работа не нужна).
- **PR #33** — единственный generic ARM64 updater/installer; не пересекается с MIPSel-каналом по файлам. Требует rebase (74 коммита позади); низкий приоритет относительно MIPSel.
- **PR #66** (handoff docs) — готов к merge после OWNER GO, либо включить в docs-PR консолидации.

### 2.4 Конфликтующие/дублирующие реализации — явные решения

- **Init-скрипты TeleMT MIPSel существуют в трёх вариантах**: (a) `S98/S99telemt-ipc-compact*` (compact-ветка), (b) генерируемые установщиком `S98telemt-mipsel`/`S99telemt-mipsel-panel` (PR #60 service-kit, с owner-маркерами и отказом `rc.unslung restart`), (c) `S99telemt-ipc-upx` (UPX-ветка, init non-executable до явного enable). **Решение:** это РАЗНЫЕ пакетные профили (Core-only compact/UPX vs Core+Panel managed) — не объединять скрипты механически; каждый профиль публикуется под своим именем пакета, конфликт портов/служб ловится preflight'ом установщика.
- **`:::7890` readiness** — только в UPX-ветке (9b1f0ed); в `gh-action-build` нет. Переносится вместе с #68; в managed-профиль (PR #60/#63) требуется отдельная синхронизация того же регрессионного кейса (`test_socks5_listener.py`).
- **Установщики**: PR #33 (ARM64 generic) vs PR #60 (MIPSel managed) — разные архитектуры/каналы, file-level пересечений нет; держать раздельно.

## 3. Гэпы production-канала `gh-action-build` (то, чего нет в основной ветке)

1. Ни одного TeleMT init-скрипта (ARM64 пакеты осознанно без init; MIPSel init'ы — только в кандидат-ветках).
2. Нет `:::7890` readiness-логики.
3. Нет генерации core.toml/panel.toml (секреты — только при первой настройке).
4. Нет TeleMT UPX-упаковки.
5. `build-mihomo.yml` был не revision-aware (исправлено в PR #67), опубликованный `-2` комплект собран из состояния, которого больше нет в Makefile (drift 1.19.33-1 ↔ published 1.19.34-2 задокументирован в PR #65 docs).

## 4. Блокеры

- **KN-1913 NAND**: UPX2 preinst требует ≈14598 KiB свободных; с установленным UPX1 доступно 13100 KiB → обновление UPX1→UPX2 на устройстве блокировано до плана освобождения места (см. Issue #64). Не обходить guard.
- **RAM 256 МиБ**: совместный mihomo+magitrickle+telemt ≈19–23 МиБ доступно — безоговорочную круглосуточную эксплуатацию не рекомендовать (Issue #61).
- **Не подтверждено физически**: real Telegram-клиент, WAN, reboot×2, нагрузка (для MIPSel beta.2/stable — критерии Issue #61).

## 5. Порядок консолидации (предложение)

1. **Mihomo S28**: PR #65 + #67 → validated 6-package matrix (CI artifacts) → MT7621 QEMU приёмка mipsel IPK → owner GO → публикация `-3` (keep-old, полная матрица).
2. **TeleMT UPX2**: PR #68 → QEMU-приёмка UPX2 SHA → beta-канал (не `latest`).
3. **beta.1 → beta.2**: PR #63 (merge с tip) — после решения по UPX1→UPX2 upgrade-пути (NAND-план, Issue #64).
4. **Managed kit**: синхронизировать `:::7890`-регрессию в installer-профиль, затем приёмка.
5. **Закрыть superseded**: #40, #41, #42, #43, #57, (#46/#47 при консолидации в #48), #60 после мержа #63.
6. **ARM64**: ничего не менять; PR #33 rebase отдельным шагом.

Каждый шаг — отдельный Draft PR + явный owner GO перед merge/publish (AGENTS.md).
