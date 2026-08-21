---
name: uk-deploy
description: Use when deploying UK Management System to prod, running Alembic migrations, rotating role passwords, bootstrapping/rotating Doppler secrets, or troubleshooting alembic/preflight/role-ownership/Doppler issues on profk.uz or infrasafe.uz. Covers the post-PR-7 least-privilege role setup, the ARCH-106 Phase 1 Doppler secret cutover, and the mandatory migrate-before-up deploy sequence.
---

# UK deploy & migrations runbook

История Alembic сжата в baseline `001` + seed `002` (PRC-05, 2026-07-10); оба прода на `alembic @003`. CI-дрейф-гейт: `alembic upgrade head` + `alembic check`.

## PR-7 (F-01) — раскатан на оба прода 2026-07-15

`uk_bot`/`profk_bot` больше НЕ владелец схемы — owner теперь `uk_migration_owner` (NOLOGIN). Runtime-контейнеры используют выделенные `uk_bot_runtime`/`uk_api_runtime`/`uk_access_runtime` (только DML через `uk_app_rw`/`access_app_rw`, credentials в `.secrets/roles/.env.<role>`, НЕ в общем `.env`).

`scripts/entrypoint-api.sh`/`entrypoint-access.sh` больше НЕ гоняют `alembic upgrade head` — только read-only preflight (`uk_management_bot/dbops/db_preflight.py`, сверяет `alembic_version` с зашитым в образ `EXPECTED_ALEMBIC_HEAD`).

## ARCH-106 — Doppler cutover (секреты приложения)

`app`/`api`/`access-api`/`migrate`/`resource-api`/`resource-worker` (Phase 1) и `media-service` (Phase 2) получают секреты (`BOT_TOKEN`, `ADMIN_PASSWORD`, `JWT_SECRET`, `INVITE_SECRET`, `ACCESS_*`, `MEDIA_*`, `REDIS_PASSWORD`, `RESOURCE_*` и т.п.) из Doppler через `doppler run --`, не из `.env`. Статус и verifier-итог — `docs/audit/2026-05-20-backlog.md`, запись ARCH-106.

**Осознанные carve-out'ы** (НЕ в Doppler, так задумано): `.env.postgres` + `.secrets/roles/.env.<role>` — PR-7 provision-механизм со своим lifecycle (генерация на хосте, никогда не проходят через транскрипт); `INFRASAFE_WEBHOOK_URL`/`ENABLED` — не секреты; `DOPPLER_*` — служебные имена CLI; локальные dev-`.env`.

**Динамические `ACCESS_DEVICE_SECRET__<ref>`** (per-device override HMAC, `access_control/services/device_auth.py`): на проде не используются — секрет устройства выводится детерминированно из `ACCESS_DEVICE_HMAC_SEED` (он в Doppler). Прокинуть их «автоматически» невозможно: `doppler run` кладёт значения в окружение compose-процесса, а контейнер получает только перечисленные в `environment:` имена — динамическое имя туда не попадёт. Если override понадобится: положить ключ в Doppler И добавить ЯВНУЮ строку `- ACCESS_DEVICE_SECRET__<ref>=${ACCESS_DEVICE_SECRET__<ref>:-}` в `environment:` у `access-api`, затем деплой.

### Имена в Doppler ≠ имена в контейнере (media)

media-service исторически использует общие имена (`SECRET_KEY`, `DATABASE_URL`), поэтому в плоском Doppler-конфиге они живут с префиксом, а compose делает mapping:

| В Doppler | В контейнере media |
|---|---|
| `MEDIA_BOT_TOKEN` | `TELEGRAM_BOT_TOKEN` |
| `MEDIA_SECRET_KEY` | `SECRET_KEY` |
| `MEDIA_API_KEYS` | `MEDIA_API_KEYS` |
| `MEDIA_DATABASE_URL` | `DATABASE_URL` (полный URI целиком) |

