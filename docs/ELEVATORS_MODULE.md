# Модуль «Лифты» (реестр, статус, заявки, календарь ТО, напоминания)

> _Составлено: 2026-09-06_

> Статус: **реализовано в ветке `worktree-feat+elevators` (Ф0–Ф6), на прод НЕ раскатано.**
> Миграции `016`, `017`. Всё за флагами `ELEVATORS_ENABLED` (backend) и
> `VITE_ELEVATORS_ENABLED` (SPA): при выключенных флагах модуль бездействует,
> API отвечает единым 404.
> Источник истины по коду: `uk_management_bot/database/models/{elevator,elevators_config}.py`,
> `services/elevator_service/`, `api/elevators/`, `handlers/elevators/`,
> `handlers/requests/create_elevator*.py`, `handlers/admin/elevator_hint.py`,
> `handlers/group_intake_elevator.py`, `utils/shift_scheduler.py` (джоба
> `elevator_reminders`), `frontend/src/pages/elevators/`, `frontend/src/components/elevators/`.
> План и журнал решений владельца: `~/.claude/plans/stateless-crunching-sundae.md` (v2.3).

## 1. Назначение и границы

Реестр лифтов ЖК с обязательным паспортом, ручным техническим статусом и
неизменяемым журналом; привязка заявок категории `elevator` к конкретному лифту
(обязательная во всех каналах); календарь ТО и освидетельствований; напоминания
персоналу и уведомления жителям подъезда. Лифт идентифицируется **дом → подъезд →
номер в подъезде**; заводской/серийный номера — реквизиты паспорта.

Границы первого релиза (осознанно): статус меняется **только руками** (менеджер в
дашборде, лифтёр в боте, подсказка менеджеру после подтверждения заявки) — автостатуса
от заявок нет; ремонт — обычная заявка, ТО/освидетельствование — пункты календаря;
договор и освидетельствование — поля паспорта, не сущности; QR/публичная карточка,
обходы, CSV-импорт, notification ledger — отложены (§10). Ядро workflow заявок
(planner/guards/runner/dispatch) **не изменялось**.

## 2. Журнал решений (сжато; полностью — план §1)

| № | Решение |
|---|---|
| Р1 | Отдельная таблица `elevators` + nullable `requests.elevator_id` (по образцу `requests.asset_id` из ТЗ ассетов). Закрывает открытый вопрос №2 `docs/ASSETS_MODULE.md` |
| Р2 | Ручной статус + подсказка «Лифт работает?» при подтверждении заявки; автостатус отложен |
| Р3 | Ремонт = заявка с `acceptance_mode=manager`; ТО и освидетельствование = календарь |
| Р4 | Договор/освидетельствование — поля паспорта. Обязательный паспорт: дом, подъезд, номер, номер паспорта, производитель, серийник |
| Р5 | Обходов нет |
| Р6 | QR/публичная карточка — второй релиз; `public_code`/`is_public` в схеме сразу |
| Р7 | Напоминания — идемпотентный тик без ledger: стадия пишется в той же транзакции, что и сообщение; потеря одного сообщения допустима, дубль — нет |
| Р8 | Масштаб — сотни лифтов; рассылка жителям только тем, у кого заполнен подъезд квартиры |
| Р9 | Ремонт лифтёра — обычная заявка: штатный автодиспетчер, без предпочтения создателя |
| Р10 | Группировка и массовое подтверждение — в карточке лифта; канбан получает только бейдж |
| Р11 | Лифт и ответ «работает?» **обязательны во всех каналах** (бот, TWA, инспектор, колл-центр, групповой приём, InfraSafe). Один валидатор для всех конструкторов |
| Р12 | Лифтёр меняет статус любого активного лифта; гейт только по специализации `elevator` |
| Р13 | Паспорта — ручной ввод, форма с «скопировать предыдущий»; импорт отложен |
| Р14 | InfraSafe передаёт **наш `elevators.id`** в `alert.uk_elevator_id`; отдельной колонки маппинга нет |
| Р15 | Групповой приём: дом из квартиры автора, лифт — inline-кнопками в чате, автовыбор при единственном лифте в подъезде; нет ответа — нет заявки |

## 3. Модель данных

Миграции: `alembic/versions/0016_elevators.py` (4 таблицы + 2 колонки),
`0017_elevator_overdue_reminders.py` (+2 колонки на `elevators`). Модели:
`database/models/elevator.py`, `elevators_config.py`, колонки в `request.py:97-98`.

```
buildings ──1:N──> elevators ──1:N──> elevator_status_events        (RESTRICT)
                       │     └──1:N──> elevator_maintenance_occurrences (RESTRICT)
                       └──1:N──> requests.elevator_id (SET NULL)
elevators_config — singleton id=1 (JSON), как board_config/auto_manager_config
```

