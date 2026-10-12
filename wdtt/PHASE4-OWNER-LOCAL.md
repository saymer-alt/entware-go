# Phase 4: owner-local test IPK

Текущий путь — отдельный `owner_local_ipk.py`; обычные `owner_test_ipk.py`/normal emission сохраняют публичный gate. Никаких ложных APPROVED: provenance содержит owner_local/owner_install_candidate=true, install_ready/public_distribution_approved=false, исходный license_gate сохранён. Отложенный backlog: [KAS#126](https://github.com/saymer-alt/keenetic-auto-setup/issues/126). Это owner-local технический канал; публичная выдача бинарников не включается.

Пакеты `wt-client-owner-test` для aarch64-3.10 и mipsel-3.4 (softfloat) проверяют pinned source/patch/overlay/SDK/Go.sum, ELF/no PT_INTERP, SHA и notices. Внутри `/opt/lib/wdtt-owner-test/VERSION` находятся binary, provenance, notices и exact-commit KAS lifecycle scripts. Нет postinst/start/prerm; read-only preinst отвергает symlink, writable/foreign parents и конфликтующие payload bytes. Архив включает только собственные directory metadata; режимы общих /opt и /opt/lib не меняются. Активация отдельной командой KAS --install-owner-test после физического preflight и разрешения владельца.

## Локальная повторная сборка/сохранение

Использовать прежний pinned SDK build; не менять Go/SDK. `--kas` должен указывать на обычный Git checkout точного Phase4 KAS commit, а не Windows worktree при запуске Linux git. Приватное сохранение использует существующий механизм verify_quarantine, расширенный отдельным kind owner-test. Нужна реальная POSIX filesystem (WSL ext4, не /mnt/c): каталог0700, IPK/reports0600, raw ELF0700. Путь новый, абсолютный, вне Git checkout/outputs/artifacts, basename wdtt-private-*. Существующие версии не перезаписываются.

```sh
python3 wdtt/owner_local_ipk.py --report /absolute/build/build-report.json \
  --binary-dir /absolute/build --kas /absolute/pinned-kas \
  --retain-private-dir /var/lib/wdtt-owner-local/wdtt-private-UNIQUE-owner-test
python3 wdtt/verify_quarantine.py --build /absolute/build \
  --report /absolute/work/quarantine-report.json \
  --retain-private-dir /var/lib/wdtt-owner-local/wdtt-private-UNIQUE-quarantine
```

Owner build сохраняет оба IPK, ELF, per-arch provenance, SHA256SUMS, notices, selected-source audit/build report и receipt. Quarantine сохраняется отдельно с неизменным preinst exit78; он не выдаётся за installable. CI создаёт временные private пакеты для тестов внутри runner, но не публикует их. Owner-local копии остаются после завершения проверки.

## Реальная проверка opkg

```sh
python3 wdtt/build_opkg_fixture.py /absolute/work/opkg-fixture
python3 wdtt/test_owner_opkg.py --opkg /absolute/work/opkg-fixture/opkg-build/src/opkg-cl \
  --build /absolute/build --kas /absolute/pinned-kas \
  --report /absolute/work/owner-opkg-report.json
```

Это настоящий pinned Entware-patched opkg с offline root, без --force-*. Проверяется наличие/SHA payload: один exit0 не принят как успех. Регрессия сохраняет найденный дефект предыдущего рецепта без directory entries. [Fixture provenance](opkg-fixture/README.md), [команды KN-1010/ARM и Manual/Automatic](https://github.com/saymer-alt/keenetic-auto-setup/blob/feature/wdtt-experimental-poc-20261011/experimental/wdtt/PHASE4-HARDWARE.md).

Production workflow/package directories и shared latest контролируются отдельной read-only regression. Все uploads — только JSON/TXT; source inventory не является новой лицензионной приёмкой. Реальный KN-1010, KN-4210, working RSS, Entware init/reboot и VK/WAN/Mihomo hardware test остаются задачами владельца после preflight.
