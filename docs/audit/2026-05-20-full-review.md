# Полный аудит UK Management System — 2026-05-20

> _Последнее редактирование: 2026-05-21_

Параллельный запуск 7 специализированных агентов + прогон pytest/vitest + Playwright E2E.

## Сводный TL;DR

Кодовая база функционально работает, новые фичи (pair_with_next, purge endpoints, webhook outbox, reconciliation) корректны на happy path. **8 пунктов уровня P0** разделены на две категории (детали — в P0-секции `2026-05-20-backlog.md`):

- **6 hard blockers** — релиз в прод без этих фиксов невозможен: FIX-001 (NameError invite), FIX-002 (живые секреты на диске), FIX-003 (FK блокирует purge), FIX-004 (БД-юзер с rolsuper=t), FIX-005 (потеря webhook при 503), FIX-006 (invite-токен в логах).
- **2 release gates** — P0 как обязательное условие для смежной работы, с явным каналом понижения до P1: FIX-007 (нет inbound HMAC; поверхность атаки = 0, пока endpoint не реализован — gate на момент реализации), FIX-008 (AddressService `async def` без `await`; FastAPI его не вызывает — gate для ARCH-014 при унификации bot/api путей).

Архитектурная зрелость **2.8/5**, прод-готовность фронта **3/5** (по агентам).

---

## Матрица результатов

Raw CRITICAL по агентам = 15 (суммирование колонки). После дедупликации (один и тот же баг найден несколькими агентами — например, NameError invite.py зафиксировали architect/security/python/qa) уникальных CRITICAL получилось **8**. Маппинг raw→deduped задокументирован в `2026-05-20-backlog.md` (поле `Source` каждого FIX-итема).

| Поток | Статус | raw CRITICAL | HIGH | MEDIUM | Заметка |
|---|---|---|---|---|---|
| Architect | ✓ | 3 | 6 | 10 | Дублирование bot/api путей, плоский pair-layout не масштабируется |
| Security | ✓ | 4 | 7 | 8 | Секреты на диске, нет inbound webhook HMAC, токен в логах |
| Python review | ✓ | 5 | 6 | 6 | AddressService async без await, NameError, 503 non-retryable |
| TypeScript review | ✓ | 0 | 4 | 6 | useMemo deps, setState in effect, 695 kB main bundle |
| Database review | ✓ | 2 | 6 | 7 | uk_bot superuser, requests FK блокирует purge, 37 unindexed FK |
| QA product | ✓ | 1 | 1 | 5 | Confirm-dialog дубль title/desc, нет unsaved guard в editor |
| E2E (Playwright) | ✓ | 0 | 0 | 1 | 9/10 passed; 1 skip (нет seed-пароля), баг в LoginPage 401-interceptor |
| Backend pytest | ⚠ | — | — | — | 780 passed / 101 failed / 150 collection errors — все падения и collect-ошибки локализованы в pre-existing legacy-файлах |
| Frontend vitest | ⚠ | — | — | — | **No test files found** — фронт без юнит-тестов |
| **Уникальных CRITICAL (deduped)** | | **8** | | | см. P0-секцию ниже |

Все ошибки бэк-тестов локализованы в pre-existing legacy-файлах. Полный список из **10 файлов** с collection-ошибками (импорты без `uk_management_bot.` префикса + двойной импорт `database.models`): `test_auth_service_role_switch.py`, `test_data_export.py`, `test_google_sheets_integration.py`, `test_invite_integration.py`, `test_onboarding.py`, `test_performance.py`, `test_purchase_fix.py`, `test_request_service.py`, `test_shift_service.py`, `test_simple_sheets_sync.py`. Тесты, добавленные в текущей итерации (board_config, webhook_sender, reconciliation, address_service, addresses, health_outbox) — все в зелёной зоне. Соответствующая задача по миграции импортов — TEST-069 в `2026-05-20-backlog.md`.

---

## CRITICAL — приоритет 0 (фиксить немедленно)

### 1. `NameError: user_data is not defined` — invite-регистрация новых пользователей сломана
**Подтверждено 4 агентами** (architect, security C2, python, qa BUG-1).
**Файл:** `uk_management_bot/web/api/invite.py:121-124`.

```python
result = invite_service.join_via_invite(
    token=data.token,
    telegram_id=data.telegram_id,
    first_name=user_data["first_name"],   # NameError
    last_name=user_data["last_name"],     # NameError
    ...
)
```

