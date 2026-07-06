# UK Management — Frontend (дашборд)

> _Последнее редактирование: 2026-07-06_

React-SPA дашборда управления ЖК: канбан заявок, персонал/смены, аналитика, адреса, контроль доступа, складской учёт материалов, а также публичное табло жителей и Telegram Mini App (TWA).

## Стек

- **React 19** + **TypeScript ~5.9**
- **Vite 7** (dev-server, сборка) — `@vitejs/plugin-react`
- **Tailwind CSS 4** (`@tailwindcss/vite`) + **shadcn/ui** (Radix UI primitives)
- **TanStack Query 5** — серверное состояние/кэш запросов
- **Zustand 5** — клиентское состояние (в т.ч. `authStore`)
- **react-router-dom 7** — роутинг
- **i18next** / **react-i18next** — локализация (RU/UZ)
- **axios** — HTTP-клиент; **recharts** — графики; **@dnd-kit** — drag&drop канбана; **sonner** — тосты

Полный список — `package.json`.

## Разработка

```bash
npm install          # первый раз
npm run dev          # → http://localhost:5173/uk/
```

- **Открывать `http://localhost:5173/uk/`**, не `/`. Базовый путь `base: '/uk/'` задан в `vite.config.ts:10` (SPA смонтирована под `/uk/` на общем домене `infrasafe.uz`). Прямой заход на `/` ломает SPA.
- Dev-server проксирует backend: `/uk/api` → `http://localhost:8085/api`, `/uk/ws` → WS на 8085 (`vite.config.ts:39-52`). Для работающих данных нужен поднятый API.
- Контейнер `uk-frontend` (порт 3002) — nginx со статической сборкой, **не** hot-reload; для разработки использовать `npm run dev`.

## Сборка

```bash
npm run build        # tsc -b && vite build → dist/
npm run preview      # предпросмотр собранного бандла
npm run lint         # eslint
```

- Ассеты собранного бандла ссылаются на `/uk/assets/*` (следствие `base: '/uk/'`).
- Тяжёлые вендоры вынесены в отдельные кэшируемые чанки (`manualChunks`, `vite.config.ts:19-25`); страницы `React.lazy`-загружаются (`src/App.tsx`).
- В production-сборке вырезаются `console`/`debugger` (`vite.config.ts:29-33`).

> После редеплоя фронта у открытых сессий возможен stale-chunk (404 стухшего lazy-чанка) → авто-reload по `vite:preloadError`; воркэраунд — `Ctrl+Shift+R`.

## Тесты

```bash
npm test             # vitest run
npm run test:watch   # watch
npm run test:cov     # coverage (v8)
# или: npx vitest
```

Стек тестов: **vitest** + **@testing-library/react** + **jsdom** + **msw** (моки сети).

## Структура `src/`

- `pages/` — страницы-роуты (`KanbanPage`, `AnalyticsPage`, `EmployeesPage`, …; вложенные модули `pages/access/*`, `pages/materials/*`, `twa/*`).
- `components/` — переиспользуемые компоненты; `components/ui/` — shadcn/ui примитивы; `components/shared/` — общие (спиннеры, error boundaries, `LanguageSwitcher`).
- `layouts/` — каркасы; `DashboardLayout.tsx` содержит сайдбар и реестр навигации `NAV_ENTRIES`.
- `hooks/` — кастомные хуки (`useTheme`, `useMediaQuery`, …).
- `stores/` — Zustand-сторы (`authStore` — сессия/роли/hydrating).
- `constants/` — константы; **`constants/roles.ts` — единый источник истины (SoT) ролей фронта** и наборов доступа для route guards (зеркалит RBAC бэкенда).
- `i18n/` — локализация: `index.ts` (init i18next), `apiMaps.ts` (маппинг API-значений → i18n-ключи: статусы/срочность/категории и т.д.), `formatters.ts` (даты/числа по локали), `locales/{ru,uz}.json`. Языка `en` в проекте нет.
- `contexts/`, `lib/`, `utils/`, `twa/` — контексты, утилиты, Telegram Mini App.

## Роутинг и доступ

Роуты и гарды — в `src/App.tsx`. Доступ к странице ограничивается через `<ProtectedRoute allowedRoles={[...]}>`; наборы ролей брать из `constants/roles.ts`, не инлайнить строки.

Как добавить страницу дашборда (роут + пункт меню + i18n-ключ + роль-константа) — пошагово в `../docs/DEVELOPMENT.md` (раздел «Как добавить страницу дашборда»).

## Ссылки

- Разработка (бот + фронт, тесты): `../docs/DEVELOPMENT.md`
- Прод-эксплуатация/деплой: `../docs/ops/RUNBOOK.md`
- Локализация: `../docs/LOCALIZATION_GUIDE.md`
