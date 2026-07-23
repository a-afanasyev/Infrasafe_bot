# TZ-хаос смен (AUD5-CODE-3 / AUD5-CODE-2 / AUD5-APIFE-4) — план реализации

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.
> При старте исполнения скопировать этот файл в `docs/superpowers/plans/2026-07-23-tz-aware-shift-domain.md` (конвенция репо).

**Goal:** Устранить naive datetime в **8 выбранных файлах** shift-домена (хирургический scope, не «канон навсегда»): aware-запись/сравнение во всех сайтах, schema-level нормализация naive-входа в API, AST-регресс-гейт на эти 8 файлов.

**Architecture:** Новый хелпер `uk_management_bot/utils/datetime_utils.py:utc_now()` (удобство, НЕ обязательный канон: inline `datetime.now(timezone.utc)` остаётся разрешён гейтом — существующие aware-сайты `shift_service.py:87,129,175` не трогаем) → механический свип бот-слоя с удалением `.replace(tzinfo=None)`-обходов и naive `datetime.combine`; `field_validator` на `CreateShiftBody`/`UpdateShiftBody` (naive→UTC coerce, как сейчас делает только PATCH) + удаление дублирующего блока из роутера (`schemas.py`/`router.py` в AST-гейт НЕ входят — там нет naive-`now`-паттерна). Без миграций (колонки уже `timestamptz`), без env/compose-изменений. Один PR.

**Tech Stack:** Python 3.11, aiogram 3, FastAPI/pydantic v2, pytest (sqlite + контейнер).

---

## Context

- **Зачем:** самый «баговый» из оставшихся P2-кластеров. Пользовательский симптом AUD5-CODE-2: `get_shift_stats` (`services/shift_service.py:251`) вычитает aware `start_time` из naive `now` → TypeError → глотается `except` (`:257`) → статистика = тихие нули. AUD5-CODE-3: naive-записи в `timestamptz` (`my_shifts.py:470,523`; `shifts.py:380`) и naive-сравнения в запросах. AUD5-APIFE-4: POST создаёт смену из naive datetime как есть, PATCH нормализует (`router.py:873-877`) → рассинхрон; на sqlite-тестах невидимо, на PG/asyncpg naive-параметр против timestamptz ломается/съезжает.
- **Решения владельца (2026-07-23):** расширенные сайты `shift_management/*` — ВКЛЮЧИТЬ; `utils/shifts.py:is_on_shift_now_*` — ОТЛОЖИТЬ (naive там осознанный, docstring; claim-семантика — отдельное решение; файл в AST-гейт НЕ вносить).
- Все datetime-колонки Shift — `DateTime(timezone=True)` (`database/models/shift.py:17-18,28-29,74-75`; baseline 0001 подтверждает timestamptz). API-слой уже везде на `datetime.now(timezone.utc)`. Хелпера `utc_now()` в репо нет — создаём. Образец фикса — QA-04 в `shift_scheduler.py:367-370`.
- **⚠️ Код и тесты BAKED в образы** — rebuild `docker compose build app && docker compose up -d app` перед КАЖДЫМ прогоном тестов (и RED, и GREEN).
- **Правила репо:** тесты бота только в контейнере; никаких коммитов/пушей без явной команды владельца; staging выборочный (`git status` до ветки, в репо есть посторонний untracked WIP: `ProFK/`, `.agents/`, `.codex/` и пр.).

## Инвентарь naive-сайтов (verified 2026-07-23)

