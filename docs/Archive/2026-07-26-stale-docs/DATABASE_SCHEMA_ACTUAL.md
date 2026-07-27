# База данных UK Management — фактическая схема (ACTUAL)

> _Последнее редактирование: 2026-07-06_

**Источник истины:** SQLAlchemy-модели `uk_management_bot/database/models/*.py` + миграции Alembic `alembic/versions/` (head = `036_materials_inventory`).
**Дата ревизии:** 2026-07-06.
**СУБД:** PostgreSQL (прод/dev через Docker, контейнер `uk-postgres`).

> ⚠️ **Автогенерация недоступна в этой среде.** Скрипт `scripts/export_schema.py` не запускался: в среде документирования нет Python-окружения бота (SQLAlchemy/зависимости) и подключаемого PostgreSQL-диалекта. Кроме того, сам скрипт устарел и **не отражает актуальную схему**, поэтому его вывод нельзя использовать как есть:
> - хардкод `Date: 2025-10-15` и только 3 ENUM-типа (`accesslevel`, `documenttype`, `verificationstatus`);
> - импортирует только `uk_management_bot.database.models` → **не видит домен access_control** (его таблицы создаются raw-миграциями 025–035, ORM-моделей в этом пакете нет);
> - в прошлом дампе присутствовала уже удалённая колонка `users.role` (удалена миграцией `022_drop_legacy_role`).
>
> Данный файл собран **вручную из кода** (file:line указаны) и заменяет дамп от 2025-10 (23 таблицы).

---

## 1. Сводка по таблицам

Всего в системе **>50 прикладных таблиц** (+ служебная `alembic_version`). Они делятся на два контура:

| Контур | Кол-во таблиц | Владелец схемы | Источник DDL |
|--------|---------------|----------------|--------------|
| **Бот/API (основной домен)** | 34 | SQLAlchemy `Base` (`database/models/*`) | миграции 001–024, 036 |
| **access_control (СКУД/ANPR/шлагбаумы)** | 22 | отдельный сервис, raw-миграции | миграции 025–035 |
| **materials (склад)** | 4 (входят в 34) | SQLAlchemy `Base` (`database/models/material.py`) | миграция 036 |
| **Итого** | **~56** | | head = 036 |

### 1.1. Таблицы основного домена (SQLAlchemy Base)

Регистрируются импортом в `uk_management_bot/database/models/__init__.py:1`.

| Таблица | Модель (файл) | Назначение |
|---------|---------------|-----------|
| `users` | `user.py:6` | Пользователи (жители, исполнители, менеджеры, обходчики). Роли — JSON `roles` + `active_role` |
| `user_documents` | `user_verification.py:37` | Документы пользователя (верификация) |
| `user_verifications` | `user_verification.py:68` | Процесс верификации пользователя |
| `access_rights` | `user_verification.py:100` | Права подачи заявок по уровню (apartment/house/yard). **НЕ путать с доменом access_control** |
| `requests` | `request.py:7` | Заявки жителей (PK = `request_number`, формат `YYMMDD-NNN`) |
| `request_comments` | `request_comment.py:12` | Комментарии/переходы статусов заявки |
| `request_assignments` | `request_assignment.py:12` | Назначения заявок (групповые/индивидуальные) |
| `request_number_counters` | `request_number_counter.py:19` | Gap-safe счётчик суффикса номера заявки по дням |
| `ratings` | `rating.py:6` | Оценки жителя по завершённой заявке (1 на заявку) |
| `shifts` | `shift.py:6` | Смены исполнителей |
| `shift_templates` | `shift_template.py` | Шаблоны смен |
| `shift_schedules` | `shift_schedule.py` | Дневные расписания/аналитика покрытия |
| `shift_assignments` | `shift_assignment.py` | Привязка заявок к сменам (AI-скоринг) |
| `shift_transfers` | `shift_transfer.py:12` | Передача смен между исполнителями |
| `quarterly_plans` | `quarterly_plan.py` | Квартальные планы покрытия сменами |
| `quarterly_shift_schedules` | `quarterly_plan.py` | Плановые смены внутри квартального плана |
| `planning_conflicts` | `quarterly_plan.py` | Конфликты планирования |
| `yards` | `yard.py:10` | Двор (территория УК) |
| `buildings` | `building.py:10` | Здание (дом) в дворе |
| `apartments` | `apartment.py:10` | Квартира в здании |
| `user_apartments` | `user_apartment.py:25` | Связь житель↔квартира с модерацией |
| `user_yards` | `user_yard.py:13` | Доп. дворы пользователя |
| `notifications` | `notification.py:15` | Уведомления пользователей (бот) |
| `audit_logs` | `audit.py:6` | Аудит действий |
| `refresh_tokens` | `refresh_token.py:6` | Refresh-токены web-сессий |
| `invite_nonces` | `invite_nonce.py:6` | Одноразовые nonce приглашений |
| `board_config` | `board_config.py:7` | Singleton-конфиг публичной витрины (id=1) |
| `feedback` | `feedback.py:16` | Обратная связь (жалобы/пожелания) |
| `webhook_outbox` | `webhook_outbox.py:7` | Исходящие вебхуки (transactional outbox) |
| `webhook_inbox` | `webhook_inbox.py:11` | Входящие вебхуки InfraSafe→UK (дедуп) |
| `materials` | `material.py:53` | Номенклатура материалов |
| `material_receipts` | `material.py:85` | Приход = партия (FIFO-лот) |
| `material_issues` | `material.py:157` | Расход материала |
| `material_issue_allocations` | `material.py:211` | FIFO-связка расход↔партия |

