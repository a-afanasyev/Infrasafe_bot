# E2E (Playwright) — ручной инструмент, НЕ CI-гейт

> Статус зафиксирован по AUD6-P2-29: спеки лежали в репо без единого
> упоминания в `ci.yml`, создавая иллюзию автоматического E2E-покрытия.
> Решение — явная пометка, а не nightly-джоба: тесты целятся в ЖИВОЙ стек
> (`E2E_BASE_URL`, по умолчанию `http://localhost:5173`), и честный прогон в
> CI потребовал бы поднимать весь compose-стек с ботом, БД и media — это
> отдельная работа, не оправданная тремя спеками.

## Что здесь есть

- `specs/login-flow.spec.ts` — вход (email+пароль+OTP-ветка).
- `specs/route-guard.spec.ts` — гейты маршрутов по ролям.
- `specs/resident-board.spec.ts` — публичное табло жителя.

## Как запускать

```bash
cd tests/e2e
npm ci

# против локального dev-фронта (vite):
#   в соседнем терминале: cd frontend && npm run dev
npx playwright test

# против прод-edge (см. docs/qa/ — так гонялся profk E2E):
E2E_BASE_URL=https://profk.uz/uk npx playwright test
```

⚠️ Dev-фронт на :3002 из docker-compose для E2E НЕ подходит (vite `base=/uk/`
против dev-nginx — SPA мёртв, известная грабля): либо `npm run dev`, либо
прод-edge.

Артефакты (скриншоты/видео/трейсы) — `artifacts/`, отчёт — `html-report/`.
Сид тестового пользователя — `scripts/seed_e2e_user.py`.
