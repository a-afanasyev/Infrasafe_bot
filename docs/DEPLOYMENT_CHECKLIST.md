# Production Deployment Checklist

> _Последнее редактирование: 2026-09-23_

> 🔴 **Команды деплоя в этом файле не ведутся.** Набор compose-файлов площадки —
> только таблица «Площадка → COMPOSE» в `.claude/skills/uk-deploy/SKILL.md`
> (profk: base + profk + payments; 105: base + media), пошаговая выкатка — там же и в
> `docs/ops/RUNBOOK.md` §2 (ARCH-106: только через `doppler run --`; PR-7: `migrate`
> обязателен перед каждым `up`; НИКОГДА `--remove-orphans`). A9-P1-3.
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
- [ ] Секреты приложения — в Doppler (`doppler run --project uk-management --config <profk|infrasafe>`), не в `.env`; полнота гарантируется `:?`-гвардами compose и SSOT-гейтом (`tests/services/test_compose_secret_env_ssot.py`). Шаблон `.env.production.template` удалён (AUD6-P2-42) — канон: `.env.example` + `.claude/skills/uk-deploy/SKILL.md`
- [ ] `DEBUG=false` in `.env`
- [ ] `JWT_SECRET` != `INVITE_SECRET`
- [ ] `ADMIN_PASSWORD` >= 12 chars
- [ ] `REDIS_PASSWORD` set
- [ ] `MEDIA_SERVICE_API_KEY` set (if media service used)
- [ ] Pre-deploy DB backup created (see ROLLBACK.md)
- [ ] Release tagged: `git tag -a vX.Y.Z -m "Release X.Y.Z"`

## Deploy

См. `docs/ops/RUNBOOK.md` §2 — команды с `$COMPOSE` площадки из таблицы uk-deploy SKILL.

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