### 1.2. Таблицы домена access_control (22)

Создаются raw-миграциями (ORM-моделей в `uk_management_bot/database/models/` нет; домен обслуживается отдельным сервисом, образ `Dockerfile.access`). DDL — в `alembic/versions/025..035`.

| Миграция | Таблицы |
|----------|---------|
| `025_access_control_territory_equipment` | `parking_zones`, `edge_controllers`, `parking_zone_yards`, `access_gates`, `access_cameras`, `access_barriers` |
| `026_access_control_vehicles_passes` | `vehicles`, `vehicle_apartments`, `access_rules`, `access_passes`, `resident_access_requests` |
| `027_access_control_events_decisions` | `camera_events`, `access_decisions`, `access_events`, `controller_sync_events` |
| `028_access_control_commands_audit_append_only` | `barrier_commands`, `manual_openings`, `access_audit_logs` |
| `033_access_control_parking_types` | `parking_spots`, `parking_spot_assignments` |
| `034_access_control_entry_confirmations` | `access_entry_confirmations` |
| `035_access_control_presence_sessions` | `vehicle_presence_sessions` |

> Миграции `029`–`032` добавляют индексы/CHECK-и/колонки к уже созданным таблицам access_control (новых таблиц не создают).

---

## 2. ENUM-типы

В основном домене PostgreSQL-ENUM используются в модуле верификации (`user_verification.py:16`):

| Тип | Значения | Где применяется |
|-----|----------|-----------------|
| `documenttype` | `passport`, `property_deed`, `rental_agreement`, `utility_bill`, `other` | `user_documents.document_type` |
| `verificationstatus` | `pending`, `approved`, `rejected`, `requested` | `user_documents.verification_status`, `user_verifications.status` |
| `accesslevel` | `apartment`, `house`, `yard` | `access_rights.access_level` |

Остальные «статусные» поля (`requests.status`, `shifts.status`, `user_apartments.status`, `feedback.status`, `material_*.doc_type` и т.п.) реализованы как `VARCHAR` + канон-ключи/`CheckConstraint`, а не как PG-ENUM. Локализация значений — через `get_text`/i18n (паттерн `urgency`).

---

## 3. Основной домен — колонки по таблицам

### 3.1. `users` (`user.py:6`)

⚠️ Колонка `role` **удалена** (миграция `022_drop_legacy_role`). Роль пользователя = JSON-массив `roles` + текущая `active_role`.