| Таблица | Роль | Ключевые поля |
|---|---|---|
| `elevators` | Реестр + паспорт + статус + договор/освидетельствование + стадии напоминаний | `building_id` FK, `entrance_number`, `elevator_number`; паспорт (`passport_number`, `manufacturer`, `serial_number` NOT NULL; `factory_number`, `model`, `production_year`, `capacity_kg`, `floors_served`, `commissioned_at`); `current_status` **nullable** CHECK ∈ working/not_working/under_repair/maintenance, `status_since`, `downtime_reason`, `spare_part_expected_on`, `publish_downtime_details`; `service_org_name/phone`, `contract_number`, `contract_until`, `cert_number`, `cert_valid_until`, `cert_act_url`; `contract_reminder_stage`, `cert_reminder_stage` (smallint, **дни**), `downtime_reminded_at`, `contract_overdue_reminded_at`, `cert_overdue_reminded_at` (017); `public_code` UNIQUE NOT NULL, `is_public`; `is_commissioned`, `archived_at`, `archived_reason`, `version` |
| `elevator_status_events` | Append-only журнал | `event_kind` CHECK ∈ status_changed/commissioned/archived/contract_changed/cert_changed/passport_changed; `old_status`, `new_status`, `occurred_at`, `actor_user_id` (SET NULL), `source` CHECK ∈ manual/request_hint/infrasafe/system, `request_number` (**строка, БЕЗ FK**), `reason`, `payload` JSONB |
| `elevator_maintenance_occurrences` | Пункт календаря ТО/освидетельствования | `kind` ∈ maintenance/certification, `due_on`, `state` ∈ planned/done/cancelled, `done_at`, `done_by_user_id`, `comment`, `request_number` (без FK), `reminder_stage` (дни), `overdue_reminded_at`, `created_by_user_id` |
| `elevators_config` | Singleton-конфиг | `data` JSONB, `updated_at`, `updated_by` (SET NULL). Seed-строки нет — дефолты несёт сервис |
| `requests` (+2) | Привязка заявки | `elevator_id` FK → `elevators.id` ON DELETE SET NULL, `ix_requests_elevator_id`; `elevator_operational` bool nullable |

### Инварианты

- **Статус NULL до ввода в эксплуатацию**: `current_status IS NOT NULL ⇔ is_commissioned`
  — сервисный инвариант (`validation.can_set_status`), не CHECK. Невведённый лифт не
  показывается жителям и не попадает в `for-building`.
- **Уникальность места** среди неархивных: partial-unique
  `uq_elevators_building_entrance_number_active (building_id, entrance_number, elevator_number) WHERE archived_at IS NULL`.
  Архивирование освобождает место; `public_code` не переиспользуется.
- **RESTRICT на дочерних FK**: журнал и календарь ссылаются на лифт с `ON DELETE RESTRICT`,
  relationship с `passive_deletes=True` — лифт архивируется, жёсткое удаление при наличии
  истории БД запрещает (без `passive_deletes` ORM пытался бы занулить NOT NULL `elevator_id`).
- **`request_number` без FK** в журнале и календаре (образец `material_issues`): история
  лифта переживает удаление заявки.
- **Стадии напоминаний хранятся в ДНЯХ** (`*_reminder_stage`: 0 = не слали, затем 30 → 14 → 7),
  а не индексом в списке: список стадий редактируется в конфиге, сохранённое значение обязано
  пережить его сжатие/расширение. Пропущенные стадии схлопываются в одно сообщение.
- **Сброс стадий** — в сервисе, не триггером: смена `contract_until` → `contract_reminder_stage=0`
  и `contract_overdue_reminded_at=NULL`; `cert_valid_until` — аналогично для cert (в т.ч. при
  закрытии освидетельствования через календарь); смена статуса → `downtime_reminded_at=NULL`;
  перенос `due_on` planned-пункта → `reminder_stage=0`.
- **`public_code` — CSPRNG**: `secrets.token_urlsafe(16)`, обрезка до 32, URL-safe алфавит,
  без последовательности (`services/elevator_service/public_code.py`).
- **Календарь**: partial-unique `(elevator_id, kind, due_on) WHERE state <> 'cancelled'`;
  `done` неизменяем (`assert_occurrence_editable`); отменённый не мешает создать пункт на ту же дату.
- **`requests.elevator_id`/`elevator_operational` NULL допустимы в БД** (другие категории,
  исторические заявки); обязательность для `category='elevator'` — инвариант валидатора Р11,
  не CHECK.
- Канон-наборы статусов/видов дублируются в миграции 016 (alembic не импортирует модели);
  паритет закреплён `uk_management_bot/tests/test_elevator_models.py`.

## 4. Сервисный слой — `services/elevator_service/`

Паттерн `material_service`: **чистое ядро без I/O** + **DB-слой** с sync/async-зеркалами.