**Правило клиентских ключей**: `MEDIA_API_KEY` обязателен и обязан входить в список `MEDIA_API_KEYS` (access-api требует именно его — `access_control/integrations/media.py`); `MEDIA_SERVICE_API_KEY` опционален, но если задан — тоже обязан входить в список (основной api предпочитает его, fallback на `MEDIA_API_KEY`).

### Bootstrap Doppler CLI на хосте (один раз на хост)

Service token (НЕ personal login), scoped на `--project uk-management --config <profk|infrasafe>`, создаётся в Doppler-дашборде (Project → Access → Service Tokens). Из реального deploy-каталога (`/opt/uk` на profk, `~/uk` на infrasafe):

```bash
read -rs DOPPLER_TOKEN   # вставить service-токен, Enter (ввод скрыт)
printf '%s\n' "$DOPPLER_TOKEN" | doppler configure set token --scope "$(pwd)"
unset DOPPLER_TOKEN
doppler run --project uk-management --config <profk|infrasafe> -- true && echo "doppler bootstrap OK"
```

### Рутинный деплой (после bootstrap)

На infrasafe/105 media-service подключается overlay-файлом — оба `-f` обязательны в КАЖДОЙ команде (`docker-compose.media.yml`).

⚠️ **С 2026-07-31 (AUD6-P2-38) `docker-compose.profk.yml` — больше НЕ standalone, а ТОНКИЙ override поверх базового `docker-compose.yml`.** Ломает мышечную память деплоя: на profk теперь ТОЖЕ оба `-f` в КАЖДОЙ команде — `-f docker-compose.yml -f docker-compose.profk.yml` (порядок важен, базовый первым). Одиночный `-f docker-compose.profk.yml` теперь = битый конфиг (в override нет build/образов большинства сервисов) — compose упадёт, а не поднимет урезанный стек.

```bash
export DEPLOY_UID=$(id -u) DEPLOY_GID=$(id -g)
# infrasafe/105 (COMPOSE=«-f docker-compose.yml -f docker-compose.media.yml»):
doppler run --project uk-management --config infrasafe -- docker compose -f docker-compose.yml -f docker-compose.media.yml build api access-api app migrate
doppler run --project uk-management --config infrasafe -- docker compose -f docker-compose.yml -f docker-compose.media.yml run --rm --no-deps --name uk-migrate migrate
doppler run --project uk-management --config infrasafe -- docker compose -f docker-compose.yml -f docker-compose.media.yml up -d --no-deps --wait --wait-timeout 120 api
doppler run --project uk-management --config infrasafe -- docker compose -f docker-compose.yml -f docker-compose.media.yml up -d --no-deps --wait --wait-timeout 120 access-api
doppler run --project uk-management --config infrasafe -- docker compose -f docker-compose.yml -f docker-compose.media.yml up -d --no-deps --wait --wait-timeout 120 app

# profk (те же шаги, COMPOSE=«-f docker-compose.yml -f docker-compose.profk.yml», --config profk):
doppler run --project uk-management --config profk -- docker compose -f docker-compose.yml -f docker-compose.profk.yml build api access-api app migrate
doppler run --project uk-management --config profk -- docker compose -f docker-compose.yml -f docker-compose.profk.yml run --rm --no-deps --name uk-migrate migrate
doppler run --project uk-management --config profk -- docker compose -f docker-compose.yml -f docker-compose.profk.yml up -d --no-deps --wait --wait-timeout 120 api
doppler run --project uk-management --config profk -- docker compose -f docker-compose.yml -f docker-compose.profk.yml up -d --no-deps --wait --wait-timeout 120 access-api
doppler run --project uk-management --config profk -- docker compose -f docker-compose.yml -f docker-compose.profk.yml up -d --no-deps --wait --wait-timeout 120 app
```

