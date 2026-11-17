# TeleMT MIPSLE — реальный QEMU User Mode, 15.11.2026

Документ фиксирует выполненные испытания реальных IPK. Зависимый [Draft PR #45](https://github.com/saymer-alt/entware-go/pull/45) на [Draft PR #44](https://github.com/saymer-alt/entware-go/pull/44). **Это не эмуляция KeeneticOS, не опробованная opkg-установка и не тест работы Telegram-прокси.**

## Актуальная приёмка: Core из run 43742529964

- [GitHub Actions #43742529964](https://github.com/saymer-alt/entware-go/actions/runs/43742529964): 4/4 SUCCESS. IPK `telemt_3.5.17-1_mipsel-3.4.ipk`, SHA-256 `b8dfbb83380d8f4353151b0de43d8c34ceb2369aea45cb6ddaf3b3089a798e5d`; ELF SHA-256 `3efa4a53c1d50bf1b7a0ed6ca7de98201faf0fa2e27eaaf5f1cd589a6bf26063`. ZIP CRC + SHA проверены после независимого скачивания.
- Официальные runtime-пакеты Entware `libc 2.27-12`, `libgcc 8.4.0-12`, `libpthread 2.27-12`, `librt 2.27-12` независимо загружены и SHA-256 совпали с утверждёнными пинами. Файлы извлечены в одноразовый `guestroot/opt/lib`.
- Настоящий `qemu-mipsel 7.2.22`, `-cpu 24Kc`, `-L guestroot`, `unshare --user --map-root-user --net` (никаких Telegram-соединений и доступного гостю внешнего сетевого интерфейса). И Core, и загрузчик Entware: `FP ABI: Soft float`.
- `telemt healthcheck --mode=qemu-smoke-invalid` → **EXIT 2**, правильный текст `Invalid --mode value`. Проверяет CLI без запуска сервера.
- `telemt run /tmp/.../invalid-existing.toml`: файл с незакрытой TOML-таблицей зафиксирован перед запуском. Из-за поведения QEMU `-L` дополнительно скопирован по тому же абсолютному пути **в гостевой корень**, иначе `openat` возвращал ENOENT даже при наличии файла на хосте. После зеркалирования → **EXIT 1, настоящий TOML parse error / unclosed table**, файл не изменён. В отличие от предыдущего IPK, **нет** `invalid timestamp`, Rust panic или `stack overflow`.
- Core **не имеет** поддерживаемого `--version`. Старый ошибочный QEMU-smoke с `--version` запускал обычный серверный путь. Текущий скрипт [`tools/telemt_mipsle_qemu_user_smoke.py`](../../tools/telemt_mipsle_qemu_user_smoke.py) использует только два явно проверенных отрицательных сценария.

| Гейт | Фактический статус |
|---|---|
| SHA-256/ELF MIPSLE softfloat/glibc static | **PASS** |
| Panel Lite RC4 CLI `--version` (старый оригинальный IPK) | **PASS** |
| Core CLI: отвергнуть неподдерживаемый healthcheck mode | **PASS** |
| Core Tokio: прочитать некорректный TOML и завершиться контролируемо | **PASS**, только отрицательный сценарий |
| Core рабочий сервер/HTTPS/Telegram, ресурсы и crypto | **NOT_TESTED** |
| KeeneticOS MT7621, native `opkg`, перезапуск, сохранение настроек | **NOT_TESTED** |
| Реальный Keenetic KN-1913 | **NOT_TESTED** |

## Прошлые неудачи и доказанный прогресс

Начальный оригинальный Core из Actions 43624729371 (IPK SHA `a04f754375056439c3d5584bf7d868eb547f844c4779e3076bfbdd84129d63fa`) не запускался из-за **FP ABI=5**, несовместимого с Entware softfloat ABI=3. Следующий Core после исправления softfloat (Actions 43720897639) достиг Rust, но падал на рекурсивных `__clock_gettime64` и подобных функциях shim, `stack overflow`. Коммит `c001a82` исправил явные вызовы glibc time32. Затем выявлен и исправлен порядок линковки `-lc shim.o -lc`. Core из Actions 43726565495 получил корректный softfloat и прекратил переполнение стека, но падал на `invalid timestamp` из-за смешения 8-байтного MIPS O32 `timespec32` и 16-байтного `timespec64`. Коммиты `7fa6cb6` + `bedab32` исправили время и отдельную запись `stat` в буфер неправильной структуры; для этих исправлений есть независимый QEMU-пробник и четыре регрессионных теста.

## Использование

```bash
python3 -m unittest discover -s tools/tests -p 'test_telemt_mipsle_qemu_user_smoke.py' -v

# host-only статическая проверка по pinned IPK:
python3 tools/telemt_mipsle_qemu_user_smoke.py --core-ipk /verified/new/core.ipk

# только на одноразовом x86_64 lab host с заранее проверенными Entware /opt/lib:
python3 tools/telemt_mipsle_qemu_user_smoke.py \
  --core-ipk /verified/new/core.ipk \
  --entware-lib-dir /verified/entware/opt/lib \
  --run-core-cli
```

Не устанавливать файлы на устройство и не сливать Draft PR только на основании двух отрицательных smoke-тестов. Для полноценного приёма нужны настоящий сервисный запуск в MT7621/KeeneticOS, `opkg`, проверки памяти и rollback.
