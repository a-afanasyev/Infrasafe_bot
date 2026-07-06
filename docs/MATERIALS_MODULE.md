# Модуль «Склад материалов» (учёт закупок и движения матсредств)

> Статус: **реализовано, задеплоено на прод 2026-07-06** (миграция `036`, PR #203).
> RBAC дашборда: `manager` + `system_admin`. Списание из бота — `executor`.
> Источник истины по коду: `uk_management_bot/database/models/material.py`,
> `services/material_service.py`, `api/materials/`, `handlers/requests/materials.py`,
> `handlers/admin/materials.py`, `frontend/src/pages/materials/`.

## 1. Назначение

Базовый складской учёт: приход материалов (закупки партиями) и расход с привязкой
к заявкам (`Request`). Считаются остатки и **себестоимость по FIFO**. До модуля в
системе был только свободный текст (`requested_materials`, `purchase_*` в `Request`) —
структурного учёта, остатков и себестоимости не было. Модуль **дополняет** контур
«Закуп», ничего в нём не ломая (текстовые поля не тронуты, интеграция read-only).

Границы (осознанные упрощения): один склад (без location), поставщик — текстовое
поле, без резервирования, без мультивалютности (сум UZS), без workflow согласования.

## 2. Модель данных — 4 таблицы одного агрегата

Файл: `database/models/material.py`. Миграция: `alembic/versions/036_materials_inventory.py`
(per-object идемпотентные guard'ы; циклический FK `receipts↔issues` через `use_alter`).

```
materials ──1:N──> material_receipts (партии/FIFO-лоты)
    │                     │
    │                     └──1:N──> material_issue_allocations <──N:1── material_issues (расход)
    └──1:N──> material_issues
```

| Таблица | Роль | Ключевые поля |
|---|---|---|
| `materials` | Номенклатура (справочник) | `name UNIQUE`, `unit`, `category?`, `min_stock?`, `is_active` (soft-delete) |
| `material_receipts` | Приход = партия (FIFO-лот) | `qty`, **`qty_remaining`**, `unit_price`, `total_amount`, `supplier?`, `doc_type` (purchase/surplus), `reversal_of_issue_id?`, snapshot `material_name`/`unit` |
| `material_issues` | Расход | `qty`, `total_cost`, `request_number?` (**строка, БЕЗ FK**), `doc_type` (request/household/shortage), `reversal_of_receipt_id?`, snapshot `material_name`/`unit` |
| `material_issue_allocations` | FIFO-связка расход↔партия (аудит себестоимости) | `issue_id`, `receipt_id`, `qty`, `unit_price`, `amount` |

### Инварианты и политика учёта (из docstring модели)

- **Append-only.** `material_issues` и `material_issue_allocations` — полностью
  immutable. `material_receipts` immutable **кроме `qty_remaining`** (единственное
  мутируемое поле — декремент при FIFO-списании). Ни DELETE-, ни PUT-эндпоинтов нет.
- **Инвариант остатка:** `qty_remaining = qty − SUM(allocations.qty)` (проверяется
  тестом). Остаток материала = `SUM(qty_remaining)` по его партиям; денормализованной
  таблицы остатков нет.
- **Отрицательные остатки запрещены** — при нехватке `InsufficientStockError` → API 409.
- **Snapshot имени/единицы** в каждой операции: переименование карточки материала
  не переписывает историю (честный аудит при живых деньгах).
- **`material_issues.request_number` — plain-строка без FK** на `requests`: складской
  журнал обязан пережить удаление заявки (`delete_request_cascade` /
  `RequestService.delete_request`). Существование заявки проверяет сервис при создании
  расхода, а не БД-констрейнт.

## 3. FIFO-логика и сторно — `services/material_service.py`

Паттерн `workflow_runner`: чистое ядро + sync (бот) / async (API) обёртки.

- **`allocate_fifo(batches, qty)`** — чистое ядро (юнит-тестируемо, без I/O): списывает
  из партий по возрастанию `created_at, id`, возвращает аллокации; нехватка →
  `InsufficientStockError(available)`. Округление сумм ROUND_HALF_UP до 0.01.
- **Конкурентность:** партии лочатся `... WHERE qty_remaining > 0 ORDER BY created_at, id
  FOR UPDATE` (на sqlite FOR UPDATE молча опускается). Стабильный ORDER BY исключает
  дедлоки; CHECK `qty_remaining >= 0` — страховка БД.
- **Сторно (исправление ошибок) — только со ссылкой на исходную операцию:**
  - *Сторно расхода* (`reversal_of_issue_id`) — полное и однократное: создаёт по одной
    surplus-партии на каждую цену из исходных аллокаций (точное восстановление
    себестоимости). Повторное сторно того же issue → 409. Гонка закрыта локом исходного
    расхода `FOR UPDATE`.
  - *Сторно прихода* (`reversal_of_receipt_id`) — только для нетронутой партии
    (`qty_remaining == qty`), списание **адресно из указанной партии** мимо общего FIFO.

## 4. API — `api/materials/` (`/api/v2/materials`)

RBAC: всё — `require_approved_roles("manager", "system_admin")` (`api/dependencies.py`).
Исполнителю API не нужен (бот идёт через sync-сервис).

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/v2/materials` | список номенклатуры (`?q&is_active&limit&offset`) |
| POST | `/api/v2/materials` | создать материал |
| PATCH | `/api/v2/materials/{id}` | правка (unit нельзя менять при наличии движений) |
| GET | `/api/v2/materials/stock` | остатки+суммы (`?q&only_low`) |
| POST | `/api/v2/materials/receipts` | приход (партия) |
| POST | `/api/v2/materials/issues` | расход (`request`/`household`); нехватка → 409 |
| POST | `/api/v2/materials/adjustments` | инвентаризация (surplus/shortage) и сторно |
| GET | `/api/v2/materials/operations` | журнал операций (фильтры+пагинация) |
| GET | `/api/v2/materials/operations/export` | CSV журнала (UTF-8 BOM) |
| GET | `/api/v2/materials/by-request/{request_number}` | расходы по заявке + total_cost |
| GET | `/api/v2/materials/procurement` | «на закуп»: дефицит (остаток < min_stock) + заявки в статусе «Закуп» |
| GET | `/api/v2/materials/procurement/export` | CSV списка дефицита |

Маппинг ошибок: нехватка остатка → **409**, несоответствие полей doc_type/сторно → **422**,
нарушение инвариантов сторно (повтор/тронутая партия/несовпадение material_id) → **409**.

> ⚠️ **Edge (InfraSafe, SEC-22):** префикс `/api/v2/materials` должен быть в allowlist
> `map $uri $uk_api_allowed` (`nginx.production.conf`), иначе на публичном edge — 404.
> Добавлен 2026-07-06 (строка `"~^/uk/api/v2/materials(/|$)" 1;`).

## 5. Бот — списание исполнителем

- Вход: кнопка «📦 Материалы» на карточке заявки исполнителя в статусе «В работе»
  (`handlers/requests/listing.py` → `handlers/requests/materials.py`).
- FSM `states/material_issue.py`: `selecting_material → entering_quantity → confirming`.
- Guard (жёсткий, не полагаться на кнопку): заявка существует, статус «В работе»,
  `executor_id == user.id`, материал активен, остаток > 0. Перепроверка на подтверждении.
- Атомарность: `issue_material_sync()` (issue + allocations + декремент партий) и
  `RequestComment(type='material')` — в одной транзакции, единый commit у хендлера.
- Управление складом менеджером — `handlers/admin/materials.py` (плюс дашборд).

## 6. Фронт — `frontend/src/pages/materials/MaterialsPage.tsx`

Роли: `MATERIALS_MODULE_ROLES = ['manager','system_admin']` (`constants/roles.ts`).
Вкладки: «Остатки» | «Журнал операций» | «На закуп». Диалоги в `components/materials/`
(MaterialFormDialog / ReceiptDialog / IssueDialog / AdjustmentDialog / MaterialSelect).
Блок «Материалы» в карточке заявки — `components/kanban/RequestDetailModal.tsx`
(GET by-request, только для `MATERIALS_MODULE_ROLES`). Хук `hooks/useMaterials.ts`.

## 7. Тесты

- `tests/test_material_allocate_fifo.py` — чистое FIFO-ядро.
- `tests/api/test_materials.py` — CRUD/receipt/issue/adjustments/сторно/CSV/procurement/RBAC/инвариант.
- `tests/api/test_materials_pg_concurrency.py` — гонки на PG (issue и сторно).
- `tests/test_material_issue_handlers.py` + `tests/handlers/test_view_request_materials_button.py` — бот FSM и кнопка.

## 8. Связанные документы

- Полный план/решения владельца: `~/.claude/plans/serene-pondering-marshmallow.md`.
- Схема БД: [DATABASE_SCHEMA_ACTUAL.md](DATABASE_SCHEMA_ACTUAL.md) (требует добавления 4 таблиц).
- Деплой: [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) (миграция 036 + edge-allowlist).
