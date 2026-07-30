#!/bin/sh
# AUD6-P1-2: миграции и seed отсюда УБРАНЫ. Раньше каждый старт api гонял
# `alembic upgrade head` + seed под той же ролью, что обслуживает runtime-DML
# (она же владелец БД) — рецидив PENT-F01. Теперь схему двигает ТОЛЬКО
# one-shot сервис `resource-migrate` (profiles: ["tools"], роль-владелец
# `resource`), а api/worker ходят под least-privilege ролью `resource_app`,
# у которой прав на DDL нет вовсе — «миграция при старте» невозможна по
# построению. Порядок деплоя (migrate ДО up) — .claude/skills/uk-deploy.
set -e

exec "$@"
