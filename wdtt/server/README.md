# Одноразовый WDTT relay: Phase 3

Кандидат строится тем же SDK из upstream SHA `1110a75f76e42c23149b8e24f9182c1ff179e515`, с patch020 AUTH, patch030 и отдельными `server_entry.go`/`server_policy.go`. Root production module graph не проверялся: закреплён client module graph. Это relay к **заранее подготовленному WG endpoint**, а не установщик полноценного интернет-шлюза. Шаблоны намеренно не проходят admission до локального заполнения.

Новый main не вызывает upstream main: нет Telegram, TCP HTTP API, shell exec, создания/удаления TUN, ip_forward, NAT/firewall или записи БД. WG endpoint допускается только literal IPv4 loopback; listener — literal IPv4. Максимум16 принятых DTLS sessions и30 минут. Профиль IPv4; IPv6 не объявлен готовым.

AUTH и GETCONF требуют существующий device и точную привязку. Relay entry запрещает master password и бессрочные credentials; срок не далее30 минут. При `now >= expires_at` отказ. Legacy DeviceID не расширяет непустой DeviceIDs. GETCONF не создаёт devices/peers и не сохраняет БД. Отзыв проверяется перед пересылкой в обе стороны; watcher100ms закрывает idle sessions, private DB reload250ms читает атомарную замену. Отсутствующая/невалидная БД останавливает relay. Это bounded отзыв, не обещание нулевой задержки распространения.

Секреты читаются из owner-only0600 regular files, nlink1, O_NOFOLLOW, в0700 каталоге того же UID. Unknown JSON fields отвергаются. Клиентская public/private пара проверяется X25519. STDIN/stdout/stderr/core dumps отключены; нормальных логов нет. Ошибки дают фиксированный exit78, штатный SIGTERM закрывает собственные sockets. Same-UID/root compromise и upstream DDoS/WRAP production audit не закрыты.

## Локальное подтверждение

CI запускает **отдельный relay executable** против userspace WG netstack, actual client, Pion TURN и Mihomo. Проверяет GETCONF, handshake, TCP, tunnel DNS, UDP64–1400 и остановку передачи после атомарного отзыва credentials. Матрица DTLS negative cases включает неверный пароль, неизвестный device, чужую/stale binding, expired/boundary-expired/unlimited/revoked credentials. Private DB tests проверяют mode, symlink/hardlink, master password и Telegram отказ.

Это не VK, не VPS и не доказательство internet egress на VM.

## Будущий запуск владельцем

Только одноразовая изолированная VM, без рабочих Xray/3X-UI/AWG и без доступа к корпоративной LAN. Владелец отдельно разрешает запуск. До этого — локальные сборки/fixture only; бинарники не распространяются до license gates. Не запускать upstream installer.

1. Получить проверенный собственный relay и его SHA256 из build-report. На VM создать непривилегированного пользователя. Конфиги хранить в его0700 каталоге на tmpfs; файлы0600. Не вводить секреты в argv/export/history.
2. Заранее подготовить выделенный WG backend **в этой одноразовой VM/namespace**. Его конфигурация должна соответствовать server public key, client public key и единственному allowed IP10.66.66.2/32. UDP56001 должен слушать loopback. Профиль relay сам этого не делает. Интернет-egress/DNS backend требует отдельной разрешённой настройки и capture; не использовать существующий gateway.
3. Заполнить [server template](server.template.json) и [DB template](database.template.json) локальным редактором. Создать один сильный пароль, device `keenetic-test`, пару client WG keys, expiry Unix timestamp в ближайшие30 минут. Нулевой expiry запрещён. DNS должен действительно обслуживаться выбранным WG backend;10.66.66.1 из примера — лабораторный DNS, не автоматически существующий resolver.
4. Сначала loopback listener и synthetic TURN. Для настоящего VK отдельно разрешить listen на тестовом IPv4:56000/UDP и ingress relay path. TCP56000 не нужен и не открывается. Не добавлять правила к чужому firewall. Не открывать UDP56001 наружу.

После допуска пример формы команды (значения только из проверенного собственного build-report, не готовая команда для production):

```sh
sh ./run-relay.sh --plan
sh ./run-relay.sh --confirm-disposable-vm /absolute/wdtt-relay-linux-amd64 VERIFIED_SHA256 /absolute/private/server.json
```

Процесс foreground, без autostart. Stop — Ctrl-C либо SIGTERM точно этого PID. Teardown закрывает только его sockets; не удаляет интерфейсы, firewall, namespace или operator configs. WG backend/одноразовая VM уничтожаются владельцем по их отдельному manifest, а не именем чужого интерфейса. Проверить UDP port baseline после stop. Повторно проверить expiry и выпустить новые credentials перед каждым тестом.

## Настоящий VK TURN — отдельный NOT RUN сценарий

Владелец использует собственный разрешённый VK account/call и локально получает актуальные TURN username/password/URLs. Не отправлять cookies/token/password в чат, Git, CI или обычные логи. Формат client creds соответствует `hashes -> CALL_HASH -> {u,p,urls}`; JSON0600 в0700 каталоге. Применять account mode, один worker. Не выдавать synthetic fixture credentials за VK.

По захвату на изолированном WAN подтвердить реальный TURN allocation/relay, согласованный call hash, WRAP/DTLS/GETCONF, WG handshake и конкретный TCP/DNS/UDP результат. Служебные VK/auth/TURN/DNS/VPS назначения должны идти WAN, не обратно в Mihomo. Нужны отдельные capture UP/DOWN, отсутствие DIRECT fallback, credential expiry/revocation и MTU/loss tests. Packet captures и raw configs остаются private; передаются только sanitized counters. Успех local TURN не закрывает этот gate.
