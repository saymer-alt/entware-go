# KN-1010 / MT7621: первый физический тест TeleMT IPC (исследовательский пакет)

**Состояние на 17.11.2026:** лабораторный QEMU-сценарий Ported KeeneticOS/Linux 4.9 пройден **63/63** (run [44154378735](https://github.com/saymer-alt/entware-go/actions/runs/44154378735)); испытание на физическом KN-1010 **NOT_TESTED**.

## 0. Границы испытания

Только тестовый KN-1010 с рабочей Entware `mipsel-3.4`. **Не обновлять штатный `telemt`, Panel Lite или init-скрипты; не трогать production-конфиги и сетевые правила.** Лабораторный пакет ставит только `/opt/bin/telemt-ipc-lab`, без конфигурации, autostart и сервисов. Все новые сетевые слушатели в этом тесте привязаны к `127.0.0.1`; реальных пользователей Telegram и upstream нет. Не начинать эксперимент, если на устройстве мало свободного места, подозрения на повреждение Entware или заняты указанные локальные порты.

## 1. Где взять проверенный IPK

Workflow [44139876820](https://github.com/saymer-alt/entware-go/actions/runs/44139876820) → **Artifacts → `telemt-ipc-lab-mipsel-3.4`** → ZIP → файл `telemt-ipc-lab_3.5.17-1ipc2_mipsel-3.4.ipk`.

Независимая байт-воспроизводимая пересборка: [44143555539](https://github.com/saymer-alt/entware-go/actions/runs/44143555539). Артефакты хранятся 7 дней, до 24.11.2026. Это GitHub Actions artifacts, **не** Release, feed или production IPK.

```text
IPK SHA256 fbf5ef4c2cad4a564483c29a584986623181574b798ec5b787cdc93c27e15daa
ELF SHA256 a83caf105dd77248de43c9e096f8248ce3851b322dfe6dd59a934801344d9506
```

## 2. Read-only preflight на KN-1010

Через SSH, до передачи/установки пакета:

```sh
uname -a
/opt/bin/opkg print-architecture
/opt/bin/opkg list-installed | grep -E '^telemt|^libc '
df -h /opt
ls -ld / /opt /opt/var /opt/var/run
cat /proc/mounts | grep ' / '
```

Ожидается архитектура `mipsel-3.4`, работающая Entware, доступная /opt и совместимый ABI. На физическом Keenetic состояние корневой ФС и каталогов может отличаться от QEMU — **не исправлять права / через chmod/chown** ради обхода защиты. Не выполнять команды установки, если архитектура не совпадает.

Для лабораторного конфига зарезервированы loopback TCP-порты `13443` и `19091`; перед запуском убедиться, что они не заняты (например, `netstat -lnt` или `ss -lnt`, если доступны). При конфликте изменить **оба** порта в примере, оставив bind на `127.0.0.1`.

## 3. Передача и установка пакета

Скачать ZIP в браузере на ПК, распаковать IPK и передать его на тестовый KN-1010 через WinSCP/SFTP/SCP в доступный каталог /opt (например, `/opt/tmp`). Путь и SSH-порт зависят от конфигурации устройства.

```sh
cd /opt/tmp || exit 1
sha256sum telemt-ipc-lab_3.5.17-1ipc2_mipsel-3.4.ipk
# Продолжать только при точном совпадении с SHA256 выше.
/opt/bin/opkg install ./telemt-ipc-lab_3.5.17-1ipc2_mipsel-3.4.ipk
/opt/bin/opkg status telemt-ipc-lab
/opt/bin/telemt-ipc-lab --help
```

Пакет **не заменяет** `/opt/bin/telemt`. При неожиданном postinst/init, несовпадении имени пакета или версии — остановиться.

## 4. Изолированная синтетическая конфигурация

Только на тестовом роутере. Не использовать существующие production-пользовательские ключи и не подменять штатный config TeleMT.

```sh
umask 077
mkdir -p /opt/var/run/telemt-ipc-kn1010 /opt/var/log /opt/etc
chmod 700 /opt/var/run/telemt-ipc-kn1010
printf '%s' '00000000000000000000000000000000' > /opt/etc/telemt-ipc-kn1010.secret
cat > /opt/etc/telemt-ipc-kn1010.toml <<'TOML'
[general]
use_middle_proxy = false
log_level = "normal"
proxy_secret_path = "/opt/etc/telemt-ipc-kn1010.secret"
quota_state_path = "/opt/etc/telemt-ipc-kn1010.limit.json"

[general.modes]
classic = true
secure = true
tls = false

[server]
port = 13443

[[server.listeners]]
ip = "127.0.0.1"

[server.api]
enabled = true
listen = "127.0.0.1:19091"
whitelist = ["127.0.0.1/32"]

[access.users]
lab = "00000000000000000000000000000000"

[censorship]
mask = false
TOML
chmod 600 /opt/etc/telemt-ipc-kn1010.secret /opt/etc/telemt-ipc-kn1010.toml
```

Установить корректные права каталога Entware по фактическому состоянию системы, не меняя их вслепую. Требования TeleMT: нет symlink в пути Unix-сокета; все предки ниже / защищены; приватный каталог сокета принадлежит эффективному UID и имеет режим 0700.

## 5. Native start → reload → stop (без pidfile-kill)

```sh
HOME=/opt TMPDIR=/opt/tmp /opt/bin/telemt-ipc-lab start \
  --log-file /opt/var/log/telemt-ipc-kn1010.log \
  --pid-file /opt/var/run/telemt-ipc-kn1010.pid \
  --control-socket /opt/var/run/telemt-ipc-kn1010/ctl.sock \
  /opt/etc/telemt-ipc-kn1010.toml
sleep 3
test -S /opt/var/run/telemt-ipc-kn1010/ctl.sock && echo SOCKET_OK
test -r /opt/var/run/telemt-ipc-kn1010.pid && echo PIDFILE_OK
/opt/bin/telemt-ipc-lab reload --control-socket /opt/var/run/telemt-ipc-kn1010/ctl.sock
/opt/bin/telemt-ipc-lab stop --control-socket /opt/var/run/telemt-ipc-kn1010/ctl.sock
test ! -e /opt/var/run/telemt-ipc-kn1010/ctl.sock && echo SOCKET_CLEAN
```

`reload` возвращает **приём запроса**, а не подтверждение полной перезагрузки конфигурации. Для надёжной проверки также удостовериться, что PID остаётся прежним, процесс жив, конфигурация применена, а после `stop` нет живого процесса. **Не выполнять `kill` по PID из файла.** При ошибке запуска сохранить локально код возврата и классифицированные симптомы. Не публиковать реальные секреты/полные логи.

## 6. Откат и отчёт

После подтверждённой остановки:

```sh
/opt/bin/opkg remove telemt-ipc-lab
# Убедиться, что штатный telemt, если он был установлен, не изменён.
/opt/bin/opkg status telemt
```

Синтетические файлы конфигурации, журнал и тестовый каталог можно удалить **после** фиксации результатов, только по их точным именам; не удалять `/opt/etc/telemt.toml`, штатные service scripts, общий /opt/var/run или чужие логи.

Для обратной связи достаточно: модель/прошивка/ядро, `opkg print-architecture`, режим и тип корневого FS, IPK SHA256 совпал/нет, `start` PASS/FAIL, socket/PID PASS/FAIL, `reload` PASS/FAIL, `stop` PASS/FAIL, `opkg remove` PASS/FAIL. **Не присылать реальные конфиги и секреты.**

Завершение этого pilot не означает готовность production-сервиса, Panel Lite, Telegram upstream и auto-start. PR #58 остаётся Draft, Issue #51 закрывать только после подтверждения на физическом устройстве.
