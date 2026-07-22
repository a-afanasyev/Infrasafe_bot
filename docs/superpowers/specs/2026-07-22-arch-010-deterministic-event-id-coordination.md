# ARCH-010 — детерминированный outbox `event_id`: координационный спек с InfraSafe

> **Статус:** ✅ **ЗАКРЫТ ЦЕЛИКОМ 2026-07-23.** Координация закрыта 2026-07-22; реализация —
> PR #247 (squash `1b5af6a`) по плану `docs/superpowers/plans/2026-07-22-arch-010-deterministic-event-id.md`
> (тест-план §7 покрыт, CI зелёный); **раскатан на ОБА прода 2026-07-23** (миграция 0004,
> `OUTBOX_SOURCE_INSTANCE` per-host из Doppler, прод-верификация: change-gate/UUIDv5/доставка 200).
> Ответы InfraSafe по 4 вопросам получены и сверены по коду (§6, A1–A5 — всё совместимо);
> retry-семантика решена (вариант A) и **InfraSafe задеплоил правку `isDuplicateEvent` на ОБЕ
> инсталляции 22.07** (§6a).
> **Тип:** design / coordination spec. **Backlog:** `docs/audit/2026-05-20-backlog.md` → ARCH-010 (закрыт).

## 0. TL;DR

Сделать `event_id` исходящих вебхуков UK→InfraSafe **детерминированным** (UUIDv5 от логической
идентичности события) вместо `uuid.uuid4()` per-call. Это оптимизация (дешевле/устойчивее дедуп у
получателя + локальная защита от дубль-emit), **не** bugfix — корректность сегодня обеспечена
InfraSafe-дедупом. Наивный backlog-«fix» (`sha256(event:entity_id:updated_at)`) архитектурно
неверен; ниже — корректная схема с обработкой reconcile-repair, конкурентности, реактивации и
кросс-инстанс-коллизий. Реализацию блокируют 4 вопроса к InfraSafe (§6).

## 1. Проблема и почему наивный fix неверен

`event_id` генерится как `str(uuid.uuid4())` в трёх местах, все через единый funnel
`_build_outbox_record` (`uk_management_bot/services/webhook_sender.py:42/59/114`, funnel `:101-126`).
Backlog предлагал `event_id = sha256(f"{event}:{entity_id}:{entity_updated_at}")[:32]`. Разбор по
коду показал, что это неверно:

- **Retry одной строки уже идемпотентен.** `process_outbox` (`webhook_sender.py:262-437`) ретраит
  **ту же строку** outbox; строка идентифицируется по PK `id` + `claim_token`, не по `event_id`.
  Новый id при ретрае/reclaim не минтуется — идемпотентность повторной доставки уже есть.
- **Повторный логический enqueue возможен НЕ только в reconcile.** `update_building`
  (`services/addresses/core.py:223-251`) **безусловно** эмитит `building.updated` после слепого
  `setattr`-цикла (`:240-241`) — даже если PATCH записал те же значения; двойной клик / дубль-хендлер
  тоже даёт второй `queue_webhook`. Такие пары получают **разные** UUID4, и дедуп InfraSafe по
  `event_id` их дублем не распознаёт. **Но подтверждённых correctness-инцидентов нет.**
- **`updated_at` — плохой прокси версии.** `onupdate=func.now()` без `server_default`
  (`request.py:107`, `building.py:33`) → NULL до первого UPDATE, и бампается любым edit
  (urgency/notes), не только сменой статуса.
- **Reconcile-repair требует свежего id** (см. §4) — детерминированный id, совпавший с оригиналом,
  InfraSafe отбросил бы `isDuplicateEvent`, а наш `unique`-индекс/`ON CONFLICT` заглушил бы ремонт.

**Две выгоды детерминизма:**
1. **Receiver-side** — InfraSafe дедупит `event_id` дешевле и устойчивее (внешняя выгода, §6).
2. **Sender-side** — `ON CONFLICT DO NOTHING` на детерминированном id гасит дубль-emit локально
   (double-click / дубль-хендлер / безусловный `building.updated`), без участия InfraSafe (§5).

## 2. Схема `event_id` — UUIDv5