| Слой | Модули | Содержимое |
|---|---|---|
| Чистое ядро (Ф2a) | `_core` (ошибки `ElevatorServiceError` → `Validation/NotFound/Conflict/State`, DTO `Message`, `StatusChange`), `validation` (Р11 `require_elevator_for_category`, `can_set_status`, паспорт), `availability` (`compute_availability_30d`), `calendar_rules` (`generate_occurrence_dates`, `next_reminder_stage`, `is_overdue`, `should_remind_overdue`, лимиты 1–24 мес × 1–36 пунктов), `reminder_rules` (`DEFAULT_ELEVATORS_CONFIG`, `merge_config`, `downtime_threshold_reached`), `public_code`, `labels` | Юнит-тесты без БД |
| DB-слой (Ф2b) | `_shared` (строители событий, `flush_or_conflict_*`: IntegrityError → 409), `reads`, `registry` (реестр с фильтрами и сводка по дворам, без N+1), `metrics` (доступность 30 дней поверх журнала), `status`, `recipients`, `passport`, `calendar`, `config`, `validation_db`, `reminders` | Каждая операция — `*_sync(Session)` для бота и `*_async(AsyncSession)` для API поверх общего строителя; **commit — у вызывающего** |
| Вне реэкспорта | `grouping` (`bulk_confirm_async`) | Импортировать **модулем**: `from ...elevator_service.grouping import bulk_confirm_async`. Тянет `workflow_runner` лениво — иначе цикл с хендлерами |

Правила:

- **Сети в сервисе нет.** `set_status_*` возвращает `StatusChange(changed, resident_messages, ...)`;
  отправляет вызывающий **после commit** своим каналом: бот — `send_notify_messages`,
  API — `api/residents/notify.py:send_plain_messages` (возвращает число доставленных),
  планировщик — `send_notify_messages(self._bot, ...)`.
- **Единственный путь смены статуса** — `set_status_*` (`FOR UPDATE`, проверка ввода в
  эксплуатацию, no-op при совпадении без сброса `status_since`, событие `status_changed`
  только при фактической смене). Уведомления жителям строятся только для
  `under_repair → repair_started`, `maintenance → maintenance_started`, `working → back_in_service`
  и только если включены в конфиге; при «Не работает» рассылки нет.
- **Валидатор Р11 в одном резолвере**: `validation_db.resolve_request_elevator_{sync,async}` —
  чистый `require_elevator_for_category` + «лифт существует, не архивирован, введён в
  эксплуатацию и, если задан `building_id`, принадлежит дому заявки». Вызывают **все четыре
  конструктора** заявок (§6). Параметр `enabled=settings.ELEVATORS_ENABLED`: при выключенном
  флаге лифт не требуется, поля NULL.
- **Импорт-гейт** `tests/services/test_elevator_service_imports.py`: чистый интерпретатор
  импортирует пакет и `grouping`; в `sys.modules` не должно быть `workflow_runner`, `httpx`,
  `aiogram`, `fastapi`.
- **Адресаты жителей** (`recipients.residents_of_entrance_*`): approved-привязка к квартире
  этого дома с `apartments.entrance = N`, пользователь не удалён и не заблокировал бота
  (`bot_blocked_at IS NULL`), EXISTS-подзапрос → один человек = одно сообщение.
- **Конфиг**: сохранённый терпим к неизвестным ключам (отбрасываются, один warning),
  патч строгий (неизвестный ключ → 422); нет строки/битые данные → дефолты.
- **Паспорт**: место лифта (дом/подъезд/номер) меняется только до ввода в эксплуатацию;
  `commissioned_at` — только через `commission`; архив отменяет planned-пункты календаря
  и снимает публичность, статус остаётся как есть; `passport_changed` — только по реально
  изменившимся полям; `version` — оптимистичная блокировка (`expected_version` в PATCH → 409).
- **Порядок блокировок**: сначала лифт `FOR UPDATE`, затем пункт календаря (archive, calendar).

## 5. API — `api/elevators/` (`/api/v2/elevators`)

Монтируется в `api/main.py:158` **всегда**; при `ELEVATORS_ENABLED=false` зависимость
роутера отвечает единым **404** на все пути (DARK-гейт как у `work_reports`: выключенная
фича не палит наличие ни 403, ни схемой; в OpenAPI-снапшот роуты попадают всегда).
RBAC только по роли (`require_approved_roles`): `_staff` = executor|manager,
`_manager_only` = manager, `_any_approved` = applicant|executor|inspector|manager.
Специализация `elevator` у executor **API не проверяется** (механизма нет; принято
осознанно, актор виден в журнале). Роутеры тонкие: транзакции — `service.py` /
`calendar_service.py`, домен — `services/elevator_service`. Статичные пути и под-роутер
календаря объявлены ДО динамического `/{elevator_id}`.

