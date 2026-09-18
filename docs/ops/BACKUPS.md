# Бэкапы БД — реестр покрытия, RPO/RTO и восстановление

> Канон по AUD7-ENG-07 (2026-09-18). Механизм живёт **вне этого репозитория** —
> кросс-бэкап хост-пиров из `/opt/profk-observability/backup/` (деплой-источник на
> profk; см. память/заметки «profk observability stack»). Здесь — реестр того, что
> реально снимается, где лежит и как восстанавливать. Репозиторный
> `scripts/backup-db.sh` + `scripts/crontab.production` (одна БД, `uk_bot`, крона нет)
> списаны — они давно не работали и вводили в заблуждение.

## Реестр (проверено на живых хостах 2026-09-18)

| Хост | Контейнер | БД | Роль дампа | Расписание | Локально (retention) | Копия у пира (retention) |
|---|---|---|---|---|---|---|
| profk | `uk-postgres` | `profk_management` (main) | `uk_admin` | root-systemd `infrasafe-backup.timer`, ежедневно ~03:19 Asia/Tashkent | `/var/backups/local/profk-*.tar`, ~8 | 105: `/home/infrasafe/backups/peer/profk/`, 40 |
| profk | `uk-postgres` | `uk_media` | `uk_admin` | тот же | тот же | тот же |
| profk | `uk-resource-postgres` | `resource_accounting` | `resource` | тот же | тот же | тот же |
| profk | `uk-payment-postgres` | `payment_control` | `payment_owner` | тот же | тот же | тот же |
| profk | `infrasafe-postgres-1` | `infrasafe` (проект InfraSafe) | `infrasafe_app` | тот же | тот же | тот же |
| profk | `/opt/asset-bot/data` | файлы asset-bot | — | тот же | в том же tar (`files/`) | тот же |
| 105 | `uk-postgres` | `uk_management` (main) | `uk_admin` | user-cron `40 3 * * *` (`~/.backup/backup-databases.sh`) | `~/backups/local/infrasafe105-*.tar`, 5–6 | profk: `/var/backups/peer/infrasafe105/`, 15 |
| 105 | `uk-postgres` | `uk_media` | `uk_admin` | тот же | тот же | тот же |
| 105 | `uk-resource-postgres` | `resource_accounting` | `resource` | тот же | тот же | тот же |
| 105 | `infrasafe-postgres-1` | `infrasafe` (проект InfraSafe) | `infrasafe_app` | тот же | тот же | тот же |

Конфиги: profk — `/etc/backup/databases.conf` (root; репо-копия
`/opt/profk-observability/backup/hosts/profk.databases.conf`), 105 —
`~/.backup/databases.conf`. Формат архива: `pg_dump -Fc` на каждую БД
(`<контейнер>__<база>.dump`) + `MANIFEST.txt` с SHA-256, tar. Метрики свежести на
profk — `infrasafe-backup-metrics.timer` → node_exporter textfile
(`backup_last_success_timestamp_seconds`), алерты — в obs-стеке.

**Не покрыто намеренно:** сами медиа-файлы (лежат в Telegram-каналах media-service,
локально только метаданные `uk_media` — решение владельца 2026-09-02); Redis
(кэш/pending, восстанавливается пустым); на 105 — InfluxDB/Node-RED/Mosquitto
(телеметрия и конфигурация в репозиториях InfraSafe). Payment-БД на 105 нет
(«Контроль платежей» включён только на profk).

## Владелец, RPO/RTO

- **Владелец:** владелец проекта (единственный оператор обоих хостов).
- **RPO:** 24 ч (одно ежедневное снятие; между снятиями изменения теряются).
  Перед рискованными операциями с БД — разовый дамп руками (см. ниже).
- **RTO (цель): ≤ 1 ч** на хост — ручная процедура ниже; репетиция 2026-09-18
  показала восстановление всех БД хоста в одноразовый контейнер за минуты.
  Цифры RPO/RTO — предложенные по факту; пересмотр — решение владельца.

## Разовый дамп перед рискованной операцией

```bash
# profk (main): под uk_admin, формат -Fc, файл в $HOME
docker exec uk-postgres pg_dump -U uk_admin -Fc profk_management > ~/backups/pre-<что>.dump
# полный внеочередной прогон кросс-бэкапа (profk): sudo -n systemctl start infrasafe-backup.service
# 105: BACKUP_CONF=~/.backup/backup.conf ~/.backup/backup-databases.sh
```

## Восстановление (репетиция 2026-09-18, обе площадки)

Репетиция — в **одноразовом** контейнере без сети и портов, прод не трогается;
образ берётся тот же, что у исходного контейнера БД (postgres 15 для uk-postgres,
16 для resource/payment, postgis для infrasafe — иначе `pg_restore` 15 не читает
дампы 16, а infrasafe падает на расширении postgis).

```bash
T=$(ls -t /var/backups/local/profk-*.tar | head -1)      # 105: ~/backups/local/infrasafe105-*.tar
W=$(mktemp -d); tar -xf "$T" -C "$W"
IMG=$(docker inspect uk-postgres --format '{{.Config.Image}}')
docker run -d --name uk-restore-rehearsal --network none -e POSTGRES_PASSWORD=r -e POSTGRES_USER=r "$IMG"
# образ делает initdb → временный сервер → рестарт: ждать строку завершения init,
# pg_isready на временном сервере врёт
until docker logs uk-restore-rehearsal 2>&1 | grep -q "PostgreSQL init process complete"; do sleep 1; done
docker exec uk-restore-rehearsal createdb -U r profk_management
docker exec -i uk-restore-rehearsal pg_restore -U r -d profk_management --no-owner --no-privileges < "$W/uk-postgres__profk_management.dump"
docker exec uk-restore-rehearsal psql -U r -d profk_management -Atc "select count(*) from pg_tables where schemaname='public'"
docker rm -f uk-restore-rehearsal; rm -rf "$W"
```

Результат репетиции 2026-09-18 (0 ошибок `pg_restore`, наборы таблиц = прод 1:1):

| Хост | БД | Таблиц (restore = прод) |
|---|---|---|
| profk | profk_management | 61 |
| profk | uk_media | 4 |
| profk | resource_accounting | 19 |
| profk | payment_control | 5 |
| profk | infrasafe | 67 |
| 105 | uk_management | 61 |
| 105 | uk_media | 4 |
| 105 | resource_accounting | 19 |
| 105 | infrasafe | 69 |

**Боевое восстановление** (в живой контейнер) — только по решению владельца:
`pg_restore --clean --if-exists` под ролью из реестра (владелец объектов —
`uk_migration_owner`/`uk_media_owner`/`resource`/`payment_owner`, поэтому без
`--no-owner`; роли должны существовать — PR-7 `provision-roles`), затем
`alembic current` (main) и preflight api. Медиа-файлы не восстанавливаются — они в
Telegram.

## Известные грабли

- `pg_restore -l` — это оглавление, не восстановление; репетиция обязана быть полной.
- Одинаковый размер tar два дня подряд — норма (паддинг до блока); сверять размеры
  внутренних дампов (`tar -tvf`).
- `uk_bot`/`profk_bot` — не superuser: дамп под ними неполный; только `uk_admin`.
- Репо-копия `hosts/infrasafe105.databases.conf` в obs-репо может отставать от
  живого `~/.backup/databases.conf` на 105 — сверять живой файл.