| Колонка | Тип | Null | Примечание |
|---------|-----|------|-----------|
| `id` | INTEGER | NOT NULL | PK |
| `telegram_id` | BIGINT | NOT NULL | UNIQUE, index |
| `username` | VARCHAR(255) | NULL | |
| `first_name` | VARCHAR(255) | NULL | |
| `last_name` | VARCHAR(255) | NULL | |
| `roles` | TEXT | NULL | JSON-массив: `["applicant","executor"]` |
| `active_role` | VARCHAR(50) | NULL | applicant / executor / manager / inspector |
| `status` | VARCHAR(50) | NOT NULL | `pending` / `approved` / `blocked` |
| `language` | VARCHAR(10) | NOT NULL | default `ru` |
| `phone` | VARCHAR(20) | NULL | |
| `specialization` | TEXT | NULL | JSON-массив специализаций |
| `verification_status` | VARCHAR(50) | NOT NULL | default `pending` |
| `verification_notes` | TEXT | NULL | |
| `verification_date` | TIMESTAMPTZ | NULL | |
| `verified_by` | INTEGER | NULL | id администратора (без FK) |
| `passport_series` | VARCHAR(10) | NULL | |
| `passport_number` | VARCHAR(10) | NULL | |
| `birth_date` | TIMESTAMPTZ | NULL | |
| `password_hash` | VARCHAR(255) | NULL | web-auth |
| `email` | VARCHAR(255) | NULL | UNIQUE, index |
| `password_reset_token` | VARCHAR(64) | NULL | |
| `password_reset_expires_at` | TIMESTAMPTZ | NULL | |
| `deleted_at` | TIMESTAMPTZ | NULL | soft-delete |
| `deleted_by` | INTEGER | NULL | FK → `users.id` |
| `deletion_reason` | TEXT | NULL | |
| `created_at` / `updated_at` | TIMESTAMPTZ | NULL | |

### 3.2. `requests` (`request.py:7`)

PK = `request_number` VARCHAR(15), формат `YYMMDD-NNN` (сервис `RequestNumberService`).

Ключевые колонки (полный список — в модели):

| Колонка | Тип | Null | Примечание |
|---------|-----|------|-----------|
| `request_number` | VARCHAR(15) | NOT NULL | PK |
| `user_id` | INTEGER | NOT NULL | FK → `users.id`, index (заявитель) |
| `category` | VARCHAR(100) | NOT NULL | |
| `status` | VARCHAR(50) | NOT NULL | default `Новая`, index |
| `description` | TEXT | NOT NULL | |
| `urgency` | VARCHAR(20) | NOT NULL | канон-ключ `low/medium/high/critical` (TASK 17) |
| `source` | VARCHAR(20) | NULL | `bot` / `twa` / вебхук и т.п. (default `bot`) |
| `address` | TEXT | NULL | legacy-адрес |
| `apartment` | VARCHAR(20) | NULL | legacy |
| `apartment_id` | INTEGER | NULL | FK → `apartments.id`, index |
| `building_id` | INTEGER | NULL | FK → `buildings.id` (ON DELETE RESTRICT), index |
| `yard_id` | INTEGER | NULL | FK → `yards.id` (ON DELETE RESTRICT), index |
| `address_type` | VARCHAR(20) | NULL | дискриминатор: `legacy/yard/building/apartment` |
| `media_files` | JSON | NULL | default `[]` |
| `executor_id` | INTEGER | NULL | FK → `users.id`, index |
| `assignment_type` | VARCHAR(20) | NULL | `group`/`individual` |
| `assigned_group` | VARCHAR(100) | NULL | |
| `assigned_at`/`assigned_by` | TIMESTAMPTZ / INTEGER | NULL | `assigned_by` FK → `users.id` |
| `completion_report` | TEXT | NULL | |
| `completion_media` | JSON | NULL | |
| материалы: `purchase_materials`, `requested_materials`, `manager_materials_comment`, `purchase_history` | TEXT | NULL | |
| возврат: `is_returned`(BOOL), `return_reason`, `return_media`(JSON), `returned_at`, `returned_by`(FK users) | | | |
| подтверждение: `manager_confirmed`(BOOL), `manager_confirmed_by`(FK users), `manager_confirmed_at`, `manager_confirmation_notes` | | | |
| `created_at`(index), `updated_at`, `completed_at` | TIMESTAMPTZ | NULL | |