| Файл | Сайты | Класс |
|---|---|---|
| `services/shift_service.py` | `:227` naive `now` для period-фильтра `start_time >=`, `:229` naive midnight, `:251` арифметика в stats (TypeError→нули) | сравнение/арифметика |
| `handlers/my_shifts.py` | `:470` запись `start_time`, `:523` запись `end_time`, `:531` duration c `.replace(tzinfo=None)` (+ложный коммент `:527-529`) | ЗАПИСЬ в БД + арифметика |
| `handlers/shifts.py` | `:380` запись `end_time`, `:151` duration с ДВОЙНЫМ `.replace(tzinfo=None)`, `:210` с одинарным; function-local `from datetime import datetime` в `:144/201/362` | ЗАПИСЬ + арифметика |
| `utils/shift_scheduler.py` | `:417` naive `now` в `between()` (_auto_assign_empty_shifts), `:326` cleanup cutoff (ShiftTransfer), 14× `task_stats[...]['last_run']` (in-memory, косметика — свипнуть для нулевого baseline гейта) | сравнение |
| `handlers/shift_management/assignment_a.py` | `:33,112,114,187,237,384` — range/day-window запросы | сравнение |
| `handlers/shift_management/assignment_b.py` | `:37,105,181,249` — day-window (`replace(hour=0,...)`); **`:375` naive `datetime.combine(shift_date, datetime.min.time())` → уходит в запрос `Shift.start_time` через `count_shifts_for_user_on_day` (`services/shift_management_service.py:245`)** | сравнение |
| `handlers/shift_management/analytics.py` | `:59` | сравнение |
| `handlers/shift_management/manual_planning.py` | `:228` strftime — display-only, свип для единообразия | display |
| `api/shifts/schemas.py` | `CreateShiftBody:145-159` / `UpdateShiftBody:162-171` — bare `datetime`, 0 field_validator'ов | вход API |
| `api/shifts/router.py` | `:873-877` — PATCH-coerce блок (станет мёртвым → удалить) | вход API |

**НЕ трогать:** `utils/shifts.py:50,57` (`is_on_shift_now_*` — отложено решением владельца); `shift_scheduler.py:370` QA-04-сайт уже aware (можно унифицировать на `utc_now()`, коммент QA-04 сохранить); `api/shifts/service.py` и весь API-слой (уже aware); from-template путь (строит aware UTC).

---

### Task 0: Подготовка + TZ-sanity

- [ ] **0.1** `git status` — зафиксировать посторонний untracked/modified; в ветку не включать.
- [ ] **0.2** TZ-проверка контейнера (обосновывает «поведение не меняется» для midnight/display-сайтов):
  ```bash
  docker exec uk-management-bot date +%Z
  docker exec uk-management-bot python -c "from datetime import datetime,timezone; print(datetime.now(), datetime.now(timezone.utc))"
  ```
  Плюс проверка **timezone DB-сессии** (naive-записи интерпретируются именно ею, не TZ контейнера):
  ```bash
  docker exec uk-management-bot python -c \
    "from sqlalchemy import text; from uk_management_bot.database.session import SessionLocal; \
     db = SessionLocal(); print(db.execute(text('SHOW timezone')).scalar()); db.close()"
  ```
  Ожидаемо UTC в обоих (расхождение wall-clock ≈ 0). Если НЕ UTC — **стоп, доложить владельцу**: исторические naive-записи скошены, нужна оценка данных до смены семантики записи.
- [ ] **0.3** `git checkout -b tz-aware-shift-domain` от актуального `main`.

### Task 1: Хелпер `utc_now()` + AST-гейт (+ shift_service = AUD5-CODE-2)

Task 1 — один checkpoint (гейт стартует RED на shift_service и зеленеет фиксом).

**Files:** Create: `uk_management_bot/utils/datetime_utils.py`, `tests/services/test_shift_tz_inventory.py`; Modify: `uk_management_bot/services/shift_service.py`; Test: `uk_management_bot/tests/services/test_shift_service.py`.

