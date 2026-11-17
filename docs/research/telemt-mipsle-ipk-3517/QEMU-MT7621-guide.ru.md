# QEMU-испытания MIPSLE-пакетов TeleMT на MT7621 (инструкция на будущее)

> Статус: **план, не выполнялся**. По ТЗ QEMU-тесты не проводятся, пока эмулятор не готов.
> Этот документ — подготовленная инструкция, чтобы испытание можно было запустить одной сессией.

## Что проверяем и почему QEMU, а не сразу роутер

| Проверка | Что доказывает |
|---|---|
| Загрузка бинарника (`/opt/lib/ld.so.1`, GLIBC ≤ 2.27) | что статические ABI-гейты не врут: динамическая загрузка реально проходит |
| `ring`/`aws-lc` на MIPS32r2 softfloat | что крипто-C-код корректен без FPU и в little-endian |
| lock-fallback AtomicU64 (portable-atomic) | throughput/джиттер счётчиков под нагрузкой на 2 ядрах 880 МГц |
| Потребление памяти | реальный RSS против лимита 256 МБ устройства |
| opkg install / remove / rollback | воспроизводимость установки и штатного удаления |
| Panel Lite RC4 | запуск, локальный HTTP, расход памяти |

QEMU не может эмулировать сам SoC MT7621 (модели машины нет), поэтому эмуляция —
универсальная MIPS32r2-платформа Malta. Это покрывает ISA/ABI/softfloat/loader,
но НЕ поведение конкретного железа (NAND, Wi-Fi, коммутатор) — это только полевые испытания.

## Подготовка стенда

1. Хост: любой x86_64 Linux/WSL2 с `qemu-system-mipsel`.
2. Ядро: mipsel, ≥3.4, с `CONFIG_MIPS_MALTA` (подходит Debian mipsel buster `vmlinux-…-4kc-malta`
   из `ftp.debian.org/debian/pool/main/l/linux/` — buster glibc 2.28 базовая система;
   само ядро 4.19 нормально грузит glibc 2.27).
3. Диск: raw-образ с rootfs (Debian mipsel buster chroot через `debootstrap --arch=mipsel buster`).
4. Entware поверх rootfs: стандартный инсталлятор `entware_install.sh` (mipsel-3.4) в `/opt`.

## Запуск

```bash
qemu-system-mipsel -M malta -cpu 74Kf -m 256M -nographic \
  -kernel vmlinux-4.19.0-…-4kc-malta \
  -drive file=rootfs.img,format=raw,if=virtio \
  -append "console=ttyS0 root=/dev/vda1 rw"
# -cpu 74Kf: MIPS32r2, LE, o32; для binary softfloat FPU не нужен вовсе
```

## Чек-лист испытаний (все шаги фиксировать выводом)

1. **Загрузка ABI**: `opkg install /opt/telemt_3.5.17-1_mipsel-3.4.ipk` →
   `/opt/bin/telemt --version`; `cat /opt/lib/ld.so.1 >/dev/null` — совпадение версий libc.
2. **CONFIG**: запустить с синтетической конфигурацией (localhost-порты, без реальных
   ключей/доменов — по границам ТЗ), убедиться в старте и отклике health/API.
3. **Память**: `systemd-run`/cgroup с лимитом 256M → снять RSS в покое и под нагрузкой
   (`smem -k` или `/proc/$pid/status` VmRSS). Фиксировать «RSS idle / RSS load».
4. **Счётчики/лимитеры**: прогнать встроенные тесты скорости TeleMT против локального
   loopback-сервера; наблюдать CPU (`top`) и дельту счётчиков — это проверка
   lock-fallback portable-atomic на 2 vCPU.
5. **Ring/crypto**: TLS-соединение через локальный loopback (синтетический сертификат),
   убедиться в handshake и отсутствии SIGILL (младшие FPU-инструкции ловятся SIGILL).
6. **opkg rollback**: `opkg remove telemt` → подтвердить удаление `/opt/bin/telemt`,
   отсутствие остатков в `/opt/etc` (пакет их не создаёт), повторная установка.
7. **Panel**: `opkg install telemt-panel-lite…ipk` → `/opt/bin/telemt-panel`,
   HTTP GET на локальный порт, RSS; `opkg remove`.
8. **Отдельно**:Panel и Core устанавливаются независимо (порядок любой, без cross-deps).

## Критерии PASS

- Все 8 шагов без SIGILL/SIGSEGV, opkg remove чистый, RSS idle+load < 200 МБ (запас к 256 МБ).
- Результаты и SHA-256 использовать для обновления статусов в Issue #37:
  `QEMU_RUNTIME`, `OPKG_INSTALL_ROLLBACK` → PASS; `PHYSICAL_DEVICE` остаётся NOT_TESTED
  до отдельного owner-GO.