`event_id = str(uuid.uuid5(NS_ARCH010, name))`. UUIDv5 даёт **36-символьный детерминированный
UUID** → влезает в существующий `WebhookOutbox.event_id String(36)` (`database/models/webhook_outbox.py:11`),
остаётся UUID-форматом (вероятно, ноль изменений формата у InfraSafe). Вариант `sha256[:32]`
отвергнут — теряет UUID-форму без выигрыша.

**Namespace-константа (не секрет), валидный UUID:**
```python
NS_ARCH010 = uuid.UUID("a7f3c1e2-4b6d-4e8a-9c0f-1d2e3f4a5b6c")
```
Замороженная константа в `webhook_sender.py`, **одинаковая на всех окружениях
(profk/infrasafe/dev/тесты) и навсегда** — её ротация сменила бы все будущие id и сломала дедуп.
При реализации прогнать `uuid.UUID(...)` на литерале для гарантии валидности.

**`name` по типам события** (без `source_instance`-префикса — он слева при глобальном дедупе, ниже):

| Событие | `name` | Комментарий |
|---|---|---|
| `building.created` | `f"building.created:{building_id}"` | one-shot |
| `building.updated` | `f"building.updated:{building_id}:{building_version}"` | версия — не timestamp (§3) |
| `building.deleted` | `f"building.deleted:{building_id}:{building_version}"` | **НЕ one-shot** (реактивация → delete снова) |
| `request.created` | `f"request.created:{request_number}"` | one-shot |
| `request.status_changed` | `f"request.status_changed:{request_number}:{status_version}"` | версия статуса (§3) |

`updated_at.isoformat()` для building отвергнут: фрагилен из-за порядка flush/refresh
(`core.py:242` flush до `enqueue_outbox` :246, `db.refresh` только на :248) и требует datetime-safe
прокидки. `building.deleted` **не** one-shot: `update_building` умеет реактивировать soft-deleted
здание (`is_active=True`), значит цикл delete→reactivate→delete даёт второе реальное удаление; без
версии их id совпал бы и `ON CONFLICT` поглотил бы второе.

### 2.1 Cross-instance коллизия + общее UNIQUE-пространство (ответ InfraSafe получен)

profk и infrasafe — **независимые прод-инсталляции** с пересекающимися локальными id.
**Ответ InfraSafe (2026-07-22, verified по их коду):** дедуп — `integration_log.event_id UUID
UNIQUE` на всю таблицу, **без scoping** ни по отправителю, ни по направлению; в том же UNIQUE-
пространстве живут и **их исходящие** детерминированные `event_id` (`to_uk`-строки). Инсталляции
физически разделены (отдельные БД/`integration_log`/секрет), отправитель различается endpoint'ом+
секретом инсталляции — кросс-инсталляционная коллизия в текущей топологии не материализуется, но
рекомендация подтверждена. Требования к нашей схеме:
- **Включать `source_instance` в UUIDv5-name** (защита от будущей консолидации/миграции баз):
  `f"{source_instance}:{event}:{entity_key}:{version}"`. Настройки в проекте сейчас НЕТ
  (`grep source_instance/OUTBOX_SOURCE` — пусто) → ввести **новую обязательную** настройку
  `OUTBOX_SOURCE_INSTANCE=profk|infrasafe` (Doppler per-config, `:?`-гард, стабильная навсегда).
- **Использовать СОБСТВЕННЫЙ namespace-UUID** (`NS_ARCH010`, §2), не выведенный из значений
  InfraSafe — чтобы наши детерминированные `event_id` структурно не пересеклись с их исходящими
  детерминированными id в общем UNIQUE-пространстве таблицы. Наш `NS_ARCH010` — произвольная
  фиксированная константа, это требование уже выполняется; зафиксировать явно.

**Инвариант данных.** Identity-метаданные (`version` / repair-nonce / `source_instance`)
прокидываются **отдельными аргументами функций** (§3b), а НЕ кладутся в shared `data`-dict — тот
идёт и в Redis `publish_building_event` (`services/redis_pubsub.py:78` — bare `json.dumps` без
`default=`; сырой `datetime`/нескаляр → TypeError, проглотится `try/except` → тихо сломает
фронт-путь). `data` остаётся чистым JSON-скаляром для wire + Redis.

## 3. Версии сущностей — миграция, change-gate, конкурентность

Fork «чем версионировать building.updated» разрешён в пользу **целочисленных версий, не timestamp**
(надёжнее, симметрично со статусом, без flush/refresh-фрагильности).

