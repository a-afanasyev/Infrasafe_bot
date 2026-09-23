# 📚 UK Management — документация

> _Последнее редактирование: 2026-09-23_

Индекс. Актуальность каждого документа — в **[DOCUMENTATION_STATUS.md](DOCUMENTATION_STATUS.md)**
(матрица 🟢/🟡/🔴/⚫).

**AUD5-PRAC-7 (2026-07-26):** документы, которые сам статус-отчёт помечал 🔴
(«вводит в заблуждение») и ⚫ («исторический архив»), физически убраны из корня
`docs/` в **[Archive/2026-07-26-stale-docs/](Archive/2026-07-26-stale-docs/README.md)** —
там же таблица «что именно устарело и куда смотреть вместо этого». Пометки в
матрице оказалось недостаточно: файл открывают по имени, а не через индекс.
**A9-P3-28 (2026-09-23):** вторая волна — исторические отчёты из корня `docs/`
уехали в **[Archive/2026-09-23-root-reports/](Archive/2026-09-23-root-reports/README.md)**,
аудиторские и security-отчёты (включая пентест из корня репо и бывший корневой
`audit/`) — в `audit/`.
Ниже — только то, на что можно опираться.

---

## Канонический комплект

**Продукт**
- [product/OVERVIEW.md](product/OVERVIEW.md) — продуктовое описание (роли, каналы, домены, границы)

**Технические документы** (`tech/`)
- [tech/ARCHITECTURE.md](tech/ARCHITECTURE.md) — архитектура, контейнеры, потоки данных, auth
- [tech/DATA_MODEL.md](tech/DATA_MODEL.md) — модель данных, ERD.
  ⚠️ Источник истины по схеме — `alembic/versions/` (baseline 001 + 002 и далее),
  а не какой-либо md-снимок: снимки протухают молча, миграции — нет
- [tech/API_REFERENCE.md](tech/API_REFERENCE.md) — `/api/v2/*`, RBAC-матрица, web-auth
- [tech/REQUESTS.md](tech/REQUESTS.md) — домен «Заявки» (статусы, назначение, приёмка)
- [tech/SHIFTS_AND_ASSIGNMENT.md](tech/SHIFTS_AND_ASSIGNMENT.md) — смены + движок назначения (5 классов)
- [tech/ROLES_AND_ACCESS.md](tech/ROLES_AND_ACCESS.md) — роли (RBAC), матрица доступа, `admin` vs `system_admin`
- [tech/ARCHITECTURE_DIAGRAMS.md](tech/ARCHITECTURE_DIAGRAMS.md) — диаграммы (контейнеры, модули, ER)
- [tech/PAYMENT_CONTROL.md](tech/PAYMENT_CONTROL.md) — контроль платежей
- [MATERIALS_MODULE.md](MATERIALS_MODULE.md) — модуль «Склад материалов» (FIFO)
- [ELEVATORS_MODULE.md](ELEVATORS_MODULE.md) — модуль «Лифты»
- [ASSETS_MODULE.md](ASSETS_MODULE.md) — ТЗ модуля «Учёт ассетов» (не реализовано)
- [access-control/TECHNICAL_SPEC.md](access-control/TECHNICAL_SPEC.md) — контроль доступа (ANPR/пропуска)

**Инструкции по ролям** (`guides/`)
- [guides/USER_GUIDE_APPLICANT.md](guides/USER_GUIDE_APPLICANT.md) — житель
- [guides/USER_GUIDE_EXECUTOR.md](guides/USER_GUIDE_EXECUTOR.md) — исполнитель
- [guides/USER_GUIDE_MANAGER.md](guides/USER_GUIDE_MANAGER.md) — менеджер
- [guides/USER_GUIDE_INSPECTOR.md](guides/USER_GUIDE_INSPECTOR.md) — обходчик
- [guides/ADMIN_GUIDE.md](guides/ADMIN_GUIDE.md) — system_admin
- [guides/SHIFTS.md](guides/SHIFTS.md) — смены (для персонала)

**Эксплуатация и разработка**
- [../README.md](../README.md) — быстрый старт, миграции (`migrate`), тесты (`make test-ci`)
- [ops/RUNBOOK.md](ops/RUNBOOK.md) — деплой, откат, порты, свежие грабли
- [DOCKER_SETUP.md](DOCKER_SETUP.md) — compose-файлы и docker-окружение
- [LOCALIZATION_GUIDE.md](LOCALIZATION_GUIDE.md) — локализация (бот + фронт i18next)
- [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md), [ROLLBACK.md](ROLLBACK.md) — чек-лист деплоя и откат
- [development/branch-policy.md](development/branch-policy.md) — жизненный цикл веток
- [development/known-constraints.md](development/known-constraints.md) — эксплуатационные ограничения

**Задачи и аудит**
- [audit/2026-05-20-backlog.md](audit/2026-05-20-backlog.md) — рабочий бэклог (источник истины по задачам)
- [audit/2026-05-20-backlog-manifest.md](audit/2026-05-20-backlog-manifest.md) — манифест: агрегаты и распределение по пакетам (генерируется)
- [audit/2026-06-12-closure-plan.md](audit/2026-06-12-closure-plan.md) — план закрытия по волнам
- `audit/` — также аудиторские и security-отчёты (исторические снимки, не норматив)
- `bugs-YYYY-MM-DD.md` — баг-репорты (конвенция из `CLAUDE.md`)

**FAQ и пользовательская справка** — [user-guide/](user-guide/README.md)

---

## Архив

- **[Archive/2026-07-26-stale-docs/](Archive/2026-07-26-stale-docs/README.md)** — 🔴/⚫ из корня `docs/`,
  перенесены 2026-07-26 (AUD5-PRAC-7). Есть таблица замен.
- **[Archive/2026-09-23-root-reports/](Archive/2026-09-23-root-reports/README.md)** — исторические
  отчёты и устаревшие справочники из корня `docs/` (A9-P3-28). Есть таблица замен.
- **Archive/Migration/**, **Archive/Phase_Reports/**, **Archive/Database/**,
  **Archive/Issues/**, **Archive/Old_Docs/** — более ранние волны архивации.

Правило: если документ противоречит коду — он либо правится, либо уезжает в
архив. Оставлять его в корне с пометкой «устарело» нельзя: пометку не читают.
