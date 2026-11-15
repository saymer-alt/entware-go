# TeleMT MIPSLE — реальный QEMU User Mode smoke, 15.11.2026

Зависимый [Draft PR #45](https://github.com/saymer-alt/entware-go/pull/45) на research-ветке [PR #44](https://github.com/saymer-alt/entware-go/pull/44). Это **не** целиком эмулятор KeeneticOS, не `opkg install` и не аппаратная приёмка.

## Фактически выполнено (без Z AI)

- В изолированном Debian x86_64 установлен `qemu-mipsel 7.2.22`. Процессы запускались с `unshare --user --map-root-user --net` (внешняя сеть гостю недоступна).
- Получены исходные GitHub Actions ZIP из [run 43624729371](https://github.com/saymer-alt/entware-go/actions/runs/43624729371); проверены SHA-256 обоих IPK.
- Из официального `bin.entware.net/mipselsf-k3.4` загружены и проверены SHA-256 `libc_2.27-12`, `libgcc_8.4.0-12`, `libpthread_2.27-12`, `librt_2.27-12`. Библиотеки извлечены в отдельный одноразовый `guestroot/opt/lib` (в том числе `ld.so.1`).
- **Panel Lite RC4: PASS — `--version`** с `qemu-mipsel -cpu 24Kc -L guestroot guestroot/opt/bin/telemt-panel --version`: `EXIT 0`, ответ `telemt-panel 1.0.0-rc.4 (lite: memory)`. Другие функции панели не проверялись.
- **Core 3.5.17: FAIL** — при аналогичном запуске штатного ELF `EXIT 1: qemu: Can't find a matching FPU mode`. Подтверждено для CPU 24Kc/24Kf/74Kf. `readelf -A` доказал **PT_MIPS_ABIFLAGS.fp_abi=5**, cpr1_size=1, `Hard float (32-bit CPU, Any FPU)` у Core, а у *реального* загрузчика Entware 2.27 **fp_abi=3, cpr1_size=0**, Soft float. Ранее ошибочная документация утверждала отсутствие секции `.MIPS.abiflags`: на самом деле она есть в обоих ELF.
- **Диагностика, не готовый фикс:** только в временной копии Core ELF изменены 2 байта `PT_MIPS_ABIFLAGS` для анализа (не в исходном IPK). QEMU прошёл прежний FPU-gate, затем Rust завершился `EXIT 134`, `thread 'main' has overflowed its stack`. Увеличение гостевого стека до 64 МиБ не устранило сбой. Диагностическая копия содержит неконсистентные `.gnu.attributes` и **не пригодна для публикации/использования**.

Таблица доказательств:

| Гейт | Статус |
|---|---|
| GitHub IPK SHA-256, Entware runtime IPK SHA-256 | **PASS** |
| Panel Lite CLI `--version` под QEMU User Mode | **PASS** |
| Core FP ABI compatibility / запуск `--version` | **FAIL** |
| QEMU User Mode запуск Core после пересборки с правильным ABI | **NOT_TESTED** |
| KeeneticOS MT7621 / native `opkg` / service restart / persistence | **NOT_TESTED** |
| Real KN-1913 / Telegram network / RAM 256MiB / heavy crypto | **NOT_TESTED** |

## Fail-closed проверочный скрипт

`tools/telemt_mipsle_qemu_user_smoke.py` теперь отказывается принимать Core, если `PT_MIPS_ABIFLAGS.fp_abi != 3`. Раньше сценарий напрямую исполнял гостевой загрузчик и мог **пропустить** сочетание несовместимых FP ABI процесса и интерпретатора. Теперь скрипт исполняет именно оригинальный guest ELF с `-L disposable-root`, чтобы QEMU проверил его настоящий `PT_INTERP`; прежний "direct loader" путь удалён. Опциональный запуск требует `unshare`, `qemu-mipsel`, предварительно скачанные доверенные библиотеки Entware, и явно заданный `--run-core-cli`.

До исправления Core ниже ожидается **BLOCKED / FP ABI 5**, а не успешный запуск:

```bash
python3 tools/telemt_mipsle_qemu_user_smoke.py \
  --core-ipk /path/telemt_3.5.17-1_mipsel-3.4.ipk \
  --panel-ipk /path/telemt-panel-lite_1.0.0.rc.4-1_mipsel-3.4.ipk
```

Новый корректный Core потребует отдельной SHA-256 фиксации и review. **Не менять бинарные метаданные постфактум ради ложного PASS**: нужно пересобрать C/Rust с согласованным настоящим softfloat toolchain/sysroot, проверить отсутствие FP-инструкций, совпадение `.MIPS.abiflags` и `.gnu.attributes`, затем отдельно исследовать вторую ошибку `stack overflow`. Это **два отдельных блокера**.

Офлайн-тесты скрипта: `python3 -I -m unittest discover -s tools/tests -p 'test_telemt_mipsle_qemu_user_smoke.py' -v`. Никакого запуска на роутере или публикации release/feed без отдельного согласия владельца.
