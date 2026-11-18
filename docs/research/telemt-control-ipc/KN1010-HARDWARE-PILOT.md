# KN-1010 / MT7621: первый физический тест TeleMT IPC (исследовательский пакет)

**Статус на 18.11.2026:** отдельно TeleMT IPC прошёл **63/63 PASS** ([run 44154378735](https://github.com/saymer-alt/entware-go/actions/runs/44154378735)); **TeleMT IPC вместе с Panel Lite RC4 прошли 66/66 PASS** в QEMU Ported MT7621/Linux 4.9 ([run 44335275918](https://github.com/saymer-alt/entware-go/actions/runs/44335275918), замороженные IPK). **Физический KN-1010: IPC Core install/start/reload/stop PASS, SOCKS5 upstream and Panel Lite manual browser access PASS (18.11.2026); GUI custom Start/Stop/Restart, managed service persistence and reboot remain NOT_TESTED.**

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

Сохранённый в research-ветке скрипт: [`scripts/kn1010-preflight-readonly.sh`](scripts/kn1010-preflight-readonly.sh). Он только читает сведения об устройстве, не выполняет установку и не меняет настройки. При ручном копировании на роутер запускается как `sh /opt/tmp/kn1010-preflight-readonly.sh`.

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

**Статус:** Panel Lite RC4 + обычный Core — 93/93 PASS ([router-emulator PR #96](https://github.com/saymer-alt/router-emulator/pull/96)); **IPC-Core + Panel Lite RC4, включая управление Core из API панели через `custom`, reboot и opkg rollback — 66/66 PASS** ([joint run #44335275918](https://github.com/saymer-alt/entware-go/actions/runs/44335275918)). Инструкция ниже намеренно начинает с `service_manager = "none"`, чтобы безопасно изолировать аппаратную проверку HTTP и Core API. **Кнопки GUI на физическом роутере этот режим не включает.**

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

**Важно:** раздел 5 заканчивается `stop` Core. Перед разделом 7 повторно запустить IPC-Core той же командой `start` из раздела 5 и убедиться в наличии сокета; иначе панель закономерно покажет `reachable:false`. Использовать синтетический IPC-Core, чей API прослушивает `127.0.0.1:19091`. Создать **отдельный** panel-config (не трогать штатный `/opt/etc/telemt-panel/config.toml`):

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


## 8. Совместный QEMU PASS и границы физического приёмочного теста

**Доказательство:** [run #44335275918](https://github.com/saymer-alt/entware-go/actions/runs/44335275918), `report.json` имеет `outcome: PASS`, **66/66 шагов**. [Draft PR #59](https://github.com/saymer-alt/entware-go/pull/59) содержит полный сценарий; это уже не гипотеза совместимости, а проверенный MT7621 guest. Новые бинарники или новые хэши не нужны.

На эмуляторе успешно прошли:

- SHA-проверка и установка обеих отдельных IPK, no-autostart;
- Panel health, login/negative login, Core 3.5.17 reachable;
- IPC reload (с тем же PID), stop и повторный start при работающей панели;
- `service_manager=custom`, три реальных HTTP POST через API панели (**stop/start/restart**) с Origin и Sec-Fetch-Site, каждый отвечает 202 и подтверждается PID/socket в Linux;
- native reboot, ручной запуск после reboot, OPKG rollback и очистка.

**Физический шаг 1:** выполнить только разделы 0–3, включая `opkg print-architecture`, `df -h /opt`, проверку уже установленных `telemt` / `telemt-panel-lite`, SHA256, и приложить обезличенный результат. Если устройство используется для других задач, остановиться до установки, а не менять чужие процессы.

**Физический шаг 2 (только после preflight):** лабораторные разделы 4–7 на `127.0.0.1`, без WAN, real Telegram upstream, автозапуска, пользовательских логинов. По завершении остановить оба тестовых процесса, проверить `opkg remove`. Убедиться, что основной `/opt/bin/telemt`, если имеется, не затронут.

**Физический шаг 3 (GUI-custom):** не подменять режим `none` на `custom` без специально подготовленных и проверенных четырёх скриптов управления и отдельного supervisor для панели. В эмуляторе такие скрипты созданы внутри одноразового лабораторного окружения (`/opt/lab`), **не** являются готовыми init-скриптами для KN-1010. Проверка настоящих кнопок требует дополнительного физического теста, хотя API совместимость в эмуляторе уже доказана.

На момент предварительной проверки подключённый KN-1010 находился в сети под **KeeneticOS 5.2 Beta 3**, а QEMU использует Ported KeeneticOS 5.1.8. Различия `/opt`/прав доступа, 256 MB памяти, init и сетевого стека следует фиксировать как отдельные аппаратные результаты; QEMU PASS не равен production GO.


## 9. Hardware pilot results (owner-reported, 2026-11-18)

**Scope:** physical Keenetic Giga KN-1010, MT7621 / Linux 4.9-ndm-5, KeeneticOS 5.2 Beta 3, Entware mipsel-3.4. These observations are direct SSH/browser outputs from the owner's test, not an independent connected device execution by CI.

- Frozen IPKs SHA256 verified exactly: IPC \`fbf5ef4c2cad4a564483c29a584986623181574b798ec5b787cdc93c27e15daa\`, Panel RC4 \`0236dfb076b14b129a6392de49f287838a11aebe7681e092084d4ce87e771e68\`. \`opkg install\` succeeded with expected versions and no dependency upgrades. Panel CLI \`version\` printed \`telemt-panel 1.0.0-rc.4 (lite: memory)\`.
- IPC daemon launched with private \`/opt/var/run/telemt-ipc-kn1010/ctl.sock\` (parent 0700, socket 0600), API 127.0.0.1:19091 and MTProxy listener 127.0.0.1:13443; \`/proc/2316/exe\` matched exact lab binary; VmRSS ~18 MiB. Initial probe after 3 s missed socket because direct DC initialization required 37 s. Retest confirmed socket and both listeners.
- Native \`telemt-ipc-lab reload --control-socket ...\`: immediate request accepted, exit 0, Core PID remained 2316 and control socket remained. Full config mutation was not asserted.
- Native \`telemt-ipc-lab stop --control-socket ...\`: stop request accepted; owner observed exit of the verified Core process and unlink of the control socket (\`IPC_STOP_PASS\`). After restarting with new lab SOCKS5 config, PID 4416 matched binary and both listeners+IPC returned.
- Only upstream is SOCKS5 \`10.0.6.78:7890\` (Mihomo), verified with curl exit 0. Owner's TeleMT log: \`via socks5://10.0.6.78:7890\`, all six named Telegram DC endpoints reachable during startup, startup time 6 s; Panel displayed healthy upstream 1/1, RTT 3 ms. Direct carrier connectivity had failed. These checks **do not** prove long-term Telegram client traffic, ME operation or real MTProxy usability.
- Panel launched manually, listened on 192.168.107.1:18082, served real browser login, overview, users, pulse, upstream health and service page. Mode \`host.service_manager=none\`: GUI control **NOT_TESTED**. The same IP address is assigned on br0 and SSTP, therefore HTTP exposure is **not VPN-only**. The operator had exposed the original test password in chat; it must not be reused.
- Foreground Panel stopped when SSH session closed. Attempted ad hoc detached start stopped with \`NOHUP_NOT_AVAILABLE\` **before changing its password/config or launching any process**. This is an environment issue, not evidence of Panel crash.
- Core emitted \`Failed to update runtime log filter: subscriber no longer exists\` after successful initialization. Not yet fixed; track as low-priority runtime warning.

**Next:** review [managed MIPSel service kit PR #60](https://github.com/saymer-alt/entware-go/pull/60) built on this research branch. Its host-only syntax/TOML gate is PASS, but the service kit is a new artifact needing physical lifecycle, GUI custom controls, logout persistence, boot and rollback tests. No public release or stable feed yet.
