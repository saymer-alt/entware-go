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
