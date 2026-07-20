# Production Deployment Checklist

> _Последнее редактирование: 2026-07-06_

> 🔴 **ВНИМАНИЕ: команды ниже ссылаются на несуществующий `docker-compose.production.yml`
> и устарели.** Реальный прод-стек infrasafe (хост `~/uk`) — **`docker compose -f
> docker-compose.yml -f docker-compose.media.yml`** (оба `-f` в каждой команде: media
> подключается overlay-файлом); profk — `-f docker-compose.profk.yml`. Каноничная выкатка
> (ARCH-106: секреты приходят из Doppler, `.env` от них очищен → без `doppler run --`
> команда упадёт на `:?`; PR-7: `migrate`-шаг обязателен перед каждым `up`):
> ```bash
> cd ~/uk && git pull --ff-only
> export DEPLOY_UID=$(id -u) DEPLOY_GID=$(id -g)
> D="doppler run --project uk-management --config infrasafe --"
> C="docker compose -f docker-compose.yml -f docker-compose.media.yml"
> $D $C build api access-api app migrate
> $D $C run --rm --no-deps --name uk-migrate migrate     # ОБЯЗАТЕЛЕН перед up
> $D $C up -d --no-deps --wait --wait-timeout 120 api access-api app
> #  НИКОГДА не добавлять --remove-orphans (снесёт uk-caddy/uk-media-service)
> ```
> ⚠️ Устаревшее утверждение «миграции применяет сам `api` на старте» больше НЕ верно:
> после PR-7 entrypoint делает только read-only preflight и падает `exit 1` при schema
> drift — миграции гоняет отдельный one-shot `migrate`.
> **Единственный актуальный источник процедуры — `.claude/skills/uk-deploy/SKILL.md`**
> (bootstrap Doppler, mapping имён media, ротация ролей и webhook-секретов).
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