`migrate`-шаг ОБЯЗАТЕЛЕН перед каждым `up` — иначе preflight уронит контейнер `exit 1` при малейшем schema drift. `--no-deps` — обязателен на каждой команде: без него Compose вправе (пере)создать `postgres`/`redis`/`resource-postgres` (stateful, не в routine-деплое). `redis`/`resource-postgres` в этот routine НЕ входят никогда — их ротация отдельная координированная процедура. ⚠️ После очистки `.env` ЛЮБАЯ compose-команда на прод-хосте без `doppler run --` падает на `:?`-интерполяции — это желаемый fail-fast, не чинить возвратом секретов в `.env`.

⚠️ **`migrate` без пересборки ВСЕХ ТРЁХ runtime-образов (`api`, `access-api`, `app`) = отложенная петля рестартов.** В каждый образ на сборке зашит `EXPECTED_ALEMBIC_HEAD`; read-only preflight сравнивает его со схемой БД строго. Прогнали `migrate`, пересобрали не всех — не пересобранный сервис переживёт текущий `up` (контейнер не пересоздавался), но упадёт в вечный restart-loop при СЛЕДУЮЩЕМ up/ребуте хоста, когда его старый образ встретит новую схему. Ровно так access-api на 105 крутился в петле двое суток (24–26.07.2026: migrate до 006 прогнали, access-api остался с зашитой 005). Поэтому `build api access-api app migrate` — всегда все четыре, даже если «менялся только бот».

### Последний шаг раскатки — annotated-тег (AUD3-38 / AUD5-PRAC-3, с 2026-07-27)

После успешной раскатки и прод-проверки — локально, из чекаута:

```bash
scripts/tag-deploy.sh <profk|infrasafe> --push     # тег на HEAD, который уехал
```

Имя `<host>-YYYY-MM-DD` (вторая раскатка за день → `.2`), тело — коммиты от
предыдущего тега этого хоста. Дата берётся у коммита, а не «сегодня».

Зачем: деплой здесь — `git pull` на хосте, поэтому без тега «что в проде» и «с чего
откатываться» существуют только как HEAD рабочей копии на машине, и проверяются
через ssh. Тег ставится **после** проверки, а не вместо неё: тег на неработающей
раскатке хуже отсутствующего — он выглядит подтверждением.

### resource-api / resource-worker — отдельный осознанный шаг (не в общей пачке)

**AUD6-P1-2 (с 2026-07-30): у resource-БД своя пара «владелец/раннтайм»** — зеркало PR-7 основной БД. `resource` (POSTGRES_USER, суперпользователь инстанса) — только миграции+seed через one-shot `resource-migrate`; сервисы ходят под `resource_app` (DML без DDL, пароль `RESOURCE_APP_PASSWORD` из Doppler). Из `entrypoint-api.sh` миграции убраны — старый «alembic на каждом старте api» больше не существует.

**Первая раскатка на хост (однократно, ДО up новых образов):**

```bash
# 1) завести RESOURCE_APP_PASSWORD в Doppler (оба конфига) — владелец, значения в чат не выводить
# 2) создать роль (идемпотентно; повтор = ротация пароля):
doppler run --project uk-management --config <profk|infrasafe> -- \
  docker compose [-f docker-compose.yml -f docker-compose.profk.yml] run --rm resource-provision-roles
```

**Рутинный деплой (порядок обязателен — migrate ДО up, как у core):**

```bash
doppler run --project uk-management --config <profk|infrasafe> -- \
  docker compose [-f docker-compose.yml -f docker-compose.profk.yml] build resource-api resource-worker resource-migrate
doppler run --project uk-management --config <profk|infrasafe> -- \
  docker compose [-f docker-compose.yml -f docker-compose.profk.yml] run --rm resource-migrate
doppler run --project uk-management --config <profk|infrasafe> -- \
  docker compose [-f docker-compose.yml -f docker-compose.profk.yml] up -d --no-deps --wait --wait-timeout 120 resource-api resource-worker
```

Проверка least-privilege после раскатки: `CREATE TABLE` под `resource_app` в psql обязан дать `permission denied for schema public`; новые таблицы будущих миграций до-грантов не требуют (default privileges от роли `resource`).