| Метод | Путь | Роли | Назначение / особенности |
|---|---|---|---|
| GET | `` | staff | Реестр: `yard_id`, `building_id`, `status`, `flag[]` ∈ no_contract/cert_expired/maintenance_overdue, `include_archived`, `limit≤200`, `offset`, `lang` |
| POST | `` | manager | Создать паспорт (201); дубль места → 409 |
| GET | `/summary` | staff | Сводка по дворам (счётчики статусов, просрочки, заявки без лифта) |
| GET / PUT | `/config` | manager | Конфиг; PUT — строгий патч, **30/min** |
| GET | `/for-building/{building_id}` | any approved | Введённые в эксплуатацию лифты дома для выбора в заявке (TWA/колл-центр); **applicant — только дома своих одобренных квартир** (403) |
| POST | `/requests/bulk-confirm` | manager | Групповая `MANAGER_CONFIRM`, ≤50 номеров, **10/min**, per-item результат; realtime/notify-интенты диспетчатся как при одиночном подтверждении |
| GET | `/{id}` | staff | Карточка: паспорт, статус, доступность 30 дн., счётчик квартир подъезда без данных о подъезде |
| PATCH | `/{id}` | manager | Правка паспорта; `expected_version` → 409 при гонке |
| POST | `/{id}/commission` | manager | Ввод в эксплуатацию (`commissioned_at`) |
| POST | `/{id}/archive` | manager | Архив (`reason` обязателен, ≤500) |
| PUT | `/{id}/status` | staff | Смена статуса (`status`, `reason ≤500`, `request_number` → `source=request_hint`), **30/min**; жителям — после commit, в ответе `notified_residents` |
| GET | `/{id}/events` | staff | Журнал |
| GET | `/{id}/requests` | staff | Заявки лифта (для чекбоксов и bulk-confirm) |
| GET | `/occurrences` | staff | Календарь всех лифтов: `from`, `to` (включительно), `state` ∈ planned/done/cancelled/all, `kind` |
| PATCH | `/occurrences/{oid}` | manager | Перенос `due_on` (сбрасывает стадию) |
| POST | `/occurrences/{oid}/cancel` | manager | Отмена |
| POST | `/occurrences/{oid}/complete` | staff | Закрытие; для certification обязательны `cert_number`, `cert_valid_until` → обновляет паспорт, событие `cert_changed` |
| GET / POST | `/{id}/occurrences` | staff / manager | Пункты лифта (`kind`, `state`, `from`, `to`) / ручной пункт (201) |
| POST | `/{id}/occurrences/generate` | manager | Генератор: `start`, `every_months` 1–24, `count` 1–36; существующие даты пропускаются (идемпотентно), 201 |

Ошибки (`errors.http_error`): `ElevatorValidationError` → 422, `NotFound` → 404,
`Conflict`/`State` → 409, прочее → 500 без текста. Схемы — `Elevator*Out`/`Elevator*In`
(уникальный префикс против коллизий имён в OpenAPI); `lang` ∈ ru/uz для подписей.

> ⚠️ **Edge (InfraSafe, SEC-22):** префикс `/api/v2/elevators` **не заявлен** в allowlist
> ни на одной площадке. До включения флага на проде — запрос InfraSafe на ОБА хоста в форме
> `~^/uk/api/v2/elevators(/|$)`; иначе SPA/TWA получат HTML-404 nginx. Запись —
> `docs/audit/2026-06-07-infrasafe-edge-allowlist-contract.md`.

## 6. Интеграция с заявками

Четыре живых конструктора Request, общей фабрики нет — каждый вызывает единый резолвер Р11
(§4) и принимает `elevator_id`/`elevator_operational`:

| Конструктор | Каналы | Как |
|---|---|---|
| `services/request_handler_service.py` (sync) | бот жителя, бот инспектора, групповой приём, бот лифтёра (ремонт) | `resolve_request_elevator_sync` в `create_request_record`; ключи FSM `elevator_id`, `elevator_operational` читает `save_request_sync` |
| `api/requests/service.py` (async) | TWA, инспектор через API | `CreateRequestBody`/`CreateInspectorRequestBody` +2 поля, pydantic-валидатор «обязательны при elevator» + `resolve_request_elevator_async` в `persist_request` |
| `api/callcenter/service.py` (async, manager) | форма колл-центра, «Создать ремонт» из карточки лифта | `CallCenterCreateRequest` + `building_id` (адрес уровня дома, взаимоисключим с `apartment_id`), `acceptance_mode` (CHECK resident/manager), `elevator_id`, `elevator_operational` |
| `services/inbound_alert.py` (async) | InfraSafe-вебхук | `AlertBlock.uk_elevator_id: int|None` (Р14) = наш `elevators.id`; резолв: активен, введён, принадлежит зданию из `external_id`; `elevator_operational=false`. Категория `elevator` без пригодного поля → **422**, `webhook_inbox.outcome=rejected` с причиной в `error`; `event_id` занят — повтор даёт 409 duplicate, партнёр шлёт исправленный алерт с новым `event_id`. Пока InfraSafe не шлёт поле, лифтовые алерты невозможны по определению Р11 — ожидаемо |

