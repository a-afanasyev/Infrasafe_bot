# scripts/ — живые операционные скрипты

> Переписан при чистке AUD6-P2-30 (39 мёртвых файлов удалены) и AUD6-P3-41:
> прежний README описывал SQLite-эру, роль `uk_bot` с паролем в открытом виде
> и «Владелец: postgres» — всё это устарело ещё с PR-7 (least-privilege роли)
> и PRC-05 (squash-baseline). Актуальная процедура деплоя/ролей —
> `.claude/skills/uk-deploy/SKILL.md`; секреты приходят из Doppler (ARCH-106).

## Контейнерные entrypoint'ы (используются Dockerfile'ами)

- `entrypoint-bot.sh`, `entrypoint-api.sh`, `entrypoint-access.sh` — старт
  сервисов; api/access делают только read-only preflight схемы (PR-7),
  миграций на старте НЕТ.
- `entrypoint-migrate.sh` — one-shot сервис `migrate` (alembic upgrade + ACL
  reconcile + check).

## Провижининг БД (PR-7 / PRC-05)

- `init_postgres.sh` / `init_postgres.sql` — инициализация контейнера postgres.
- `provision_roles.sh` / `provision_roles.sql` — создание/ротация runtime-ролей
  (`uk_bot_runtime`/`uk_api_runtime`/`uk_access_runtime`, гранты через
  `uk_app_rw`/`access_app_rw`). Пароли генерируются на хосте, в git не живут.
- `dba_ownership_transfer.sql`, `dba_inventory.sql` — разовый перенос владения
  на `uk_migration_owner` и инвентаризация (использовались в PR-7 rollout,
  исполняются и CI-гейтом `pg-role-separation`).

## CI и локальная верификация

- `test-ci-local.sh` — эталонный локальный прогон, 1-в-1 с CI-джобой
  `backend-tests` (`make test-ci`).
- `backlog_manifest.py` — гейт манифеста бэклога (CI).
- `dump_openapi.py` — выгрузка OpenAPI для `docs/tech/API_REFERENCE.md` (CI).

## Эксплуатация

- `backup-db.sh` + `crontab.production` — бэкапы.
- `tag-deploy.sh <profk|infrasafe> --push` — annotated-тег после раскатки
  (AUD3-38): без него «что в проде» существует только как HEAD чекаута хоста.
- `seed_e2e_user.py` — сид пользователя для E2E.
- `bootstrap_database.py`, `export_schema.py`, `apply_verification_migration.py`,
  `cleanup_sql.sh`, `migrate_database.sh`, `test-media-service.sh` — редко
  используемые/исторические утилиты; перед использованием сверяться с
  актуальной процедурой в uk-deploy SKILL.md.
