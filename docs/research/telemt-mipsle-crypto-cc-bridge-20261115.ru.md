# TeleMT MIPSLE: проверенный C/ASM-мост Entware GCC 8.4 для ring и aws-lc

**Дата:** 15.11.2026. Только исследование на disposable Linux/QEMU User Mode. Без Z AI, без прошивки KeeneticOS, без физического маршрутизатора, без Core rebuild/release. Основано на [Draft PR #46](https://github.com/saymer-alt/entware-go/pull/46).

## Почему нужен мост

TeleMT 3.5.17 (upstream pinned SHA `66708d2866f3f3a4541c4fa67984d408e71a8af4`) по `Cargo.lock` содержит `ring 0.17.14` и `aws-lc-sys 0.45.0`. Имеющийся исследовательский Core из PR #44 несовместим с Entware MIPSLE: FP ABI=5 (Hard/FPXX), а штатные glibc 2.27 и загрузчик `/opt/lib/ld.so.1` требуют Soft float (ABI=3).

Мы нашли настоящий `gcc_8.4.0-9_mipsel-3.4.ipk` с Soft-float заголовками, `cc1`, crt и библиотеками. В ограниченном QEMU User Mode драйвер GCC8 не может сделать `execv(cc1)` без binfmt. Для короткой C-проверки можно вызывать оригинальный `cc1` непосредственно под QEMU и затем MIPSLE GNU assembler на хосте. Для `.S` применён целевой препроцессор MIPSLE + GNU assembler с `-msoft-float`. Это исследовательская схема, **не полноценная замена GCC/CMake/Cargo**.

## Что добавлено

- `tools/telemt_mipsle_cc_bridge.py`: compile-only адаптер синтаксиса `cc-rs` (`-c`, `-o`, `-I`, `-D`, `-U`, `-std`, `-O`, `-g`, `-f`, `-W` и т. п.). **Не исполняет линковку**, отклоняет `-mhard-float`, некорректную архитектуру, непроверенные флаги, `-Wl,/-Wa,/-Wp,`, ответные файлы. Каждый новый ELF `.o` отдельно проходит строгую ABI-проверку, только после чего атомарно заменяет старый объект. Ошибка компиляции оставляет прежний файл без изменений. У гостевого `cc1` отключена сеть посредством `unshare --user --map-root-user --net`.
- `tools/telemt_mipsle_ring_c_smoke.py`: скачивает строго зафиксированный `ring-0.17.14.crate` и проверяет SHA-256 из Cargo.lock; создаёт `ring_core_generated/prefix_symbols.h` на основании **точных массивов** в оригинальном `build.rs` (155 имён и 7 переименований). Проверяет четыре настоящих C-файла.
- `tools/telemt_mipsle_aws_lc_c_smoke.py`: скачивает `aws-lc-sys-0.45.0.crate` с SHA из Cargo.lock и проверяет два C-файла.
- 3 новых host-only test suites: 14 + 6 + 5 = **25 unit-тестов**. При совместном прогоне с уже подготовленными ранее 43 тестами зависимого PR #46 — **68/68 PASS**.

## Воспроизводимые фактические результаты

Pin crate: `ring 0.17.14` SHA-256 `a4689e6c2294d81e88dc6261c768b63bc4fcdb852be6d1352498b114f61383b7`.

| ring C-исходник | SHA-256 скомпилированного `.o` | ABI |
|---|---|---|
| `crypto/mem.c` | `8a5725a0734c23e3e315e8a3aa5b3468efca8d502ccf9d754ebc360b5696d8b1` | Soft float 3, PASS |
| `crypto/limbs/limbs.c` | `61f21fa6a3ce5cee95cdac1a18fb8ab501d4dd2fb9ac998cf90859aa93ea05be` | Soft float 3, PASS |
| `crypto/fipsmodule/aes/aes_nohw.c` | `ef15117e4e0e05e213a075e1b23e9559498e2da72d287d95f5fc763df97e6da3` | Soft float 3, PASS |
| `crypto/curve25519/curve25519.c` | `8d6aeec20a33212ecba9b39d7db75fd99485002a3c20f0ebc19e3ec09c7f23ae` | Soft float 3, PASS |

Pin crate: `aws-lc-sys 0.45.0` SHA-256 `9bff6c3b54fad79a2e60b8102caf565819711497c1f5f092f49508e2f5c31b27`.

| aws-lc C-исходник | SHA-256 скомпилированного `.o` | ABI |
|---|---|---|
| `aws-lc/crypto/mem.c` | `4247cb2a896898a1a8ef19737c8bf0b2c33f6cba0a75911fabdaec304cf2f9d0` | Soft float 3, PASS |
| `aws-lc/crypto/bytestring/cbs.c` | `ba55eea5a035bf05aaf2d436d9fa2cfa47997623f1f6287253c4b518341b4e1f` | Soft float 3, PASS |

В отдельной проверке вручную `.S` с `jr $ra` и `nop` также собрался в Soft-float объект. C-команда `ring` с `-O3 -g3 -ffunction-sections -fdata-sections` и полным набором используемых `ring` предупреждений прошла. Неверный `-I` давал код ошибки, и существующий `.o` **не был перезаписан**. Набор всех 68 host-only unit-тестов и оба crate smoke повторно прошли на чистой Linux-среде с проверенными IPK.

## Как запускать без агента

На отдельной одноразовой Debian x86_64 VM (нужны Python 3.11+, QEMU User Mode, unshare, MIPSLE host binutils и GCC только для препроцессинга `.S`):

```bash
sudo apt-get install qemu-user binutils-mipsel-linux-gnu gcc-mipsel-linux-gnu
# Отдельно скачивает 4 SHA-pinned Entware IPK, 1.5 MiB ring crate и 9.7 MiB aws-lc crate:
python3 tools/telemt_mipsle_ring_c_smoke.py --workspace /tmp/telemt-c-bridge-lab
python3 tools/telemt_mipsle_aws_lc_c_smoke.py --workspace /tmp/telemt-c-bridge-lab
python3 -I -m unittest discover -s tools/tests -p 'test_telemt_mipsle_*.py' -v
```

При ручном запуске compile-only cc-rs-подобной команды заранее подготовить SDK через `prepare_sdk` из `tools/telemt_mipsle_gcc8_cc1_smoke.py`, затем указать `ENTWARE_MIPSEL_GUESTROOT=/ABSOLUTE/LAB/sdk/guestroot`; путь не должен указывать на действующую `/opt` или системное SDK. **В каждом вызове мост ничего сам не скачивает**.

## Что остаётся непроверенным

Пока доказаны только **4 C файла ring + 2 C файла aws-lc + маленький `.S`**, а не сборка всех библиотек. В частности, `aws-lc-sys` имеет отдельный CMake-процесс и сотни C/ASM исходников, который не покрыт этим инструментом; не доказано корректное выполнение crypto, link whole library, `Cargo build`, корректная адаптация rustc-linker, `glibc shim` (включая риск повреждения struct stat), Rust stack overflow, ограничения RAM MT7621, native `opkg`, рестарт и персистентность KeeneticOS.

**Следующий безопасный этап:** интеграция с конкретными вызовами `cc` из `ring` build.rs и с CMake `aws-lc-sys`, ревизия опций компилятора и отделённый linker wrapper на официальных Entware crt. Только после unit + реального C/ASM набора — один ограниченный `Cargo` Core build, затем полноценный QEMU User Mode. Не переносить исследовательский CC bridge напрямую в релизный CI без отдельного review; не делать merge текущего Draft PR без GO владельца.