- [ ] **1.1** `datetime_utils.py`: `def utc_now() -> datetime: return datetime.now(timezone.utc)` + docstring (AUD5-CODE-3: канон для shift-домена; Shift-колонки timestamptz). Ничего не импортировать кроме stdlib (существующие `utils/date_helpers.py`/`helpers.py` тянут i18n — не туда).
- [ ] **1.2** AST-гейт `tests/services/test_shift_tz_inventory.py` по образцу `tests/services/test_workflow_read_inventory.py`: module-level `SWEPT_FILES` (стартует с одного `uk_management_bot/services/shift_service.py`, растёт по таскам; финал = **8 файлов**); `ast.parse` каждого файла, нарушения **трёх видов**: (а) `Call(Attribute(attr='now', value=Name('datetime')))` **без аргументов** и `Attribute(attr='utcnow')`; (б) `Call(Attribute(attr='combine', value=Name('datetime')))` **без keyword `tzinfo`**; (в) `Call(Attribute(attr='replace'))` с единственным keyword `tzinfo=Constant(None)` (паттерн `.replace(tzinfo=None)`). Assert пустого списка с внятным сообщением («используй utc_now() / datetime.now(timezone.utc) / combine(..., tzinfo=timezone.utc)»). В docstring гейта: почему RED-механизм для query-сайтов именно гейт (sqlite сравнивает строково — поведенческий тест не упадёт честно). + 2 юнит-теста хелпера (`tzinfo is timezone.utc`, `utcoffset()==timedelta(0)`).
- [ ] **1.3** Поведенческие RED-тесты stats — в `uk_management_bot/tests/services/test_shift_service.py`, класс `TestGetShiftStats` (стиль файла — MagicMock). **Плюс правка существующей фикстуры:** `_make_shift` этого файла ставит naive `shift.start_time = datetime(2026, 4, 2, 9, 0, 0)` — после фикса открытая смена в старых тестах даст aware `now` − naive start → TypeError → нули → фейл. Перевести фикстуру на aware (`tzinfo=timezone.utc`), прогнать весь файл:
  - `test_stats_nonzero_for_open_aware_shift`: `patch.object(ShiftService, "list_shifts", return_value=[shift])`, shift: `start_time = datetime.now(timezone.utc) - timedelta(hours=2)`, `end_time=None`, `status=SHIFT_STATUS_ACTIVE` → `total_hours ≈ 2.0`, `active_count == 1`. Сейчас честно RED: naive `now` − aware start → TypeError → нули.
  - `test_stats_closed_shift_uses_end_time`: aware-пара start/end, точные часы.
- [ ] **1.4** Rebuild → прогон → убедиться в RED (гейт по `:227/:251` + оба stats-теста).
- [ ] **1.5** Фикс `shift_service.py`: import `utc_now`; `:227` и `:251` → `now = utc_now()`; `:229` → `start = now.replace(hour=0, minute=0, second=0, microsecond=0)` (aware UTC-midnight ≡ прежнему поведению при TZ=UTC, Task 0.2).
- [ ] **1.6** Rebuild → оба набора (`docker exec uk-management-bot pytest -q` и `pytest -q tests/api tests/services`) → PASS. Checkpoint.

### Task 2: Хендлеры `my_shifts.py` + `shifts.py` (naive-записи в БД)

**Files:** Modify: `uk_management_bot/handlers/my_shifts.py`, `uk_management_bot/handlers/shifts.py`; Test: Create `uk_management_bot/tests/handlers/test_shift_tz_aware_writes.py` (mock-паттерн из `test_my_shifts_current.py`: AsyncMock callback, mock db c query-chain, kwargs `db=/user=/roles=` через `require_role` — см. memory `reference_require_role_di_signature`).

- [ ] **2.1** Добавить оба файла в `SWEPT_FILES` (гейт → RED).
- [ ] **2.2** RED-тесты:
  - `test_start_shift_writes_aware_start_time` (`handle_start_shift`): после вызова `shift.start_time.tzinfo is not None` и `utcoffset()==timedelta(0)`.
  - `test_end_shift_writes_aware_end_time_and_duration` (`handle_end_shift`): mock-shift c `start_time` = aware **+05:00** (Ташкент), фактически 2 часа назад. RED-трюк: старый код стрипает +05 wall-time в naive → duration врёт на 5ч; новый aware-код даёт ≈2ч. Ассерты: `end_time` aware-UTC; `actual_duration` ≈ 2 (вытащить из аргументов `edit_text`/`get_text().format`).
  - `test_end_shift_select_writes_aware_end_time` — путь `shifts.py:380`. ⚠️ Seam другой: `end_shift_yes_with_id` (`shifts.py:345`) НЕ принимает `db=` и сам открывает `session_scope()` → патчить `uk_management_bot.handlers.shifts.session_scope` контекстным менеджером, возвращающим mock DB (не DI-kwargs).
  - Duration-display для `shifts.py:151` и `:210`: +05:00-старт 2ч назад → в тексте `hours` ≈ 2, не 7.
