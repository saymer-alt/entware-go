# TeleMT MIPSLE: воспроизведённая ошибка FPU ABI и безопасный предсборочный контроль

15.11.2026. Исследование без Z AI, без длительной Rust/LTO-сборки, без физических Keenetic и без публикации IPK. Продолжение [Draft PR #44](https://github.com/saymer-alt/entware-go/pull/44) и [QEMU User Mode #45](https://github.com/saymer-alt/entware-go/pull/45).

## Подтверждённое поведение

| Реальный бинарник | GNU / MIPS FP ABI | QEMU User Mode |
|---|---:|---|
| Core 3.5.17 из run 43624729371 | 5 — Hard float / FPXX | FAIL: Can't find a matching FPU mode |
| Panel Lite RC4 из того же run | 3 — Soft float | PASS: --version, exit 0 |
| Загрузчик Entware glibc 2.27 | 3 — Soft float | ожидаемый ABI |

В исследовательском скрипте Core (PR #44) обычный C-компилятор запускается **без флага -msoft-float**, в том числе для shim.o. При этом флаг -msoft-float задаётся позднее линкеру. Он не переписывает ABI метаданные уже скомпилированных C-объектов. Rust target-feature +soft-float не распространяется автоматически на ring/aws-lc C-часть.

Дешёвое независимое воспроизведение на Debian GCC mipsel 12.2 с исходником, включающим time.h и sys/stat.h:

- Обычная C-компиляция: объект ABI=5, Hard float.
- Та же команда с -msoft-float: ошибка, отсутствует gnu/stubs-o32_soft.h в Debian hardfloat cross-headers.
- C-объект без libc include с -msoft-float: ABI=3, Soft float.

**Нельзя исправлять эту ошибку редактированием двух байт в готовом ELF.** На одной такой исключительно диагностической копии после прохождения FPU-gate Rust завершился stack overflow. Это отдельный неподтверждённый по первопричине дефект, который надо повторно исследовать на правильно пересобранном Core.

## Что добавлено в этом зависимом Draft PR

- tools/telemt_mipsle_fp_abi_gate.py — offline ELF32 little-endian MIPS parser: сопоставляет секцию .MIPS.abiflags, PT_MIPS_ABIFLAGS и .gnu.attributes и требует FP ABI=3. Проверяет также объектные .o, не зависит от QEMU, GCC, сети. Поле CPR1 size выводится как диагностика, но намеренно не обязано быть 0: в работоспособной Panel Lite FP ABI=3 и CPR1 size=32.
- tools/telemt_mipsle_softfloat_probe.py — compile-only тест подлинных glibc 2.27 softfloat C-заголовков (features.h, gnu/stubs-o32_soft.h, time.h, sys/stat.h), с компиляцией крошечного C-объекта и проверкой его ABI. Нет SDK — немедленный SOFTFLOAT_SDK_BLOCKED, без долгого Cargo.
- tools/tests/test_telemt_mipsle_fp_abi_gate.py — быстрые положительные и отрицательные unit-тесты ELF метаданных и неполного SDK.

Примеры запуска с корня репозитория:

    python3 tools/telemt_mipsle_fp_abi_gate.py /path/to/telemt /path/to/shim.o
    python3 tools/telemt_mipsle_softfloat_probe.py --gcc mipsel-linux-gnu-gcc --headers /trusted/entware-mipsel-sdk/.../usr/include
    python3 -I -m unittest discover -s tools/tests -p 'test_telemt_mipsle_fp_abi_gate.py' -v

Предсборочный gate **не доказывает** корректность glibc shim, отсутствие FP-инструкций, поддержку ограничений kernel/MT7621, отсутствие переполнения стека или runtime TeleMT. Эти проверки остаются отдельными.

## Путь к настоящему исправлению Core (не выполнен в этом PR)

1. Подготовить проверенный Entware MIPSLE soft-float SDK с GCC и glibc 2.27, взяв за основу [конфигурацию Entware mipsel-3.4](https://github.com/Entware/Entware/blob/master/configs/mipsel-3.4.config) и [официальную инструкцию сборки](https://github.com/Entware/Entware/wiki/Compile-packages-from-sources). Нельзя генерировать фиктивный gnu/stubs-o32_soft.h из hard-float файла, это скроет несовместимость ABI.
2. Сначала выполнить tiny C-probe; потом компилировать C-зависимости и shim.o с -msoft-float, используя **совместимые glibc 2.27 заголовки**, а не Debian 2.39. Прогнать gate на реальном shim.o до длинного Cargo.
3. Прогнать gate на итоговом Core вместе с GLIBC version gate, FP instruction census и реальным QEMU user-mode --version. Лишь после этого исследовать возможный Rust stack overflow, криптографию, RAM и остальные runtime-гейты.
4. Не повторять идентичные дорогие сборки; по утверждённой политике остановиться после двух одинаковых FAIL без новых свидетельств.

**Границы:** этот PR добавляет только диагностику. Исходный build-telemt-core.sh и тяжёлые workflow PR #44 не изменены, чтобы случайно не запускать долгую сборку. Никаких релизов, установки Entware на рабочий роутер или merge без review.

## Разбор штатного Entware SDK — 15 ноября 2026

**Новые проверенные источники:**

- Entware: [mipsel-3.4.config](https://github.com/Entware/Entware/blob/541289a115d32d1ab044e87608bc0ca6b2154ee9/configs/mipsel-3.4.config), commit `541289a115d32d1ab044e87608bc0ca6b2154ee9`; SHA-256 файла `280de04bff8d538ac62371dedae0eca37169903e8d175970ba4cdfee3e8ad2a2`.
- Официальный архив [include.tar.gz](https://bin.entware.net/mipselsf-k3.4/include/include.tar.gz) — 39 407 263 байта, проверенный SHA-256 `bb76e07d72bfdd8e737cfd82b6cad1521377f8b505f2eb743b555d9596019ceb`, 29 917 entries. **Он не является glibc SDK:** нет `features.h`, `sys/stat.h`, `gnu/stubs-o32_soft.h` и `gnu/stubs.h`.
- GNU [glibc-2.27.tar.xz](https://ftp.gnu.org/gnu/glibc/glibc-2.27.tar.xz), измеренный SHA-256 `5172de54318ec0b7f2735e5a91d908afe1c9ca291fec16b5374d9faadfc1fc72`; скачан с GNU по HTTPS, подпись GPG отдельно не проверена.

**Реально выполненный ограниченный эксперимент на изолированном Debian x86_64 + mipsel GCC 12.2:**

1. glibc 2.27 успешно сконфигурирована с `CC='mipsel-linux-gnu-gcc -msoft-float'`, `--host=mipsel-linux-gnu`, `--build=x86_64-linux-gnu`, `--enable-kernel=3.4.0`, `--disable-werror`.
2. `make -j4 install-headers` завершился успешно. Получено 419 заголовков; **`gnu/stubs-o32_soft.h` не появился**. В glibc это генерируемый файл, и простого install-headers недостаточно.
3. Первая сборка glibc остановилась на множественных определениях `__nss_*_database`, связанных с новым GCC default `-fno-common`.
4. Повторная ограниченная попытка с `CFLAGS='-O2 -g -fcommon'` устранила указанные определения. Успешно сформированы локальные `build/libc.so` и `build/elf/ld.so`, дальнейшая компоновка модулей продвинулась, но временная сессия была прекращена **до подтверждения полной готовности**.
5. GCC 12 выдавал предупреждения о смешении Soft-float glibc с Hard-float `crtbegin*.o`, `crtend*.o`, `libgcc.a`. Даже если такой эксперимент закончить, **он не является пригодным штатным Entware SDK**. Не применять на роутере и не маскировать `gnu/stubs-o32_soft.h` копией hardfloat stubs.

**Новая проверка, добавленная в текущий PR:** `tools/telemt_mipsle_entware_config_gate.py` и десять unit-тестов. Проверяется именно штатная конфигурация GCC 8.4 / glibc 2.27 / MIPS32r2 / Soft float, без внешнего компилятора. **10/10 тестов PASS**, реальный upstream Entware config — `ENTWARE_MIPSEL_3_4_PASS`; GCC 8.4 и его целевые заголовки фактически пока не получены.

**Следующий воспроизводимый шаг** — отдельный постоянный Linux x86_64 host для сборки штатного Entware toolchain, без живого Keenetic и без Z AI:

```bash
git clone https://github.com/Entware/Entware.git
cd Entware
git checkout --detach 541289a115d32d1ab044e87608bc0ca6b2154ee9
cp configs/mipsel-3.4.config .config
python3 /path/to/entware-go/tools/telemt_mipsle_entware_config_gate.py --config .config
make defconfig
python3 /path/to/entware-go/tools/telemt_mipsle_entware_config_gate.py --config .config
# Ресурсоёмкие цели, в этой сессии НЕ запускались:
make tools/install
make toolchain/install
make target/compile
```

После этого определить фактический GCC8.4 и include path в staging_dir, запустить **`--gcc`** у config gate и compile-only `telemt_mipsle_softfloat_probe.py` с заголовками glibc2.27, затем ELF ABI gate на реальном `shim.o`. Только после успешных дешёвых проверок разрешён один ограниченный Cargo Core rebuild и проверка QEMU User Mode. Использовать исходные hardfloat C wrappers или подменённый ELF запрещено.

**Текущие гейты:** Entware config PASS; glibc 2.27 configure PASS; glibc install-headers PASS; реальный softfloat `stubs-o32_soft.h` NOT_READY; штатный Entware GCC8.4 SDK NOT_TESTED; Core rebuild NOT_TESTED; оригинальный Core ABI=5 FAIL.