- **`Request.status_version INTEGER NOT NULL DEFAULT 0`** — инкремент **только при реальной смене
  статуса**, в обеих ветвях executor'а **до** создания webhook: `_apply_sync`
  (`services/workflow_runner.py:226-241`) и `_apply_async` (`:375-390`). Гейт уже есть — оба
  `_apply_*` рано выходят на `result.no_op`, так что same→same статус не эмитит и не бампает
  (reconcile зовёт emit напрямую по repair-пути, §4). NB: `workflow_runner.py:169` — лишь сборка
  `CommandOutcome`, НЕ точка мутации; инкремент туда НЕ ставить.
- **`Building.building_version INTEGER NOT NULL DEFAULT 0`** — инкремент **только если реально
  что-то изменилось**:
  - **change-gate в `update_building` (P1-A):** сейчас слепой `setattr`-цикл (`core.py:240-241`)
    эмитит всегда. Требуется: сравнить старые/новые значения затронутых полей до записи; если ни
    одно не изменилось — **не** бампать версию и **не** эмитить `building.updated`.
  - **no-op в `delete_building` (P1-C):** `core.py:263` сейчас безусловно ставит `is_active=False`
    и эмитит; требуется ранний выход, если здание уже `is_active=False` (без bump/emit). Реактивация
    (`update_building` c `is_active=True`) — реальное изменение → `building.updated` с новой версией.
  - `create_building` оставляет 0.
- **Конкурентность — сериализовать всю мутацию, не только счётчик (P1-B).** Атомарного
  `UPDATE ... version=version+1 RETURNING` НЕ достаточно: business-поля всё равно меняются на
  ORM-объекте, загруженном обычным `db.get` (`_get_building_or_raise`, `core.py:49-53`) — два
  конкурентных апдейта получат разные версии, но payload второго может нести stale-поля первого
  (lost-update по данным). Поэтому — **`SELECT ... FOR UPDATE` как основной вариант для здания**:
  под локом строки dirty-check → мутация полей → bump версии → flush → построение payload (весь путь
  `update_building`/`delete_building` внутри лока; реализация — `_get_building_or_raise(...,
  for_update=True)` или отдельный lock-хелпер). **Для Request отдельный лок НЕ нужен — он уже есть:**
  executor грузит `req` через `.with_for_update()` (`workflow_runner.py:299` sync, `:442` async),
  in-place `status_version += 1` на залоченном объекте безопасен.
- **Alembic-миграция:** две колонки `nullable → backfill 0 → NOT NULL DEFAULT 0`.

### 3b. Контракт передачи identity — отдельные аргументы + fail-loud

Единственный способ прокидки — **явные аргументы функций** через всю цепочку (не `data`-dict).
Ввести неизменяемый носитель:
```python
@dataclass(frozen=True)
class EventIdentity:
    version: int | None = None
    repair_run_id: str | None = None
    # source_instance берётся из настройки внутри builder'а, не прокидывается зовущими
```

**Изменения сигнатур (весь путь):**
- `enqueue_outbox(db, *, event, data, identity)` — `services/addresses/events.py:47`
- `queue_webhook(db, event, endpoint, data, identity)` /
  `queue_webhook_sync(session, event, endpoint, data, identity)` — `webhook_sender.py:129/136`
- `_build_outbox_record(event, endpoint, data, identity)` — `webhook_sender.py:101` (единый funnel)
- `build_building_payload(event, data, identity)` / `build_request_payload(event, data, identity)`
  — `webhook_sender.py:32/56` (строят `name` из `identity`)
- `emit_request_status_changed(_sync)(..., identity)` — `services/webhook_payloads.py:63-80`;
  эмиттеры создания (`emit_request_created*`) — `identity=None` (one-shot).

**Fail-loud валидация в единой точке (`_build_outbox_record`):**
- versioned-события (`building.updated`, `building.deleted`, `request.status_changed`) требуют
  **ровно одно** из `version` / `repair_run_id`;
- одновременно `version` И `repair_run_id` → **raise**;
- отсутствие **обоих** для versioned-события → **raise** (не тихий uuid-фолбэк);
- one-shot (`building.created`, `request.created`) — `identity` без version/repair (или `None`).

## 4. Repair-bypass — оба reconcile-пути

Reconcile переотправляет событие, когда InfraSafe **потерял** сущность (`reconcile_buildings`
`services/reconciliation.py:126-150`; `reconcile_requests` `:254-260`) — ремонт **обязан обойти**
дедуп, иначе `isDuplicateEvent` его отбросит и потеря не восстановится.