- [ ] **2.3** Rebuild → RED подтверждён.
- [ ] **2.4** Фикс `my_shifts.py`: import `utc_now`; `:470` → `shift.start_time = utc_now()`; `:523` → `end_time = utc_now()`; `:531` → `(end_time - shift.start_time).total_seconds()/3600` — **убрать `.replace(tzinfo=None)` и удалить ложный коммент `:527-529`** (оставить обход при aware end_time = сломать арифметику в обратную сторону).
- [ ] **2.5** Фикс `shifts.py`: top-level import `utc_now`; `:151` → `duration = utc_now() - shift.start_time` (убрать двойной replace); `:210` → аналогично; `:380` → `shift.end_time = utc_now()`. Function-local `from datetime import datetime` (`:144/201/362`) убирать только если `datetime` в функции больше не используется (проверить каждую).
- [ ] **2.6** **Правка существующих тестов, которые сломает aware-переход** (включить в этот же checkpoint):
  - `uk_management_bot/tests/test_handler_shifts.py:65` — `_make_shift` c naive `datetime(2025, 1, 15, 9, 0, 0)`, helper питает оба duration-пути → перевести на aware UTC.
  - `uk_management_bot/tests/test_fs_batch_p2.py:257` (`test_end_shift_handles_tz_aware_start_time`) — тест закреплял СТАРОЕ поведение (naive `end_time` против aware start); плюс sqlite после записи `DateTime(timezone=True)` возвращает **naive** datetime (подтверждено владельцем локально) → после фикса aware `end_time` − naive-из-sqlite `start_time` = TypeError в обратную сторону. Переписать на mock-shift с aware `start_time` (не полагаться на sqlite round-trip); docstring обновить под новое поведение. Если тест невозможно увести от sqlite — явный задокументированный тестовый normalizer, но mock предпочтителен.
- [ ] **2.7** Rebuild → оба набора PASS. Checkpoint. (`strftime('%H:%M')` теперь на aware-UTC — вывод идентичен прежнему при TZ=UTC.)

### Task 3: `shift_scheduler.py`

**Files:** Modify: `uk_management_bot/utils/shift_scheduler.py`. RED-механизм — гейт (см. 1.2: sqlite маскирует `between()`-баг).

- [ ] **3.1** Добавить файл в `SWEPT_FILES` → rebuild → гейт RED.
- [ ] **3.2** Фикс: import `utc_now`; `:417` → `now = utc_now()` + коммент в стиле QA-04 (`:367-370`); `:326` → `cutoff_date = utc_now() - timedelta(days=30)`; все 14 `task_stats[...]['last_run']` → `utc_now()` (нулевой baseline гейта вместо exclusion-list); `:370` → `utc_now()` для унификации, **коммент QA-04 сохранить по смыслу, но переформулировать literal `datetime.now()` → «naive now»** (иначе противоречит grep-верификации 6.2; источник истины — AST-гейт, он комментарии не видит).
- [ ] **3.3** Rebuild → оба набора PASS. Checkpoint.

### Task 4: Расширенный свип `shift_management/*` (решение владельца: включено)

**Files:** Modify: `handlers/shift_management/assignment_a.py`, `assignment_b.py`, `analytics.py`, `manual_planning.py`.

- [ ] **4.1** Добавить 4 файла в `SWEPT_FILES` → rebuild → гейт RED (в т.ч. по combine-правилу 1.2(б) на `assignment_b.py:375`).
- [ ] **4.2** Механическая замена по инвентарю (a: `:33,112,114,187,237,384`; b: `:37,105,181,249`; analytics `:59`; manual_planning `:228`). **Плюс `assignment_b.py:375`:** `day_start = datetime.combine(shift_date, datetime.min.time(), tzinfo=timezone.utc)` — иначе naive-окно уходит в запрос `count_shifts_for_user_on_day`. Day-window `replace(hour=0,...)` становится UTC-midnight ≡ прежнему при TZ=UTC; бизнес-таймзона day-window — явно вне scope. Лишние function-local `datetime`-импорты убрать по правилу 2.5.
- [ ] **4.3** Rebuild → оба набора PASS. Checkpoint.

### Task 5: AUD5-APIFE-4 — schema-level нормализация + чистка роутера

