# Статус документации проекта UK Management

> Аудит от **2026-07-06** (5 параллельных агентов-аналитиков, сверка доков с текущим
> кодом). Источник истины — код, не старые отчёты. Легенда статуса:
> 🟢 актуально · 🟡 частичный дрейф · 🔴 сильно устарело/вводит в заблуждение ·
> ⚫ исторический архив (не обновлять, пометить) · ❌ документация отсутствует.

## Сводка: наличие и актуальность по элементам

### Бот — ядро (заявки / роли / смены / назначение)

| Элемент | Док | Статус | Проблема |
|---|---|---|---|
| Обзор системы назначения | `docs/REQUEST_ASSIGNMENT_SYSTEM.md` | 🔴 | удалённые сервисы/хендлеры, alembic-миграция «не существует», устаревший статусный контур |
| Тех-руководство назначения | `docs/TECHNICAL_GUIDE_REQUEST_ASSIGNMENT.md` | 🔴 | `models/assignment.py`→реально `database/models/request_assignment.py`; классы `Assignment`→`RequestAssignment`; роли без inspector/system_admin |
| Комплексный референс заявок | `docs/requests.md` | 🔴 | `AssignmentOptimizer`/`GeoOptimizer` удалены (ARC-04); жив только SmartDispatcher |
| Пользовательское руководство | `docs/USER_GUIDE_REQUEST_ASSIGNMENT.md` | 🟡 | роли, нет приёмки/возврата |
| Система смен (референс) | `docs/shifts.md` | 🟡 | «в разработке»; не отражена декомпозиция ShiftAssignmentService (ARC-03) |
| README бота | `uk_management_bot/README.md` | 🔴 | роли, sqlite вместо PostgreSQL/alembic, «в разработке» |
| Верификация (dev/admin guides) | `uk_management_bot/VERIFICATION_SYSTEM_*.md` | 🟡 | подсистема жива, сверить экраны вручную |
| Анализ смен / приёмка | `SHIFT_SYSTEM_ANALYSIS.md`, `TASK_16_*`, `TASK_17_*` | ⚫ | исторические отчёты — пометить архивом |
| **Декомпозиция ShiftAssignmentService (5 классов)** | — | ❌ | нет живого тех-описания |

### API (`/api/v2/*`)

| Элемент | Док | Статус | Проблема |
|---|---|---|---|
| **Единый перечень эндпоинтов + RBAC-матрица** | — | ❌ | OpenAPI в prod off, репо-снапшота нет |
| **Materials-API** (12 эндпоинтов) | `docs/MATERIALS_MODULE.md` (создан) | 🟢 | было ❌ — закрыто этим аудитом |
| Web-auth (cookie `uk_access`, MFA/OTP) | — | ❌ | `AUTH_P1/2/3` описывают **бот**, а не 8 HTTP-эндпоинтов `auth/router.py` |
| Edge-allowlist контракт | `docs/audit/2026-06-07-infrasafe-edge-allowlist-contract.md` | 🟡 | нет materials; есть удалённый notifications |
| Stats-API + ARC-06 stats_service | — | ❌ | не зафиксировано |
| `AUTH_P1/P2/P3_COMPLETED.md` | те же | ⚫ | бот-отчёты, пометить архивом |

### Frontend (дашборд)

| Элемент | Док | Статус | Проблема |
|---|---|---|---|
| README фронта | `frontend/README.md` | 🔴 | стоковый Vite-шаблон, 0 строк о проекте |
| Dev-запуск (`npm run dev` :5173 vs :3002) | `README.md` | 🔴 | «hot-reload на :3002» — ложь, там nginx-сборка |
| Набор локалей | `README.md`, `CLAUDE.md` | 🔴 | заявлен `en.json`, которого нет (реально `{ru,uz}`) — **исправлено** |
| i18n-конвенции фронта | — | ❌ | `LOCALIZATION_GUIDE` только про бот |
| «Как добавить раздел/роут» | — | ❌ | реальный процесс = 4-5 файлов |
| MaterialsPage (раздел) | `docs/MATERIALS_MODULE.md` (создан) | 🟢 | было ❌ |
| RBAC-константы ролей | `frontend/src/constants/roles.ts` (inline JSDoc) | 🟢 | отличная inline-дока |
| Архплан / UX-аудит фронта | `docs/modernization/architecture-plan.md`, `docs/ux-audit-report.md` | ⚫ | до-модернизационный AS-IS, всё уже реализовано |

### Данные / Инфра / Деплой

| Элемент | Док | Статус | Проблема |
|---|---|---|---|
| Схема БД | `docs/DATABASE_SCHEMA_ACTUAL.md` | 🔴 | 23 таблицы (2025-10), нет access_control (025–035) и materials (036); документирует удалённую `users.role` |
| Индекс БД | `docs/DATABASE_README.md` | 🔴 | «27 таблиц», «Alembic — Week 3» (уже боевой, head=036) |
| Чек-лист деплоя | `docs/DEPLOYMENT_CHECKLIST.md` | 🔴 | ссылается на несуществующий `docker-compose.production.yml` — **исправлено** |
| Откат | `docs/ROLLBACK.md` | 🟡 | те же команды через несуществующий compose — **исправлено** |
| Troubleshooting | `docs/TROUBLESHOOTING.md` | 🔴 | контейнеры `*-dev`, таблица `assignments` — не существуют |
| Docker Setup | `docs/DOCKER_SETUP.md` | 🟡 | верная прод-команда (:418), но список сервисов неполон, имя сети |
| Quick Start / Development | `docs/QUICK_START.md`, `docs/DEVELOPMENT.md` | 🔴/🟡 | pre-Docker `python main.py`, SQLite-легаси |
| Entrypoints | `scripts/entrypoint-{api,bot}.sh` | 🟢 | api авто-гонит alembic, bot — нет |
| Media-сервис | `media_service/README.md` | 🟡 | порты standalone vs overlay 8009 |
| **Runbook свежих мин** (orphan uk-caddy, .env dup-key, порты, allowlist, stale-chunk) | — | ❌ | знания только в agent-memory |