- **`reconcile_run_id`** — `uuid4().hex`, генерится **один на весь запуск** reconcile (не на entity),
  в начале `reconcile_buildings`/`reconcile_requests`; общий для всех строк цикла запуска.
- **Nonce в `name`:** repair-путь → `f"{event}:{entity_key}:repair:{reconcile_run_id}"`. Разный
  `event_id` ⇒ InfraSafe естественно не считает дублем, и наш `unique`/`ON CONFLICT` не глушат
  ремонт. Разные запуски дают разные repair-id — ОК (ремонты редки, сознательный opt-out дедупа).
- **Точки прокидки (через `identity`, §3b — НЕ через `data`):**
  - building: `reconcile_buildings` (`reconciliation.py:138`) →
    `queue_webhook(db, "building.created", endpoint, data, EventIdentity(repair_run_id=run_id))`.
  - request: `reconcile_requests` (`reconciliation.py:257-259`) →
    `emit_request_status_changed(db, rn, projected, projected, "reconcile", EventIdentity(repair_run_id=run_id))`
    (обычный позиционный/kw-аргумент; `*` в вызове НЕ пишется — это синтаксис только в определении).
- **`repair: true` — фиксированно top-level** в payload (не внутри `building`-объекта), для обоих
  событий, единообразно для InfraSafe-парсера. Семантический сигнал (аудит/метрики «это ремонт»);
  механически bypass делает nonce. Просим InfraSafe принять поле, НЕ требуем менять `isDuplicateEvent`.

## 5. Наша сторона — `ON CONFLICT DO NOTHING` + окно локального дедупа

Детерминированный id делает дубль-emit безопасным: вместо `IntegrityError` — no-op. Заменить
`db.add(_build_outbox_record(...))` (`webhook_sender.py:133` async / `:154` sync) на dialect-aware
upsert `INSERT ... ON CONFLICT (event_id) DO NOTHING`.

- **Кросс-диалект helper:** Postgres (`postgresql.insert().on_conflict_do_nothing`) и SQLite
  (`sqlite.insert().on_conflict_do_nothing`, поддержан текущим SQLAlchemy), ветвление по
  `session.bind.dialect.name` — иначе SQLite-тесты (`tests/api/test_webhook_outbox_concurrency.py`,
  `test_webhook_outbox_pg_concurrency.py`) упадут.
- **Окно локальной защиты ограничено retention'ом — но приёмная сторона держит бессрочно.**
  `purge_old_sent_outbox` (`services/outbox_retention.py:21`, `DEFAULT_RETENTION_DAYS=30`) удаляет
  наши `sent`-строки старше 30 дней; после purge наш `unique`-индекс повтор нормального события уже
  не глушит. **Но это безопасно:** InfraSafe дедупит `event_id` **бессрочно** (§6 A1 — существование
  строки в `integration_log`, ретеншна нет) → повтор нормального события отбрасывается у них навсегда.
  Наша 30-дневная очистка при таком поведении безопасна. Repair сюда не относится — у него свежий
  nonce, он намеренно НЕ дедупится (§4).

## 6. Вопросы к InfraSafe — ОТВЕТЫ ПОЛУЧЕНЫ (2026-07-22, verified по коду приёмной стороны)

Ответы сверены InfraSafe по `webhookRoutes.js` / `webhookVerifier.js` / `webhookValidation.js` /
`integration_log` + миграция 011.

- **A1. TTL/окно дедупа — БЕССРОЧНО (сегодня).** `isDuplicateEvent` = существование строки в
  `integration_log` (`SELECT ... WHERE event_id=$1`, `webhookVerifier.js:219`); ретеншна таблицы нет
  нигде → повтор того же `event_id` вечно получает `200 {"message":"Already processed"}` без
  обработки. Упомянутые «600с» — другой механизм (replay-защита HMAC-подписи, nonce TTL 310с при
  окне таймстампа 300с), не про `event_id`. **Оговорка:** «бессрочно» — свойство реализации, не
  контракт; при желании впишем гарантию (напр. «дедуп ≥ 90 дней»). Наша 30-дневная очистка `sent`
  безопасна (§5).