**Инвариант (CHECK `ck_requests_address_type_fk`, `request.py:14`):** `address_type IS NULL` ИЛИ ровно один из `apartment_id`/`building_id`/`yard_id` заполнен согласно дискриминатору (`legacy` → все три NULL).

### 3.3. `request_comments` (`request_comment.py:12`)

`id` PK; `request_number` FK → `requests.request_number`; `user_id` FK → `users.id`; `comment_text` TEXT; `comment_type` VARCHAR(50) (`status_change`/`clarification`/`purchase`/`report`); `previous_status`/`new_status` VARCHAR(50); `is_internal` BOOL default false; `media_files` JSON; `created_at`.

### 3.4. `request_assignments` (`request_assignment.py:12`)

`id` PK; `request_number` FK → `requests.request_number`; `assignment_type` VARCHAR(20) (`group`/`individual`); `group_specialization` VARCHAR(100); `executor_id` FK → `users.id`; `status` VARCHAR(20) default `active`; `created_at`; `created_by` FK → `users.id`.
**Инвариант:** partial-unique `uq_request_assignments_active` по `request_number` WHERE `status='active'` (не более одного активного назначения; история cancelled/completed сохраняется).

### 3.5. `request_number_counters` (`request_number_counter.py:19`)

`day_prefix` VARCHAR(6) PK (YYMMDD, бизнес-дата Asia/Tashkent); `last_seq` INTEGER NOT NULL. Монотонный gap-safe счётчик суффикса.

### 3.6. `ratings` (`rating.py:6`)

`id` PK; `request_number` VARCHAR(15) FK → `requests.request_number`; `user_id` FK → `users.id`; `rating` INTEGER (1–5); `review` TEXT; `created_at`.
**Инвариант:** UNIQUE `uq_ratings_request_number` (одна оценка на заявку — идемпотентность приёмки).

### 3.7. `shifts` (`shift.py:6`)

`id` PK; `user_id` FK → `users.id` (nullable); `start_time` NOT NULL / `end_time`; `status` (`active/completed/cancelled/planned/paused`); `planned_start_time`/`planned_end_time`; `shift_template_id` FK → `shift_templates.id`; `shift_type`; `specialization_focus`/`coverage_areas` JSON; `geographic_zone`; лимиты `max_requests`/`current_request_count`/`priority_level`; аналитика `completed_requests`, `average_completion_time`, `average_response_time`, `efficiency_score`, `quality_rating`; `created_at`/`updated_at`.

### 3.8. `shift_transfers` (`shift_transfer.py:12`)

`id` PK; `shift_id` FK → `shifts.id` (index); `from_executor_id` FK → `users.id` (index); `to_executor_id` FK → `users.id` (nullable, index); `assigned_by` FK → `users.id` (nullable, index, REG-02); `status` (`pending/assigned/accepted/rejected/cancelled/completed/expired`); `reason` (`illness/emergency/workload/vacation/other`); `comment`; `urgency_level` (`low/normal/high/critical`); `created_at`(tz-aware, index)/`assigned_at`/`responded_at`/`completed_at`; `auto_assigned` BOOL; `retry_count`/`max_retries`.

### 3.9. `shift_templates`, `shift_schedules`, `shift_assignments`, `quarterly_plans`, `quarterly_shift_schedules`, `planning_conflicts`

Домен планирования смен (AI-скоринг, квартальные планы). Структура развёрнута в моделях `shift_template.py`, `shift_schedule.py`, `shift_assignment.py`, `quarterly_plan.py`. Ключевое:
- `shift_schedules.date` — UNIQUE (одно расписание на дату).
- `shift_assignments`: FK `shift_id`→`shifts.id`, `request_number`→`requests.request_number`; поля AI-скоринга (`ai_score`, `confidence_level`, `specialization_match_score`, `geographic_score`, `workload_score`).
- `quarterly_shift_schedules`: FK на `quarterly_plans.id`, `users.id` (assigned_user_id), `shifts.id` (actual_shift_id).
- `planning_conflicts`: FK на `quarterly_plans.id`, `users.id` (resolved_by).

