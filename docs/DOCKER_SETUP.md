# Docker-окружение UK Management

> _Последнее редактирование: 2026-09-23_

Короткая справка по compose-файлам репозитория. Документ сознательно **не**
повторяет процедуры, у которых есть единственный источник истины:

| Что | Где |
|---|---|
| Первый локальный запуск (роли PR-7 → `migrate` → сервисы), тесты, линт | корневой [README.md](../README.md) |
| Сервисы, порты, потоки данных | [tech/ARCHITECTURE.md](tech/ARCHITECTURE.md) §2 |
| Прод-деплой: набор `-f` площадки, `doppler run --`, `migrate` → `up`, ротация секретов | [`.claude/skills/uk-deploy/SKILL.md`](../.claude/skills/uk-deploy/SKILL.md) (таблица «Площадка → COMPOSE») |
| Откат, эксплуатационные грабли | [ops/RUNBOOK.md](ops/RUNBOOK.md), [ROLLBACK.md](ROLLBACK.md) |
| Бэкапы БД | [ops/BACKUPS.md](ops/BACKUPS.md) |

> История (AUD5-PRAC-1, 2026-07-26 и A9-P3-27, 2026-09-23): прежняя версия этого
> файла описывала «dev-вариант на SQLite» и команды `docker-compose` v1. SQLite-ветки
> нет: `settings.py` запрещает SQLite при `DEBUG=False`, а все стеки, включая
> `docker-compose.dev.yml`, работают на PostgreSQL. Файлы `env.example` /
> `env.dev.example` удалены — единственный пример окружения `.env.example`.

## Compose-файлы

| Файл | Назначение |
|---|---|
| `docker-compose.yml` | Базовый стек: `app`, `group-intake-bot` (профиль `group-intake`), `api`, `access-api`, `frontend`, `postgres`, `redis`, `resource-postgres`/`resource-api`/`resource-worker`; one-shot'ы под профилем `tools`: `provision-roles`, `migrate`, `resource-provision-roles`, `resource-migrate` |
| `docker-compose.media.yml` | Overlay: `media-service` + one-shot `media-migrate` (площадка 105) |
| `docker-compose.profk.yml` | Тонкий override площадки profk (сети `uk-network` external + `uk-internal`, бренд фронта, media внутри). Standalone не работает — только поверх базового файла |
| `docker-compose.payments.yml` | Overlay «Контроль платежей»: `payment-postgres`, `payment-api`, one-shot `payment-migrate`; добавляет `PAYMENT_SERVICE_URL/TOKEN` в `api` |
| `docker-compose.dev.yml` | Самостоятельный dev-стек с hot-reload (`make dev-up`): `app` на `Dockerfile.dev` с примонтированными `uk_management_bot/` и `alembic/`, свои `postgres`/`redis` (контейнеры `*-dev`). Без ролей PR-7 — не эталон, проверка перед мержем — `make test-ci` |

Сервисы под профилем `tools` (`migrate`, `provision-roles`, `media-migrate`,
`payment-migrate` и др.) обычный `docker compose up -d` не поднимает — их
запускают явно `docker compose run --rm <сервис>`.

## Локальная работа

```bash
docker compose ps                               # статус
docker logs uk-management-bot --tail 20         # логи бота (контейнер)
docker compose build app && docker compose up -d app   # пересборка бота: сервис `app`, не имя контейнера
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" ping
make dev-up                                     # dev-стек с hot-reload
```

Healthcheck бота — `http://localhost:8000/health` внутри контейнера `app`.
У `group-intake-bot` healthcheck отключён намеренно: health-сервер поднимает
только основной бот.

## Сеть и порты

- Все host-порты биндятся на `127.0.0.1`; наружу система доступна только через
  edge InfraSafe по prefix-allowlist.
- Сеть — фиксированное имя `uk-network` (без префикса compose-проекта):
  `docker network inspect uk-network`.
- Контейнеры бота/API/access работают только по IPv4 (`sysctls` с
  `disable_ipv6`) — в Узбекистане нет рабочего IPv6-egress.
- На проде **никогда** не использовать `--remove-orphans`: в стеке есть
  orphan-контейнеры edge/InfraSafe.