- **A2. Формат UUIDv5 — ДА, без изменений.** Валидация version-agnostic (regex
  `webhookValidation.js:3` не проверяет version/variant-биты; колонка `event_id UUID` принимает любую
  версию). Переход uuid4→uuid5 прозрачен.
- **A3. `repair: true` — ДА, примут.** Strict-schema нет, лишние top-level поля не отвергаются; весь
  body пишется в `integration_log.payload` (JSONB) → `repair:true` авто-виден в их аудите (спец-
  фильтра в UI нет, но в payload есть). **Важно:** давать ремонтам НОВЫЙ `event_id` — **обязательно**
  (не опционально): при бессрочном дедупе (A1) повтор старого id всегда будет отброшен. Наш
  repair-nonce (§4) это и обеспечивает.
- **A4. Дедуп глобальный в пределах инсталляции; инсталляции физически разделены.** `event_id UUID
  UNIQUE` на всю таблицу, без scoping по отправителю/направлению (в т.ч. пересекается с их исходящими
  детерминированными id). profk/infrasafe — раздельные БД → кросс-коллизия сейчас невозможна, но
  рекомендации подтверждены и учтены в §2.1: (а) включить `source_instance` в UUIDv5-name;
  (б) использовать СВОЙ namespace-UUID.
- **A5. Менять `isDuplicateEvent` НЕ требуется** для bypass — обеспечиваем nonce'ом. (Но см. §6a —
  отдельный вопрос про retry-семантику, где правка `isDuplicateEvent` — один из вариантов.)

## 6a. ⚠️ Retry-семантика после 5xx InfraSafe — вариант A, ✅ ЗАДЕПЛОЕН InfraSafe 2026-07-22

InfraSafe приём — **insert-first**: строка в `integration_log` с `event_id` вставляется ДО
обработки; при падении обработки строка остаётся `status=error`, нам возвращается 500. Дедуп
проверяет **существование** строки, не её статус.

**Уточнение по нашему коду (verified `webhook_sender.py:392-407`):** наш outbox-worker ретраит **ту
же строку** с **тем же `event_id`** уже СЕГОДНЯ (регенерации id на ретрае нет — меняются лишь
`attempts`/`retry_after`/`status`). Значит характеристика InfraSafe «сегодня ретрай приходит с новым
id и переобрабатывается» **неверна для worker-retry пути**: наш ретрай после их 500 уже сегодня
получает `Already processed`, а событие застревает `status=error` до repair. Т.е. дыра
**пре-существующая**, ARCH-010 её не создаёт — лишь делает «тот же id» универсальным.

**✅ ВЫБРАН вариант A (владелец, 2026-07-22): InfraSafe правит `isDuplicateEvent` — пропускать строки
`status=error`.** Ретрай с тем же id после 5xx → переобработка. Чинит и пре-существующий баг (наш
worker уже сегодня ретраит тем же id, поэтому их insert-first уже сегодня стрендит упавшие события),
восстанавливает self-healing. Repair остаётся второй линией защиты. Вариант B (полагаться только на
почасовую сверку — и только если её детект по фактическому состоянию сущности, а не по
`integration_log`) отклонён: оставляет пре-существующий баг и даёт медленное восстановление.

**✅ Сиквенсинг выполнен — InfraSafe задеплоил вариант A на ОБЕ инсталляции (profk + infrasafe)
2026-07-22; внешний гейт снят.** Подтверждённое поведение приёма: повтор с тем же `event_id` после
их 5xx — событие в статусе «обработано/в обработке» → по-прежнему `200 Already processed`; событие,
на котором они упали → **атомарно переоткрывается и обрабатывается заново** (конкурентные повторы
безопасны — выигрывает ровно одна доставка). Наша retry-политика снова «лечит» их transient-сбои,
как было при случайных id. **Следствие для нас:** при 5xx — просто ретраить тем же `event_id`
(наш worker это уже делает, `webhook_sender.py:392-407`); repair (§4) остаётся только для
**потерянных сущностей**, для transient-ошибок больше не нужен.

**Мелочь (уже соблюдаем):** окно таймстампа подписи — 300с, переподписывать в момент отправки на
каждом ретрае (`send_webhook` уже так делает).

**Опция верификации перед cutover:** InfraSafe предложил синтетик-прогон (повтор после искусственной
500) на одной из инсталляций — организуют по запросу перед нашим переключением.

## 7. Тест-план реализации (для будущего тикета)