`RequestCard` (`api/requests/schemas.py`) получил `elevator_id`, `elevator_label`
(«д. …, подъезд N, лифт M» на языке пользователя), `elevator_status`; заполняются одним
batch-запросом на страницу (`api/requests/elevator_fields.py`, без N+1), используются
роутерами заявок и колл-центра. Ремонт: заявка `category=elevator`, `acceptance_mode=manager`,
`elevator_operational=false`, адрес уровня дома; дальше — штатный автодиспетчер, назначение,
переназначение менеджером (особых правил нет, Р9).

## 7. Бот

| Поверхность | Файлы | Callback-префиксы | Поведение |
|---|---|---|---|
| Житель — шаг лифта при создании | `handlers/requests/create_elevator.py` (общие шаги, `ElevatorFlow`), `create_elevator_resident.py` (тонкие хендлеры под `RequestStates.elevator_pick/elevator_operational`), `keyboards/elevators.py` | `elv:pick:{id}`, `elv:op:1|0` | Для `category=elevator` при включённом флаге и известном доме: список введённых лифтов дома → «Лифт сейчас работает?». Ровно один пригодный лифт в доме или в подъезде квартиры жителя — автоподстановка. Двор — «укажите дом». Дом без лифтов — Р11 не обойти: телефон диспетчера (`board_config.contacts.dispatch_phone`) и возврат к категории. Статус «в ремонте»/«на ТО» — мягкая подсказка, не блокирует. Сервер проверяет принадлежность лифта дому (`ensure_elevator_usable_sync(building_id=…)`); `clear_elevator_data` снимает ключи при смене категории |
| Инспектор | `handlers/inspector_requests.py` (`InspectorRequestStates.elevator_pick/elevator_operational`, `INSPECTOR_FLOW`) | те же `elv:*` | Те же шаги после выбора категории; отличается ролью, клавиатурой категорий и отменой |
| Менеджер — подсказка после подтверждения | `handlers/admin/elevator_hint.py`, вызов из `admin/views.py` **после** try подтверждения | `elv:st:{elevator_id}:{status}:{номер}`, `elv:keep` | После `MANAGER_CONFIRM` заявки с `elevator_id`: «Лифт {label}: сейчас «{статус}». Лифт работает?» — четыре статуса + «Оставить как есть». Нажатие → `set_status_sync(source="request_hint", request_number)`; повтор статуса — no-op; жителям — после commit. Сбой подсказки не откатывает подтверждение |
| Групповой приём | `handlers/group_intake_elevator.py`, вклинивание в `group_intake.py` после «Да» автора | `gint:bld:{n}`, `gint:elv:{id}`, `gint:op:1|0` | Кандидат остаётся под тем же Redis-ключом промпта; фазы: `elevator_building` (адрес автора на уровне двора → выбор дома), `elevator_pick`, `elevator_operational`. Автоподстановка при единственном лифте в подъезде квартиры автора/в доме. Отвечает **только автор** (и в staff-группе). **Единый дедлайн 30 мин** (`ELEVATOR_ANSWER_TIMEOUT`): one-shot asyncio-таймер + Redis-TTL записи (остаток + `TTL_GRACE`=60 с, шаги окно не продлевают) + ленивая проверка `is_expired` на нажатии; истёк — промпт правится «заявка не оформлена», заявки нет |
| Лифтёр — меню «🛗 Лифты» | `handlers/elevators/` (`menu`, `card`, `status`, `repair`, `maintenance`, `_units`, `_keyboards`, `_texts`, `_router`), кнопка в `keyboards/base.py` для executor при флаге | `elvm:*` (`yards`, `yard:{id}`, `bld:{id}`, `card:{id}`, `st:{id}[:{status}]`, `noreason`, `rep:{id}`, `urg:{key}`, `repst:{id}:{номер}:1|0`, `occs:{id}`, `occ:{oid}:done`, `skip`, `cancel`) | RoleGate роутера по роли executor; специализация `elevator` (алиас `maintenance`) проверяется в каждом sync-юните (`_units.check_access`) — без неё внятный отказ, не тишина. Двор → дом → лифт → карточка (статус, доступность 30 дн., ближайшее ТО, открытые заявки). Смена статуса с причиной или «Без причины» → `set_status_sync(source="manual")` → жителям после commit → «X → Y (уведомлено: N)». Ремонт: описание (≥ мин. длины) → срочность → штатный `save_request` (`acceptance_mode=manager`, `elevator_operational=False`, адрес дома, роль `staff_group`) → предложение «Поставить лифту „В ремонте“?» (reason «ремонт {номер}», номер в журнале). Отметка ТО/освидетельствования: комментарий (или «Пропустить»); для освидетельствования — номер акта, срок ДД.ММ.ГГГГ, ссылка (опц., `validate_url`) → «Выполнено, следующее ТО: {дата}» |