`--no-deps` здесь критичен вдвойне: `resource-postgres` — stateful, Postgres игнорирует новый `POSTGRES_PASSWORD` при существующем volume, поэтому расхождение Doppler ↔ реальный пароль БД тихо ломает клиентов. Если `RESOURCE_*`-значения в Doppler менялись — перед `up` сверить равенство с работающим контейнером (printenv-паттерн, наружу только OK/FAIL):

```bash
doppler run --project uk-management --config <cfg> -- sh -c '
  for v in RESOURCE_SESSION_SECRET RESOURCE_SERVICE_TOKEN; do
    [ "$(docker exec uk-resource-api printenv "$v" 2>/dev/null)" = "$(printenv "$v")" ] \
      && echo "$v OK" || echo "$v FAIL — не деплоить, сначала выяснить какая сторона права"
  done
'
```

**Ротация секрета в Doppler не применяется сама** — только следующий `doppler run -- docker compose up -d <service>` подхватит новое значение (config-hash изменится, Compose пересоздаст контейнер).

### ⚠️ Одноразово перед Phase 2 rollout: выделенная DB-роль `uk_media_owner`

Шаг 0 (2026-07-21) показал: media на ОБОИХ хостах подключается к `uk_media` под ролью
основной БД (`profk_bot` на profk, `uk_bot` на infrasafe), и эти роли владеют 4 таблицами +
4 sequences в `uk_media`. Пароль этих ролей — в `.env.postgres` (PR-7 carve-out). Если
положить `MEDIA_DATABASE_URL` в Doppler под тем же паролем — источников истины станет два, и
ротация роли через `provision-roles` тихо сломает media. Поэтому перед cutover media
переводится на выделенную least-privilege роль, чей пароль живёт ТОЛЬКО в Doppler.

Выполнять на КАЖДОМ хосте под суперюзером (`docker exec -it uk-postgres psql -U uk_admin -d uk_media`).
`REASSIGN OWNED` НЕ использовать — он заденет глобальные объекты (основную БД роли); только
точечные `ALTER`:

```sql
-- проверить, не создана ли уже
SELECT rolname FROM pg_roles WHERE rolname='uk_media_owner';
CREATE ROLE uk_media_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
\password uk_media_owner   -- пароль: openssl rand -hex 24; сгенерировать, вставить, СРАЗУ в Doppler как часть MEDIA_DATABASE_URL
ALTER DATABASE uk_media OWNER TO uk_media_owner;
GRANT ALL ON SCHEMA public TO uk_media_owner;   -- для create_all будущих таблиц
-- 4 таблицы + 4 sequences (индексы следуют за таблицей автоматически);
-- имена подставить из шага 0, здесь текущий набор media:
ALTER TABLE media_files, media_tags, media_channels, media_upload_sessions OWNER TO uk_media_owner;
ALTER SEQUENCE media_files_id_seq, media_tags_id_seq, media_channels_id_seq, media_upload_sessions_id_seq OWNER TO uk_media_owner;
```

Верификация под новой ролью:
`SELECT current_user;` → `uk_media_owner`; `CREATE TABLE _p(x int); DROP TABLE _p;` → успех;
`SELECT count(*) FROM media_files;` → работает. `MEDIA_DATABASE_URL` в Doppler указывает на
`uk_media_owner`, старая роль основной БД к `uk_media` больше не привязана.

### media-service — отдельный шаг (Phase 2)

Обновлять при изменении его кода/секретов. Migrate-шаг UK не нужен (у media свой lifecycle БД).

```bash
# profk:
doppler run --project uk-management --config profk -- docker compose -f docker-compose.yml -f docker-compose.profk.yml build media-service
doppler run --project uk-management --config profk -- docker compose -f docker-compose.yml -f docker-compose.profk.yml up -d --no-deps --wait --wait-timeout 120 media-service
# infrasafe/105 — оба -f:
doppler run --project uk-management --config infrasafe -- docker compose -f docker-compose.yml -f docker-compose.media.yml build media-service
doppler run --project uk-management --config infrasafe -- docker compose -f docker-compose.yml -f docker-compose.media.yml up -d --no-deps --wait --wait-timeout 120 media-service
```