### Сквозные домены

| Элемент | Док | Статус | Проблема |
|---|---|---|---|
| **Модуль «Склад материалов»** | `docs/MATERIALS_MODULE.md` (создан) | 🟢 | было ❌ — задеплоенный домен без единой доки |
| Access-control ТЗ | `docs/access-control/TECHNICAL_SPEC.md` v1.4 | 🟡 | статус «до реализации», а модуль в проде |
| Access-control модель/деплой/README | `DATA_MODEL_PILOT.md`, `DEPLOYMENT_CHECKLIST.md`, `access_control/README.md` | 🟢 | актуальны (порт 8086/8087 уточнить) |
| **ANPR-камеры DS-TCG205-B (топология Б)** | — | ❌ | решение владельца только в `~/.claude/plans`, в репо нет; TECHNICAL_SPEC §18 держит вопрос открытым |
| Локализация (бот) | `docs/LOCALIZATION_GUIDE.md` | 🟡 | нет фронт-i18next, `status_display.py`, `address_helpers`; битая ссылка `check_localization.py` |
| Безопасность (актуальный SoT) | `AUDIT_REPORT.md` (корень) | 🟢 | аудит #4, трекает SEC-фиксы |
| Security-снимки | `docs/SECURITY_AUDIT_FINAL.md`, `docs/SECURITY_STATUS.md` | 🔴 | 15.10.2025 «0 critical / PRODUCTION READY» — противоречат MFA-bypass (SEC-01) |

## Приоритеты (что делать)

**Сделано этим аудитом:**
1. ✅ Создан `docs/MATERIALS_MODULE.md` (был ключевой пробел — задеплоенный домен без доков).
2. ✅ Создан этот статус-отчёт.
3. ✅ Исправлен дрейф локалей (`{ru,uz,en}`→`{ru,uz}`) в `README.md` и `CLAUDE.md` + hot-reload.
4. ✅ Пометки-баннеры на вводящих в заблуждение доках (security-снимки, архплан фронта, TASK_16/17, SHIFT_SYSTEM_ANALYSIS).
5. ✅ Починены прод-команды в `DEPLOYMENT_CHECKLIST.md` / `ROLLBACK.md` (реальный compose-стек).

**Волна 2 (2026-07-06) — создан канонический комплект (`docs/product`, `docs/tech`, `docs/guides`, `docs/ops`):**
6. ✅ Продуктовое описание `product/OVERVIEW.md` + архитектура `tech/ARCHITECTURE.md`.
7. ✅ `tech/REQUESTS.md`, `tech/SHIFTS_AND_ASSIGNMENT.md` (5 классов движка), `tech/DATA_MODEL.md`, `tech/API_REFERENCE.md`.
8. ✅ Перегенерирован `DATABASE_SCHEMA_ACTUAL.md` (~56 таблиц, +access_control +materials, убран `users.role`).
9. ✅ Ролевые инструкции `guides/{APPLICANT,EXECUTOR,MANAGER,INSPECTOR,ADMIN}.md`.
10. ✅ `ops/RUNBOOK.md`, переписаны `DEVELOPMENT.md` и `frontend/README.md`, расширен `LOCALIZATION_GUIDE.md`.
11. ✅ Баннеры-указатели на устаревших `REQUEST_ASSIGNMENT_SYSTEM.md`/`TECHNICAL_GUIDE_REQUEST_ASSIGNMENT.md`/`shifts.md`; фикс `requests.md` (убраны удалённые оптимизаторы); статус `access-control/TECHNICAL_SPEC.md` → «реализовано».

**Осталось (по согласованию):**
- 🟡 Внести ТЗ ANPR (топология Б, `~/.claude/plans/anpr-hikvision-camera-tz-v2.md`) в `docs/access-control/`.
- 🟡 Обновить сам файл контракта `docs/audit/2026-06-07-infrasafe-edge-allowlist-contract.md` (+materials, −notifications) — сейчас поправка отражена в `tech/API_REFERENCE.md`.
- 🟡 Пометить/удалить `TROUBLESHOOTING.md`, `QUICK_START.md` (заменены `ops/RUNBOOK.md`) — сейчас частично устарели.
- 🟡 Опционально: версионируемый OpenAPI-снапшот `/api/v2/*` (сейчас перечень — в `tech/API_REFERENCE.md`).

**✅ Решено (2026-07-06): `admin` vs `system_admin` — разные роли.** `admin` — общий
управленческий администратор (≈ manager, ~116 authz-сайтов), НО не в каноническом реестре
`USER_ROLES` (код-долг). `system_admin` — админ модуля контроля доступа. Access-control RBAC
(`registry.py`) использует manager/system_admin/security_operator, `admin` не участвует.
Зафиксировано в новом **[tech/ROLES_AND_ACCESS.md](tech/ROLES_AND_ACCESS.md)** (модель ролей +
матрица доступа + RBAC access-control). Гайды ADMIN/MANAGER обновлены.

**Открытый код-долг (не документация):** роль `admin` отсутствует в реестре `USER_ROLES`
(бот `constants.py`/`settings.py`/`enums.py` + фронт `roles.ts`) и не покрыта parity-тестом,
хотя используется в ~116 authz-проверках. Асимметрия: `system_admin` не проходит на основной
`/dashboard/*`, `admin` — не в access-control. Консолидация роли — решение владельца.