Общее: DB-фаза — sync-юниты под `run_db` (гейт AUD3-37), наружу frozen-DTO; всё из БД
проходит `html.escape` (parse_mode=HTML); тексты доменных ошибок в чат не попадают —
вердикт маппится на ключ локали. Локали: `elevators.*` (bot, notify, …), `requests.elevator.*`,
`main_menu.elevators`, группа — в `group_intake.*`; RU + UZ.

## 8. Фронт

Роли `ELEVATORS_MODULE_ROLES = ['manager','executor']` (`constants/roles.ts`); конфиг —
только manager. Флаг читается функцией `isElevatorsEnabled()` (`utils/featureFlags.ts`,
переключаемо в тестах через `vi.stubEnv`).

- **Дашборд** (`App.tsx`, за `VITE_ELEVATORS_ENABLED`): `/dashboard/elevators` (реестр:
  `ElevatorsPage` — сводка по дворам `ElevatorSummaryCards`, фильтры дом/подъезд/статус/признаки,
  таблица), `/new` и `/:id/edit` (`ElevatorFormPage` — паспорт, «скопировать предыдущий»),
  `/:id` (`ElevatorDetailPage` — вкладки паспорт / статус с кнопками `StatusChangeDialog` /
  журнал / календарь `OccurrenceDialogs` / заявки с чекбоксами и «Подтвердить выбранные» →
  после bulk один раз `ElevatorStatusPromptDialog`; «Создать ремонт» `CreateRepairDialog`;
  архив `ArchiveDialog`), `/calendar` (`ElevatorsCalendarPage` — все лифты за период),
  `/config` (`ElevatorsConfigPage`, manager; маршрут объявлен отдельно, чтобы `config`
  ранжировался выше `:id`). Пункт меню — `DashboardLayout.tsx` (`nav.elevators`).
  Хуки `useElevators`, `useElevatorCalendar`, `useElevatorsConfig`; типы `types/elevators.ts`.
- **TWA** — `twa/components/ElevatorStep.tsx` в мастере `twa/pages/applicant/CreatePage.tsx`:
  список лифтов дома (`GET /for-building/{id}`) → выбор → «Лифт сейчас работает?».
  Автовыбор при единственном лифте дома (подъезд квартиры API не отдаёт). Без лифтов —
  только назад к категории (Р11). Мягкая подсказка при `under_repair`/`maintenance`.
  Черновик хранит `elevator`; при несовпадении с флагом — сброс шага.
- **Колл-центр** — `components/callcenter/CallCenterElevatorFields.tsx` в `CallCenterModal.tsx`:
  для категории «Лифт» каскад двор → дом из справочника (→ `building_id`), лифт дома,
  «работает?»; всё обязательно, иначе 422.
- **Канбан** — бейдж `🛗 {elevator_label}` с точкой статуса `ElevatorStatusDot` на
  `kanban/RequestCard.tsx` (только при включённом флаге); поля из `useKanban.ts`.
  Фильтров/группировки/мультивыбора на канбане нет (Р10).
- **Подсказка после подтверждения** — `components/elevators/ElevatorStatusPromptDialog.tsx`:
  четыре статуса + «Оставить как есть» → `PUT /{id}/status` с `reason` (`statusReason.ts`, ≤500)
  и `request_number` при одной заявке; тот же статус — «без изменений» без запроса.

## 9. Напоминания и уведомления

Джоба `elevator_reminders` в `utils/shift_scheduler.py` (контейнер бота, APScheduler в UTC):
`IntervalTrigger(hours=1)`, `max_instances=1`, `coalesce=True`; регистрируется **только при
`ELEVATORS_ENABLED`** (флаг читается один раз в `setup_jobs`, включение = рестарт бота);
ключ `task_stats['elevator_reminders']`. Тик: `asyncio.to_thread(_elevator_reminders_sync)` —
`collect_reminders_sync` + `apply_reminders_sync` в **одной транзакции**, commit, и лишь затем
рассылка `send_notify_messages` (best-effort; потеря допустима, дубль — нет, Р7). Все даты —
бизнес-дата `business_today` (`utils/business_time`), час запуска ни на что не влияет.

Пять видов (`services/elevator_service/reminders.py`):

1. ТО / освидетельствование по календарю — стадии `staff_reminders.maintenance` /
   `certification` (дефолт 30/14/7 дней) → менеджерам и лифтёрам;
2. просрочка пункта календаря — с 8-го дня, еженедельно → менеджерам и лифтёрам;
3. договор обслуживания (`contract_until`) — стадии до срока, после истечения (с 1-го дня)
   еженедельно «нет действующего договора» → менеджерам;
