# Чек-лист деплоя модуля контроля доступа (access_control)

> _Последнее редактирование: 2026-07-10_

---

## ⚠️ PRC-05 (2026-07-10): цепочка миграций СЖАТА — читать ПЕРЕД разделом A2

Вся цепочка `001…037` (включая access-control `024→035`) **схлопнута в один baseline `001` + seed `002`**.
Ревизий `024`/`035` в коде **больше нет**. Все упоминания «`024→035`», «head `035`», «прогнать `025…035`» ниже — **историческая справка**, НЕ текущая процедура. Актуальный head = **`002`**.

**Fresh-install (пустая БД) — обычный `alembic upgrade head` применяет baseline `001`+`002`.** B0-предусловия (то, что делает АДМИН `uk_admin`, НЕ мигратор):
- рантайм-мигратор (`uk_bot`/`profk_bot`) = `NOSUPERUSER NOCREATEDB NOCREATEROLE`, но **владелец БД и схемы `public`** (иначе не создаст даже `alembic_version` — нужен `CREATE ON SCHEMA public`);
- роль `access_app_rw` создать **ЗАРАНЕЕ** под `uk_admin` (мигратор `NOCREATEROLE` её не создаст — DO-блок baseline тогда самоскипнет гранты). Если роль есть до `upgrade` — baseline навесит least-privilege гранты (append-only-таблицы: `SELECT,INSERT` без `UPDATE/DELETE`);
- append-only функция+4 триггера (§9.7) и `idx_requests_date_prefix` идут внутри baseline `001`.
- Гейт в CI: job **`b0-least-privilege`** воспроизводит именно этот сценарий (restricted-мигратор + pre-provision роли).

**Существующая БД, уже мигрированная на старый head (напр. прод @`037`) — НЕ `upgrade`, а прямой re-stamp на `002`** (процедура B6, выполнена на обоих продах 2026-07-10):
1. бэкап; 2. `git pull` (baseline-код) + `docker compose build api`;
3. **штамп в обход entrypoint:** `docker compose run --rm --no-deps --entrypoint "" api python -m alembic stamp 002 --purge` (`--purge` обязателен: старый head удалён из кода, обычный `stamp` упадёт на его резолве; **НЕ `up` первым** — entrypoint `upgrade head` от старого head рухнет);
4. `DROP FUNCTION IF EXISTS public.update_updated_at_column()` (мёртвый орфан, если есть);
5. `docker compose up -d api` → entrypoint `upgrade head` = no-op на `002`;
6. смоук: `alembic current`=`002`, api/bot healthy, `alembic check` = «No new upgrade operations detected».

Откат re-stamp: `UPDATE alembic_version SET version_num='<old_head>'` + образ со старой цепочкой.

---