**Files:** Modify: `uk_management_bot/api/shifts/schemas.py`, `uk_management_bot/api/shifts/router.py`; Test: `tests/api/test_shift_schemas.py`, `tests/api/test_shift_overlap.py`.

- [ ] **5.1** RED-тесты:
  - `test_shift_schemas.py`: `test_create_naive_datetimes_coerced_to_utc` (naive → `tzinfo == timezone.utc`, wall-clock не изменён); `test_create_aware_datetimes_preserved` (+05:00 проходит нетронутым — семантика текущего PATCH); `test_create_mixed_naive_aware_succeeds` — **честный RED с точным критерием**: `start_time=datetime(2026, 8, 1, 10, 0)` (naive), `end_time=datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc)` (aware) → модель ОБЯЗАНА создаться успешно, `start_time == datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)`, `end_time` не изменён (сейчас: `check_time_order` кидает TypeError naive-vs-aware `<=` → RED); `test_update_naive_datetimes_coerced_to_utc` (Optional-поля, None-safe).
  - `test_shift_overlap.py` (aware `BASE`, autouse `_silence_publish`). ⚠️ На sqlite «naive POST → 201, overlap → 409» проходит И БЕЗ фикса (обе стороны naive) — такой ассерт ничего не доказывает. Честный RED — проверять нормализацию, а не статус-код:
    - `test_post_naive_iso_normalized_to_utc` — POST с naive-ISO строками → 201 **и `start_time`/`end_time` в JSON-ответе несут UTC-offset** (`+00:00`/`Z`; сейчас ORM-объект naive → сериализуется без offset → RED). Дополнительный ассерт: spy/monkeypatch на `find_overlapping_shift_for_update` — полученные kwargs `start_time`/`end_time` aware.
    - `test_patch_naive_iso_still_ok` — PATCH с naive-ISO `end_time` → 200 и offset в ответе. **Явно regression-GREEN** (PATCH коэрсит уже сейчас): фиксирует, что удаление роутер-блока не регрессит.
- [ ] **5.2** Rebuild → RED (mixed-тест; offset-ассерты POST-пути).
- [ ] **5.3** Фикс `schemas.py`: import `timezone`; на **оба** body (идиома `api/registration/schemas.py:44-52`):
  ```python
  @field_validator("start_time", "end_time", mode="after")
  @classmethod
  def _ensure_utc(cls, v):
      # Клиент может прислать ISO без offset — считаем UTC (семантика прежнего
      # PATCH-коэрса в router; Shift-колонки timestamptz). Aware не трогаем.
      if v is not None and v.tzinfo is None:
          return v.replace(tzinfo=timezone.utc)
      return v
  ```
  field_validator отработает до `model_validator(mode='after')` → `check_time_order` всегда видит согласованную aware-пару.
- [ ] **5.4** `router.py`: удалить мёртвый PATCH-блок `:873-877` (for-loop + коммент). ORM в роутер не добавлять (AST-гейт `test_shifts_router_inventory.py`).
- [ ] **5.5** Проверить существующие naive-конструкции в `test_shift_schemas.py` (`TestCreateShiftBody:196-246`, `TestUpdateShiftBody:252-271`) — они ассертят дефолты/ошибки, не равенство datetime; коэрс их не ломает (перепроверить прогоном).
- [ ] **5.6** Rebuild → оба набора PASS. Checkpoint.

### Task 6: Финальная верификация + ревью + owner-gate

