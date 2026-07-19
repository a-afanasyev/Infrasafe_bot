# RUNBOOK — эксплуатация UK Management

> _Последнее редактирование: 2026-07-06_

Операционный справочник по прод-стеку UK Management (Telegram-бот + REST API + React-дашборд + медиа-сервис + контроль доступа). Истина — код и compose-файлы; при расхождении доверять им, а не этому документу.

> Пилот/трайл. Все заявки на проде — тестовые. Cutover-релизы выполняются как обычный релиз, без ночного окна и stop-the-world.

---

## 1. Карта контейнеров и портов

Прод-стек поднимается двумя compose-файлами: `docker-compose.yml` + `docker-compose.media.yml`. Контроль доступа (`access-api`) объявлен в основном `docker-compose.yml`.

| Контейнер | Сервис (compose) | Образ / сборка | Host-порт (127.0.0.1) | Порт в контейнере | Роль |
|---|---|---|---|---|---|
| `uk-management-bot` | `app` | `Dockerfile` | — (health 8000 внутри) | 8000 | Telegram-бот (aiogram) |
| `uk-management-api` | `api` | `Dockerfile.api` | `8085` | 8080 | REST + WS дашборда, применяет миграции |
| `uk-access-api` | `access-api` | `Dockerfile.access` | `8087` (`ACCESS_API_HOST_PORT`) | 8080 | Домен контроля доступа (ANPR/шлагбаумы) |
| `uk-frontend` | `frontend` | `frontend/Dockerfile` | `3002` | 80 | Nginx со сборкой SPA дашборда |
| `uk-postgres` | `postgres` | `postgres:15-alpine` | `5432` | 5432 | PostgreSQL (общая БД `uk_management`) |
| `uk-redis` | `redis` | `redis:7-alpine` | `6379` | 6379 | Redis (кэш, rate-limit, pub/sub) |
| `uk-media-service` | `media-service` | `media_service/Dockerfile` | `8009` | 8000 | Медиа-сервис (фото), лог. БД `uk_media` |

Ссылки: `docker-compose.yml:8` (`app`), `:67` (`api`), `:113` (`access-api`), `:173` (`postgres`), `:220` (`redis`), `:254` (`frontend`); `docker-compose.media.yml:9` (`media-service`).

Заметки:
- Все host-порты биндятся только на `127.0.0.1` — снаружи доступ идёт через edge-nginx (InfraSafe), не напрямую.
- `access-api` host-порт = **8087** (`docker-compose.yml:157`). 8086 на shared-деплое занят influxdb — не переназначать на него.
- Edge ходит в `access-api:8080` по docker-сети `uk-network`; host-порт нужен только для локальной диагностики.
- Сеть фиксированного имени `uk-network` (`docker-compose.yml:283`) — без префикса каталога проекта.

Домен: `infrasafe.uz`. Edge/реверс-прокси: контейнер `infrasafe-nginx-1` (сторона InfraSafe), дашборд смонтирован под префиксом `/uk/`, API — под `/uk/api/*` с prefix-allowlist SEC-22.

---

## 2. Каноничная выкатка на прод

Выполнять из корня репозитория на прод-хосте. Оба compose-файла указываются в каждой команде.

```bash
# 1. Забрать код
git pull --ff-only

# 2. Пересобрать образы (bot/api/access-api/frontend/media-service)
docker compose -f docker-compose.yml -f docker-compose.media.yml build

# 3. Поднять с пересозданием контейнеров, чтобы подхватить .env и новые образы
docker compose -f docker-compose.yml -f docker-compose.media.yml up -d --force-recreate

# 4. Убедиться, что миграции применились (см. §4)
docker logs uk-management-api 2>&1 | grep "Migrations complete"
```

Критично:
- **НИКОГДА не использовать `--remove-orphans`.** На прод-хосте живут контейнеры вне этого compose-набора (`uk-caddy`, и при рассинхроне — `uk-media-service`); `--remove-orphans` их снесёт.
- **`--force-recreate` обязателен**, чтобы контейнер перечитал `.env` (иначе изменённые переменные не подхватятся при `up -d` без пересоздания).
- **ARCH-106 Phase 1 (Doppler):** `app`/`api`/`access-api`/`migrate`/`resource-api`/`resource-worker` получают секреты из Doppler, не из `.env` — каждая команда `build`/`run`/`up` из этого раздела для этих сервисов должна идти через `doppler run --project uk-management --config <profk|infrasafe> -- ...` и с `--no-deps` (не трогать `postgres`/`redis`/`resource-postgres` — они вне routine-Doppler-деплоя). Точные wrapped-команды и bootstrap Doppler на хосте → `.claude/skills/uk-deploy/SKILL.md`.
- Сборка/деплой по SSH — запускать в detached/`nohup`-режиме, чтобы обрыв сессии не прервал `build` (см. память по detached-build).
- Точечная пересборка одного сервиса (например, только фронт):
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.media.yml build uk-frontend  # имя сервиса: frontend
  docker compose -f docker-compose.yml -f docker-compose.media.yml up -d --force-recreate frontend
  ```
  Проверить имя сервиса (`frontend`, не `uk-frontend`) — команды compose оперируют именами сервисов, а не `container_name`.

---

## 3. Откат

```bash
# 1. Вернуться на предыдущий рабочий коммит/тег
git log --oneline -n 10          # найти предыдущий рабочий SHA
git checkout <good-sha>          # или git reset --hard <good-sha> — ТОЛЬКО с подтверждением владельца

