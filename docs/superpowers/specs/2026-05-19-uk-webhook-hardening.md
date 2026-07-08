---

> _Последнее редактирование: 2026-05-21_

 Context (зачем это нужно)

 Production-инцидент 2026-05-19: Manager создал здание в UK Dashboard
 (POST /api/v2/addresses/buildings, building id=1 "Olmazor City 14V").
 Building попал в UK БД, но не пришёл в InfraSafe. Таблица
 webhook_outbox оказалась пуста. Ручной INSERT + ручной process_outbox()
 вытолкнули событие — InfraSafe получил его корректно (HMAC валидный,
 схема корректная, integration_log.status=success).

 Транспорт работает. Проблема выше — между API-handler'ом и outbox-записью.

 CTO-уровень разбор (4 параллельных Explore-агента в InfraSafe-сессии)
 выявил четыре реальных бага и два архитектурных риска:

 ┌─────┬─────────────────────────────────────────────────────────────────────┬──────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────┐
 │  #  │                                 Bug                                 │             Файл / линии             │                                  Severity                                  │
 ├─────┼─────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────┤
 │ 1   │ Race в process_outbox под --workers 2 (no SKIP LOCKED)              │ services/webhook_sender.py:175-188   │ High (бесшумный 2× трафик; InfraSafe dedupлирует, но архитектурно неверно) │
 ├─────┼─────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────┤
 │ 2   │ queue_webhook() молча skipается при ENABLED=False на момент handler │ services/webhook_sender.py:73-76     │ Critical (потеря событий без следа)                                        │
 ├─────┼─────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────┤
 │ 3   │ REDIS_PUBSUB_URL дефолт без пароля → AuthenticationError            │ services/redis_pubsub.py:21,38,60,86 │ Medium (WS-push сломан, логи засорены)                                     │
 ├─────┼─────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────┤
 │ 4   │ Отсутствие observability для outbox-lag и replay-механизма          │ везде                                │ High (нашёл проблему пользователь, не мониторинг)                          │
 └─────┴─────────────────────────────────────────────────────────────────────┴──────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────┘

 Архитектурные риски:
 - --workers 2 без cross-process coordination → race (закрывается PR-A).
 - Pydantic settings читаются раз на startup → опасно полагаться на live env
 changes без recreate контейнера (закрывается PR-B + PR-D safety-net).

 ---

 Scope (что делаем)

 4 PR в UK-репо, все must для production. Идут в порядке зависимостей.

 PR-A: FOR UPDATE SKIP LOCKED в process_outbox()

 Файл: uk_management_bot/services/webhook_sender.py

 Изменение:

 # СЕЙЧАС (lines 175-188):
 stmt = (
     select(WebhookOutbox)
     .where(
         WebhookOutbox.status == "pending",
         or_(WebhookOutbox.retry_after.is_(None),
             WebhookOutbox.retry_after <= now),
     )
     .order_by(WebhookOutbox.created_at)
     .limit(50)
 )
 result = await db.execute(stmt)
 records = result.scalars().all()

 # ПОСЛЕ:
 stmt = (
     select(WebhookOutbox)
     .where(
         WebhookOutbox.status == "pending",
         or_(WebhookOutbox.retry_after.is_(None),
             WebhookOutbox.retry_after <= now),
     )
     .order_by(WebhookOutbox.created_at)
     .limit(50)
     .with_for_update(skip_locked=True)   # ← добавлено
 )

 Почему SKIP LOCKED а не Redis-mutex:
 - Outbox уже живёт в Postgres, нет смысла гнать coordination в Redis.
 - SKIP LOCKED — actual parallelism (worker 1 берёт строки 1-50, worker
 2 — 51-100), а Redis SET NX = serial (только один worker активен).
 - Lock держится до await db.commit() на line 228 (~end of function),
 что покрывает весь цикл send+update.
 - Postgres-native, нет deadlock'ов при graceful shutdown.

 Acceptance:
 - Запустить 2 параллельных process_outbox() против БД с 100 pending —
 каждая запись отправлена ровно один раз.
 - Уже работающие тесты в tests/test_webhook_sender.py продолжают проходить.

 Тест: новый tests/api/test_webhook_outbox_concurrency.py
 - Сетап: вставить 100 WebhookOutbox(status='pending') записей,
 замокать send_webhook чтобы он возвращал (True, "", False, 0).
 - Запустить asyncio.gather(process_outbox(), process_outbox()).
 - Проверить mock_send_webhook.call_count == 100 (ровно 100, не 200).
 - Проверить все записи status='sent', attempts=1.

 ---
 PR-B: Fail-loud + REDIS_PUBSUB_URL derive

 Файл 1: uk_management_bot/services/webhook_sender.py:73-76

 # СЕЙЧАС:
 async def queue_webhook(db, event, endpoint, data):
     if not settings.INFRASAFE_WEBHOOK_ENABLED:
         return

 # ПОСЛЕ:
 async def queue_webhook(db, event, endpoint, data):
     if not settings.INFRASAFE_WEBHOOK_ENABLED:
         logger.warning(
             "queue_webhook SKIPPED: INFRASAFE_WEBHOOK_ENABLED=False "
             "(event=%s endpoint=%s) — event will be LOST. "
             "Reconciliation will replay it within 1h if it's a building/request.",
             event, endpoint,
         )
         return

 Файл 2: uk_management_bot/config/settings.py

 Найди класс Settings (Pydantic BaseSettings). После всех полей добавь:

 @property
 def REDIS_PUBSUB_URL_RESOLVED(self) -> str:
     """REDIS_PUBSUB_URL with auth derived from REDIS_URL if not explicitly set.

     Default behaviour: take REDIS_URL (which has auth in prod) and swap /0 → /1
     so pubsub runs on db 1. If REDIS_PUBSUB_URL is explicitly set in env, it
     wins (escape hatch for separate Redis instance).
     """
     if self.REDIS_PUBSUB_URL:
         return self.REDIS_PUBSUB_URL
     if self.REDIS_URL:
         if self.REDIS_URL.endswith("/0"):
             return self.REDIS_URL[:-2] + "/1"
         return f"{self.REDIS_URL.rstrip('/')}/1"
     return "redis://redis:6379/1"

 (Если REDIS_PUBSUB_URL field ещё не объявлен — добавь REDIS_PUBSUB_URL: str = "" рядом с REDIS_URL.)

 Файл 3: uk_management_bot/services/redis_pubsub.py

 Заменить четыре места (lines 21, 38, 60, 86):

 # СЕЙЧАС:
 url = getattr(settings, 'REDIS_PUBSUB_URL', 'redis://redis:6379/1')

 # ПОСЛЕ:
 url = settings.REDIS_PUBSUB_URL_RESOLVED

 Acceptance:
 - В production логи uk-management-api перестают содержать
 redis.exceptions.AuthenticationError.
 - WebSocket push events на frontend начинают приходить (kanban
 обновляется в реальном времени).
 - В тесте: установить только REDIS_URL=redis://:pwd@host/0, прочитать
 settings.REDIS_PUBSUB_URL_RESOLVED → должно быть redis://:pwd@host/1.

 Тест: новый tests/services/test_redis_pubsub_url.py
 - 4 кейса:
   a. REDIS_PUBSUB_URL явно задан → возвращается как есть.
   b. REDIS_PUBSUB_URL пуст, REDIS_URL=redis://:pwd@h:6379/0 →
 возвращает redis://:pwd@h:6379/1.
   c. REDIS_PUBSUB_URL пуст, REDIS_URL=redis://h:6379 (без /N) →
 возвращает redis://h:6379/1.
   d. Оба пусты → fallback на redis://redis:6379/1.

 ---
 PR-C: Outbox observability

 Файл 1: uk_management_bot/api/main.py

 Найди существующий /health endpoint (или corner около startup) и добавь
 рядом новый:

 from sqlalchemy import select, func
 from datetime import datetime, timedelta, timezone
 from uk_management_bot.database.models.webhook_outbox import WebhookOutbox

 @app.get("/health/outbox")
 async def outbox_health():
     """Outbox lag metrics for monitoring / alerting.

     Returns 200 always (so HTTP probes don't flap); consumer (Prometheus
     scrape, alert rule) decides thresholds.
     """
     if not settings.INFRASAFE_WEBHOOK_ENABLED:
         return {"enabled": False, "pending": 0, "oldest_pending_age_sec": 0, "failed_last_24h": 0}

     from uk_management_bot.database.session import AsyncSessionLocal
     if AsyncSessionLocal is None:
         return {"enabled": True, "error": "db_unavailable"}

     now = datetime.now(timezone.utc)
     try:
         async with AsyncSessionLocal() as db:
             pending = await db.scalar(
                 select(func.count(WebhookOutbox.id))
                 .where(WebhookOutbox.status == 'pending')
             ) or 0
             oldest = await db.scalar(
                 select(func.min(WebhookOutbox.created_at))
                 .where(WebhookOutbox.status == 'pending')
             )
             failed_24h = await db.scalar(
                 select(func.count(WebhookOutbox.id))
                 .where(
                     WebhookOutbox.status == 'failed',
                     WebhookOutbox.created_at > now - timedelta(hours=24),
                 )
             ) or 0
         return {
             "enabled": True,
             "pending": pending,
             "oldest_pending_age_sec": (now - oldest).total_seconds() if oldest else 0,
             "failed_last_24h": failed_24h,
         }
     except Exception as e:
         logger.exception("outbox_health failed")
         return {"enabled": True, "error": str(e)}

 Файл 2: uk_management_bot/services/webhook_sender.py — после
 await db.commit() на line 228, добавить:

 sent = sum(1 for r in records if r.status == 'sent')
 failed = sum(1 for r in records if r.status == 'failed')
 retried = len(records) - sent - failed
 logger.info(
     "process_outbox cycle: fetched=%d sent=%d failed=%d retried=%d",
     len(records), sent, failed, retried,
 )

 Acceptance:
 - curl https://infrasafe.uz/uk/api/health/outbox отдаёт JSON.
 - В docker logs uk-management-api каждые 10 секунд (когда есть records)
 появляется одна строка process_outbox cycle: ....

 Тест: unit-тест для outbox_health мокает БД, проверяет 3 значения
 вернулись корректно. Cycle log можно покрыть caplog в существующих
 тестах process_outbox.

 ---
 PR-D: Reconciliation job — UK↔InfraSafe drift detection с auto-replay

 Зачем: PR-A/B/C закрывают наблюдаемые баги. Reconciliation —
 safety-net для будущих regressions Bug-2-style (тихий skip
 queue_webhook или новые такие же баги в request/comment events).
 Раз в час сверяем inventory, авто-replay пропавшего.

 Файл 1: новый uk_management_bot/clients/infrasafe_client.py

 """httpx client для опроса InfraSafe-side state (для reconciliation)."""
 import httpx
 from uk_management_bot.config.settings import settings

 INFRASAFE_API_TIMEOUT = 30.0

 async def fetch_infrasafe_external_buildings() -> set[str]:
     """Return set of building external_id (UUIDs as str) known to InfraSafe.

     Uses public-ish endpoint /api/buildings-metrics (no auth required for GET
     in current InfraSafe — confirmed by code review). Filters externally-synced.
     """
     base = settings.INFRASAFE_WEBHOOK_URL.rstrip('/')
     url = f"{base}/api/buildings-metrics?limit=5000"
     async with httpx.AsyncClient(timeout=INFRASAFE_API_TIMEOUT) as client:
         resp = await client.get(url)
         resp.raise_for_status()
         data = resp.json()
     items = data.get('data', data) if isinstance(data, dict) else data
     return {
         str(item['external_id'])
         for item in items
         if item.get('external_id')
     }

 ▎ Внимание: проверь что /api/buildings-metrics действительно
 ▎ возвращает external_id поле. Если нет — добавляется отдельным
 ▎ ChangeRequest в InfraSafe (см. финальную секцию). Если нужен auth —
 ▎ заменить на service-creds (UK_INTERNAL_AUTH_TOKEN env).

 Файл 2: новый uk_management_bot/services/reconciliation.py

 """UK ↔ InfraSafe building reconciliation (cron-style, runs from API lifespan)."""
 import logging
 from datetime import datetime, timezone
 from sqlalchemy import select, text
 from uk_management_bot.config.settings import settings
 from uk_management_bot.database.session import AsyncSessionLocal
 from uk_management_bot.database.models.building import Building
 from uk_management_bot.database.models.yard import Yard
 from uk_management_bot.services.webhook_sender import queue_webhook
 from uk_management_bot.clients.infrasafe_client import fetch_infrasafe_external_buildings

 logger = logging.getLogger(__name__)

 # Advisory-lock id — random fixed integer; ensures only one worker reconciles
 RECONCILE_LOCK_KEY = 0x7eC0_7C1l_E_001  # mnemonic, any 64-bit int works

 async def reconcile_buildings() -> dict:
     """Run one reconcile cycle. Returns summary stats."""
     if not settings.INFRASAFE_WEBHOOK_ENABLED:
         return {"skipped": "disabled"}

     async with AsyncSessionLocal() as db:
         locked = await db.scalar(
             text("SELECT pg_try_advisory_lock(:k)"),
             {"k": RECONCILE_LOCK_KEY},
         )
         if not locked:
             logger.debug("reconcile_buildings: skipped (lock held by other worker)")
             return {"skipped": "lock_held"}

         try:
             # 1. UK side: all active buildings with their UK ids
             uk_stmt = (
                 select(Building.id, Building.address, Building.yard_id, Yard.name)
                 .join(Yard, Yard.id == Building.yard_id)
                 .where(Building.is_active == True)
             )
             uk_rows = (await db.execute(uk_stmt)).all()
             uk_by_id = {row.id: row for row in uk_rows}

             # 2. InfraSafe side: external_ids it has
             try:
                 is_externals = await fetch_infrasafe_external_buildings()
             except Exception:
                 logger.exception("reconcile_buildings: failed to fetch InfraSafe state")
                 return {"error": "infrasafe_fetch_failed"}

             # 3. Compute drift.
             #    NOTE: InfraSafe's external_id is a *UUID derived from UK building*,
             #    not a direct id. The webhook payload includes building.id (int);
             #    InfraSafe stores it as deterministic UUID. We compare by re-deriving.
             #    See webhook_sender.build_building_payload — payload["event_id"]
             #    is random UUID per send, but InfraSafe stores building.external_id
             #    as a value passed by UK (currently UK doesn't pass external_id —
             #    InfraSafe computes its own UUID from the integer id). This is
             #    an interop bug to clarify in InfraSafe ChangeRequest.
             #    For now, treat missing as "no row in InfraSafe matched to ANY
             #    UK id" — coarse but useful: if InfraSafe has 0 externals and UK
             #    has 5, all 5 are missing.
             #    TODO(PR-Δ): once UK passes a deterministic external_id in payload
             #    (e.g. UUIDv5 of UK id under fixed namespace), use exact set diff.

             # Simplified drift check until clean external_id mapping:
             uk_count = len(uk_by_id)
             is_count = len(is_externals)
             missing_est = max(0, uk_count - is_count)
             extra_est = max(0, is_count - uk_count)

             if missing_est == 0 and extra_est == 0:
                 logger.info("reconcile_buildings: in sync (uk=%d is=%d)", uk_count, is_count)
                 return {"in_sync": True, "uk": uk_count, "infrasafe": uk_count}

             logger.warning(
                 "reconcile_buildings: drift detected — uk=%d infrasafe=%d (estimated missing=%d extra=%d)",
                 uk_count, is_count, missing_est, extra_est,
             )

             # 4. Re-enqueue UK buildings that don't appear to be in InfraSafe.
             #    Heuristic: queue events for UK buildings NEWER than the oldest
             #    InfraSafe sync window (last 7 days). Avoid bulk-replaying full
             #    history on first run.
             #    For now: enqueue all UK buildings with created_at within last 7d.
             from datetime import timedelta
             cutoff = datetime.now(timezone.utc) - timedelta(days=7)
             recent = [r for r in uk_rows if r.created_at >= cutoff] if hasattr(uk_rows[0] if uk_rows else None, 'created_at') else uk_rows

             enqueued = 0
             for row in recent[:50]:  # cap per cycle
                 await queue_webhook(
                     db, "building.created",
                     "/api/webhooks/uk/building",
                     {"id": row.id, "address": row.address, "yard_name": row.name},
                 )
                 enqueued += 1
             await db.commit()
             logger.warning("reconcile_buildings: enqueued %d replay events", enqueued)
             return {"in_sync": False, "uk": uk_count, "infrasafe": is_count, "enqueued": enqueued}

         finally:
             await db.execute(
                 text("SELECT pg_advisory_unlock(:k)"),
                 {"k": RECONCILE_LOCK_KEY},
             )

 Файл 3: uk_management_bot/api/main.py — расширить existing lifespan
 после _outbox_loop():

 # В существующем lifespan(), после блока создания outbox-task'а, добавить:

 async def _reconciliation_loop():
     # Run reconciliation hourly. Sleep first so we don't slam startup.
     await asyncio.sleep(300)  # 5 min warmup
     while True:
         try:
             from uk_management_bot.services.reconciliation import reconcile_buildings
             result = await reconcile_buildings()
             _logger.info("reconcile_buildings cycle: %s", result)
         except Exception:
             _logger.exception("Reconciliation error")
         await asyncio.sleep(3600)  # 1 hour

 reconcile_task = None
 if settings.INFRASAFE_WEBHOOK_ENABLED:
     reconcile_task = asyncio.create_task(_reconciliation_loop())
     _logger.info("Reconciliation loop started (1h interval, advisory-lock guarded)")

 И в shutdown-секции, добавить reconcile_task.cancel() рядом с
 task.cancel().

 Acceptance:
 - Раз в час в логах появляется reconcile_buildings cycle: {...}.
 - При --workers 2 только один из них логирует
 reconcile_buildings: in sync ...; второй — skipped (lock held).
 - Если building в UK создан но не дошёл в InfraSafe (симулировать выключив
 ENABLED=false на момент creation), reconcile найдёт и enqueued=1.

 Тест: новый tests/services/test_reconciliation.py
 - 3 кейса: no drift, missing in IS, advisory-lock concurrent.
 - Замокать fetch_infrasafe_external_buildings и queue_webhook.

 ---
 Зависимости и порядок merge

 PR-A (race fix)           ─┐
                            ├─→ PR-C (observability)
 PR-B (settings fix)       ─┘
                            │
                            └─→ PR-D (reconciliation)
                                      │
                                      ↓
                               Deploy + smoke

 - PR-A и PR-B параллельно — разные файлы, разные тесты.
 - PR-C после A (метрики осмысленнее после race fix).
 - PR-D после B (reconciler пользуется queue_webhook; warning от B
 поможет debug'ить если reconcile сам skipается).

 Полный объём: ~600 LOC (~150 кода + ~450 тестов и edge cases).
 Эффорт оценка: 1.5 рабочих дня на разработку + полдня smoke на deploy.

 ---
 Verification — после deploy

 1. Sanity settings (можно сразу после deploy)

 docker exec uk-management-api python -c "
 from uk_management_bot.config.settings import settings
 print('ENABLED:', settings.INFRASAFE_WEBHOOK_ENABLED)
 print('PUBSUB has password:', '@' in settings.REDIS_PUBSUB_URL_RESOLVED)
 "
 # expect: True, True

 2. Health outbox endpoint

 curl -sk https://infrasafe.uz/uk/api/health/outbox
 # expect: {"enabled": true, "pending": 0, "oldest_pending_age_sec": 0, "failed_last_24h": 0}

 3. Cycle log виден

 docker logs --since 30s uk-management-api 2>&1 | grep "process_outbox cycle"
 # expect: 0-3 строк за 30 секунд (depending on load)

 4. End-to-end: создать building → видно в InfraSafe ≤15s

 - В UK Dashboard /uk/dashboard/addresses создать новое здание.
 - Через ≤15s:
 docker exec infrasafe-postgres-1 psql -U infrasafe_app -d infrasafe -c "
   SELECT building_id, name, external_id FROM buildings WHERE external_id IS NOT NULL ORDER BY building_id DESC LIMIT 3;
 "
 # expect: новое здание с external_id

 5. Race fix — нет дубликатов в InfraSafe integration_log

 docker exec infrasafe-postgres-1 psql -U infrasafe_app -d infrasafe -c "
   SELECT entity_id, COUNT(*) FROM integration_log
    WHERE direction='from_uk' GROUP BY entity_id HAVING COUNT(*) > 1;
 "
 # expect: 0 rows

 6. Redis-pubsub auth errors исчезли

 docker logs --since 5m uk-management-api 2>&1 | grep -i "redis.*auth"
 # expect: пусто

 7. Reconciliation в логах (через ~5 минут после старта)

 docker logs --since 10m uk-management-api 2>&1 | grep "reconcile_buildings"
 # expect: "Reconciliation loop started" + (через 5 min) "in sync" / "drift detected"

 8. Manual drift recovery test

 - Временно установить INFRASAFE_WEBHOOK_ENABLED=false через
 docker compose stop api && docker compose up -d api, создать здание в UK.
 - Вернуть INFRASAFE_WEBHOOK_ENABLED=true, recreate.
 - Через ~1 час reconcile должен обнаружить drift и replay'ить событие
 в outbox; PR-A worker отправит в течение 10s.

 ---
 InfraSafe-side ChangeRequests (отдельный план, отдельная сессия)

 PR-D reconciliation корректно работает только если InfraSafe API даёт
 способ узнать "какие UK-buildings я уже знаю". Зависит от:

 CR-1: GET /api/buildings-metrics отдаёт external_id
 - Нужно проверить: возможно уже отдаёт (UK-сессии read-only access:
 docker exec infrasafe-app-1 sh -c "curl -s http://localhost:3000/api/buildings-metrics?limit=2" | jq .data[0]).
 - Если нет — добавить external_id в response shape в
 Infrasafe/src/controllers/buildingController.js или
 buildingsMetricsController.js (по результатам разведки).

 CR-2: Deterministic external_id mapping
 - Текущий: UK шлёт building.id (int) в webhook payload, InfraSafe
 присваивает random UUID — это плохо для reconciliation, нет
 однозначного match.
 - Решение: UK должен генерировать external_id как UUID5(namespace,
 str(building.id)) и передавать в payload; InfraSafe сохраняет как есть.
 - Файлы UK: services/webhook_sender.py::build_building_payload —
 добавить payload['building']['external_id'] = uuid.uuid5(...).
 - Файлы InfraSafe: src/models/Building.js::createFromUK или
 syncFromUK — использовать building.external_id из payload вместо
 генерации.

 CR-3: Internal auth for reconciliation fetcher (опционально)
 - Если решено не делать /buildings-metrics совсем публичным —
 ввести env UK_INTERNAL_AUTH_TOKEN, заголовок
 Authorization: Bearer <token>, проверка на стороне InfraSafe.

 Все три CR описаны для отдельной сессии в InfraSafe-репо. PR-D в UK
 может быть смержен без них — будет работать в degraded режиме (статистика
 по count'ам, не по конкретным building id'ам).

 ---
 Что НЕ делаем в этих PR

 - Не трогаем schema webhook_outbox (миграции не нужны).
 - Не двигаем outbox в отдельный uk-worker container — PR-A
 (SKIP LOCKED) решает race-проблему без новой инфры.
 - Не добавляем Celery/dramatiq/RQ — текущий asyncio.create_task loop +
 Postgres-only достаточно для текущей нагрузки.
 - Не делаем CLI replay tool — reconciliation (PR-D) автоматизирует
 то что вручную делалось через ad-hoc python -c '...'.
 - Не меняем поведение InfraSafe-receiver (он уже idempotent через
 isDuplicateEvent).

 ---
 Critical files (для исполнителя — read first)

 Прочитать перед началом:

 ┌─────────────────────────────────────────────────────┬──────────────────────────────────────────────────────────────────────────────────────┐
 │                        Файл                         │                                       Контекст                                       │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
 │ uk_management_bot/services/webhook_sender.py:73-228 │ queue_webhook + process_outbox (PR-A, PR-B, PR-C #2)                                 │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
 │ uk_management_bot/services/redis_pubsub.py          │ все 4 publish/subscribe (PR-B #3)                                                    │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
 │ uk_management_bot/config/settings.py                │ Settings class shape (PR-B #2)                                                       │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
 │ uk_management_bot/api/main.py:39-71                 │ lifespan + outbox loop (PR-C #1, PR-D #3)                                            │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
 │ uk_management_bot/api/addresses/router.py:296-334   │ building POST handler (caller queue_webhook — менять не нужно, только понимать flow) │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
 │ uk_management_bot/database/session.py:30-55         │ async_engine + AsyncSessionLocal (для reconciliation DB-access)                      │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
 │ uk_management_bot/database/models/webhook_outbox.py │ schema outbox                                                                        │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
 │ uk_management_bot/database/models/building.py       │ UK Building model (PR-D)                                                             │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
 │ uk_management_bot/database/models/yard.py           │ UK Yard model (нужен join для reconciliation)                                        │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
 │ Dockerfile.api:72                                   │ --workers 2 (источник race, не трогать)                                              │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────┤
 │ tests/test_webhook_sender.py                        │ существующие unit-тесты (не сломать)                                                 │
 └─────────────────────────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────────────┘

 ---
 Risk / Mitigation

 ┌──────────────────────────────────────────────────────────────────────┬───────────────────────────────────────────────────────────────┐
 │                                 Риск                                 │                          Mitigation                           │
 ├──────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤
 │ SKIP LOCKED повышает latency при низком concurrency                  │ LIMIT 50 мал, деградация ~5-10ms незаметна                    │
 ├──────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤
 │ /health/outbox 500 при недоступной БД                                │ try/except → возвращает {"error": "..."} со status 200        │
 ├──────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤
 │ Reconciliation грузит InfraSafe API                                  │ limit=5000 параметром; запрос раз в час; httpx timeout 30s    │
 ├──────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤
 │ Reconciliation реквест может failиться надолго → outbox accumulates  │ process_outbox независим, продолжит работу                    │
 ├──────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤
 │ Advisory lock не release при crash worker'а                          │ Postgres автоматически снимает at session end                 │
 ├──────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤
 │ REDIS_PUBSUB_URL_RESOLVED ломает старые .env с явным URL без auth    │ Backward-compat: явный REDIS_PUBSUB_URL env побеждает derived │
 ├──────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────┤
 │ PR-D deploy без CR-1/2 → reconciliation работает coarse (count-only) │ Документировано; warning в логах если external_id missing     │
 └──────────────────────────────────────────────────────────────────────┴───────────────────────────────────────────────────────────────┘

 ---
 Definition of Done

 - PR-A merged, тесты зелёные, tests/api/test_webhook_outbox_concurrency.py зелёный
 - PR-B merged, тесты зелёные, tests/services/test_redis_pubsub_url.py зелёный
 - PR-C merged, /health/outbox отвечает 200 на сервере
 - PR-D merged, tests/services/test_reconciliation.py зелёный
 - Deploy на demo (scripts/deploy-uk.sh или ручной recreate api)
 - Все 8 verification-чеков пройдены
 - В docker logs нет redis.*auth errors за 10 минут после deploy
 - Создан новый building в UK Dashboard — он появляется в InfraSafe
 за ≤15 секунд автоматически (без ручного trigger)