Любой POST `/api/register` с новым `telegram_id` → 500. Существующие pending пользователи донабираются нормально (ветка с `existing_user`).

**Фикс:**
```python
parts = data.full_name.split() if data.full_name else []
result = invite_service.join_via_invite(
    token=data.token,
    telegram_id=data.telegram_id,
    first_name=parts[0] if parts else "",
    last_name=" ".join(parts[1:]) if len(parts) > 1 else "",
    specialization=data.specialization,
)
```

### 2. Живые секреты на диске в `.env`-файлах
**Источник:** security audit, C-1.

| Secret | Файл | Действие |
|---|---|---|
| `BOT_TOKEN` (bot A) | `.env:10` | Revoke в @BotFather |
| `MEDIA_BOT_TOKEN` (media bot) | `.env:12`, `media_service/.env:2` | Revoke (дубликат) |
| `BOT_TOKEN` (bot B) | `uk_management_bot/.env:8` | Revoke |
| `INVITE_SECRET` | `.env:20` | Ротировать |
| `INFRASAFE_WEBHOOK_SECRET` (outgoing подпись) | `.env:187` | Ротировать через `INFRASAFE_USE_NEXT_SECRET` flow |
| `UK_WEBHOOK_SECRET` (inbound, см. FIX-007) | `uk_management_bot/.env` / `settings.py:99-100` | Ротировать одновременно с реализацией inbound endpoint |
| `JWT_SECRET` | `.env:190` | Ротировать |
| `ADMIN_PASSWORD` | `uk_management_bot/.env:11` | Ротировать |

Восемь чувствительных значений (два разных `BOT_TOKEN` + `MEDIA_BOT_TOKEN` + `INVITE_SECRET` + `INFRASAFE_WEBHOOK_SECRET` + `UK_WEBHOOK_SECRET` + `JWT_SECRET` + `ADMIN_PASSWORD`). Bot-id'ы Telegram также убраны из этого документа — они публикуются в @BotFather и не являются "секретами" по строгому определению, но для целей этого отчёта оставлять любые fingerprints исходных значений нет смысла. Все идентификаторы и значения полностью замаскированы.

Файлы в `.gitignore`, в git не утекли. Но любой с доступом к dev-машине или образу контейнера видит их в открытом виде. **Обязательно ротировать перед любым прод-релизом**, даже если репо не публиковался.

### 3. `requests.apartment_id` ON DELETE NO ACTION блокирует purge yards/buildings
**Подтверждено architect C3, database C2.**

`yards → buildings → apartments` каскадируют, но FK от `requests.apartment_id` блокирует. Хотя purge endpoints проверяют `linked_requests`, гонка с одновременным INSERT request или soft-deleted history даст FK violation после `db.delete()`.

**Фикс:** изменить FK на `ON DELETE SET NULL` миграцией:
```sql
ALTER TABLE requests DROP CONSTRAINT requests_apartment_id_fkey;
ALTER TABLE requests ADD CONSTRAINT requests_apartment_id_fkey
  FOREIGN KEY (apartment_id) REFERENCES apartments(id) ON DELETE SET NULL;
```

### 4. `uk_bot` — суперпользователь PostgreSQL
**Database C1.** `rolsuper=t, rolcreatedb=t, rolcreaterole=t`. Любая компрометация коннекшена даёт DROP DATABASE.

**Фикс:**
```sql
ALTER ROLE uk_bot NOSUPERUSER NOCREATEDB NOCREATEROLE;
-- Затем убедиться что явные GRANT покрывают app-операции.
```

### 5. Webhook 503 помечен `retryable=False` — потеря событий при кратком даунтайме InfraSafe
**Python C3.** `webhook_sender.py:189-190`. Уточнение по коду (`process_outbox` lines 250-330): условие повышения в `failed` — `if not retryable or record.attempts >= max_retries`. То есть при `retryable=False` запись становится `status="failed"` **сразу после первой неудачной попытки**, не "после max_retries". Это и есть остриё бага — короткий 503 → перманентная потеря события без шанса на retry.

**Фикс:** заменить на `(False, "HTTP 503: service unavailable", True, 0)`.