# 2. Пересобрать и пересоздать
docker compose -f docker-compose.yml -f docker-compose.media.yml build
docker compose -f docker-compose.yml -f docker-compose.media.yml up -d --force-recreate
```

Важно про откат миграций:
- Alembic-миграции **не откатываются автоматически** откатом кода. Прод-схема останется на `head` предыдущего деплоя.
- Откат схемы (`alembic downgrade`) выполнять только вручную и только при подтверждённой необходимости — многие миграции необратимы/содержат backfill. Downgrade запускать в `uk-management-api` (только там есть alembic — см. §4).
- Деструктивные git-операции (`reset --hard`, `force push`) — только с явным подтверждением владельца.

---

## 4. Проверка миграций

**PR-7 (F-01) раскатан на оба прода 2026-07-15.** `scripts/entrypoint-api.sh`/`entrypoint-access.sh` больше НЕ гоняют `alembic upgrade head` — только read-only preflight (`uk_management_bot/dbops/db_preflight.py`), сравнивающий `alembic_version` с зашитым в образ на этапе сборки `EXPECTED_ALEMBIC_HEAD`; при рассинхроне контейнер падает `exit 1` ДО старта Uvicorn. Миграции — отдельный one-shot `docker compose run --rm --name uk-migrate migrate` (`scripts/entrypoint-migrate.sh`: `alembic upgrade head` → `uk_management_bot/dbops/acl_reconcile.py` → `alembic check`), **обязателен перед каждым `up -d api access-api app`** — забытый шаг не «тихо не сломается», а уронит preflight на первом же старте контейнера.

В образе бота (`uk-management-bot`) alembic по-прежнему отсутствует, `scripts/entrypoint-bot.sh` просто запускает процесс.

Владелец схемы (`public`) и всех объектов — `uk_migration_owner` (`NOLOGIN`); миграции выполняются под `uk_migrator` (`LOGIN NOINHERIT`) через `SET SESSION ROLE uk_migration_owner` в `alembic/env.py`. Runtime-контейнеры (`app`/`api`/`access-api`) подключаются под `uk_bot_runtime`/`uk_api_runtime`/`uk_access_runtime` — только DML через `uk_app_rw`/`access_app_rw`, без DDL/ownership. Credentials — `.secrets/roles/.env.<role>` (не в общем `.env`), генерируются `docker compose run --rm --name uk-provision-roles provision-roles`. Полный verifier-log обоих rollout'ов: `docs/audit/2026-07-15-pr7-rollout.md`.

Текущий head: `003` (проверить `alembic/versions/`, если сомнение).

```bash
# Успех миграций в логах api
docker logs uk-management-api 2>&1 | grep -E "Running database migrations|Migrations complete"

# Текущая ревизия схемы в БД (запускать в api-контейнере — alembic только там)
docker exec uk-management-api python -m alembic current

# Сверить с head репозитория
docker exec uk-management-api python -m alembic heads