- [ ] **6.1** Rebuild; полный прогон обоих наборов; smoke: `docker logs uk-management-bot --tail 20`.
- [ ] **6.1b** **Чистка импортов + lint (CI-гейт ruff — blocking):** после свипа станут неиспользуемыми `datetime` в `my_shifts.py:9`, `datetime`/`timezone` в `shift_scheduler.py:6`, top-level и function-local `datetime` в `assignment_a.py:2` (и возможно др.) — удалить лишнее по факту; прогнать `ruff check .` в контейнере (или локально той же версией) → 0 ошибок в затронутых файлах.
- [ ] **6.2** Grep-верификация по **8 свипнутым файлам** (источник истины — AST-гейт; grep — вторичная проверка кода, комменты переформулированы в 3.2): `grep -rn "datetime.now()"` → пусто; `grep -rn "replace(tzinfo=None)\|datetime.combine" <8 файлов>` → пусто / только с `tzinfo=`. `utils/shifts.py`, `api/shifts/service.py` не тронуты (diff-проверка).
- [ ] **6.3** Опциональный live-smoke через MCP telegram-qa: начать/завершить ad-hoc смену, «Моя статистика» показывает ненулевые часы (симптом AUD5-CODE-2).
- [ ] **6.4** Обновить `docs/audit/2026-05-20-backlog.md`: AUD5-CODE-3, AUD5-CODE-2 (закрывается волной), AUD5-APIFE-4 → ✅ с датой/PR; staging выборочно `git add -p`, итог `git diff --cached`.
- [ ] **6.5** Ревью: superpowers:requesting-code-review / code-reviewer по диффу ветки; Critical/Important — чинить до продолжения.
- [ ] **6.6** **Owner-gate:** запросить ОК на серию коммитов (по таску, `fix(aud5-code-3): ...` / `fix(aud5-apife-4): ...`), push и `gh pr create`. Без ОК — стоп.

### Task 7: Раскатка (отдельный gate — только по явной команде владельца)

По скиллу `uk-deploy` (загрузить перед деплоем). Миграций нет, Doppler-изменений нет — но `migrate`-шаг обязателен (preflight), все команды через `doppler run`:

- [ ] **7.1** На каждом хосте (profk → infrasafe/105): build `api access-api app migrate` → `run --rm --no-deps migrate` → `up -d --no-deps --wait api access-api app` (105 — оба `-f`).
- [ ] **7.2** Прод-верификация: логи api/app чистые; начать/завершить тестовую смену (или PATCH смены naive-ISO строкой → 200 и корректное время в БД); «Моя статистика» исполнителя ненулевая.
- [ ] **7.3** Финализировать бэклог-записи (раскатано), обновить memory при наличии граблей.

## Verification (сводно)

1. Оба тест-набора в контейнере зелёные после каждого таска (rebuild перед каждым прогоном), включая исправленные легаси-фикстуры (1.3, 2.6).
2. AST-гейт: 0 нарушений всех трёх правил (naive `now`/`utcnow`, `combine` без tzinfo, `.replace(tzinfo=None)`) в **8 файлах** `SWEPT_FILES`; `utils/shifts.py`, `schemas.py`, `router.py` вне гейта.
3. Поведение: stats ненулевые для aware-смен; duration при +05:00-старте ≈ реальным часам; naive-POST → ответ с UTC-offset (= семантика PATCH); mixed naive/aware body успешно валидируется (точный критерий 5.1).
4. Diff-гигиена: `utils/shifts.py`, `api/shifts/service.py`, from-template путь — не тронуты.

## Ключевые ловушки

- Убирая naive `now`, ОБЯЗАТЕЛЬНО убрать парные `.replace(tzinfo=None)`-обходы (`my_shifts.py:531`, `shifts.py:151,210`) — иначе TypeError в обратную сторону. То же для легаси-тест-фикстур с naive start_time (`test_shift_service.py`, `test_handler_shifts.py:65`, `test_fs_batch_p2.py:257`) — без их правки набор не позеленеет.
- sqlite возвращает **naive** datetime после записи в `DateTime(timezone=True)` (подтверждено локально) — тесты на «сохранённое значение aware» строить на mock/схеме, не на sqlite round-trip; для HTTP RED использовать offset в JSON-ответе.
- `is_on_shift_now_*` (`utils/shifts.py`) — осознанно naive, отложено владельцем; в `SWEPT_FILES` не вносить.
- sqlite маскирует naive-vs-timestamptz в запросах → для query-сайтов RED = AST-гейт, не поведенческий тест (задокументировано в гейте).
- `AwareDatetime` вместо коэрса — нельзя (422 на легаси-клиентов; текущий PATCH молча коэрсит).
- Код baked в образы: rebuild перед КАЖДЫМ pytest (RED и GREEN).
- Function-local `from datetime import datetime` удалять только после проверки остальных использований в функции.
- Коммиты/пуш/деплой — только по явной команде владельца; staging выборочный.
