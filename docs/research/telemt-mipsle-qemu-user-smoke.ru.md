# TeleMT MIPSLE: дешёвый QEMU User Mode smoke (без готового эмулятора Keenetic)

**Статус: подготовленный инструмент; реальные MIPSLE IPK здесь не запускались.**
Связан с [PR #44](https://github.com/saymer-alt/entware-go/pull/44) и Issue #37.
Не путать с [Keenetic Ported MT7621 E2E](https://github.com/saymer-alt/router-emulator/issues/73).

## Зачем и что уже сделано

Чтобы не расходовать Z AI на повторную Rust/LTO-компиляцию, проверить именно **готовые** IPK из GitHub Actions run 43624729371:
- `telemt_3.5.17-1_mipsel-3.4.ipk`, SHA256 `a04f754375056439c3d5584bf7d868eb547f844c4779e3076bfbdd84129d63fa`;
- `telemt-panel-lite_1.0.0.rc.4-1_mipsel-3.4.ipk`, SHA256 `0236dfb076b14b129a6392de49f287838a11aebe7681e092084d4ce87e771e68`.

Новый `tools/telemt_mipsle_qemu_user_smoke.py` **по умолчанию не исполняет** TeleMT.
Он сверяет pinned SHA, использует уже существующий `telemt_mipsle_ipk_preflight.py` для проверки ELF/архитектуры/control и отклоняет дополнительные payload-пути.

### Шаг 1: только offline static (Python 3, без сети)

```bash
python3 tools/telemt_mipsle_qemu_user_smoke.py \
  --core-ipk /path/telemt_3.5.17-1_mipsel-3.4.ipk \
  --panel-ipk /path/telemt-panel-lite_1.0.0.rc.4-1_mipsel-3.4.ipk
```

При совпадении входных IPK выводит `STATIC_PREFLIGHT_PASS`; `QEMU_USER_CORE_CLI`, `QEMU_SYSTEM_MT7621`, `OPKG_INSTALL_ROLLBACK`, `PHYSICAL_DEVICE` остаются **NOT_TESTED**.

### Шаг 2: опциональный ограниченный qemu-user запуск Core `--version`

Нужен Linux x86_64 с `qemu-mipsel` (`qemu-user`) и `unshare` из util-linux, **а также локально распакованный и отдельно проверенный** каталог динамических библиотек Entware **mipsel-3.4/glibc 2.27** (loader `ld.so.1`, libc, libgcc_s, pthread, rt, m, dl). Он может быть подготовлен в research-окружении PR #44 по pinned SHA пакетов. **Не использовать живой `/opt` роутера.**

```bash
python3 tools/telemt_mipsle_qemu_user_smoke.py \
  --core-ipk /path/telemt_3.5.17-1_mipsel-3.4.ipk \
  --run-core-cli \
  --entware-lib-dir "$HOME/entware-build/sysroot/usr/mipsel-linux-gnu/lib"
```

Режим `--run-core-cli` только по явному флагу: извлекает проверенный ELF в одноразовый каталог, запускает **гостевой** `ld.so.1` под `qemu-mipsel` с `--library-path` на каталоге Entware, выполняет `--version`; `unshare --user --map-root-user --net` отключает сеть, а 12-секундный timeout не позволяет зависнуть навсегда. Нет sudo, опkg и изменения системных файлов. Для полного filesystem sandbox этот инструмент **не предназначен**: используйте отдельную тестовую VM/WSL.

Если user namespaces отключены, qemu отсутствует, loader/libs не совпадают, случился timeout, nonzero exit или загрузчик падает — статус **BLOCKED**; запрещено ставить PASS или убирать изоляцию. Не нужно запускать полную Rust-компиляцию заново. Сетевые ключи/конфигурации не передаются.

**Ограничения PASS:** `QEMU_USER_CLI_SMOKE_PASS` доказывает только выполнение версии CLI через напрямую вызванный гостевой загрузчик. Это **не** доказывает путь PT_INTERP в реальной гостевой ОС, фактическую установку opkg, корректность glibc shim под рабочей нагрузкой, сеть Telegram, crypto, lock-fallback AtomicU64, RAM 256 MB, физический KN-1913. Panel Lite пока только статически проверяется, сервер не запускается.

### Дешёвые unit-тесты

```bash
python3 -I -m unittest discover -s tools/tests -p 'test_telemt_mipsle_qemu_user_smoke.py' -v
```

Локально при подготовке: 10/10 PASS (checksum, path escape, unexpected package payload, absent QEMU, offline process isolation, nonzero exit). Реальные MIPSLE ELF/IPK **не доступны в этой локальной среде**, поэтому интеграция с ними NOT_TESTED. Никаких SDK/LTO/QEMU-system/публикаций/живых устройств в этом PR нет.

**GitHub PR — отдельная зависимая ветка от PR #44**; не мержить самостоятельно в `gh-action-build` и не запускать release workflow. Результаты реальных IPK должны фиксироваться отдельно с SHA/версиями libc/QEMU. После готовности полноценного эмулятора приоритет у настоящих MT7621/Entware/opkg испытаний.
