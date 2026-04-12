# Production Deployment Checklist

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
