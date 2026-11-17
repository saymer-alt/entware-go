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


## 7. Panel Lite RC4: отдельная совместная проверка на localhost

**Статус:** Panel Lite RC4 + **обычный Core** ранее 93/93 PASS в QEMU ([router-emulator PR #96](https://github.com/saymer-alt/router-emulator/pull/96)); **IPC-версия Core + Panel Lite вместе** на момент написания НЕ ПРОВЕРЕНЫ в QEMU. `service_manager = "none"` позволяет проверить веб-интерфейс и API-доступ к Core, но **не** проверяет кнопки управления Core в панели.

Готовый экспериментальный Panel IPK: [workflow 43624729371, artifact `telemt-panel-lite-mipsel-experimental`](https://github.com/saymer-alt/entware-go/actions/runs/43624729371). Срок хранения до 21.11.2026. Имя внутри ZIP: `telemt-panel-lite_1.0.0.rc.4-1_mipsel-3.4.ipk`.

```text
Panel IPK SHA256 0236dfb076b14b129a6392de49f287838a11aebe7681e092084d4ce87e771e68
Panel ELF SHA256 380cb5112b58538eafec9ae9fab27fb22c994fd36ce3130c541c5e11b29a40c8
```

Проверить свободный localhost-порт 18082. **Не устанавливать Panel Lite, если уже работает `/opt/bin/telemt-panel` или установлен действующий `telemt-panel-lite` — сначала определить совместимость/конфликт пакетов.** После передачи IPK на KN-1010 и сверки SHA:

```sh
cd /opt/tmp || exit 1
sha256sum telemt-panel-lite_1.0.0.rc.4-1_mipsel-3.4.ipk
/opt/bin/opkg install ./telemt-panel-lite_1.0.0.rc.4-1_mipsel-3.4.ipk
/opt/bin/telemt-panel version
```

Использовать заранее запущенный синтетический IPC-Core из разделов 4–5, чей API прослушивает `127.0.0.1:19091`. Создать **отдельный** panel-config (не трогать штатный `/opt/etc/telemt-panel/config.toml`):

```sh
umask 077
h=$(printf '%s\n' 'lab-test-change-afterwards' | /opt/bin/telemt-panel hash-password) || exit 1
mkdir -p /opt/var/lib/telemt-panel-ipc-kn1010
cat > /opt/etc/telemt-panel-ipc-kn1010.toml <<TOML
listen = "127.0.0.1:18082"
data_dir = "/opt/var/lib/telemt-panel-ipc-kn1010"

[tls]
mode = "http"

[telemt]
url = "http://127.0.0.1:19091"
auth_header = ""

[auth]
username = "labadmin"
password_hash = "$h"

[store]
driver = "memory"

[host]
service_manager = "none"
TOML
chmod 600 /opt/etc/telemt-panel-ipc-kn1010.toml
```

В отдельной SSH-сессии запустить **в foreground**, чтобы штатное завершение было через Ctrl+C:

```sh
HOME=/opt /opt/bin/telemt-panel -config /opt/etc/telemt-panel-ipc-kn1010.toml
```

Для открытия GUI на ПК использовать SSH port forwarding до `127.0.0.1:18082` роутера, а не открывать его на WAN:

```sh
ssh -L 18082:127.0.0.1:18082 USER@ROUTER
```

Открыть `http://127.0.0.1:18082`, войти `labadmin` с **тестовым** паролем `lab-test-change-afterwards`, проверить авторизацию, `/api/health`, статус Core `reachable:true` и версию `3.5.17`. Затем выполнить IPC `reload` Core, убедиться, что соединение панели сохраняется; выполнить IPC `stop`, убедиться, что панель показывает недоступность Core; запустить Core вручную заново и проверить `reachable:true`. Это **не тест внешнего Telegram upstream** и не тест API управления демоном из панели.

В конце завершить панель через Ctrl+C, подтвердить отсутствие запущенного `telemt-panel`, затем при отсутствии других зависимостей `opkg remove telemt-panel-lite` и IPC-пакет по разделу 6. Не удалять чужие файлы, не менять init scripts и веб-панель рабочего роутера.