4. освидетельствование лифта (`cert_valid_until`) — как договор → менеджерам;
5. длительный простой — порог `downtime_threshold_days` по статусу (дефолт `not_working: 7`,
   `under_repair: null` = выключен), еженедельно → менеджерам.

`staff_reminders.overdue_weekly` гейтит **все** еженедельные напоминания о просроченном
(2, 3, 4 после истечения); простой (5) им не управляется. Лифтёры — executor со
специализацией `elevator` (алиас `maintenance`), `universal` не входит; адресаты дедуплицируются
по `telegram_id`. Тексты HTML-безопасны.

Конфиг `elevators_config.data` (дефолты `reminder_rules.DEFAULT_ELEVATORS_CONFIG`):
`module_public` (задел под QR), `downtime_threshold_days {not_working, under_repair}`,
`resident_notifications {repair_started, maintenance_started, back_in_service}`,
`staff_reminders {maintenance, certification, contract: [30,14,7]; overdue_weekly: true}`;
стадии — убывающий список дней ≤365.

Уведомления жителям подъезда (§4) — из `set_status` тремя каналами вызывающих сторон;
при «Не работает» рассылки нет.

**Multi-replica:** `max_instances=1` защищает от наложения тиков только внутри одного
процесса; вторая реплика бота даст дубли напоминаний (как и у всех джоб этого файла) —
при горизонтальном масштабировании нужен внешний лок (advisory lock / redis). Сейчас
бот — один процесс на площадку.

## 10. Флаги и деплой

- `ELEVATORS_ENABLED` (env, Doppler; `config/settings.py:301`, default false; в
  `docker-compose.yml` для `app` и `api` — `${ELEVATORS_ENABLED:-false}`): API → 404, джоба
  не регистрируется, кнопка «Лифты» и шаги выбора лифта в боте отсутствуют, резолвер Р11 не
  требует лифт, `uk_elevator_id` игнорируется. **Один флаг на бот и API** — задавать обоим
  сервисам одинаково.
- `VITE_ELEVATORS_ENABLED` (build-arg `frontend/Dockerfile`, compose `${VITE_ELEVATORS_ENABLED:-}`;
  пусто = OFF): меню, маршруты дашборда, шаг TWA, поля колл-центра, бейдж канбана.
  Фронт пересобирается отдельно (build-time).
- `elevators_config` — строка id=1 создаётся при первом сохранении из дашборда; до этого дефолты.

Порядок включения на площадке:

1. Заявить `/api/v2/elevators` в edge-allowlist **обеих** площадок (форма `(/|$)`), дождаться
   подтверждения, проверить curl'ом: до включения флага ожидается 404 **JSON** от приложения,
   не HTML nginx (§5).
2. `doppler run -- docker compose ... run --rm migrate` (`alembic upgrade head` → 016, 017),
   затем `up -d` api/app — рутина `.claude/skills/uk-deploy/SKILL.md` (migrate ДО up, иначе preflight).
3. `ELEVATORS_ENABLED=true` для `app` и `api` в Doppler, рестарт; проверить в логе бота
   регистрацию джобы (`setup_jobs`) и `task_stats['elevator_reminders']`.
4. Фронт: сборка с `VITE_ELEVATORS_ENABLED=true` (обе ветви бренда), деплой `uk-frontend`.
5. InfraSafe: чтобы лифтовые алерты создавали заявки, партнёр должен слать
   `alert.uk_elevator_id` = наш `elevators.id` (Р14); до этого алерты категории `elevator` →
   422 + `webhook_inbox.outcome=rejected` — штатно. Новый пункт контракта, InfraSafe ещё не
   уведомлён.
6. Наполнение: паспорта руками (Р13), ввод в эксплуатацию → статус → календарь.
   На 105 (infrasafe) флаг выключен до отдельного решения владельца.

## 11. Отложено (план §3, кратко)

Автостатус лифта от заявок (3.1; подготовлено `requests.elevator_id`/`elevator_operational`,
`source`/`request_number` в журнале; условие — метрика игнорирования подсказки + рефакторинг
«одна фабрика Request»), обходы (3.2), QR и публичная карточка (3.3; `public_code`, `is_public`,
`module_public` готовы; нужен публичный префикс и QR-библиотека), организации и договоры как
сущности (3.4), таблица актов освидетельствования (3.5), notification ledger (3.6), скрытые
служебные заявки (3.7), шаблоны планов ТО (3.8), автосвязь повторных сигналов InfraSafe (3.9),
аудит подъездов квартир (3.10; счётчик в карточке есть), жёсткая блокировка обращений при
ремонте (3.11), CSV-импорт паспортов (3.12), группировка/мультивыбор на канбане (3.13;
`bulk-confirm` готов), предпочтение создателя в автодиспетчере (3.14).

## 12. Тесты

