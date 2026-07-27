# 📚 UK Management — документация

> _Последнее редактирование: 2026-07-26_

Индекс. Актуальность каждого документа — в **[DOCUMENTATION_STATUS.md](DOCUMENTATION_STATUS.md)**
(матрица 🟢/🟡/🔴/⚫).

**AUD5-PRAC-7 (2026-07-26):** документы, которые сам статус-отчёт помечал 🔴
(«вводит в заблуждение») и ⚫ («исторический архив»), физически убраны из корня
`docs/` в **[Archive/2026-07-26-stale-docs/](Archive/2026-07-26-stale-docs/README.md)** —
там же таблица «что именно устарело и куда смотреть вместо этого». Пометки в
матрице оказалось недостаточно: файл открывают по имени, а не через индекс.
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
- [MATERIALS_MODULE.md](MATERIALS_MODULE.md) — модуль «Склад материалов» (FIFO)
- [access-control/TECHNICAL_SPEC.md](access-control/TECHNICAL_SPEC.md) — контроль доступа (ANPR/пропуска)

**Инструкции по ролям** (`guides/`)
- [guides/USER_GUIDE_APPLICANT.md](guides/USER_GUIDE_APPLICANT.md) — житель
- [guides/USER_GUIDE_EXECUTOR.md](guides/USER_GUIDE_EXECUTOR.md) — исполнитель
- [guides/USER_GUIDE_MANAGER.md](guides/USER_GUIDE_MANAGER.md) — менеджер
- [guides/USER_GUIDE_INSPECTOR.md](guides/USER_GUIDE_INSPECTOR.md) — обходчик
- [guides/ADMIN_GUIDE.md](guides/ADMIN_GUIDE.md) — system_admin
- [USER_GUIDE_REQUEST_ASSIGNMENT.md](USER_GUIDE_REQUEST_ASSIGNMENT.md) — назначение заявок (для пользователя)

**Эксплуатация и разработка**
- [../README.md](../README.md) — быстрый старт, миграции (`migrate`), тесты (`make test-ci`)
- [ops/RUNBOOK.md](ops/RUNBOOK.md) — деплой, откат, порты, свежие грабли
- [DOCKER_SETUP.md](DOCKER_SETUP.md) — docker-окружение (🟡: список сервисов неполон)
- [LOCALIZATION_GUIDE.md](LOCALIZATION_GUIDE.md) — локализация (бот + фронт i18next)
- [MANUAL_TESTING_GUIDE.md](MANUAL_TESTING_GUIDE.md) — ручное тестирование
- [development/branch-policy.md](development/branch-policy.md) — жизненный цикл веток
- [development/known-constraints.md](development/known-constraints.md) — эксплуатационные ограничения

**Задачи и аудит**
- [audit/2026-05-20-backlog.md](audit/2026-05-20-backlog.md) — рабочий бэклог (источник истины по задачам)
- [audit/2026-05-20-backlog-manifest.md](audit/2026-05-20-backlog-manifest.md) — манифест: агрегаты и распределение по пакетам (генерируется)
- [audit/2026-06-12-closure-plan.md](audit/2026-06-12-closure-plan.md) — план закрытия по волнам

**Домены (справочно)**
- [shifts.md](shifts.md) — смены
- [photo.md](photo.md) — работа с фотографиями
- [FAQ.md](FAQ.md) — частые вопросы
- [ARCHITECTURE_DIAGRAMS.md](ARCHITECTURE_DIAGRAMS.md) — диаграммы

---

## Архив

- **[Archive/2026-07-26-stale-docs/](Archive/2026-07-26-stale-docs/README.md)** — 🔴/⚫ из корня `docs/`,
  перенесены 2026-07-26 (AUD5-PRAC-7). Есть таблица замен.
- **Archive/Migration/**, **Archive/Phase_Reports/**, **Archive/Database/**,
  **Archive/Issues/**, **Archive/Old_Docs/** — более ранние волны архивации.

Правило: если документ противоречит коду — он либо правится, либо уезжает в
архив. Оставлять его в корне с пометкой «устарело» нельзя: пометку не читают.