### 3.10. Справочник адресов: `yards` / `buildings` / `apartments`

- **`yards`** (`yard.py:10`): `id` PK; `name` VARCHAR(200) UNIQUE index; `description`; `gps_latitude`/`gps_longitude` FLOAT; `is_active` BOOL index; `created_at`/`created_by`(FK users)/`updated_at`.
- **`buildings`** (`building.py:10`): `id` PK; `address` VARCHAR(300) index; `yard_id` FK → `yards.id` (ON DELETE CASCADE, index); GPS; `entrance_count`/`floor_count` (default 1); `is_active` index; аудит-поля.
- **`apartments`** (`apartment.py:10`): `id` PK; `building_id` FK → `buildings.id` (ON DELETE CASCADE, index); `apartment_number` VARCHAR(20) index; `entrance`/`floor`/`rooms_count` INTEGER; `area` NUMERIC(8,2); `is_active`; аудит. UNIQUE `uix_building_apartment` (`building_id`,`apartment_number`).

### 3.11. Связи пользователь↔адрес

- **`user_apartments`** (`user_apartment.py:25`): `id` PK; `user_id` FK→users (CASCADE, index); `apartment_id` FK→apartments (CASCADE, index); `status` (`pending/approved/rejected`, index); `requested_at`/`reviewed_at`/`reviewed_by`(FK users); `admin_comment`; `is_owner`/`is_primary` BOOL; UNIQUE `uix_user_apartment` (`user_id`,`apartment_id`).
- **`user_yards`** (`user_yard.py:13`): `id` PK; `user_id` FK→users (CASCADE, index); `yard_id` FK→yards (CASCADE, index); `granted_at`/`granted_by`(FK users)/`comment`; UNIQUE `uix_user_yard`.

### 3.12. Верификация: `user_documents` / `user_verifications` / `access_rights`

- **`user_documents`** (`user_verification.py:37`): `id` PK; `user_id` FK→users; `document_type` ENUM `documenttype`; `file_id`(Telegram) VARCHAR(255); `file_name`/`file_size`; `verification_status` ENUM `verificationstatus` (default PENDING); `verification_notes`; `verified_by`(FK users)/`verified_at`; аудит.
- **`user_verifications`** (`user_verification.py:68`): `id` PK; `user_id` FK→users; `status` ENUM `verificationstatus`; `requested_info` JSON; `requested_at`/`requested_by`(FK users); `admin_notes`; `verified_by`(FK users)/`verified_at`; аудит.
- **`access_rights`** (`user_verification.py:100`): `id` PK; `user_id` FK→users; `access_level` ENUM `accesslevel`; `apartment_number`/`house_number`/`yard_name`; `is_active` BOOL; `expires_at`; `granted_by`(FK users, NOT NULL)/`granted_at`; `notes`; аудит.

### 3.13. Инфраструктурные таблицы

- **`notifications`** (`notification.py:15`): `id` PK; `user_id` FK→users (index); `notification_type`; `title`/`content`; `is_read`/`is_sent` BOOL; `meta_data` JSON; `request_number_fk` FK→requests (nullable, index); аудит. Partial-index `ix_notifications_user_unread` (`user_id` WHERE `is_read=false`).
- **`audit_logs`** (`audit.py:6`): `id` PK; `user_id` FK→users (nullable); `telegram_user_id` BIGINT (index, переживает удаление пользователя); `action` VARCHAR(100); `details` JSON; `ip_address` VARCHAR(45); `created_at`.
- **`refresh_tokens`** (`refresh_token.py:6`): `id` PK; `user_id` FK→users (ON DELETE CASCADE, index); `token_hash` VARCHAR(64) UNIQUE index; `expires_at`; `created_at`; `revoked_at`; `device_info`.
- **`invite_nonces`** (`invite_nonce.py:6`): `id` PK; `nonce` VARCHAR(64) UNIQUE index; `used_by` BIGINT; `used_at`; `invite_payload` JSON.
- **`board_config`** (`board_config.py:7`): `id` PK (singleton=1); `data` JSON; `updated_at`; `updated_by` FK→users (ON DELETE SET NULL, index).
- **`feedback`** (`feedback.py:16`): `id` PK; `user_id` FK→users; `type` (`complaint`/`wish`); `text` TEXT; `media_files` JSON (list media_id); `source` (`bot`/`twa`); `status` (`new`/`in_review`/`resolved`); `reply`/`replied_at`/`replied_by`(FK users); `created_at`.

