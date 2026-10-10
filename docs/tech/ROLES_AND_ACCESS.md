# Роли и модель доступа (RBAC)

> _Последнее редактирование: 2026-10-10_

> **С 2026-10-10 права решают действия, а не имена ролей** — принцип, рецепты и
> каталог в [RBAC.md](RBAC.md). Этот документ описывает сами роли и то, какие
> права они дают сегодня (матрица «как есть», снимок прав — §5).
>
> Реестр ролей: бот — `uk_management_bot/utils/constants.py` (`USER_ROLES`),
> `config/settings.py`, `utils/enums.py` (`UserRole`), parity-тест
> `tests/test_roles_parity.py`; фронт — `frontend/src/constants/roles.ts`.
> Кто что может — `uk_management_bot/authz/catalog.py`.
> `user.roles` — массив строк (jsonb, DB-049), `user.active_role` — режим меню,
> прав не даёт (legacy-колонка `user.role` УДАЛЕНА миграцией 022).

## 1. Канонические роли (реестр, 6 шт.)

Проверяются на паритет между `Settings.USER_ROLES == constants.USER_ROLES ==
enum UserRole` (`tests/test_roles_parity.py:23-32`) и зеркалятся во фронте
(`constants/roles.ts:USER_ROLES`).

| Роль | Назначение |
|---|---|
| `applicant` | Житель — подаёт заявки (бот/TWA) |
| `executor` | Исполнитель — выполняет заявки, работает в сменах |
| `manager` | Менеджер — контроль заявок, персонал, смены, аналитика (дашборд+бот) |
| `inspector` | Обходчик — заявки обхода (building-level), только бот |
| `system_admin` | Админ **модуля контроля доступа** (ТЗ access_control §3.2): оборудование, полный доступ к access-домену |
| `security_operator` | Оператор охраны — пост охраны в модуле доступа (события/пропуска/фото) |

## 2. Роль `admin` — отдельная, но НЕ в реестре (важно)

`admin` — **отдельная действующая роль** (подтверждено владельцем), задумана как
**общий управленческий администратор ≈ `manager`**, но на деле равна ему только
в боте. Точные цифры — в снимке прав (§5):

- **бот**: `has_admin_access`/`RoleGate`/`require_role(['admin','manager'])` пускают
  `admin` наравне с `manager` (71 декоратор, 12 root-фильтров, ~100 inline-вызовов);
- **API ядра**: из ~100 менеджерских маршрутов `admin` без `manager` проходит
  только **11** — `auto-manager-config`, `payment-control/*`, `resource-accounting/ticket`;
  остальные гейтятся `require_roles("manager")`;
- **фронт**: основной `/dashboard/*` гейтится `['admin','manager']` (`App.tsx`), то есть
  чистый `admin` видит дашборд, но получает 403 почти от всех его API.

