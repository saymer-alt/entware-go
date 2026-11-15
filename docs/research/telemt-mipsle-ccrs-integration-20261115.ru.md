# TeleMT MIPSLE — реальный Cargo cc-rs 1.4.5 → Entware GCC 8.4

**15 ноября 2026.** Исследовательская проверка, продолжение [Draft PR #47](https://github.com/saymer-alt/entware-go/pull/47). Никакой записи в рабочий Keenetic, публикации IPK, полного TeleMT Core rebuild или использования акционных токенов Z AI.

## Подтверждённая проблема и минимальное исправление

Первый **настоящий** запуск `Cargo build.rs` с `cc = "=1.4.5"` и предыдущим компиляторным мостом завершался FAIL ещё до полноценного C-compile:

- `cc-rs` вызывает `CC -E detect_compiler_family.c` и анализирует вывод для определения семейства GCC/Clang. Мост не принимал `-E`.
- Затем `cc-rs` вызывает `CC -O0 -ffunction-sections -fdata-sections -fPIC -g -gdwarf-4 -fno-omit-frame-pointer -Wall -Wextra -o ... -c native/bridge.c`. Мост отклонял `-gdwarf-4`.

Исправление в `tools/telemt_mipsle_cc_bridge.py`: добавить **только** bounded `-E SOURCE.c` без записи файла, подлинный Entware GCC8 `cc1` через `qemu-mipsel` c `unshare --user --map-root-user --net`; выводить результат в stdout для `cc-rs`. Разрешить `-gdwarf-2..5` при строгом разборе аргументов. Любые `-Wl,`, `-Wa,`, `-Wp,`, `-mhard-float`, произвольные параметры линковки и неподдерживаемые режимы по-прежнему **fail-closed**.

## Доказательства реального запуска

Среда: одноразовая Debian 12 x86_64, Cargo 1.65.0, официальный Rust 1.85.1 host rustc+std, `cc-rs 1.4.5`, QEMU User Mode 7.2.22, GNU MIPS32r2 binutils, четыре проверенных Entware IPK с настоящим GCC8/glibc2.27 из зависимого PR #46. Rust-зависимости загружены с crates.io, проверены по SHA-256, помещены в локальный vendor; `cargo build --offline -vv`, а у гостевого GCC сеть отключена.

| Проверка | Результат |
|---|---|
| Ровно `cc-rs 1.4.5` Cargo `build.rs`, GCC8 `-E` detection | **PASS** |
| `cc-rs` compile с `-gdwarf-4`, Entware GCC8 cc1 и MIPS32r2 assembler | **PASS** |
| `libcc_mipsle_probe.a`: один `.o`, `bridge_add`, Soft float ABI=3 | **PASS** |
| Оригинальные 4 `ring 0.17.14` C-файла через **тот же настоящий `cc-rs`** → `libring_c_subset.a` | **PASS** |
| Все 4 объекта в `libring_c_subset.a` и символ `ring_core_0_17_14__CRYPTO_memcmp` | **PASS**, ABI=3 для каждого |
| Строгий `telemt_mipsle_ccrs_archive_gate.py`: настоящий Soft-float `.a` | **PASS** |
| Тот же инструмент: намеренно Hard-float `.a` | **BLOCKED**, правильный отказ (exit=2) |
| Python offline unit (PR #46 + #47 + этот PR) | **83/83 PASS** |

Тестовый `libring_c_subset.a`: SHA-256 `e28dd83f562eefb938276f7cfb7191b0999b284e7d6325763be5dd44df4d9e20` в использованном одноразовом стенде. Полнота и криптографическая корректность ring из этого не следуют: тестировались **только четыре C-объекта**, без полного набора источников и без Rust-link.

### Зафиксированная цепочка crates.io

`tools/tests/fixtures/ccrs_mipsle/Cargo.lock` создан реальным Cargo `generate-lockfile --offline` на локальном vendor, где tarball каждого источника проверен по checksum.

- `cc 1.4.5`: `005ec2760ca554fae18df7a11195552ec576cd665632a881bc011d5bb2fd4d80`.
- `find-msvc-tools 0.1.12`: `3e0f1c7c3a72c66fd80abe965175f7523475c0489a87d3ff9d6e8c87d87a9d2d`.
- `shlex 2.0.1`: `f8fadd59c855ef2080decdef8ff161eb6661b86933c9d82e5ba29dc602a55aba`.

В `Cargo.lock` **нет** optional `jobserver`/`libc`, поскольку feature `parallel` не используется в этом host-only smoke.

## Воспроизведение

`tools/tests/fixtures/ccrs_mipsle` — маленький host-side Cargo project. Его Rust `main.rs` не потребляет MIPS-архив; `build.rs` явно вызывает `cc::Build::target("mipsel-unknown-linux-gnu")` и `mipsel-linux-gnu-ar`. Так мы проверяем цепочку C-компиляции, не пытаясь запускать TeleMT или линковать MIPS в x86-программу.

Требования: Linux x86_64, Python 3.11+, Rust host (в проверке 1.85.1), Cargo, `qemu-mipsel`, `unshare`, `mipsel-linux-gnu-ar/as`; подготовленный проверенный Entware GCC8 guestroot через `prepare_sdk` из зависимого PR #46. В окружении, где Cargo не может обратиться к индексу, потребуется предварительный `cargo vendor` из `Cargo.lock` (или локальный vendor из строго SHA-verified .crate). Сама команда `cargo build --locked --offline` не обращается к сети.

```bash
export ENTWARE_MIPSEL_GUESTROOT=/absolute/lab/sdk/guestroot
export CC_mipsel_unknown_linux_gnu=/absolute/repo/tools/telemt_mipsle_cc_bridge.py
cd /absolute/repo/tools/tests/fixtures/ccrs_mipsle
cargo build --locked --offline -vv

# Проверка минимальной библиотеки:
ARCHIVE=$(find target/debug/build -name libcc_mipsle_probe.a -print -quit)
python3 ../../../telemt_mipsle_ccrs_archive_gate.py \
    --archive "$ARCHIVE" --expected-objects 1
```

Для режима `ring` сначала получить **проверенный** crate `ring 0.17.14` и создать `ring_core_generated/prefix_symbols.h` из оригинального `build.rs`, как в `telemt_mipsle_ring_c_smoke.py`; задать `TELEMT_RING_SOURCE_ROOT=/absolute/ring-0.17.14` и `TELEMT_RING_GENERATED_INCLUDE=/absolute/generated`. Перезапустить `cargo build --locked --offline`, затем проверить:

```bash
ARCHIVE=$(find target/debug/build -name libring_c_subset.a -print -quit)
python3 ../../../telemt_mipsle_ccrs_archive_gate.py \
    --archive "$ARCHIVE" --expected-objects 4 \
    --required-symbol ring_core_0_17_14__CRYPTO_memcmp
```

Гейт читает все `.o` через `mipsel-linux-gnu-ar p`, проверяет ELF32/MIPS, `ET_REL`, `.MIPS.abiflags` и `.gnu.attributes`, требует `FP ABI=3` у каждого объекта. Не публикует файлы и не запускает код из `.a`.

## Оставшиеся блокеры

**Не проверены:** полный `ring`, CMake-механизм `aws-lc-sys 0.45.0` (пока только 2 C-файла в PR #47), все флаги `cc-rs` на реальном TeleMT Cargo, настоящий linker Rust на Entware crt, `glibc time64/stat shim`, возможный Rust stack overflow, сборка и запуск нового Core, `opkg` и KeeneticOS/QEMU-system.

До нового Core rebuild нужно отдельное исследование `aws-lc` CMake-toolchain и linker wrapper с ABI-gates. Не менять bytes исходных Core IPK/ELF и не объявлять `CORE_RUNTIME_PASS` на основании этих тестов. Draft PR остаётся исследовательским до review и разрешения на merge.