### 3.14. Вебхуки (интеграция InfraSafe)

- **`webhook_outbox`** (`webhook_outbox.py:7`): `id` PK; `event_id` VARCHAR(36) UNIQUE; `event`/`endpoint`; `payload` JSON; `status` (`pending/in_flight/sent/failed`, CHECK); `attempts`; `last_error`; `retry_after`; `claim_token`/`claimed_at`/`claim_count` (lease-доставка, CODE-01); `created_at`/`sent_at`. Индексы: `ix_webhook_outbox_status_created`, partial `ix_webhook_outbox_pending`, partial `ix_webhook_outbox_in_flight`.
- **`webhook_inbox`** (`webhook_inbox.py:11`): `id` PK; `event_id` VARCHAR(64) UNIQUE; `event`; `source_ip`; `payload` JSON; `outcome` (`accepted`/`ignored`/`rejected`); `request_number`; `error`; `received_at`.

### 3.15. Склад материалов (4 таблицы)

`materials`, `material_receipts`, `material_issues`, `material_issue_allocations` — FIFO-учёт с себестоимостью, append-only + сторно. Полное описание модели, инвариантов (`qty_remaining = qty − SUM(allocations)`), CHECK-ов и API — в **[docs/MATERIALS_MODULE.md](MATERIALS_MODULE.md)** и модели `database/models/material.py:1`. Кратко:
- `materials`: `name` UNIQUE (глобально, включая is_active=false), `unit` (CHECK: pcs/m/m2/l/kg/pack/set), `min_stock` NUMERIC.
- `material_receipts`: партия (FIFO-лот), immutable кроме `qty_remaining`; `reversal_of_issue_id` (циклический FK через `use_alter`).
- `material_issues`: расход, immutable; `request_number` — **plain-строка без FK** (журнал переживает удаление заявки); CHECK `ck_issues_target`.
- `material_issue_allocations`: связка расход↔партия (аудит себестоимости), immutable.

---

## 4. Alembic / миграции

- **Head:** `036_materials_inventory` (`alembic/versions/`).
- **Кто прогоняет:** миграции применяет **только контейнер `uk-management-api`** на старте — у образа бота (`uk-management-bot`) нет `alembic`. Форсировать: `docker exec uk-management-api alembic upgrade head`.
- **Дрейф:** `alembic_version` может опережать реальную схему при частичном апгрейде — проверять через `information_schema`, не по номеру в `alembic_version`.
- **Идемпотентность:** миграции model-backed объектов пишутся идемпотентными (CI = `create_all` + `upgrade head`).
- Домены 025–035 (access_control) обёрнуты в feature-guard: таблицы создаются только при включённом домене (см. тело миграций).

---

## 5. Как перегенерировать этот файл

При наличии рабочего окружения бота (PostgreSQL + зависимости):

```bash
cd /Users/andreyafanasyev/Code/UK
python scripts/export_schema.py   # выведет database_schema_actual.sql + DATABASE_SCHEMA_ACTUAL.md
```

⚠️ Перед использованием вывода скрипт нужно поправить: убрать хардкод даты, добавить недостающие ENUM/домен access_control (он читается только из миграций), убедиться что колонка `users.role` отсутствует. До этого момента настоящий файл — авторитетный ручной срез.