### 6. Invite-токен логируется plaintext в info-логах
**Security C-4.** `handlers/auth.py:172`. Полный `invite_v1:...` уходит в `docker logs`. Тот, у кого доступ к логам — может зарегистрироваться по чужому токену в окно его TTL.

**Фикс:** маскировать как `f"{token[:8]}…"` — оставить только префикс, без хвоста, без длины. Сохранять полный токен запрещено даже на DEBUG-уровне.

### 7. Нет проверки подписи входящих webhook'ов от InfraSafe — **подготовительный**, не текущий блокер
**Security C-3.** `UK_WEBHOOK_SECRET` объявлен в settings, но **inbound webhook router не реализован**. Текущая поверхность атаки = 0 (endpoint не существует, обращение → 404). Включено в P0 как **gating-условие на реализацию inbound flow**: вместе с endpoint'ом обязана появиться HMAC-проверка + replay-protection. Если до релиза inbound не делается — пункт можно отложить до момента, когда delivery от InfraSafe потребуется. До тех пор `UK_WEBHOOK_SECRET` нужно ротировать вместе с остальными секретами (см. FIX-002), потому что значение уже на диске.

### 8. AddressService — 16 `async def` без `await`, на sync Session — **tech-debt, не runtime-блокер**
**Python C4.** `services/address_service.py:23,68,75,249,263,545,561,586,780,815,850,870,893,914,944,1036`.

Уточнение по факту: `grep "AddressService" uk_management_bot/api/` пуст — FastAPI/API **не вызывает AddressService напрямую**. Сервис используется только из синхронных aiogram-handler'ов (bot). Под нагрузкой event loop FastAPI не блокируется, потому что путь вызова не пересекается с async-стеком API. Однако сама комбинация `async def` + sync `Session` + zero `await` — ловушка для будущих разработчиков, которые попробуют вызвать метод из FastAPI-роутера и получат тихое блокирующее поведение.

