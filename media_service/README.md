# UK Media Service

FastAPI-сервис хранения фото/видео: байты — в приватных Telegram-каналах
(свой бот), метаданные — в БД `uk_media`. Эндпоинты, потребители, ручной
поиск фото через VPN и контракт с клиентами — `docs/tech/MEDIA_SERVICE.md`.
Деплой и секреты (Doppler, роль `uk_media_owner`) — `.claude/skills/uk-deploy/SKILL.md`.

## Устройство

```
app/
  main.py              lifespan (preflight схемы, общий Telegram-клиент), X-API-Key middleware
  api/v1/media.py      загрузка, выдача байтов, поиск, publication-lock, обслуживание
  api/v1/health.py     /health (без проверок), /health/ready (БД; цель healthcheck)
  services/
    media_storage.py   Telegram ↔ БД: загрузка, архив/удаление (саги), каналы
    telegram_client.py скачивание с общим бюджетом 25 с и ретраями
    media_search.py    поиск/статистика/timeline (ручной поиск владельца)
    preview_cache.py   дисковый кэш превью публичной витрины
  core/config.py       настройки; в проде fail-fast на пустые каналы/ключи/SECRET_KEY
migrations/            идемпотентные SQL (run_migrations.py, шаг media-migrate)
schema_baseline/       прод-схема до 0001 — для дрейф-гейта
```

Схему пустой БД строит `create_all` при старте, изменения — `migrations/*.sql`
(перевод на alembic — бэклог A9-P3-33).

## Тесты

Как в CI (`.github/workflows/ci.yml`, джоба `media-tests`): Telegram мокается,
основная БД — sqlite, дрейф-гейт и поиск — на настоящем PostgreSQL.

```bash
cd media_service
pip install --require-hashes -r requirements-dev.txt
MEDIA_PG_DRIFT_URL=postgresql+psycopg2://media:<pw>@localhost:5432/uk_media \
MEDIA_REQUIRE_PG_TESTS=1 pytest -q --cov=app --cov=run_migrations --cov-fail-under=73
```

`test_upload.py` — ручной smoke живого стека, из pytest исключён (`pytest.ini`).

## Конфигурация

Секреты (`TELEGRAM_BOT_TOKEN`, `SECRET_KEY`, `MEDIA_API_KEYS`, `DATABASE_URL`)
на хостах приходят из Doppler с префиксом `MEDIA_`; несекретное (каналы,
`ALLOWED_ORIGINS`) — `media_service/.env` (см. `.env.example`).