⚠️ Изменили несекретную часть `media_service/.env` (каналы, `ALLOWED_ORIGINS`) — нужен `--force-recreate`: `env_file` не входит в config-hash, а `docker restart` вообще не перечитывает файл. `ALLOWED_FILE_TYPES` в этот файл НЕ добавлять — ломает старт.

Проверка секретов media (наружу только OK/FAIL; имена в Doppler с `MEDIA_`-префиксом — см. таблицу выше):

```bash
doppler run --project uk-management --config <cfg> -- sh -c '
  running=$(docker inspect -f "{{.State.Running}}" uk-media-service 2>/dev/null || echo absent)
  if [ "$running" = "true" ]; then
    for pair in "TELEGRAM_BOT_TOKEN MEDIA_BOT_TOKEN" "SECRET_KEY MEDIA_SECRET_KEY" \
                "MEDIA_API_KEYS MEDIA_API_KEYS" "DATABASE_URL MEDIA_DATABASE_URL"; do
      set -- $pair
      [ "$(docker exec uk-media-service printenv "$1" 2>/dev/null)" = "$(printenv "$2")" ] \
        && echo "$1 OK" || echo "$1 FAIL"
    done
  elif [ "$running" = "absent" ]; then echo "media runtime absent — equality skipped"
  else echo "=== STOP: контейнер media существует, но ОСТАНОВЛЕН — расследовать до деплоя ==="; fi
'
```

### group-intake-bot — выделенный бот Group Intake (за compose-профилем)

Заявки из ТГ-групп обслуживает ОТДЕЛЬНЫЙ бот (свой токен `GROUP_INTAKE_BOT_TOKEN`,
свой polling-процесс `group_intake_main.py`; прецедент asset-bot — один polling на
токен). Сервис за профилем `group-intake` — в рутинный `up` НЕ входит и без
`COMPOSE_PROFILES=group-intake` compose его не видит вовсе.

Первое включение на хосте:
1. BotFather: создать бота, `/setprivacy → Disable` (нужно читать все сообщения групп).
2. Doppler (оба конфига по необходимости): `GROUP_INTAKE_BOT_TOKEN`, `ANTHROPIC_API_KEY`,
   `GROUP_INTAKE_ENABLED=true` — через web-dashboard.
3. Несекретное в `.env` хоста: `COMPOSE_PROFILES=group-intake` (или передавать
   `--profile group-intake` в каждую команду).

Рутинное обновление (тот же образ, что у app — build app пересобирает и его базу):

```bash
doppler run --project uk-management --config <profk|infrasafe> -- \
  docker compose <оба -f> --profile group-intake build group-intake-bot
doppler run --project uk-management --config <profk|infrasafe> -- \
  docker compose <оба -f> --profile group-intake up -d --no-deps --wait --wait-timeout 120 group-intake-bot
```

Проверка: `docker logs uk-group-intake-bot --tail 20` — строка `Group Intake bot: @<username>`.
Fail-fast настроек: флаг без токена/ключа/Redis валит старт; токен == BOT_TOKEN — тоже
(два поллера на одном токене дерутся за getUpdates). Уведомления по созданным заявкам
уходят от ОСНОВНОГО бота (send-only инстанс внутри процесса) — это штатно.

## Ротация партнёрских webhook-секретов (dual-secret, `*_NEXT`)

Секреты `INFRASAFE_WEBHOOK_SECRET` (исходящий, мы подписываем) и `UK_WEBHOOK_SECRET` (входящий, мы проверяем) разделены с InfraSafe — односторонняя смена рвёт живую интеграцию. Поэтому в коде есть grace-window механизм (`settings.py` §4.4/R-18): верификатор принимает OLD || NEW, подписант переключается флагом. Переменные проброшены только сервису `api` (там живут и `process_outbox`, и inbound-роутер).

