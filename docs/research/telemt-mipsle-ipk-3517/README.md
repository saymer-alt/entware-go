# TeleMT 3.5.17 + Panel Lite RC4 → Entware mipsel-3.4 IPK (experimental)

> **15.11.2026: prior Core CI ABI PASS is a proven FALSE POSITIVE.** Under
> actual QEMU User Mode the previous hardfloat Core (FP ABI 5) fails against
> Entware's softfloat loader (FP ABI 3). The recipe here is a **new research
> candidate**, not yet a successful TeleMT Core runtime. We now compile
> C/shim with -msoft-float, use audited FPU-free crt copies, and reject
> non-softfloat ABI before IPK publication. The Debian glibc __stub_ header
> alias is research-only; a native Entware cross-glibc dev sysroot remains
> preferable. Panel Lite RC4 CLI is independently QEMU verified.
> Do not merge/release/deploy before real new Core smoke passes. Details:
> [dependent PR #45](https://github.com/saymer-alt/entware-go/pull/45).

Продолжение Issue #37 после PR #43 (compat-слой atomic64): превращаем два успешно
кросс-скомпилированных бинарника в **два отдельных экспериментальных IPK**, ABI-совместимых
с Entware `mipsel-3.4` на MT7621 (MIPS32r2 LE, softfloat, glibc 2.27, загрузчик `/opt/lib/ld.so.1`).
Пакеты готовы к будущим QEMU-испытаниям (см. [QEMU-MT7621-guide.ru.md](QEMU-MT7621-guide.ru.md));
публикация в feed/Release и установка на устройства — запрещены ТЗ.

## Статусы

| Гейт | Результат | Доказательство |
|---|---|---|
| `CORE_BUILD` | PASS | upstream `66708d28…` + patch PR #43; nightly `-Z build-std`, MIPS32r2, o32 |
| `CORE_ENTWARE_ABI` | PASS | interpreter `/opt/lib/ld.so.1`; RUNPATH `/opt/lib`; макс. GLIBC-версия символов ≤ 2.27; **0 FPU-инструкций** (objdump-census); 0 `.MIPS.abiflags` (legacy-представление, как у самих библиотек Entware) |
| `PANEL_BUILD` | PASS | рецепт PR #40 без изменений: Go (go.mod), Node 22, `GOOS=linux GOARCH=mipsle GOMIPS=softfloat CGO_ENABLED=0 GOEXPERIMENT=nojsonv2 -tags lite` |
| `PANEL_STATIC_PREFLIGHT` | PASS | pure-Go статический ELF32 MIPSLE; PR #42-инструмент, режим `lite-rc4` |
| `IPK_PACKAGE_VALIDATION` | PASS | оба IPK проходят расширенный PR #42-инструмент (`telemt_mipsle_ipk_preflight.py`, + режим `core`); control.tar.gz/data.tar.gz, `Architecture: mipsel-3.4`, без `opt/etc`/`opt/var`, без автозапуска; unit-тесты 7/7 |
| `QEMU_RUNTIME` | NOT_TESTED | эмулятор не готов (гайд написан, выполнение — отдельный owner-GO) |
| `OPKG_INSTALL_ROLLBACK` | NOT_TESTED | только после QEMU |
| `PHYSICAL_DEVICE` | NOT_TESTED | только после QEMU + owner-GO |
| RAM 256 МБ | NOT_MEASURED | MIPSLE-бинарник не исполняется на x86_64-хосте (эмулятор не готов); реальный RSS будет измерен в QEMU. Статическая часть: бинарник 26.8 MB on-disk (strip-debug), IPK core 9.3 MB сжатый |

CI: workflow `telemt-mipsle-ipk-3517-rc4-experimental` (изолированный, `contents: read`,
artifacts 7 дней, без Release/feed) — ссылка на прогон добавлена в Issue #37.

## Что выяснилось про Entware ABI (главное в этой задаче)

Наивный бинарник из PR #43 (glibc 2.39, `/lib/ld.so.1`) **не запускается** на Entware:

1. **GLIBC-версии символов.** У 2.39-сборки в `.gnu.version_r` — `GLIBC_2.32/2.33/2.34`;
   на glibc 2.27 загрузчик отвечает «version GLIBC_2.34 not found». Главный источник —
   `Scrt1.o`/`crt1.o` 2.34+ (ссылка на `__libc_start_main@GLIBC_2.34`). Фикс: crt-объекты
   и `libc_nonshared.a` из glibc **2.24** (Debian stretch cross; ≤2.27 всегда совместимо),
   а не «пересборка с новыми заголовками».
2. **Sysroot из того, что реально крутится на устройстве.** Entware не публикует готовый
   toolchain (только сборка через OpenWrt SDK — слишком тяжело). Поэтому sysroot собран
   из **runtime-пакетов Entware feed** `mipselsf-k3.4`: `libc_2.27-12`, `libgcc_8.4.0-12`,
   `libpthread_2.27-12`, `librt_2.27-12` (pthread/rt — **отдельные пакеты**, в libc только
   базовые заглушки). Это даёт линковку ровно против тех .so, что лежат в `/opt/lib`.
3. **Search order линковщика.** Debian cross-gcc подставляет install-relative `-L` раньше
   sysroot — без `-B$SYSROOT/usr/mipsel-linux-gnu/lib/` линковка молча уходит в 2.39.
   Фикс: `-B` первым аргументом + `--sysroot` + явный `libc.so`-скрипт
   `GROUP ( libc.so.6 libc_nonshared.a AS_NEEDED ( ld.so.1 ) )` (`__tls_get_addr` на MIPS
   живёт в ld.so.1).
4. **Softfloat.** `mipselsf` = soft-float (MT7621 без FPU). Rust: `-C target-feature=+soft-float`
   (codegen soft, census 0). C-код ring/aws-lc компилируется в дефолтном режиме — дистрибутивные
   2.39-заголовки не содержат `gnu/stubs-o32_soft.h`; эти исходники не содержат FP-математики,
   а гейт `FPU instructions: 0` по objdump гарантирует отсутствие cop1 в итоговом бинарнике.
   `patchelf`-подход отклонён по ТЗ: интерпретатор — не единственная несовместимость.
5. **FP ABI.** Ни наши объекты (rustc не эмитит `.MIPS.abiflags` для этой цели), ни библиотеки
   Entware не несут abiflags — legacy-представление, ld и ld.so проверки FP-ABI не отклоняют.
6. **time64-символы (`__clock_gettime64`, `__fcntl_time64`, `__stat64_time64`, `__ioctl_time64`,
   `__nanosleep64`) и `__isoc23_strtol`.** Заголовки glibc 2.39 при `_GNU_SOURCE` (обязателен
   для aws-lc, задается cc-rs) на 32-бит архитектурах редиректят clock_gettime/nanosleep/
   fcntl/ioctl/stat → `__*_time64` и strtol → `__isoc23_strtol`; кроме того, rust 1.102 std
   сам ссылается на `__clock_gettime64` через `weak!` (y2038-подготовка), и при
   `lto = "fat"` (профиль upstream) эта функция инлайнится в cgu бина, теряя
   `extern_weak`-линкаж → сильная ссылка. В glibc 2.27 этих символов нет. Фикс: шим-объект
   (`shim.o`, компилируется с `-fPIC`, линкуется напрямую `-C link-arg`, т.к. архив
   до ссылающихся объектов не подтягивается) — точный бэкпорт семантики glibc-2.34+:
   time64-структуры (`{i64 sec, i32 nsec, pad}` — идентичны у std и glibc) конвертируются
   в 2.27-syscalls; Y2038-усечение приемлемо для research-сборки и документировано.
7. **Итоговый ABI-гейт бинарника:** interpreter `/opt/lib/ld.so.1`; RUNPATH `/opt/lib`;
   NEEDED = libgcc_s.so.1, librt.so.1, libpthread.so.0, libm.so.6, libdl.so.2, libc.so.6,
   ld.so.1 (все пакеты есть в Entware); максимальная GLIBC-версия символов **2.25 ≤ 2.27**;
   **0 FPU-инструкций**; 0 `.MIPS.abiflags` (legacy-представление, как у самих библиотек
   Entware); 26 835 456 байт.

## Рецепты

Локально (WSL Ubuntu, cross-gcc 12 из PR #43-стенда):
```bash
bash docs/research/telemt-mipsle-ipk-3517/scripts/build-telemt-core.sh   # сборка + ABI-гейт
python3 tools/telemt_mipsle_ipk_preflight.py --kind core --file telemt_3.5.17-1_mipsel-3.4.ipk
python3 tools/telemt_mipsle_ipk_preflight.py --kind lite-rc4 --file telemt-panel-lite_1.0.0.rc.4-1_mipsel-3.4.ipk
python3 -I tools/tests/telemt_mipsle_ipk_preflight_tests.py              # unit: 7/7 OK
```

CI: `.github/workflows/telemt-mipsle-ipk-3517-rc4-experimental.yml`:
`boundary-guard` (изолированность: только research-файлы меняются, ARM64-пайплайны не тронуты)
→ `core-ipk` (Entware ABI сборка + IPK + preflight + artifact 7 дней)
→ `panel-ipk` (рецепт PR #40 + IPK + preflight + artifact 7 дней)
→ `mipsle-only-gate` (имена файлов и control только `mipsel-3.4`, ARM64-подмены невозможны).

## Пины (sha256 входных артефактов)

```
0fcec2bb0fb545ee427985950557fa5c5a6e811f4885d6821ad6af006abd2486  libc6-dev-mipsel-cross_2.24-10cross1_all.deb (archive.debian.org)
45c7ef0bda2acb4475a75efee9734e83f69f54e128971b7a196d88c8b048a222  libc_2.27-12_mipsel-3.4.ipk (bin.entware.net)
bbecc26b579470d52053b72e41dddb70415963eac9f74baf1747b9d2ecdcaaa3  libgcc_8.4.0-12_mipsel-3.4.ipk
8f50a9f331ad7b2bf6125c8826f71b643db62a113f09a93a3827ef3520bb3d34  libpthread_2.27-12_mipsel-3.4.ipk
49880f71e56b1f14738b3ff1412d41a632a3c679e802d06fafdabd227566ce85  librt_2.27-12_mipsel-3.4.ipk
```

Выходные артефакты (локальная проверенная сборка 2026-11-14; CI-прогон дублирует в run-логе):

```
6b2dbd03ee9328ad55968fe2683e1f5a3edec3349a40ba85ade63e3c85cf8908  telemt (ELF, 26 835 456 байт, interpreter /opt/lib/ld.so.1)
b8e16a6a48fc282ad479630f1275642ae188b7d4244d20c11e108fb92773e5e6  telemt_3.5.17-1_mipsel-3.4.ipk (9 270 997 байт, preflight PASS)
```
SHA-256 панели — из CI-прогона (reproducible-сборка Go: `-trimpath`, фиксированный version).

## Границы

- Отдельная research-ветка; Draft PR в `gh-action-build`; **не merge**; ARM64-пайплайны/релизы не тронуты (проверяется `boundary-guard`).
- Пакеты без конфигов, ключей, init-скриптов и автозапуска; удаление штатное (`opkg remove`).
- Real opkg install, QEMU, физический KN-1913 — NOT_TESTED до готовности эмулятора/owner-GO.
