# Unofficial TeleMT IPC for Entware MIPSel — 3.5.17 beta.1

> **Предрелиз для тестирования на реальных роутерах. Не официальный релиз разработчиков Telemt или Telemt Panel.** Тег `telemt-mipsel-v3.5.17-beta.1` существует отдельно от `latest`; установленное ПО и Entware-feed автоматически не обновляются.

## Что включено

- **Core**: модифицированный Telemt 3.5.17 (`telemt-ipc-lab_3.5.17-1ipc2_mipsel-3.4.ipk`). Отличие от upstream — поддержка безопасного локального `start/reload/stop` через AF_UNIX управляющий сокет для старого ядра Linux 4.9/MIPSel, плюс MIPSel/atomic64 softfloat-совместимость.
- **Panel**: Telemt Panel Lite **1.0.0-rc.4** (`telemt-panel-lite_1.0.0.rc.4-1_mipsel-3.4.ipk`), совместимая с Core API. Это облегчённая версия с `store = "memory"`, а не полный DB-backed дистрибутив.
- **Установка**: `telemt-mipsel-install.sh`, `telemt-mipsel-service.sh`; создают отдельные конфиги, случайные пользовательские секреты, файл с закрытой ссылкой, лог и пароль Panel, Start/Stop/Restart/Status и отдельный автозапуск через Entware `S98/S99`. Обычный `/opt/bin/telemt` не заменяется.
- **Установка не требует ручного редактирования TOML.** Сетевые параметры передаются через одну команду; внешний NAT/порт-форвардинг остаётся задачей администратора.

## Поддерживаемая платформа

`mipsel-3.4` Entware на MT7621/совместимых устройствах (Keenetic KN-1010, KN-1913 — **целевая аппаратная платформа**, поддержка на конкретной прошивке требует проверки). Другие архитектуры не поддерживаются данным архивом.

## Доказательства и ограничения

**Подтверждено на 18.11.2026**:

- 66/66 совместных QEMU MT7621 тестов Core IPC + Panel Lite.
- На физическом KN-1010: IPC Core start/reload/stop, работа Core через SOCKS5 до Telegram DC, Panel RC4 в браузере, индивидуальная управляемая лабораторная установка, пароль/секрет пользователя, Start/Restart из CLI и созданные S98/S99.

**Не заявлено как проверенное**:

- Универсальный `telemt-mipsel-install.sh` на KN-1913, загрузка через S98/S99 после **двух реальных перезагрузок**.
- Реальный внешний Telegram-клиент и WAN-вход на KN-1913.
- Обновление между версиями, восстановление после прерванной установки, работа долгое время под нагрузкой и подтверждённый rollback для универсального установщика.
- Исправление всех аппаратных особенностей KeeneticOS 5.2 Beta 3 или других прошивок.
- Веб-панель хранит историю в RAM; некоторые данные могут теряться при перезапуске. Обновлятор upstream нельзя использовать на экспериментальном IPC-бинарнике до появления отдельного проверенного канала.

Из-за этого **beta.1 рекомендуется только для контролируемого теста с доступом к SSH и возможностью отката**. Настройки удалённого роутера/сеть до установки сохраняйте.

## Установка

Скачайте ZIP релиза, проверьте SHA256, распакуйте файлы в одну папку `/opt/tmp/telemt-mipsel-beta.1/` на *целевом роутере* (не обязательно на KN-1010). Нужны существующая исправная Entware `mipsel-3.4`, постоянный /opt, доступный от роутера SOCKS5 и незанятые 13443/18082/19091. Два IPK ставятся **из локальных файлов**, а не через поиск пакетов в интернете.

```sh
cd /opt/tmp/telemt-mipsel-beta.1 || exit 1
sha256sum -c SHA256SUMS || exit 1
sh -n telemt-mipsel-install.sh && sh -n telemt-mipsel-service.sh || exit 1
sh telemt-mipsel-install.sh \
  ./telemt-ipc-lab_3.5.17-1ipc2_mipsel-3.4.ipk \
  ./telemt-panel-lite_1.0.0.rc.4-1_mipsel-3.4.ipk \
  YOUR_ROUTER_ACCESSIBLE_SOCKS5_IP:PORT \
  YOUR_REACHABLE_TELEGRAM_HOST_OR_IP \
  127.0.0.1
```

Параметры: `CORE_IPK PANEL_IPK SOCKS5_IP:PORT TELEGRAM_PUBLIC_OR_LAN_HOST PANEL_BIND_IP`. Последний параметр можно заменить на **реальный частный IP роутера**, чтобы пользоваться панелью из доверенной LAN/SSTP вместо loopback. По умолчанию выбрана локальная привязка, **не** `0.0.0.0`.

Installer создаёт случайный секрет пользователя `home` для `dd` (Secure MTProxy) и случайный пароль Panel `admin`, но **не показывает их в терминале**. Только локальные файлы с доступом root:

- `/opt/etc/telemt-mipsel/private-telegram-link.txt`
- `/opt/etc/telemt-mipsel/private-panel-password.txt`

Не отправляйте секреты в чаты/логи. Не публикуйте Panel HTTP/18082 или Core API/19091 в Интернет.

После проверки Telegram-клиента:

```sh
/opt/etc/telemt-mipsel/service.sh status
/opt/etc/telemt-mipsel/service.sh enable-boot
```

Это создаёт только `S98telemt-mipsel` и `S99telemt-mipsel-panel`; `rc.unslung` должен быть корректно подключён в KeeneticOS. Для выключения автозапуска: `service.sh disable-boot`.

Для удаления экспериментальных пакетов с сохранением пользовательской конфигурации и секретов:

```sh
/opt/etc/telemt-mipsel/service.sh uninstall
```

Проверьте актуальные пути/коды вручную до первого запуска команды. В случае нарушения идентичности процесса сервис откажется останавливать PID.

## Исходники и лицензии

**Unofficial / modified Telemt**: оригинал `telemt/telemt` 3.5.17, upstream SHA `66708d2866f3f3a4541c4fa67984d408e71a8af4`; применены `telemt-3.5.17-mipsle-atomic64-compat.patch` и `telemt-3.5.17-daemon-control.patch` (исходный модуль `local_control.rs`). Исходники и инструкции воспроизведения находятся в документах research этого репозитория. Оригинальная лицензия **Telemt License 3.3**, текст в `LICENSE.TELEMT.txt` — нужно сохранять при распространении модифицированной версии. Имя Telemt используется исключительно для указания совместимости/происхождения, не для выдачи за официальный релиз.

**Unofficial binary port of Telemt Panel Lite**: `amirotin/telemt_panel` тег `v1.0.0-rc.4`. MIT License в `LICENSE.PANEL.txt`, copyright contributors preserved.

Оригинальные проекты не поддерживают этот экспериментальный пакет официально. Исследовательские PR: #58 (Core), #59/#62 (совместимость), #60 (сервисный комплект); выпускная матрица Issue #61.

## SHA256 исходных экспериментальных пакетов

```text
fbf5ef4c2cad4a564483c29a584986623181574b798ec5b787cdc93c27e15daa  telemt-ipc-lab_3.5.17-1ipc2_mipsel-3.4.ipk
0236dfb076b14b129a6392de49f287838a11aebe7681e092084d4ce87e771e68  telemt-panel-lite_1.0.0.rc.4-1_mipsel-3.4.ipk
```

**Каналы**: этот prerelease не подменяет `latest`, не публикуется в обычный Entware-feed и не включает автоматическое обновление на experimental IPC.
