# DEVELOPMENT — разработка UK Management

> _Последнее редактирование: 2026-07-06_

Гайд по локальной разработке: Telegram-бот (aiogram 3 / Python 3.11), REST API (FastAPI) и React-дашборд (Vite + TypeScript). Прод-эксплуатация — в `docs/ops/RUNBOOK.md`.

---

## 1. Dev-окружение бота (+ API, PostgreSQL, Redis)

Бот и его зависимости поднимаются через `docker-compose.dev.yml` (hot-reload кода через volume-монтирование, без пересборки образа).

```bash
# Поднять dev-стек (app + postgres + redis)
docker compose -f docker-compose.dev.yml up -d

# Логи бота
docker compose -f docker-compose.dev.yml logs -f app

# Перезапуск после правок (обычно не нужен — код смонтирован volume'ом)
docker compose -f docker-compose.dev.yml restart app
```

Особенности dev-стека (`docker-compose.dev.yml`):
- Образ `Dockerfile.dev`, `LOG_LEVEL=DEBUG`, `DEBUG=true`.
- Код бота смонтирован: `./uk_management_bot:/app/uk_management_bot` (`docker-compose.dev.yml:21`).
- Alembic смонтирован для hot-reload новых ревизий без ребилда: `./alembic`, `./alembic.ini` (`:23-24`).
- Контейнеры называются `uk-management-bot-dev`, `uk-postgres-dev`, `uk-redis-dev` — **не** путать с прод-именами `uk-*` (см. RUNBOOK).
- Пароль БД в dev — фиксированный `uk_bot_password` (`:13`), в проде берётся из `.env`.

> Прод-стек (`docker-compose.yml` + `docker-compose.media.yml`) в разработке напрямую не нужен — он про деплой. Всё описано в `docs/ops/RUNBOOK.md`.

### Роли и локализация (напоминание)
- `user.roles` — JSON-массив строк, `user.active_role` — активная роль. Устаревшее поле `user.role` не использовать.
- Локализация бота: `get_text(key, language=lang)`, статусы через `utils/status_display.py`, адреса через `utils/address_helpers.localize_address()`. Файлы — `config/locales/{ru,uz}.json`. Подробнее — `docs/LOCALIZATION_GUIDE.md`.

---

## 2. Dev-окружение фронтенда (дашборд)

Фронтенд разрабатывается вне Docker — через Vite dev-server с hot-reload.

```bash
cd frontend
npm install          # первый раз
npm run dev          # → http://localhost:5173/uk/
```

Критично:
- **Открывать `http://localhost:5173/uk/`**, а не `http://localhost:5173/`. Базовый путь `base: '/uk/'` (`frontend/vite.config.ts:10`) обязателен — прямой заход на `/` ломает SPA (пустая страница / неверные пути ассетов).
- Dev-server проксирует API/WS на локальный `api` (`http://localhost:8085`): `/uk/api` → `/api`, `/uk/ws` → `/ws` (`frontend/vite.config.ts:39-52`). То есть для полноценной работы дашборда нужен поднятый `api` (порт 8085 — см. прод-compose, либо локально запущенный FastAPI).
- Контейнер `uk-frontend` (порт 3002) — это **nginx со статической сборкой**, не hot-reload. Для разработки использовать `npm run dev`, не dev-контейнер фронта.

Сборка и preview:
```bash
npm run build        # tsc -b && vite build → dist/ (ассеты под /uk/)
npm run preview      # локальный preview собранного бандла
npm run lint         # eslint
```

Подробнее о стеке и структуре — `frontend/README.md`.

---

## 3. Тесты

### Бот — только внутри контейнера
Два набора (оба в CI):

```bash
# 1) unit / handlers / services (testpaths = uk_management_bot/)
docker exec uk-management-bot pytest -q

# 2) API + интеграция / SSOT-гейты (sqlite-conftest'ы)
docker exec uk-management-bot pytest -q tests/api tests/services
```

Замечания:
- Запускать в прод-контейнере `uk-management-bot`; в dev — `uk-management-bot-dev`.
- Корневой top-level `tests/*.py` удалён (был заброшенный legacy) — не воссоздавать пакет `tests/api` как top-level.
- pytest требует `--import-mode=importlib` (зашит в образе через pyproject).

### Фронтенд — vitest
```bash
cd frontend
npm test             # vitest run (одноразовый прогон)
npm run test:watch   # watch-режим
npm run test:cov     # с coverage (v8)
# либо напрямую:
npx vitest
```

---

## 4. Чек-лист: как добавить страницу дашборда

Новая страница дашборда — это 4–5 согласованных точек. Пропуск любой = битый роут/пустой пункт меню/непереведённая метка.

1. **Роут** — `frontend/src/App.tsx`:
   - lazy-import компонента страницы: `const FooPage = lazy(() => import('./pages/FooPage'))` (рядом с `:18-40`).
   - `<Route>` внутри нужного route-group с обёрткой `<PageErrorBoundary>` (пример — `:103-111`).
   - гард доступа: родительский `<ProtectedRoute allowedRoles={[...]}>` (`:102`, `:119`, `:141`). Для отдельного набора ролей — свой route-group, как сделано для `access`/`materials`.

2. **Пункт меню** — `frontend/src/layouts/DashboardLayout.tsx`:
   - добавить запись в `NAV_ENTRIES` (`:71`) — лист `{ to, labelKey, Icon }` или в существующую группу (`children`).
   - при ограничении по ролям — поле `allowedRoles` (сайдбар сам скроет пункт/пустую группу, `:116-117`, `:425-431`).
   - иконка — из `lucide-react` (импорт в `:14-39`).

3. **Локализация метки** — ключ `nav.*`:
   - добавить в `frontend/src/i18n/locales/ru.json` **и** `uz.json` (обе локали обязательны; `en` в проекте нет).

4. **Роль-константа** (если новый набор доступа) — `frontend/src/constants/roles.ts`:
   - это SoT ролей фронта, зеркалит RBAC бэкенда. Новый набор объявлять здесь (пример — `ACCESS_MANAGER_ROLES`, `MATERIALS_MODULE_ROLES`), а не инлайнить массив строк в `App.tsx`/`DashboardLayout.tsx`.

5. **Проверка**: `npm run dev` → `http://localhost:5173/uk/...`, залогиниться ролью с доступом; прогнать `npm run lint` и `npm test`.

---

## 5. Ссылки

- Прод-эксплуатация, деплой, откат, грабли: `docs/ops/RUNBOOK.md`
- Фронтенд (стек, структура, тесты): `frontend/README.md`
- Локализация (бот + фронт): `docs/LOCALIZATION_GUIDE.md`
- SoT ролей фронта: `frontend/src/constants/roles.ts`
- Compose: `docker-compose.dev.yml` (dev), `docker-compose.yml` + `docker-compose.media.yml` (прод)
