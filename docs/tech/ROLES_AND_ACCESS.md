# Роли и модель доступа (RBAC)

> Источник истины: бот — `uk_management_bot/utils/constants.py` (`USER_ROLES`),
> `config/settings.py`, `utils/enums.py` (`UserRole`), parity-тест
> `tests/test_roles_parity.py`; фронт — `frontend/src/constants/roles.ts`;
> access-control — `access_control/api/registry.py`.
> `user.roles` — JSON-массив строк, `user.active_role` — текущая активная роль
> (legacy-колонка `user.role` УДАЛЕНА миграцией 022).

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

`admin` — **отдельная действующая роль** (подтверждено владельцем), играет роль
**общего управленческого администратора ≈ `manager`**. Используется в ~116 местах
авторизации бота и основного API как `any(role in ['admin','manager'])`:

- `filters/role_filter.py:30`, `keyboards/base.py:134,154`, `utils/auth_helpers.py:62,69,86`
- `handlers/user_verification.py` (верификация пользователей — 7+ гейтов)
- `api/requests/router.py:676,699`, `api/shifts/router.py:122`
- фронт: `App.tsx:102` — основной `/dashboard/*` гейтится `['admin','manager']`

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

## 3. RBAC модуля «Контроль доступа»

Access-control (`access_control/api/registry.py`) гейтится тремя наборами —
**`admin` в них НЕ участвует** (роли раздельны):

| Набор (registry.py) | Роли | Что покрывает |
|---|---|---|
| `EVENTS_PASSES_ROLES` (:40) | `security_operator`, `manager`, `system_admin` | События/пропуска (пост охраны) |
| `VEHICLES_REQUESTS_ROLES` (:41) | `manager`, `system_admin` | База авто/заявок, история проездов |
| `PHOTO_VIEW_ROLES` (:45) | `security_operator`, `manager`, `system_admin` | Просмотр фото проездов |

Фронт зеркалит это (`constants/roles.ts`): `ACCESS_MODULE_ROLES =
{manager, system_admin, security_operator}`, `ACCESS_MANAGER_ROLES =
{manager, system_admin}`. **Оборудование** (камеры/шлагбаумы/контроллеры) — только
`system_admin` (`AccessEquipmentPage.tsx:914` `useHasRole('system_admin')`; бэкенд
отдаёт GET только system_admin, manager → 403, табы скрыты).

Иерархия внутри модуля: `security_operator` (пост охраны) ⊂ `manager` (база+история)
⊂ `system_admin` (+оборудование).

## 4. Матрица доступа к разделам дашборда (`App.tsx`)

| Раздел | Гейт (allowedRoles) | admin | manager | system_admin | security_operator |
|---|---|:-:|:-:|:-:|:-:|
| `/dashboard/*` (заявки, персонал, смены, адреса, аналитика, обр.связь) | `['admin','manager']` | ✅ | ✅ | ❌ | ❌ |
| `/dashboard/access` (обзор) | `ACCESS_MODULE_ROLES` | ❌ | ✅ | ✅ | ✅ |
| `/dashboard/access/{history,database,equipment}` | `ACCESS_MANAGER_ROLES` | ❌ | ✅ | ✅ | ❌ |
| `/dashboard/materials` (Склад) | `MATERIALS_MODULE_ROLES` | ❌ | ✅ | ✅ | ❌ |

> Асимметрия `admin`↔`system_admin` (первый — основной дашборд, второй — access/склад)
> — прямое следствие §2. Если нужен единый «супер-админ», роль требует консолидации.

## 5. Связанные документы
- [../product/OVERVIEW.md](../product/OVERVIEW.md) — роли на бизнес-уровне.
- [../guides/ADMIN_GUIDE.md](../guides/ADMIN_GUIDE.md) — инструкция `system_admin`.
- [../access-control/TECHNICAL_SPEC.md](../access-control/TECHNICAL_SPEC.md) — ТЗ модуля доступа.