1. Положить новое значение в Doppler как `INFRASAFE_WEBHOOK_SECRET_NEXT` (и/или `UK_WEBHOOK_SECRET_NEXT`) — **через web-dashboard, не CLI** (CLI печатает plaintext).
2. Деплой `api` рутинной процедурой → наш верификатор с этого момента принимает и старый, и новый входящий секрет.
3. Скоординироваться с InfraSafe: они добавляют новый секрет на своей стороне (их верификатор тоже принимает оба).
4. Флип подписанта: `INFRASAFE_USE_NEXT_SECRET=true` в Doppler → деплой `api`. Исходящие запросы подписываются новым секретом.
5. После подтверждения обеими сторонами: перенести значение `*_NEXT` в основной ключ, очистить `*_NEXT`, снять флаг `USE_NEXT` → деплой `api`. Окно закрыто.

Проверка проброса (значения не печатаются): `docker exec uk-management-api env | cut -d= -f1 | grep NEXT`.

## Ротация JWT_SECRET без force-logout (ARCH-107, dual-key через `kid`)

Раньше смена `JWT_SECRET` мгновенно разлогинивала все web/TWA-сессии. Теперь верификатор (`api/auth/service.py`, общий для `api` и `access-api`) принимает набор ключей {primary, next} — каждый токен несёт `kid` в заголовке, подписант (`api`) переключается флагом. Переменные `JWT_SECRET_NEXT`/`JWT_USE_NEXT_SECRET` проброшены **только `api` и `access-api`** (`app`/`migrate` JWT не верифицируют; их settings-валидация флага не увидит — это нормально).

1. Новое значение → Doppler как `JWT_SECRET_NEXT` — **через web-dashboard, не CLI**. Требования (fail-fast на старте): ≥32 символов, ≠ `JWT_SECRET`, ≠ `INVITE_SECRET`.
2. Деплой `api` + `access-api` рутинной процедурой → оба верификатора принимают оба ключа; подписант ещё на старом.
3. Флип: `JWT_USE_NEXT_SECRET=true` в Doppler → деплой `api`. Новые токены подписываются NEW (`kid: next`); старые продолжают проходить.
4. Grace-окно ≥ **1 часа** (самый долгоживущий JWT — access, 60 мин; registration ticket 30 мин, mfa 5 мин). Refresh-токены — не JWT (opaque, хэш в БД), ротацию не чувствуют: по ним фронт молча получает новые access-токены уже под NEW.
5. Финализация **одной правкой Doppler**: значение NEXT → `JWT_SECRET`, очистить `JWT_SECRET_NEXT`, снять `JWT_USE_NEXT_SECRET` (флаг без ключа = fail-fast) → деплой `api` + `access-api`. Токены эпохи флипа (`kid: next`) продолжают проходить — верификатор перебирает весь набор, `kid` только упорядочивает перебор.

⚠️ Шаг 5 без шага 4 (финализация раньше, чем истекли OLD-токены) = тот самый force-logout, от которого механизм защищает. Между шагами 3 и 5 обязан пройти час.

**Abort после флипа** (передумали на шаге 3–4): НЕ чистить `JWT_SECRET_NEXT` сразу — токены эпохи флипа подписаны им и умрут с 401 до истечения. Порядок: снять только `JWT_USE_NEXT_SECRET` → деплой `api` (подписант вернулся на старый ключ) → выждать тот же час → очистить `JWT_SECRET_NEXT` → деплой `api` + `access-api`.

## Провижининг / ротация паролей ролей (PR-7, не путать с Doppler-секретами приложения)

```
docker compose run --rm --name uk-provision-roles provision-roles
```

Требует `DEPLOY_UID`/`DEPLOY_GID` в env и коннект от суперюзера — `uk_bot`/`profk_bot` уже без `CREATEROLE`, использовать `uk_admin` через `docker exec uk-postgres psql -U uk_admin` при ручном перезапуске.

Post-rollout verifier-log: `docs/audit/2026-07-15-pr7-rollout.md`.
