# Production Deployment Checklist

> 🔴 **ВНИМАНИЕ: команды ниже ссылаются на несуществующий `docker-compose.production.yml`.**
> Реальный прод-стек (хост `~/uk`, 7 контейнеров) — **`docker compose -f docker-compose.yml
> -f docker-compose.media.yml`**. Каноничная выкатка:
> ```bash
> cd ~/uk && git pull --ff-only
> docker compose -f docker-compose.yml -f docker-compose.media.yml build frontend api app
> docker compose -f docker-compose.yml -f docker-compose.media.yml up -d --force-recreate frontend api app
> #  НИКОГДА не добавлять --remove-orphans (снесёт uk-caddy/uk-media-service)
> ```
> Миграции применяет сам `api` на старте (`entrypoint-api.sh` → `alembic upgrade head`);
> проверка: `docker logs uk-management-api | grep "Migrations complete"`, `alembic current` = head.
> Новый SPA-эндпоинт `/api/v2/*` требует добавления в InfraSafe edge-allowlist (SEC-22),
> иначе 404 на публичном edge (`nginx.production.conf`, `map $uri $uk_api_allowed`).
> Полный runbook: [DOCUMENTATION_STATUS.md](DOCUMENTATION_STATUS.md). Разделы ниже — устаревают.

## Pre-Deploy

- [ ] All tests pass: `docker exec uk-management-bot pytest`
- [ ] Frontend build clean: `cd frontend && npm run build`
- [ ] No secrets in code: `git grep -i "password\|token\|secret" -- "*.py" "*.ts" "*.yml" | grep -v template | grep -v test`
- [ ] `.env` on server has all vars from `.env.production.template`
- [ ] `DEBUG=false` in `.env`
- [ ] `JWT_SECRET` != `INVITE_SECRET`
- [ ] `ADMIN_PASSWORD` >= 12 chars
- [ ] `REDIS_PASSWORD` set
- [ ] `MEDIA_SERVICE_API_KEY` set (if media service used)
- [ ] Pre-deploy DB backup created (see ROLLBACK.md)
- [ ] Release tagged: `git tag -a vX.Y.Z -m "Release X.Y.Z"`

## Deploy

```bash
git pull origin main
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d
```

## Post-Deploy Verification

- [ ] Migrations applied: `docker logs uk-management-api | grep "Migrations complete"`
- [ ] API health: `curl -s https://your-domain.com/health | jq .`
- [ ] Bot health: `docker logs uk-management-bot --tail 20`
- [ ] Bot responds in Telegram (send /start)
- [ ] Frontend loads: open https://your-domain.com in browser
- [ ] WebSocket connection works (open dashboard, check real-time updates)
- [ ] Backup cron active: `crontab -l | grep backup`

## Rollback

If anything fails, follow `docs/ROLLBACK.md`.