**Статус:** разработка в `main` (PR #163–#167). **Прод частично задеплоен 2026-06-29** — см. блок ниже. Остаётся внешнее/конфиг: B (InfraSafe allowlist), D (TG-канал), A3 (точки въезда в UI), E (smoke).
**Дата составления:** 29 июня 2026
**Источник:** факты сверены с кодом на `main` (`99ce636`): `env.example`, `Caddyfile`, `docker-compose.yml`, `media_service/app/core/config.py`, `uk_management_bot/main.py`.

**Статус прод-деплоя (2026-06-29, хост `95.46.96.105:/home/infrasafe/uk`):**

- [x] **A1 — секреты в прод-`.env`** (4 `ACCESS_*` + `MEDIA_API_KEY`), + добавлены `ACCESS_EVENT_BROKER=redis`, `ACCESS_NONCE_BACKEND=redis`, `ACCESS_ENABLE_DOCS=false`.
- [x] **Код стека обновлён** `a0b66ea` (#162) → `99ce636` (#167) через `git pull --ff-only`.
- [x] **A2 — миграции** `024→035` применены entrypoint'ом `api` под `uk_bot`; 4 append-only триггера стоят; роль `access_app_rw` штатно self-skip (uk_bot без CREATEROLE); 15 access-таблиц. Бэкап до миграции: `uk_pre_access_2026-06-29-155506.dump`.
- [x] **A4 — `access-api` поднят**, healthy, без `RuntimeError`. ⚠️ **Host-порт 8086 занят `infrasafe-influxdb-1`** → переехал на **8087** (edge ходит по docker-сети `access-api:8080`, не через host-порт). В репо порт сделан конфигурируемым `${ACCESS_API_HOST_PORT:-8087}`; на проде временно hardcode 8087 → после коммита фикса сбросить дивергенцию: `git checkout docker-compose.yml && git pull`.
- [x] **A5 — бот ребилнут**, подписчик `access:resident_notify` слушает (redis-broker).
- [x] **D — TG-канал `access`** — `CHANNEL_ACCESS=-1004419783881` (`uk_media_access_private`), media-service пересобран + `init_channels.py`; end-to-end заливка `POST /media/upload-access` = HTTP 201, фото в канале.
- [ ] **B — InfraSafe allowlist** (2 location на `uk-access-api:8080`) — **передано InfraSafe 2026-06-29, ждём раскатку** (см. раздел B).
- [ ] **A3 — точки въезда в UI** — не сделано.
- [ ] **E — прод-smoke** — после B/D/A3.

Полный порядок остатка: **B (InfraSafe edge) → A3 (точки въезда в UI) → E (smoke)**.

---

## A. Наша сторона (до прод-деплоя)

- [ ] **A1. Положить секреты в прод-`.env`** — 4 доменных + медиа-ключ (раздел C).
  Без `ACCESS_SNAPSHOT_SIGNING_SEED` / `ACCESS_DEVICE_HMAC_SEED` сервис падает `RuntimeError` на старте; без `ACCESS_PHOTO_URL_SECRET` / `ACCESS_CODE_SECRET` — падает при работе с фото/кодами (дефолтов в коде намеренно нет, §9.1/§11).
  Не-секретный конфиг уже зашит в compose: `ACCESS_NONCE_BACKEND=redis`, `ACCESS_EVENT_BROKER=redis`, `MEDIA_SERVICE_URL=http://media-service:8000`.

- [ ] **A2. Прогнать миграции 025–035 рабочей ролью `uk_bot`** (НЕ привилегированной). ⚠️ Контринтуитивный, но проверенный на dev нюанс. **[ИСТОРИЧЕСКОЕ после PRC-05 — миграций 025–035 больше нет, см. baseline `001`+`002` и B0-предусловия в блоке PRC-05 вверху.]**
  Это **11 ревизий** `025`…`035` (включая `030 = barrier_commands_lease_columns`), цепочка от `024`, head `035`. `028` ставит **append-only триггеры (`CREATE TRIGGER`)** на 4 журнальные таблицы; `031` создаёт роль `access_app_rw` + DB-гранты.
  - Гнать **под `uk_bot`** (дефолт контейнера `uk-management-api`; `access-api` миграции не применяет). Почему именно `uk_bot`: миграции `030/032/034/035` создают таблицы/колонки — кто создал, тот владелец. Под `uk_admin` новые объекты достались бы `uk_admin`, и рантайм-роль `uk_bot` **потеряла бы к ним доступ** → сервисы падают. Миграции спроектированы под запуск рабочей ролью.
  - **028 (триггеры)** ставятся нормально — `uk_bot` владеет таблицами. Это и есть реальная защита append-only в пилоте (триггер бьёт даже владельца — проверено: `DELETE`/`UPDATE` → `ERROR: append-only violation … §9.7`).
  - **031 (роль+гранты)** под `uk_bot` (`NOSUPERUSER`/без `CREATEROLE`) **штатно деградирует**: DO-блок ловит `insufficient_privilege`, пишет `NOTICE: access_app_rw not created … grants skipped`, `RETURN` — миграция НЕ падает. Этот grant-слой — задел на будущий least-privilege коннект; для пилота не нужен (access-api ходит как `uk_bot`). Включить опционально потом — чистым SQL под `uk_admin` (см. план A2, Шаг 5).
  - После апгрейда сверить **реальную схему** (`pg_trigger`, `to_regclass`), а не `alembic_version` (урок про migration-drift).
  - Подробный пошаговый план с командами и бэкапом — в этом файле ниже не дублируется; см. ответ ассистента «A2 пошагово».

- [ ] **A3. Завести точки въезда через UI «Оборудование»**: зоны → въезды → камеры/шлагбаумы/edge-контроллеры. Сгенерировать **device api-key каждому контроллеру** (показывается один раз, далее rotate). Реальная камера не нужна — проверяется симулятором/тест-событием.

- [ ] **A4. Поднять `access-api` в прод-compose.** Сервис описан (`Dockerfile.access`, порт `127.0.0.1:8086:8080`, общая `uk-network`/postgres/redis). В проде выставить **`ACCESS_ENABLE_DOCS=false`** (в `env.example` стоит `true`).

- [ ] **A5. Ребилд бота с `ACCESS_EVENT_BROKER=redis`.** Фоновый подписчик `access:resident_notify` (уведомления жителям) живёт в боте (`uk_management_bot/main.py:401`, запускается только при `ACCESS_EVENT_BROKER=redis`). Без ребилда уведомления жителям не пойдут.

- [ ] **A6. Долги пост-пилота (НЕ блокеры деплоя, в TODO):** mTLS edge↔controller (отложен до реального edge), WS-revocation, rate-limit, реальный TG-канал + retention фото (см. D — сейчас plumbing + синтетика).

---

## B. InfraSafe (внешнее, их сторона) — передано 2026-06-29, ждём раскатку

Прод-edge = `infrasafe-nginx-1` (`nginx.production.conf`), нашего `uk-caddy` на проде нет → nginx проксирует `/uk/*` прямо в наши контейнеры. nginx подключён к `uk-network` + `infrasafe_leaflet-network` → резолвит наши сервисы. Нужны 2 выделенных `location` (длиннее `^~ /uk/api/` и `^~ /uk/ws/v2/` → longest-prefix перехватит):

- [ ] **B1. REST:** `^~ /uk/api/v1/access/` → `rewrite ^/uk/api/(.*)$ /api/$1` → **`uk-access-api:8080`** (= `/api/v1/access/X`).
- [ ] **B2. WebSocket:** `^~ /uk/ws/v1/access/` → `rewrite ^/uk/ws/(.*)$ /ws/$1` → **`uk-access-api:8080`**, `Upgrade`/`Connection` + `read/send timeout 86400s` (live-экран охраны §9.6).
- **Upstream-имя:** резолвятся оба (`uk-access-api` = container_name, `access-api` = compose-alias, оба → один контейнер на `uk-network`); договорились на **`uk-access-api:8080`** ради консистентности с их `uk-management-api:8080`.
- **Rate-limit:** их зона `uk_api` (~120 r/min/IP burst 60) для пилота достаточна — через edge идёт только дашборд/TWA (human), ingestion камер/шлагбаумов НЕ через edge (device-auth внутри). Поднять только если операторы за одним NAT-IP ловят 429.
- **CSP не трогать** — `connect-src` `/uk/`-страниц уже содержит `'self'` + `wss://infrasafe.uz` (WS same-origin).
- **Проверка после reload:** `curl -ski https://infrasafe.uz/uk/api/v1/access/events` → **401/403 = ок**, **404 = location не подхватился**, **502 = не то DNS-имя**.

> До раскатки любой access-эндпоинт на проде отдаёт 404 на edge; дашборд/TWA и A3-через-UI недоступны.

---

## C. Секреты (сгенерировать и положить в прод-`.env`)

| Переменная | Назначение (§ТЗ) | Команда генерации |
| --- | --- | --- |
| `ACCESS_SNAPSHOT_SIGNING_SEED` | Ed25519-подпись offline-snapshot (§8.2) | `python -c "import secrets;print(secrets.token_hex(32))"` (64 hex) |
| `ACCESS_DEVICE_HMAC_SEED` | HMAC device-auth (§9.1) | `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `ACCESS_PHOTO_URL_SECRET` | HMAC signed-URL фото (§11) | `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `ACCESS_CODE_SECRET` | HMAC одноразовых гостевых кодов (§9.3) | `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `MEDIA_API_KEY` | X-API-Key к медиа-сервису | должен **входить в `MEDIA_API_KEYS`** медиа-сервиса |

- [ ] Все 5 значений сгенерированы и положены в прод-`.env`.
- [ ] `MEDIA_API_KEY` совпадает с одним из ключей в `MEDIA_API_KEYS` медиа-сервиса.
- [ ] Не-секретный конфиг в `.env`: `CHANNEL_ACCESS=<id канала>` (см. D), `ACCESS_ENABLE_DOCS=false`.
- [ ] Секреты НЕ коммитятся и НЕ выводятся в логи.

---

## D. TG-канал access + медиаагент

Фото проездов (§11) льются в медиа-сервис в **отдельный канал `access`**, изолированно от заявок. В одном канале две под-категории: `access_overview` (общий вид авто) и `access_plate` (фото номера). Сейчас это **plumbing + синтетика**; для прод-фото:

- [ ] **D1. Создать новый приватный TG-канал** под access-фото (отдельно от канала заявок).
- [ ] **D2. Добавить бота медиа-сервиса администратором** канала (право постить).
- [ ] **D3. Узнать числовой `channel_id`** (формат `-100…`).
- [ ] **D4. Прописать `CHANNEL_ACCESS=-100…`** в env медиа-сервиса и прогнать `init_channels.py`.
  Канал `access` (`uk_media_access_private`) регистрируется **только если `CHANNEL_ACCESS` задан** (`media_service/app/core/config.py:46`, `init_channels.py:62`); иначе домен просто не используется, а загрузка фото вернёт `503 access channel not configured`.
- [ ] **D5. Retention фото** (срок хранения §11) — сейчас заглушка, прод-долг.

> Механика: access-api грузит фото отдельным device-auth эндпоинтом **вне пути решения** (латентность §10.2) → `camera_events.*_photo_url = media://{id}`; отдача — через signed-URL (`ACCESS_PHOTO_URL_SECRET`).

---

## E. Прод-smoke после деплоя

- [ ] **E1.** `access-api` поднялся без `RuntimeError` (логи: секреты A1 на месте).
- [ ] **E2.** `GET /api/v1/access/...` через прод-edge отдаёт не 404 (B1 применён).
- [ ] **E3.** WS-панель охраны `/ws/v1/access/...` подключается (B3 same-origin).
- [ ] **E4.** Тест-событие проезда от симулятора-контроллера (device api-key из A3) → решение принимается, событие появляется на экране охраны.
- [ ] **E5.** Загрузка фото проезда → попадает в TG-канал `access` (D), отдаётся по signed-URL.
- [ ] **E6.** Уведомление жителю приходит в бот (A5 — подписчик `access:resident_notify` активен).
- [ ] **E7.** Журнальные таблицы append-only: попытка `UPDATE`/`DELETE` отклоняется триггером (A2 `028`).

---

**Кратко «можно деплоить, когда»:** C (секреты) → D (канал `access`) → A2 (миграции под `uk_bot`, head `035`, триггеры стоят) → A4/A5 (compose + ребилд бота) → B (InfraSafe добавил 2 префикса) → A3 (точки въезда в UI) → E (smoke зелёный).

---

## Приложение: раннбук A2 (команды)

> Контейнеры на проде: `uk-management-api` (alembic), `uk-postgres`. БД `uk_management`, рабочая роль `uk_bot`.
> Проверено на dev-стеке: цепочка `024→035` применяется чисто, 4 триггера встают, append-only реально блокирует `DELETE`/`UPDATE`.

> ⚠️ **ИСТОРИЧЕСКИЙ блок (до PRC-05).** Ревизий `024`/`035` в коде больше нет — head теперь `002`.
> Для fresh-install/re-stamp сегодня используй блок **PRC-05** в начале файла, а не команды ниже.

```bash
# 0. Бэкап БД
docker exec uk-postgres pg_dump -U uk_bot -d uk_management -Fc -f /tmp/uk_pre_access.dump
docker cp uk-postgres:/tmp/uk_pre_access.dump ./

# 1. Пред-проверки (ничего не меняют)
docker exec uk-management-api alembic current   # ждём: 024
docker exec uk-management-api alembic heads      # ждём: ровно один head 035

# 2. (опц.) offline-SQL на ревью
docker exec uk-management-api alembic upgrade 024:head --sql > /tmp/access_migr_review.sql

# 3. Применить рабочей ролью uk_bot (дефолт контейнера)
docker exec uk-management-api alembic upgrade head
#  NOTICE: access_app_rw not created … grants skipped  — ЭТО НОРМА (031 деградирует штатно).
#  Любой ERROR/traceback — стоп.

# 4. Проверка
docker exec uk-management-api alembic current    # ждём: 035 (head)
docker exec uk-postgres psql -U uk_bot -d uk_management -c \
"SELECT tgrelid::regclass AS tbl, tgname FROM pg_trigger WHERE NOT tgisinternal
 AND tgrelid::regclass::text IN ('access_events','access_decisions','manual_openings','access_audit_logs') ORDER BY 1;"
#  ждём 4 строки
docker exec uk-postgres psql -U uk_bot -d uk_management -c \
"SELECT to_regclass('public.access_events'), to_regclass('public.presence_sessions'),
        to_regclass('public.access_passes'), to_regclass('public.barrier_commands');"
#  ждём не-NULL во всех
```

**Шаг 5 (опционально, defense-in-depth §9.7):** включить grant-слой `access_app_rw` — нужно только если access-api будет коннектиться отдельной least-privilege ролью (не текущий пилот). Выполняется под `uk_admin` (суперюзер) чистым SQL — DO-блок-копия логики 031 (см. историю чата «A2 пошагово, Шаг 5»); владения таблиц не меняет.
