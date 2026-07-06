# Runbook: webhook_outbox failures & retention

> _Последнее редактирование: 2026-06-13_

**Scope:** транзакционный outbox для исходящих вебхуков UK → InfraSafe
(`webhook_outbox`). Закрывает DOCS-095 (документирование by-design rollback +
alerting) и OPS-105 (retention + Prometheus-метрики).

## 1. By-design: outbox INSERT откатывает доменную операцию

Запись в `webhook_outbox` происходит **в той же транзакции**, что и доменная
операция (например, `building.create`). Это сознательный выбор transactional
outbox: либо и доменная запись, и событие зафиксированы, либо ни то, ни другое.

**Следствие:** если INSERT в `webhook_outbox` падает (нарушение констрейнта,
переполнение диска, недоступность БД на коммите), то **доменная операция
откатывается целиком** — пользователь увидит ошибку и повторит. Это НЕ баг:
так мы не теряем события (нет «создал здание, но не уведомил InfraSafe»).

**Чего НЕ бывает:** «осиротевшая» доменная запись без события или событие без
доменной записи. Согласованность важнее доступности на этом пути.

## 2. Симптомы и алерты

Источник метрик: `GET /api/health/outbox` (JSON) и `GET /metrics`
(Prometheus, OPS-105). Оба token-gated (`HEALTH_METRICS_TOKEN`, SEC-064) —
Prometheus скрейпит с bearer-токеном.

Prometheus-гейджи (`/metrics`):

| Метрика | Значение | Алерт |
|---|---|---|
| `uk_outbox_pending` | необработанные `pending` | рост без спада → воркер встал |
| `uk_outbox_oldest_pending_age_seconds` | возраст старейшего `pending` | > 300s → доставка отстаёт |
| `uk_outbox_failed_last_24h` | `failed` за 24ч | > 0 → разобрать причину |
| `uk_outbox_stuck_in_flight` | `in_flight` старше lease | стабильно > 0 → crash-loop воркера (PR-5) |

**Доменный INSERT-failure** виден не в outbox-метриках (записи там нет —
транзакция откатилась), а в **логах API/бота**: ERROR при создании
сущности + `webhook_outbox`-трейс. Рекомендуемый алерт:
`rate(log ERROR matching "webhook_outbox" / "outbox") > 0` за минуту.

## 3. Диагностика

```bash
# Метрики (внутри api-контейнера, токен из .env):
docker exec uk-management-api python -c "import urllib.request; \
  print(urllib.request.urlopen('http://localhost:8080/api/health/outbox').read())"

# Свежие failed-записи:
docker exec uk-postgres psql -U uk_bot -d uk_management -c \
  "SELECT id,event,attempts,last_error,created_at FROM webhook_outbox \
   WHERE status='failed' ORDER BY created_at DESC LIMIT 20;"

# Зависшие in_flight (старше lease — владелец упал):
docker exec uk-postgres psql -U uk_bot -d uk_management -c \
  "SELECT id,event,claimed_at,claim_count FROM webhook_outbox \
   WHERE status='in_flight' ORDER BY claimed_at LIMIT 20;"
```

## 4. Восстановление

- **`pending` растёт, доставки нет:** проверить доступность InfraSafe-эндпоинта
  и логи `_outbox_loop`; при недоступности получателя записи дозреют сами,
  когда он вернётся (at-least-once, idempotent receiver).
- **`stuck_in_flight` > 0 стабильно:** воркер падает между claim и
  финализацией (crash-loop). Записи освобождаются reclaim'ом после lease
  (`INFRASAFE_OUTBOX_LEASE_SECONDS`) и доставятся повторно тем же `event_id`.
  Разобрать причину падения по логам; ручной сброс при необходимости:
  `UPDATE webhook_outbox SET status='pending', claim_token=NULL, claimed_at=NULL WHERE status='in_flight' AND claimed_at < now() - interval '10 minutes';`
- **`failed`:** разобрать `last_error`; повторная доставка — ручным
  `UPDATE ... SET status='pending', attempts=0` после устранения причины.
- **Доменный INSERT-failure (rollback):** устранить корневую причину
  (диск/констрейнт/БД), пользователь повторяет операцию штатно.

## 5. Retention (OPS-105)

Фоновая задача `_outbox_retention_loop` (lifespan, запускается только при
`INFRASAFE_WEBHOOK_ENABLED`) раз в сутки удаляет `status='sent'` записи старше
**30 дней** (`services/outbox_retention.py:purge_old_sent_outbox`). `failed`,
`pending`, `in_flight` НЕ трогаются. Окно — константа `DEFAULT_RETENTION_DAYS`.
Лог цикла: `Outbox retention cycle: {'deleted': N}`.
