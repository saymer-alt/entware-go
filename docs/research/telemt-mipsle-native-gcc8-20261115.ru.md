# TeleMT MIPSLE — реальный Entware GCC 8.4 Soft-float toolchain без KeeneticOS

Дата: 15 ноября 2026. Исследовательский, **не релизный** эксперимент. Все программы MIPSLE запускались в изолированной Linux-среде с `qemu-mipsel` и `unshare --user --map-root-user --net`, без доступа гостевых процессов к сети.

## Найдено

Ранее считалось, что нужно сначала полностью собрать Entware buildroot. Однако официальный пакет [gcc_8.4.0-9_mipsel-3.4.ipk](https://bin.entware.net/mipselsf-k3.4/gcc_8.4.0-9_mipsel-3.4.ipk) **уже содержит настоящий GCC 8.4, glibc 2.27 headers, `gnu/stubs-o32_soft.h`, C crt и libgcc.a**. Пакет проверен по официальному индексу Entware.

| Пакет (официальный Entware mipselsf-k3.4) | SHA-256 |
|---|---|
| `gcc_8.4.0-9_mipsel-3.4.ipk` | `2d56b649742903e229235e231898effef4aa969c5b5d48468a7e1a6d2bb39db5` |
| `libc_2.27-12_mipsel-3.4.ipk` | `45c7ef0bda2acb4475a75efee9734e83f69f54e128971b7a196d88c8b048a222` |
| `libgcc_8.4.0-12_mipsel-3.4.ipk` | `bbecc26b579470d52053b72e41dddb70415963eac9f74baf1747b9d2ecdcaaa3` |
| `libstdcpp_8.4.0-12_mipsel-3.4.ipk` | `5e1c6a59222ed9bc65a9a55f7f48aaba53655b53f4f9e3f36d5845bb101dcddc` |

**Важное отличие:** отдельный архив `include/include.tar.gz` **не** содержал glibc headers. Они извлечены именно из IPK GCC. Все четыре package bytes SHA-256 PASS. `gcc --version` под QEMU: `gcc (OpenWrt GCC 8.4.0) 8.4.0`.

## Воспроизведено

1. `qemu-mipsel -cpu 24Kc -L guestroot guestroot/opt/bin/gcc --version` — PASS, GCC 8.4.
2. Запуск обычного драйвера GCC для компиляции при отсутствии binfmt-misc падает на `execv: Exec format error`, потому что драйвер пытается породить гостевой `cc1` как дочерний процесс.
3. Прямой запуск **оригинального GCC8 `cc1`** через QEMU с параметрами `-msoft-float -fPIC -isystem <гостевые заголовки>` и сборка `.s` системным MIPSLE `mipsel-linux-gnu-as` — PASS. Фактический `shim.c` из `build-telemt-core.sh` PR #44 успешно скомпилирован. Объект `shim-gcc8.o`: `SOFTFLOAT_PASS`, `FP ABI=3`, `CPR1 size=0`.
4. Свежая независимая Linux-среда: `cc1` GCC8 → GNU MIPSLE assembler → GNU MIPSLE linker (`crt1.o`, `crti.o`, `crtbegin.o`, `libgcc_s`, `libc` и др. из проверенного Entware) → динамический ELF с `PT_INTERP=/opt/lib/ld.so.1`, `FP ABI=3` → `qemu-mipsel -cpu 24Kc -L guestroot <hello>` **возвратил 17, как задано в `main()`**. `DYNAMIC_ENTWARE_GCC8_GLIBC227_QEMU_USER_PASS`.
5. Скрипт выполнен ещё раз с тем же pin-cache — тот же SHA тестового ELF `a2e8e7287e565d586bcfbe8823faae527552b13e3884e1920b4e07b7cbe24ce5` и успешный запуск.

## Автоматизированные команды

В отдельной Debian x86_64 VM/контейнере **без привилегий на живых сетевых устройствах** должны быть Python 3.11+, QEMU User Mode, `unshare` и `binutils-mipsel-linux-gnu`:

```bash
sudo apt-get install qemu-user binutils-mipsel-linux-gnu
# Разовый download 4 официальных IPK по фиксированному SHA, распаковка в /tmp и
# настоящий compile + dynamic link + QEMU test:
python3 tools/telemt_mipsle_gcc8_elf_smoke.py --workspace /tmp/telemt-gcc8-research
# Проверить C shim без тяжёлого Cargo:
python3 tools/telemt_mipsle_gcc8_cc1_smoke.py --workspace /tmp/telemt-gcc8-research \
  --source /tmp/research/shim.c --output /tmp/research/shim-gcc8.o
python3 tools/telemt_mipsle_fp_abi_gate.py /tmp/research/shim-gcc8.o
python3 -I -m unittest discover -s tools/tests -p 'test_telemt_mipsle_*.py' -v
```

Для `shim.c` берётся **точное содержимое** heredoc из `docs/research/telemt-mipsle-ipk-3517/scripts/build-telemt-core.sh`; до Cargo-прогона файл можно получить из проверенной версии скрипта, не меняя его код. Сценарии ограничены по размеру пакетов, SHA, времени, отключают сеть у гостевого GCC/программы и не перезаписывают существующий выходной `.o`.

**Результаты независимой проверки текущего HEAD PR:** все 43 host-only unit PASS, в чистой среде динамический ELF PASS, реальный shim.c C-объект PASS. Результат не является проверкой `telemt` под QEMU, `opkg` внутри KeeneticOS, целой цепочки Cargo/ring/aws-lc или корректности glibc shim во всех режимах.

## Что делать дальше

Отдельно адаптировать `CC_mipsel_unknown_linux_gnu` для вызова нативного GCC8 `cc1` под QEMU и хостового ассемблера/линкера для **всех** вариантов C/assembly вызовов `ring` и `aws-lc` (сохранить MIPS ABI=3). Рекомендуется сначала дешёвый ограниченный C-only regression этих пакетов и затем ровно один полный Cargo Core rebuild. Отдельно проверить runtime Rust stack overflow и совместимость glibc shim. Не считать `GCC8 ELF smoke` разрешением на выпуск TeleMT Core или установку на реальный роутер.

Зависимые задачи: [PR #44](https://github.com/saymer-alt/entware-go/pull/44), [PR #45](https://github.com/saymer-alt/entware-go/pull/45), [PR #46](https://github.com/saymer-alt/entware-go/pull/46).