# Реальная запись в БД (когда есть подозрение на дрейф alembic_version vs схема)
docker exec uk-postgres psql -U uk_bot -d uk_management -c "SELECT version_num FROM alembic_version;"
```

Мина дрейфа: `alembic_version` может опережать реальную схему (штамп без применённого DDL). При подозрении — проверять фактическое наличие столбцов/таблиц через `information_schema`, а не только `alembic current`.

---

## 5. Добавление edge-allowlist (SEC-22)

Edge-nginx (InfraSafe, контейнер `infrasafe-nginx-1`) проксирует `/uk/api/*` по prefix-allowlist. **Новый SPA-эндпоинт `/api/v2/*` (или иной новый префикс) вернёт 404 на edge, пока его префикс не добавлен в allowlist.** Симптом бывает замаскирован (например, «MFA Invalid code» при исправном OTP — на самом деле 404 на edge).

Файл: `nginx.production.conf` (сторона InfraSafe/edge — проверить точный путь на прод-хосте, репозиторий может быть отдельный).

Процедура:
```bash
# 1. Добавить префикс в allowlist в nginx.production.conf
#    (location-блок с проксированием на нужный upstream)

# 2. Проверить синтаксис
docker exec infrasafe-nginx-1 nginx -t

# 3. Применить без рестарта (graceful reload)
docker exec infrasafe-nginx-1 nginx -s reload
```

Тонкость сопоставления префиксов: путь со слэшем на конце (`profile/`) не матчит bare-префикс `/api/v2/profile` — расхождение слэша ломало вход в дашборд. Сверять форму префикса точно с тем, что шлёт SPA.

---

## 6. Свежие грабли (обязательно к прочтению перед деплоем)

| Грабля | Симптом | Что делать |
|---|---|---|
| `--remove-orphans` | Снесены `uk-caddy` / `uk-media-service` | Никогда не передавать этот флаг в `up`/`down` на проде |
| `.env` duplicate-key | Compose берёт **последнее** значение дублирующегося ключа → «загадочно неверная» переменная | `grep -cE '^KEY=' .env` должен вернуть `1`; убрать дубли |
| `.env` не подхватился | Изменил `.env`, но контейнер работает по-старому | `up -d --force-recreate` (обычный `up -d` не перечитывает env без пересоздания) |
| Новый `/api/v2/*` → 404 на edge | SPA-запрос 404/«MFA Invalid code» при исправном коде | Добавить префикс в edge-allowlist SEC-22 (§5) |
| access-api порт | Конфликт с influxdb | Host-порт = 8087, НЕ 8086 (`docker-compose.yml:157`) |
| Stale-chunk фронта | «Ошибка загрузки страницы» на lazy-роутах у открытой сессии после редеплоя фронта (404 стухшего chunk) | Авто-reload по `vite:preloadError` (PR #175); воркэраунд — `Ctrl+Shift+R` |
| Redis под паролем | pub/sub/rate-limit не работают, если `REDIS_PASSWORD` задан, но URL без auth | `REDIS_PUBSUB_URL` не хардкодить — деривится из `REDIS_URL` с паролем (`docker-compose.yml:83-87`) |
| compose orphan `uk-caddy` | — | Прод-деплой всегда `-f docker-compose.yml -f docker-compose.media.yml`, без `--remove-orphans` |

---

## 7. Базовый troubleshooting

Прод использует реальные имена контейнеров (`uk-*`), **не** `*-dev` (те — из `docker-compose.dev.yml`, локальная разработка).

```bash
# Статус и health всех сервисов
docker compose -f docker-compose.yml -f docker-compose.media.yml ps

# Логи
docker logs uk-management-bot --tail 50
docker logs uk-management-api --tail 50
docker logs uk-access-api --tail 50
docker logs uk-media-service --tail 50

# PostgreSQL: готовность и таблицы
docker exec uk-postgres pg_isready -U uk_bot -d uk_management
docker exec uk-postgres psql -U uk_bot -d uk_management -c "\dt"
docker exec uk-postgres psql -U uk_bot -d uk_management -c "SELECT COUNT(*) FROM requests;"

# Redis: ping (с паролем, если задан REDIS_PASSWORD)
docker exec uk-redis redis-cli ping
docker exec uk-redis sh -c 'redis-cli -a "$REDIS_PASSWORD" ping'   # если Redis под паролем

# Health-эндпоинты (изнутри контейнеров)
docker exec uk-management-api curl -sf http://localhost:8080/health
docker exec uk-access-api    curl -sf http://localhost:8080/health
docker exec uk-media-service curl -sf http://localhost:8000/api/v1/health
```

Диагностика по симптомам:
- Дашборд не грузится / 404 на API → проверить edge-allowlist SEC-22 (§5) и что `uk-frontend`/`api` подняты.
- Бот молчит → `docker logs uk-management-bot`; в UZ нет IPv6-egress, стек форсит IPv4 (`docker-compose.yml:22-24`) — при `TelegramNetworkError` проверять этот sysctl.
- Миграции не применились → §4; `api` не стартует, если `alembic upgrade head` упал.
- «Странная» переменная окружения → проверить дубли в `.env` (§6).

---

## 8. Ссылки

- Dev-окружение и добавление страниц: `docs/DEVELOPMENT.md`
- Фронтенд: `frontend/README.md`
- Локализация: `docs/LOCALIZATION_GUIDE.md`
- Compose: `docker-compose.yml`, `docker-compose.media.yml`, `docker-compose.dev.yml`
- Entrypoint API (миграции): `scripts/entrypoint-api.sh`
