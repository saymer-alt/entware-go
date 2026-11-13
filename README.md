# entware-go

Неофициальный форк [Entware Go](https://github.com/spatiumstas/entware-go) с дополнительными пакетами для **Keenetic** и других устройств с Entware. Здесь находятся рецепты сборки и отдельные автоматизированные сборки IPK.

**Готовые пакеты:** [GitHub Release `latest`](https://github.com/saymer-alt/entware-go/releases/tag/latest). Каждый процесс сборки публикует и обновляет только файлы своего пакета, не затрагивая остальные.

## Основные пакеты

| Пакет | Для чего нужен | Документация |
| --- | --- | --- |
| **Mihomo** | Прокси-ядро; автоматические сборки для нескольких архитектур | [Каталог пакета](mihomo/) |
| **Beszel Agent** | Агент мониторинга; пакет собирается вручную | [Каталог пакета](beszel-agent/) |
| **WARPSCOUT** | Диагностика WARP, WireGuard, AmneziaWG и MASQUE на ARM64 | [Установка и команды](warpscout/README.md) |
| **TeleMT** | Telegram MTProxy для ARM64 | [Установка и обновление](docs/telemt-updates.ru.md) |
| **TeleMT Panel Lite** | Панель управления TeleMT для ARM64 | [Установка и обновление](docs/telemt-updates.ru.md) |

Это список отдельно сопровождаемых пакетов форка, а не полный перечень рецептов Entware.

## WARPSCOUT (ARM64 Keenetic)

WARPSCOUT публикуется как IPK для Entware `aarch64-3.10`. Это **консольная утилита**, а не фоновая служба: она не запускается автоматически. Поддерживаются устройства класса KN-1012, KN-1812, KN-3811 и KN-3812 с подходящей ARM64-версией Entware.

**[Техническая документация: установка, обновление IPK, AWG/WG/MASQUE и проверка сборки](warpscout/README.md).**

**[Практическое руководство на русском: поиск зарубежного Cloudflare NODE через AWG на Keenetic, оценка результатов и экспорт конфигурации](https://github.com/saymer-alt/link-generators/blob/main/docs/WARPSCOUT-KEENETIC.md).**

Новые версии проверяются каждые шесть часов. Установщик может выбрать пакет из Entware feed, даже если в GitHub уже есть более новая версия; для проверки обновлений предусмотрен отдельный `warpscout/update.sh` (см. [известное ограничение #21](https://github.com/saymer-alt/entware-go/issues/21)). Файл `/opt/etc/warpscout/warpscout-account.json` содержит приватные данные аккаунта — не публикуйте его.

## TeleMT и TeleMT Panel Lite (ARM64)

Неофициальные IPK для **TeleMT** и **TeleMT Panel Lite** автоматически собираются и публикуются в [`latest`](https://github.com/saymer-alt/entware-go/releases/tag/latest). Проверка новых версий выполняется каждые шесть часов.

**[Инструкция на русском: проверка версий, скачивание и проверка IPK, обновление и особенности интеграции с панелью](docs/telemt-updates.ru.md).**

## Важно об обновлениях

**Публикация IPK в GitHub Release не означает обновление на устройстве.** Пакет появится в `opkg update` / `opkg upgrade` только после обновления соответствующего индексируемого Entware feed. Скачанные из GitHub IPK перед ручной установкой необходимо проверить; порядок проверки приведён в инструкциях к пакетам.

## Для сопровождающих

[Правила внесения изменений](CONTRIBUTING.md) · [Стандарт выпусков](RELEASE-STANDARD.md) · [Политика безопасности](SECURITY.md)