⚠️ **Рассинхрон (код-долг, не документация):** `admin` НЕ входит в канонический
`USER_ROLES` (ни бот-реестр, ни `constants/roles.ts`), не покрыта parity-тестом и
`validate_role`. Роль «живёт» только в разбросанных authz-проверках. Следствия:
- Новый код на базе реестра (реестр-driven guard'ы, `roles.ts`) роль `admin` не знает.
- `system_admin` **не входит** в `['admin','manager']` → чистый `system_admin` **не
  проходит** на основной `/dashboard/*` (только на access/materials route-группы).
- Чистый `admin` проходит на основной дашборд, но **не** в модуль контроля доступа (см. §3).

> Решение по консолидации (внести `admin` в реестр, либо заменить на `manager`/
> `system_admin` в authz-сайтах, либо оставить как есть) — за владельцем. Здесь
> зафиксирована фактическая картина; код не менялся.

## 2.0.1 Выдача `manager` через `/admin` (выключено в проде, A9-P2-4)

Команда бота `/admin` + общий `ADMIN_PASSWORD` выдаёт роль `manager` любому аккаунту
(`handlers/base.py:cmd_admin` → `AuthService.make_admin_by_password_sync`). Решение
владельца 2026-09-23: за флагом `ADMIN_COMMAND_ENABLED` (дефолт `false`, в прод-конфигах не
задаётся) — при выключенном флаге команда не матчится и ведёт себя как неизвестная, а
сервис отказывает даже с верным паролем. Менеджеры заводятся инвайтами и из дашборда;
`/admin` — только для первого менеджера на новой площадке и локалки (процедура —
`.claude/skills/uk-deploy/SKILL.md`, «Первый менеджер на площадке»). При включённом
флаге сообщение с паролем удаляется, выдача пишется в `audit_logs`
(`action=admin_command_role_grant`), действующие менеджеры получают уведомление.

## 2.1 Капабилити и псевдо-роли (вне реестра, но действующие)

- **`resource_meter_entry`** — капабилити контролёра показаний (лежит в
  `users.roles` рядом с ролями): открывает ввод показаний счётчиков из
  Mini App («Учёт ресурсов»). Выдаётся/снимается менеджером в карточке
  сотрудника (`PATCH /employees/{id}/meter-entry`).
- **`staff_group`** — псевдо-роль адресного резолвера для staff-репортов
  Group Intake (в `users.roles` НЕ хранится): задаёт разрешённые уровни
  адреса (`yard`, `building`) без требования принадлежности. См.
  [REQUESTS.md §2, §5](REQUESTS.md).

## 3. RBAC модуля «Контроль доступа»

API охраны гейтится действиями `access.*` каталога ([RBAC.md §9](RBAC.md#9-каталог-действий));
все требуют одобренный аккаунт, **`admin` в них НЕ участвует** (роли раздельны):

| Действие | Роли | Что покрывает |
|---|---|---|
| `access.events.read`, `access.operator`, `access.live`, `access.presence.read`, `access.photos.read` | `security_operator`, `manager`, `system_admin` | Пост охраны: события, пропуска, пульт, живой поток, фото |
| `access.registry.manage`, `access.management`, `access.zones.manage`, `access.metrics.read` | `manager`, `system_admin` | База авто/заявок, история, управление, зоны, метрики |
| `access.equipment.manage`, `access.diagnostics` | `system_admin` | Оборудование (камеры/шлагбаумы/контроллеры), диагностика |
| `access.resident.self` | `applicant` | Свои авто и пропуска жителя |

Интерфейс использует те же действия: маршрут `/dashboard/access` —
`access.events.read`, экраны менеджера — `access.registry.manage`, табы
оборудования — `access.equipment.manage` (`AccessEquipmentPage`, `useCan`).

Иерархия внутри модуля: `security_operator` (пост охраны) ⊂ `manager` (база+история)
⊂ `system_admin` (+оборудование).

## 4. Матрица доступа к разделам дашборда (`App.tsx`, `DashboardLayout.tsx`)

Гейты — действия из профиля (`ProtectedRoute action=...`, поле `action` пункта
меню). Спецификация — `frontend/src/authz/uiActions.test.ts`.

| Раздел | Действие | admin | manager | system_admin | security_operator | executor |
|---|---|:-:|:-:|:-:|:-:|:-:|
| `/dashboard/*` (заявки, персонал, смены, адреса, аналитика, обр.связь) | `dashboard.use` | ✅ | ✅ | ❌ | ❌ | ❌ |
| пункт «Жители» / «Группы» | `residents.manage` / `group_intake.manage` | ❌ | ✅ | ❌ | ❌ | ❌ |
| пункт «Контроль платежей» (build-флаг) | `payments.manage` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `/dashboard/access` (обзор) | `access.events.read` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `/dashboard/access/{history,database,equipment}` | `access.registry.manage` | ❌ | ✅ | ✅ | ❌ | ❌ |
| `/dashboard/materials` (Склад) | `materials.manage` | ❌ | ✅ | ✅ | ❌ | ❌ |
| `/dashboard/elevators` / `.../config` (build-флаг) | `elevators.read` / `elevators.manage` | ❌ | ✅ | ❌ | ❌ | ✅ / ❌ |
| `/dashboard/resource-accounting` (Учёт ресурсов, build-флаг) | `resources.launch` | ✅ | ✅ | ✅ | ❌ | ❌ |

`admin` видит «Учёт ресурсов» с RBAC A1 (2026-10-10): API пускал его туда всегда,
интерфейс прятал. Остальные строки совпадают с прежними массивами ролей.

> Асимметрия `admin`↔`system_admin` (первый — основной дашборд, второй — access/склад)
> — прямое следствие §2. Если нужен единый «супер-админ», роль требует консолидации.

## 5. Матрица «как есть» — снимок прав (RBAC, этап 0)

Перед переходом на действия вместо имён ролей (вариант O3, решение владельца
2026-10-10) текущие права зафиксированы **по результату, а не по механизму**:
каждый гейт вызывается с синтетическими пользователями всех сочетаний ролей,
найденных на обоих продах, плюс граничные случаи (пустые роли, pending).

| Файл | Что фиксирует | Объём (2026-10-10) |
|---|---|---|
| `tests/rbac_baseline/core_api.json` | Каждый маршрут API ядра × профиль → пропуск | 207 маршрутов: 31 публичный, 14 «любой вошедший», 162 по ролям |
| `tests/rbac_baseline/access_api.json` | То же для API охраны | 67 маршрутов: 11 публичных, 56 по ролям |
| `tests/rbac_baseline/bot_handlers.json` | `require_role`, root-фильтры `RoleGate`, режимы `RoleFilter` | 100 гейтов: 86 декораторов, 12 root-фильтров, 2 фильтра режима |
| `tests/rbac_baseline/inline_checks.json` | Функции, сравнивающие роль со строкой-именем в теле (`"manager" in roles`) — двунаправленный ратчет | 82 функции: handlers 43, services 15, api 13, utils 6, keyboards 4, database 1 |

Генератор — `tests/rbac_baseline/builder.py` (`--check` / `--write`). Тесты:
`tests/services/test_rbac_baseline.py` (матрица = снимок) и
`tests/services/test_rbac_role_predicates.py` (явная таблица предикатов
`has_admin_access`, `has_manager_role`, `has_executor_access`, `get_user_roles`,
`RoleGate`, `is_manager`, workflow `_is_manager` по всем профилям).

**Правило:** красный снимок = изменились полномочия. Перевод проверок на действия
обязан оставить матрицу прежней. Осознанное изменение прав — отдельный PR с
решением владельца, `--write` и разбором диффа.

**Особенности текущего поведения, найденные снимком (не исправлены, ждут решения):**

1. **Статус не проверяется большинством гейтов.** `require_roles` (API), `require_role`
   и `RoleGate` (бот) пускают pending-аккаунт с нужной ролью: приглашённый, но ещё не
   одобренный менеджер проходит **92 из 148** менеджерских маршрутов API ядра,
   pending-исполнитель — пул/взятие/выполнение/проблему простого режима. Статус
   (`require_approved_roles`) проверяют лифты, отчёты о работах, склад, контроль
   платежей, создание заявок и адресные чтения, а также **все** маршруты API охраны.
2. **`has_executor_access` расходится сам с собой:** через `roles=` пропускает
   `executor`, `manager`, `admin`; через `user=` — только `executor`.
3. **`admin` ≠ `manager`** (см. §2): бот — да, API — 11 маршрутов, workflow-гарды
   (`_is_manager`) и `has_manager_role` — нет.
4. **`RoleFilter` смотрит на `active_role`** (режим меню), а не на набор ролей: два
   хендлера архива показываются по выбранному режиму, а не по правам.
5. **Простой режим** (`/api/v2/requests/pool`, `/{n}/claim`, `/{n}/complete`,
   `/{n}/problem`) — `require_roles("executor")`, менеджер без `executor` получает 403.
6. **Лифты** — 21 приватный маршрут: чтение и смена статуса — `executor`+`manager`,
   управление реестром и календарём — только `manager`; плюс флаг `ELEVATORS_ENABLED`.

## 6. Связанные документы
- [../product/OVERVIEW.md](../product/OVERVIEW.md) — роли на бизнес-уровне.
- [../guides/ADMIN_GUIDE.md](../guides/ADMIN_GUIDE.md) — инструкция `system_admin`.
- [../access-control/TECHNICAL_SPEC.md](../access-control/TECHNICAL_SPEC.md) — ТЗ модуля доступа.