- Перевернуть 2 теста уникальности в `uk_management_bot/tests/services/test_webhook_sender.py`:
  `test_event_id_is_unique_per_call` (:94-97), `test_event_id_is_unique` (:465-468) — при идентичном
  входе id теперь **равны** (кроме repair-пути).
- `tests/services/test_webhook_sender_sync.py` сломается на переходе `db.add`→`execute(upsert)`:
  `_capture_async_record` (:192-196) ассертит `db.add.assert_called_once()` через `MagicMock` —
  переписать capture на upsert-совместимый (перехват `execute`/реальная сессия).
- Новый: одинаковый `(event, entity_id, version)` → одинаковый id; смена
  `status_version`/`building_version` → разный.
- Новый: reconcile-repair id ≠ оригиналу (nonce), для building **и** request.
- Новый: sync/async parity инкремента `status_version` (`_apply_sync` vs `_apply_async`).
- Новый (change-gate): PATCH `update_building` теми же значениями → версия НЕ бампается,
  `building.updated` НЕ эмитится; PATCH с реальным изменением → бамп + emit.
- Новый (delete no-op): `delete_building` уже-неактивного → без bump/emit; цикл
  delete→reactivate→delete даёт два разных `building.deleted` id (через версию).
- Новый (concurrent): два конкурентных `update_building` одной сущности под `SELECT ... FOR UPDATE`:
  разные версии, разные `event_id`, обе строки в outbox, и **payload второго несёт свои поля, не
  stale-поля первого**. Аналогично для status-перехода (лок уже есть). Прогон под Postgres-харнессом.
- Новый (cross-instance): один `entity_key`+версия на двух `source_instance` → разные id.
- `ON CONFLICT`-helper: двойной insert одного id → одна строка, без исключения; SQLite и (где есть)
  Postgres (`test_webhook_outbox_pg_concurrency.py`).
- Redis-регресс: версия/datetime не утекают сырьём в shared `data` (`services/addresses/payloads.py:13-24`).

## 8. Опорные ссылки на код (verified 2026-07-22)

- Генерация id: `services/webhook_sender.py:42,59,114`; funnel `_build_outbox_record` `:101-126`.
- Insert-путь: `webhook_sender.py:129-133` (async), `:136-154` (sync) — оба `db.add`.
- Delivery worker: `webhook_sender.py:262-437` (ключ PK `id`+`claim_token`, не event_id).
- Модель: `database/models/webhook_outbox.py:11` (`String(36), unique=True, index`).
- Повторный emit: `services/addresses/core.py:223-251` (update безусловен), `:254-269` (delete).
- Reconcile: `services/reconciliation.py:126-150` (building), `:254-260` (request), `:128` (контракт).
- Статус-переход/эмиссия: `services/workflow_runner.py:226-241` (`_apply_sync`), `:375-390`
  (`_apply_async`), `:299`/`:442` (`with_for_update`); НЕ `:169`. Emit — `services/webhook_payloads.py:63-80`.
- Redis: `services/redis_pubsub.py:70-81`; shared builder `services/addresses/payloads.py:13-24`.
- Retention: `services/outbox_retention.py:18,21` (30 дней).
- Модели: `database/models/request.py:107`, `database/models/building.py:33`.
- Контракт/дедуп: `docs/audit/verifier-logs/OPS-112.md:48`,
  `docs/audit/2026-05-22-FIX-007-infrasafe-operator-handoff.md:68-72,79,129`.
- Тесты: `uk_management_bot/tests/services/test_webhook_sender.py:94-97,465-468`;
  `tests/services/test_webhook_sender_sync.py:178-196`;
  `tests/api/test_webhook_outbox_concurrency.py`, `test_webhook_outbox_pg_concurrency.py`.

## 9. Оценка

**НЕ 1 час** (историческая backlog-оценка описывала отвергнутый однострочный `sha256`-fix). После
разблокировки InfraSafe — реалистично **~несколько дней**: миграция двух колонок + change-gate +
FOR UPDATE-сериализация + `EventIdentity`-контракт (смена сигнатур всей цепочки + fail-loud) +
repair-nonce в двух reconcile-путях + dialect-aware `ON CONFLICT`-helper + перевёрнутые/новые/
parity/concurrent/cross-instance-тесты (вкл. переписанный `test_webhook_sender_sync`) + раскатка на
оба хоста. Гейтится §6.
