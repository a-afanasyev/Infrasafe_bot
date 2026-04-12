# Rollback Procedure

## Release Tagging Convention

Every production deploy must be tagged:

```bash
git tag -a v1.2.3 -m "Release 1.2.3"
docker compose -f docker-compose.production.yml build
docker tag uk-management-bot:latest uk-management-bot:v1.2.3
docker tag uk-management-api:latest uk-management-api:v1.2.3
```

## Pre-Deploy Backup (mandatory)

Before every deploy, create a tagged backup:

```bash
docker exec uk-postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB | \
  gzip > /opt/uk-management/backups/uk_management_PRE_DEPLOY_$(date +%Y%m%d_%H%M%S).sql.gz
```

## Quick Rollback (to previous release)

1. Identify last known-good release tag:

   ```bash
   git tag --sort=-creatordate | head -5
   ```

2. Checkout the release:

   ```bash
   git checkout v1.2.2  # specific known-good tag
   ```

3. Rebuild and restart:

   ```bash
   docker compose -f docker-compose.production.yml build
   docker compose -f docker-compose.production.yml up -d
   ```

4. Verify:

   ```bash
   curl -s https://your-domain.com/health | jq .
   docker logs uk-management-api --tail 20
   docker logs uk-management-bot --tail 20
   ```

5. Return to main branch after fix:

   ```bash
   git checkout main
   ```

## Database Rollback

### Schema-only rollback (migration revert)

Only safe if the new migration was additive (new columns/tables):

```bash
docker exec uk-management-api python -m alembic current
docker exec uk-management-api python -m alembic downgrade -1
```

### Data restore from backup

If migration was destructive or data is corrupted:

```bash
# 1. Stop app and API (keep DB running)
docker compose -f docker-compose.production.yml stop app api

# 2. Restore from the pre-deploy backup
gunzip < /opt/uk-management/backups/uk_management_PRE_DEPLOY_YYYYMMDD.sql.gz | \
  docker exec -i uk-postgres psql -U $POSTGRES_USER -d $POSTGRES_DB

# 3. Run migrations for the rollback target version
docker exec uk-management-api python -m alembic upgrade head

# 4. Restart services
docker compose -f docker-compose.production.yml up -d app api
```
