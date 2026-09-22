# Rollback Procedure

> _Последнее редактирование: 2026-09-23_

Прежняя версия этого файла описывала откат через несуществующий
`docker-compose.production.yml` и была помечена неверной (A9-P1-3). Канон
отката теперь один — чтобы процедуры не расходились с реальным прод-стеком:

- **Команды отката кода и схемы** — `docs/ops/RUNBOOK.md`, §3 «Откат».
- **Набор compose-файлов площадки** (`$COMPOSE`) — только таблица
  «Площадка → COMPOSE» в `.claude/skills/uk-deploy/SKILL.md`
  (profk: base + profk + payments; 105: base + media). Все команды — через
  `doppler run --project uk-management --config <profk|infrasafe> --`.
- **Бэкапы и восстановление данных** — `docs/ops/BACKUPS.md`.

Коротко (подробности и предупреждения — в RUNBOOK §3):

```bash
cd <deploy-каталог> && git checkout <предыдущий тег profk-YYYY-MM-DD / infrasafe-YYYY-MM-DD>
export DEPLOY_UID=$(id -u) DEPLOY_GID=$(id -g)
# bash (в zsh нужен ${=COMPOSE}); COMPOSE — строго из таблицы «Площадка → COMPOSE» в .claude/skills/uk-deploy/SKILL.md:
#   profk: COMPOSE="-f docker-compose.yml -f docker-compose.profk.yml -f docker-compose.payments.yml"
#   105:   COMPOSE="-f docker-compose.yml -f docker-compose.media.yml"
: "${COMPOSE:?задайте COMPOSE своей площадки из таблицы SKILL — без него compose поднимет стек без overlay}"
doppler run --project uk-management --config <cfg> -- docker compose $COMPOSE build api access-api app migrate
doppler run --project uk-management --config <cfg> -- docker compose $COMPOSE up -d --no-deps --wait --wait-timeout 120 --force-recreate api access-api app
# НИКОГДА --remove-orphans. Откат схемы — только вручную через one-shot migrate (RUNBOOK §3).
```

Теги релизов ставит `scripts/tag-deploy.sh` (`<host>-YYYY-MM-DD[.n]`).