- Модели/схема: `uk_management_bot/tests/test_elevator_models.py` (паритет CHECK с миграцией,
  RESTRICT); `tests/services/test_metadata_completeness.py` (+4 таблицы).
- Чистое ядро: `uk_management_bot/tests/services/elevator_service/test_{validation,availability,calendar_rules,reminder_rules,public_code}.py`.
- DB-слой (sqlite-conftest): `tests/services/test_elevator_service_{status,passport,calendar,reads,recipients,config,grouping}.py`,
  `test_elevator_reminders.py`, импорт-гейт `test_elevator_service_imports.py`.
- API: `tests/api/test_elevators_{registry,status_calendar,requests_config}.py`,
  `test_requests_elevator_required.py` (Р11 в TWA/инспекторе), `test_callcenter_elevator.py`,
  `test_inbound_alert_elevator.py` (422 + inbox), `test_residents_notify_plain.py`.
- Бот: `uk_management_bot/tests/handlers/test_elevator_request_flow.py`, `test_elevator_inspector_flow.py`,
  `test_elevator_hint_manager.py`, `test_group_intake_elevator.py`, `test_save_request_elevator.py`,
  `test_elevators_{menu,status,repair,maintenance}.py` (общий `elevators_harness.py`);
  джоба — `tests/utils/test_shift_scheduler.py::TestElevatorRemindersJob`, `test_shift_scheduler_offloading.py`.
- Фронт: `pages/elevators/*.test.tsx`, `hooks/useElevator*.test.ts`,
  `components/elevators/{ElevatorStatusPromptDialog,statusReason}.test.*`, `kanban/RequestCard.test.tsx`,
  `callcenter/CallCenterModal.test.tsx`, `twa/components/elevatorSelection.test.ts`,
  `twa/pages/applicant/CreatePage.test.tsx`; фикстуры `test/fixtures/elevators.ts`.
- Ратчеты, которых касается модуль: `test_handler_authz_ratchet`, `test_aud337_async_handlers_gate`
  (CONVERTED), `test_aud5_code10_long_functions_ratchet`, broad-except.

Локальные особенности (не дефекты): эталон — `make test-ci`. Локальный `.venv` несёт
alembic 1.16.x при пине 1.18.4 в `requirements.txt` — расхождения в выводе/предупреждениях
`alembic check` считать шумом окружения. На Python 3.13 старые тесты `test_shift_scheduler.py`
с `asyncio.get_event_loop().run_until_complete(...)` без текущего loop падают `RuntimeError` —
это окружение, не модуль; новые тесты лифтов гоняются через `asyncio.run`. OpenAPI-снапшот
`docs/tech/openapi.json` регенерировать только из CI-образа (пин pydantic).

## 13. Эксплуатационные заметки

- «Лифт не показывается жителю / нет в `for-building`» — лифт не введён в эксплуатацию
  (`is_commissioned=false`, статус NULL) или архивирован. Ввод — `POST /{id}/commission`.
- Житель не получил уведомление о ремонте/ТО — проверить `apartments.entrance` его квартиры
  (NULL → не адресат, Р8), статус привязки `approved`, `bot_blocked_at`; счётчик «квартир
  подъезда без данных о подъезде» есть в карточке лифта.
- InfraSafe-алерт по лифту отвергнут — `webhook_inbox.outcome=rejected`, причина в `error`
  (`elevator: …`); повтор того же `event_id` → 409; партнёр шлёт новый `event_id`.
- Напоминание не пришло — джоба есть только при флаге; смотреть `task_stats['elevator_reminders']`
  и стадии на сущности (`*_reminder_stage` в днях, `*_reminded_at`); смена даты сбрасывает стадию,
  повторной отправки уже пройденной стадии не будет (идемпотентность по дизайну).
- Статус лифта «устарел» — автостатуса нет по решению Р2; источник правды — журнал
  (`source`, `actor_user_id`, `request_number`). Метрика для триггера возврата 3.1 — доля
  заявок с лифтом, подтверждённых без ответа на подсказку.
- Любой executor с ролью может сменить статус через API (специализация не проверяется) —
  принято осознанно (план §12 P1.4), актор виден в журнале.
- Удаление лифта невозможно при наличии журнала/календаря (RESTRICT) — только архив.

## 14. Связанные документы

- План v2.3 с журналом решений: `~/.claude/plans/stateless-crunching-sundae.md`.
- Модуль-образец: `docs/MATERIALS_MODULE.md`; закрытый вопрос №2 реестра объектов — `docs/ASSETS_MODULE.md` §10.
- Схема БД: `docs/tech/DATA_MODEL.md` §3, §6, §7a.
- Edge-allowlist: `docs/audit/2026-06-07-infrasafe-edge-allowlist-contract.md`.
- Деплой/миграции: `.claude/skills/uk-deploy/SKILL.md`.
