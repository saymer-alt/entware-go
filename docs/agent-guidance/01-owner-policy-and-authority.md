# Owner decisions, release limits and engineering debt

> **Source-preserving move — 2026-11-07.** Read for owner decisions, new subsystem design, legal constraints or owner approval gates. Historic decisions are preserved; no implicit new permission is granted.
>
> All sections below are preserved from the root `AGENTS.md` on `gh-action-build` at `e5739548655fa1c5eb350a8f15306719ee1ee21b`. Only relative Markdown link paths, if any, are rebased to this directory; inline-code repository paths still assume repo root. References to previous SDK versions, package releases, tests or hardware validation are historical until checked against current source/Actions.
>
> Read this guide **only when relevant**. The short [root AGENTS.md](../../AGENTS.md) remains binding. The repo is the `saymer-alt` fork, not upstream. No read permission, approval of a Draft PR or old documented success authorizes a release, IPK publication, SDK migration, upstream push or production router changes.

---

> **Обязательный контракт для всех агентов и авторов ТЗ (30.10.2026):** [подробная постановка задач без «эффекта обезьяньей лапки»](https://github.com/saymer-alt/saymer-alt/blob/main/AGENT-TASK-CONTRACT.md). Перед работой проверить исходные refs/SHA, готовые результаты, точную цель, scope/non-goals, сохранность данных и сервисов, зависимости, границы разрешений/owner GO, негативную приёмку и доказательства. Не сокращать существенные требования ради токенов. Буквальное выполнение в ущерб цели считается **FAIL**. Местные правила безопасности и архитектуры обязательны.

> **Владелец, 26.10.2026 — общее правило для всех проектов:** перед внедрением новой функции / серьёзной переделки требуется короткая «защита идеи» — доказать проблему, сравнить альтернативы (включая ничего не менять / штатную ОС / ждать upstream), оценить пользу, **ТЭО**, стоимость сопровождения, риски, измеримый тест и критерии STOP. Нет доказательства пользы — DEFER/SKIP. Мелкие исправления не требуют отдельной бюрократии. **Источник:** [Proof Before Build](https://github.com/saymer-alt/saymer-alt/blob/main/PROOF-BEFORE-BUILD.md) ([центральный PR #9](https://github.com/saymer-alt/saymer-alt/pull/9)). Существующие safety/CI/permissions сохраняются.

# AGENTS.md — entware-go (saymer-alt fork)

## Owner-wide design gate — SIMPLICITY-FIRST (2026-10-24)

Before a new service, subsystem, manager, web panel, installer/uninstaller, or heavy CI path, apply the [common engineering contract](https://github.com/saymer-alt/saymer-alt/pull/7). First compare: (A) existing/manual route, (B) smallest safe change, (C) ambitious design. Choose A/B unless C has evidence, cost/complexity budget, and explicit owner approval. If a helper grows into another platform or expensive E2E cycles repeat without new evidence, STOP adding layers and seek an architectural decision. Preserve all verified safety boundaries and working user behavior. [KAS uninstall retrospective #225](https://github.com/saymer-alt/keenetic-auto-setup/issues/225) is an **anti-pattern**, not a best-practice pattern. This documentation change does not authorize production or release modifications.

## ⚑ Решение владельца от 2026-10-11: WORKING-FIRST / LICENSE AUDIT DEFERRED

**ПРОЕКТЫ ВЕДУТСЯ В ПЕРВУЮ ОЧЕРЕДЬ ДЛЯ ЛИЧНОГО НЕКОММЕРЧЕСКОГО ИСПОЛЬЗОВАНИЯ. РЕПОЗИТОРИИ ПУБЛИЧНЫЕ.**

**ПРИОРИТЕТ: РАБОТАЮЩИЕ СБОРКИ, IPK, ТЕСТЫ И БЕЗОПАСНОСТЬ. ПЛАНОВЫЙ ЛИЦЕНЗИОННЫЙ АУДИТ ОТЛОЖЕН. НЕ ЛОМАТЬ И НЕ ОСТАНАВЛИВАТЬ СУЩЕСТВУЮЩИЕ РЕЛИЗЫ ИЗ-ЗА НЕЗАВЕРШЁННОЙ ИНВЕНТАРИЗАЦИИ НОВОГО ЭКСПЕРИМЕНТАЛЬНОГО КОМПОНЕНТА.**

Для всех Codex / ZCode / других агентов:
- Не задавать владельцу повторно общий вопрос «что делать с лицензией?» и не превращать каждый статус-отчёт в новый аудит. Устаревшие или неполные notices фиксировать однократно в [отложенной задаче KAS #126](https://github.com/saymer-alt/keenetic-auto-setup/issues/126), не останавливая независимую инженерную работу.
- Продолжать безопасные сборки, тесты, IPK-рецепты, CI, аппаратные проверки, watchdog/rollback и работу действующих релизных конвейеров. Никогда не отключать Mihomo, WARPSCOUT, Beszel Agent, KAS, Builder Studio, `latest` или их CI только ради косметического license-review нового WDTT.
- **При этом предупреждение, публичный GitHub и некоммерческий характер сами по себе НЕ предоставляют разрешение на распространение чужого кода.** Сохранять существующие LICENSE, copyright/NOTICE, происхождение исходников и условия. При доказанном ограничении прав на конкретный компонент не выпускать **этот** компонент вопреки условиям; сообщить владельцу только о конкретном неизбежном решении. Не распространять юридическую неопределённость одного компонента на исправные независимые проекты.
- Экспериментальные WDTT/IPK могут иметь отдельный, явно обозначенный канал и ручной режим без вмешательства в production. Отсутствие завершённой инвентаризации не должно маскировать технические риски: AUTH, секреты, портовые конфликты, restart storms, rollback, архитектура/ABI и аппаратный допуск остаются обязательными проверками.
- Это правило не является разрешением менять `stable`, сливать PR, автоматически публиковать `latest`, менять работающую инфраструктуру или отменять CI. Любые такие действия — только по обычному процессу и owner GO.

**К лицензированию вернуться по отдельному запросу владельца или при конкретном установленном препятствии распространению. Не инициировать бесконечные повторные обсуждения.**


Instructions for coding agents working in this repository.
When something is unclear or dangerous: stop and report to the owner — do not improvise.

## Requires explicit owner approval

- Changing the Entware SDK or Go toolchain in any workflow.
- Creating releases/branches beyond the documented scheme, publishing to the feed
  manually, changing repo settings, wiring up `telegram-push.yml`.
- Any conflict resolution in fork-specific files during upstream sync.


## Technical debt

- Treat technical debt as an explicit engineering risk, but do not confuse it with cosmetics, personal style preferences, or merely "ugly" working code.
- For each debt item, provide evidence first and classify its impact: **High** (breakage/security/data-loss risk or blocks operation), **Medium** (impedes development, duplicates/diverges logic, or materially increases maintenance cost), **Low** (local complexity with little current risk).
- Do not refactor for cleanliness alone. Pay down debt when the benefit and risk reduction justify the change; do not rewrite stable, verified code without a concrete reason.
- Debt fixes must keep minimal scope, preserve existing safety boundaries, and pass the project's normal regression/safety checks. If the fix creates greater risk or new debt, stop and propose a safer alternative.
- If debt is discovered outside the current task, do not silently expand scope: record the finding and recommendation, and implement it only when it is in scope or explicitly approved by the operator.