**Фикс:** убрать `async` (sync helper для bot-handler'ов) — минимальная инвазивность, фиксирует контракт. Альтернатива (переписать на `AsyncSession`) — отдельный эпик в "Что не покрыто бэклогом". Классификация P0 здесь — для предотвращения регрессии при ARCH-014 (попытка унификации bot/api путей через единый AddressService). Если ARCH-014 откладывается — FIX-008 можно понизить до P1.

---

## HIGH — приоритет 1

### Backend / Python
- **H1** Дублирование `queue_webhook` / `queue_webhook_sync` (~30 строк идентичной логики, divergence risk).
- **H2** `address_service.py` 1413 строк, `addresses/router.py` 1207 строк — превышают потолок 800.
- **H3** 24× `except Exception` в `address_service.py` — глотает всё, возвращает `str(e)` в UI.
- **H4** `web/api/invite.py:107` — использует устаревший `user.role` вместо `user.active_role`/`user.roles`.
- **H5** `web/api/invite.py:84` — legacy `db.query(User)` (SQLAlchemy 1.x).
- **H6** `sys.path.append` в `web/main.py:15` и `web/api/invite.py:12` (хрупко, не нужно).
- **H7** `address_service.py` — все `logger.error(f"...{e}")` вместо lazy `%s` и без `logger.exception()`.

### Frontend / TypeScript
- **H1** `AddressesPage.tsx:233` — `useMemo` без `t` в deps; UI устаревает при смене языка.
- **H2** `BoardEditorPage.tsx:157` — `setState` синхронно в `useEffect` body, флагается React Compiler.
- **H3** `ResidentBoardPage.tsx:85` — `Date.now()` в render-функции (impure).
- **H4** `AddressesPage.tsx:134` — `catch {}` без аргумента и комментария.
- Bundle warning: `index-*.js = 695 kB`, `AnalyticsPage = 389 kB` — нужен code split.

### Security
- **H-1** TWA refresh-token в `localStorage` (30-дневный TTL, XSS-exposed).
- **H-2** Zustand `auth-store` persistит user.id и roles в `localStorage`.
- **H-3** `POST /api/v2/auth/set-password` без rate-limit.
- **H-4** `validate_invite_token` без consuming nonce → TOCTOU race.
- **H-5** `POST /api/v2/media/upload` — не валидирует `request_number` и `category`.
- **H-6** `media_service/.env` — `ALLOWED_ORIGINS=*` + `DEBUG=true` локально.
- **H-7** `database/migrations/add_performance_indices.py` — DDL f-string без quoted_name.

### Database
- **H1** `users.roles` хранится как TEXT (JSON string), не jsonb → нет GIN, нет `@>`/`?`.
- **H2** `requests` таблица — нет индексов на `status`, `user_id`, `executor_id`, `created_at`. Каждый list-query — seq scan.
- **H3** `notifications` — нет индекса на `user_id`. Unread-выборка — seq scan.
- **H4** **37 FK-столбцов без индексов на дочерней стороне** (полный список в database-агенте; самые горячие — `requests.user_id`, `requests.executor_id`, `notifications.user_id`, `request_assignments.*`, `ratings.*`).
- **H5** `webhook_outbox` — нет partial index `WHERE status='pending'`; полный btree включает sent/failed.
- **H6** `board_config.updated_by` — без FK constraint и без индекса.

### Architecture
- **H1** Два FastAPI app (`api/main.py`, `web/main.py`) с независимыми CORS, middleware, Sentry-инициализацией.
- **H2** AddressService (sync) и `api/addresses/router.py` (async) — два независимых repository с дублированной валидацией.
- **H3** Outbox: `event_id = uuid.uuid4()` — два ручных retry дают разные event_id, ломая идемпотентность.
- **H4** `reconcile_buildings` cap=50 + sort по hash external_id — replay'ит одни и те же 50, остальные не доходят.
- **H5** `api/main.py` смешивает lifespan/inline-endpoints/bootstrap.
- **H6** Bot handlers напрямую `next(get_db())` без `with`/`finally` → возможна утечка коннекшенов.

### QA-баги (продуктовые)
- **BUG-2** Локализация ошибок бота: address_service возвращает русские строки в UI.
- **BUG-3** BoardEditor — нет unsaved-changes guard'а.
- **BUG-4** `pair_with_next` allows `stats + requests` без warning — UX-смелл.
- **BUG-5** `confirmDeleteYard/Building/Apartment` — title и description одинаковы.

### E2E
- **LoginPage 401-interceptor bug**: `apiClient` пытается рефрешнуть токен на странице login → редирект перетирает inline-error.

---

## MEDIUM (выборка)

- `MODULE_IDS` / `ModuleId` дублируется в Python и TS — нужна кодогенерация типов.
- `defaults.py` (Python) + `defaultBoardConfig` (TS) — 6 точек синхронизации одного дефолта.
- `pair_with_next` — плоская модель, не поддерживает 3-в-ряд; рекомендация перейти на rows-of-modules.
- Public board endpoint — per-worker in-memory cache; per-status N+1 на `PIPELINE_STATUSES`.
- Все 30 таблиц используют `integer` PK (max 2.1B); audit_logs/requests/notifications/webhook_outbox должны быть `bigint`.
- `board_config.data` — `json`, не `jsonb` (нельзя индексировать).
- `webhook_outbox.status` без CHECK constraint.
- `updated_at` колонки полагаются исключительно на ORM onupdate (нет триггеров).
- 22 дубликата btree-индексов на `id` PK (SQLAlchemy `index=True` на pk).
- В `users` живут оба поля `role` (legacy) и `roles` (новый) без CHECK consistency.
- `apartments.area` — `double precision` (IEEE 754), должен быть `numeric(8,2)`.
- Webhook `outbox_health` endpoint — без auth, отдаёт internal metrics.
- 3 debug-route'а в `web/main.py` (`/test`, `/simple`, `/minimal`) активны в проде.
- `get_statistics` — 8 последовательных SELECT'ов вместо одного с conditional aggregates.

---

## Тестовая инфраструктура

### Backend pytest (контейнер uk-management-bot)
```
780 passed
101 failed   ← все в pre-existing legacy-файлах (workload_predictor, integration_full_cycle, request_assignment_system)
150 errors   ← collection errors из-за import path (database.models vs uk_management_bot.database.models)
 15 subtests passed
```

**Новые тесты, добавленные в текущей итерации, — в зелёной зоне** (board_config, webhook_sender, reconciliation, address_service, addresses, health_outbox).

### Frontend vitest
```
No test files found.
```
Покрытие нулевое. Срочно нужны юнит-тесты как минимум для:
- `pair_with_next` default/toggle/reorder reset
- `useAddresses` purge mutations
- `confirmDelete` vs `confirmPurge` dialog state separation
- LoginPage 401 handling (после фикса interceptor-баги)

### E2E (Playwright) — новые тесты
Файлы сгенерированы агентом:
- `tests/e2e/playwright.config.ts`
- `tests/e2e/specs/resident-board.spec.ts`
- `tests/e2e/specs/route-guard.spec.ts`
- `tests/e2e/specs/login-flow.spec.ts`
- артефакты в `tests/e2e/artifacts/*.png`

```
10 тестов: 9 passed, 0 failed, 1 skipped (нет E2E_MANAGER_PASSWORD fixture)
```

Покрытые critical user flows:
- Public resident-board рендерится (ticker, clock, org name, 4 stat tiles, footer realtime)
- `pair_with_next=true` — два модуля в одной строке, Y-разница < 80px
- Editor route guard (без auth → /login)
- Dashboard route guard
- Login page рендерится
- Неверные креды → 401 (выявил interceptor-баг)

---

## Архитектурные рекомендации (top-5)

1. **Извлечь `shared/` пакет**, отделив `services/` и `database/` от пакета `uk_management_bot`. Это убирает дублирование между sync/async и между bot/api/web.
2. **Один путь записи доменных мутаций → один эмиттер событий** (`AddressService` → `EventBus.enqueue_webhook` + `publish_redis`), убрав дублирующиеся side-effects в API router.
3. **Outbox v2**: детерминированный `event_id = sha256(event + entity_id + entity_updated_at)`, partial index `WHERE status='pending'`, retention cron 30 дней, Prometheus метрики.
4. **Board layout → rows-of-modules**: заменить `LayoutItem[]` на `{ rows: { id, modules: ModuleId[] }[] }`. Решает масштабирование на N-в-ряд + убирает compensating logic в editor.
5. **Решить судьбу `web/`**: либо слить с api (один FastAPI app), либо строго изолировать через HTTP (web вызывает api напрямую). Сейчас — параллельные миры с расходящимися конфигами.

---

## Production readiness

| Атрибут | Оценка | Источник |
|---|---|---|
| Layering | 2/5 | architect |
| Testability | 3/5 | architect |
| Observability | 3/5 | architect |
| Scalability | 3/5 | architect |
| Security separation | 3/5 | architect |
| Frontend prod-ready | 3/5 | typescript-reviewer |

**Среднее: 2.8/5** — production-ready для текущей малой нагрузки, но декомпозиция и фикс CRITICAL обязательны перед расширением.

---

## Артефакты этой сессии

**В репозитории (воспроизводимые после checkout):**
- E2E тесты: `tests/e2e/specs/*.spec.ts` (3 файла: resident-board, route-guard, login-flow)
- Этот отчёт: `docs/audit/2026-05-20-full-review.md`
- Бэклог: `docs/audit/2026-05-20-backlog.md`

**Ephemeral (только на машине аудитора, не tracked):**
- E2E скриншоты: `tests/e2e/artifacts/*.png` — игнорятся через `*.png` в `.gitignore` (line 166); для CI нужно либо whitelist'ить эту директорию в `.gitignore`, либо аплоадить как CI-artifacts.
- Скриншот фичи pair_with_next: `board-paired.png` в корне — тоже `*.png`-gitignored. Не воспроизводится после `git clean -fdx`; чтобы пересоздать — открыть `/uk/resident-board` после выставления `announcements.pair_with_next=true` в БД (см. SQL ниже) и снять скриншот.
- Backend pytest вывод: был на `/private/tmp/claude-501/.../tasks/bq8kyol9b.output` — host-specific temp-директория агента, после перезапуска оболочки не сохраняется. Для повторного прогона: `docker exec uk-management-bot pytest tests/ --ignore=<10 legacy files> --tb=line -q`.

**Локальное состояние БД, которое надо откатить:**
БД-патч `announcements.pair_with_next=true` оставлен включённым в локальной `uk-postgres`. Сброс:

```bash
docker exec -i uk-postgres psql -U uk_bot -d uk_management <<'SQL'
UPDATE board_config SET data = jsonb_set(
  data::jsonb, '{layout}',
  '[{"id":"stats","visible":true},{"id":"requests","visible":true},
    {"id":"announcements","visible":true},{"id":"rating","visible":true},
    {"id":"hours","visible":true}]'::jsonb, false)::json
WHERE id = 1;
SQL
```
