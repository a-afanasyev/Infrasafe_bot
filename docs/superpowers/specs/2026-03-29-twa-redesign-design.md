# TWA Redesign — UK Management Mini App

**Дата:** 2026-03-29
**Статус:** Approved
**Продукт:** Самостоятельное Telegram Mini App, продаётся отдельно от бота

---

## 1. Контекст

UK Management — система управления заявками ЖК. Существует бот (aiogram), веб-дашборд (React) и базовое TWA (3 страницы). Задача: создать полноценное Mini App для двух ролей (applicant, executor) с дизайном уровня 9-10/10, стилистически согласованным с веб-дашбордом.

**Менеджер:** TWA не нужен — есть бот для уведомлений + полный веб-дашборд.

**Вход:** Telegram initData (через бот) или QR-код в подъезде (deep link `t.me/bot?startapp=...`).

---

## 2. Роли и страницы

### 2.1 Applicant (заявитель) — 6 страниц + 1 push-экран

**Tab Bar:** Главная | Заявки | Создать (+) | Приёмка (badge) | Профиль

| # | Страница | Тип | Описание |
|---|----------|-----|----------|
| A1 | **Главная (Новости)** | Tab | Объявления УК, плановые работы, часы работы, контакты, экстренные номера, QR-код для соседей. Pull-to-refresh. |
| A2 | **Мои заявки** | Tab | Список заявок с фильтром Active/Archive. Badge на табе с количеством активных. Карточки с статусом, категорией, датой. |
| A3 | **Создание заявки** | Tab (+) | Step wizard: категория → адрес (из привязанных квартир) → описание → фото/видео (до 5) → срочность → подтверждение. Progress bar сверху. |
| A4 | **Приёмка** | Tab | Заявки в статусе "Исполнено" (свои + соседи по квартире). Оценка 1-5 звёзд, возврат с причиной и фото. Badge на табе. |
| A5 | **Профиль** | Tab | Имя, телефон, язык (ru/uz), квартира, мои адреса, переключатель уведомлений. |
| A6 | **Детали заявки** | Push | Статус-timeline (вертикальный), описание, фото, исполнитель (аватар+имя), комментарии, кнопка "Связаться". |

### 2.2 Executor (исполнитель) — 8 страниц + 1 push-экран

**Tab Bar:** Задания | Смена | Закуп (badge) | Архив | Профиль

| # | Страница | Тип | Описание |
|---|----------|-----|----------|
| E1 | **Мои задания** | Tab | Активные заявки назначенные мне. Сортировка по срочности. Swipe-actions: "В работу", "Выполнена". Группировка по статусу. |
| E2 | **Смена** | Tab | Кнопка старт/стоп смены. Таймер с текущей длительностью. Текущая специализация. Количество активных заявок. |
| E3 | **Закуп материалов** | Tab | Заявки в статусе "Закуп". Список запрошенных материалов. Фото чека. Кнопка "Закуплено". Badge на табе. |
| E4 | **Архив** | Tab | История выполненных заданий. Средний рейтинг. Статистика: выполнено за неделю/месяц. |
| E5 | **Профиль** | Tab | Специализации (теги), рейтинг (звёзды), отработано часов за месяц, язык. |
| E6 | **Детали задания** | Push | Полная информация: адрес (с кнопкой "Навигация" → карты), описание, фото, заявитель, история статусов. Кнопки действий внизу: "В работу" / "Закуп" / "Уточнение" / "Выполнена". |
| E7 | **Мои смены** | Push (из E2) | Расписание на неделю (горизонтальный скролл по дням). История смен. Учёт времени. |
| E8 | **Отчёт о выполнении** | Push (из E6) | Форма: фото результата (до 5), комментарий, кнопка "Отметить выполненной". |

---

## 3. Дизайн-система

### 3.1 Стиль

Наследует веб-дашборд:
- **Цвета:** CSS variables из дашборда (`--accent`, `--bg-card`, `--text-primary`, etc.)
- **Акцент:** зелёный `#10b981` (emerald-500)
- **Тема:** Telegram WebApp theme params (автоматически light/dark)
- **Скругления:** 12-16px (мобильный стиль, чуть мягче чем веб)
- **Тени:** минимальные, упор на borders

### 3.2 Типографика

- **Display:** тот же font-family что в дашборде (system + IBM Plex Sans)
- **Body:** system font stack (-apple-system, Segoe UI, Roboto)
- **Mono:** IBM Plex Mono (номера заявок)
- Размеры: 13px body, 15px titles, 11px captions

### 3.3 Компоненты (общие)

| Компонент | Описание |
|-----------|----------|
| `BottomTabBar` | 4-5 табов, иконки + текст, badge, haptic feedback |
| `StatusBadge` | Цветные теги статусов (цвета из дашборда) |
| `RequestCard` | Карточка заявки: номер, категория (иконка), статус, дата, описание (1 строка) |
| `StepWizard` | Progress bar + шаги, Back button через Telegram SDK |
| `StarRating` | 5 звёзд, touch-friendly (44px tap targets) |
| `SwipeAction` | Свайп карточки для быстрых действий (iOS-style) |
| `PullToRefresh` | Нативный pull-down для обновления |
| `BottomSheet` | Модальное окно снизу (подтверждения, фильтры) |
| `PhotoUploader` | Камера/галерея, превью сетка, удаление |
| `EmptyState` | Иконка + текст + CTA для пустых списков |
| `Timeline` | Вертикальный timeline статусов заявки |
| `ShiftTimer` | Анимированный таймер текущей смены |

### 3.4 Telegram WebApp SDK

- `Telegram.WebApp.ready()` — инициализация
- `Telegram.WebApp.themeParams` — цвета темы
- `Telegram.WebApp.HapticFeedback` — вибрация на действиях
- `Telegram.WebApp.BackButton` — нативная кнопка "Назад"
- `Telegram.WebApp.MainButton` — основная кнопка внизу (для wizard шагов)
- `Telegram.WebApp.initDataUnsafe` — данные пользователя для авторизации
- `Telegram.WebApp.expand()` — полноэкранный режим
- `Telegram.WebApp.close()` — закрытие Mini App

---

## 4. Архитектура

### 4.1 Файловая структура

```
frontend/src/twa/
├── App.tsx                    # TWA router + Telegram SDK init
├── components/
│   ├── BottomTabBar.tsx
│   ├── StatusBadge.tsx
│   ├── RequestCard.tsx
│   ├── StepWizard.tsx
│   ├── StarRating.tsx
│   ├── SwipeAction.tsx
│   ├── BottomSheet.tsx
│   ├── PhotoUploader.tsx
│   ├── EmptyState.tsx
│   ├── Timeline.tsx
│   ├── ShiftTimer.tsx
│   └── PullToRefresh.tsx
├── pages/
│   ├── applicant/
│   │   ├── HomePage.tsx         # A1: Новости
│   │   ├── RequestsPage.tsx     # A2: Мои заявки
│   │   ├── CreatePage.tsx       # A3: Создание
│   │   ├── AcceptancePage.tsx   # A4: Приёмка
│   │   ├── ProfilePage.tsx      # A5: Профиль
│   │   └── RequestDetailPage.tsx # A6: Детали
│   └── executor/
│       ├── TasksPage.tsx        # E1: Задания
│       ├── ShiftPage.tsx        # E2: Смена
│       ├── PurchasePage.tsx     # E3: Закуп
│       ├── ArchivePage.tsx      # E4: Архив
│       ├── ProfilePage.tsx      # E5: Профиль
│       ├── TaskDetailPage.tsx   # E6: Детали задания
│       ├── MyShiftsPage.tsx     # E7: Мои смены
│       └── CompletionReport.tsx # E8: Отчёт
├── hooks/
│   ├── useTelegramSDK.ts       # Telegram WebApp API wrapper
│   ├── useTWAAuth.ts           # initData авторизация
│   ├── useHaptic.ts            # Haptic feedback
│   └── useRole.ts              # Определение роли → routing
└── styles/
    └── twa.css                 # TWA-specific overrides
```

### 4.2 Routing

```
/twa                    → useRole() → redirect to /twa/app или /twa/exec
/twa/app                → Applicant TabBar (Главная)
/twa/app/requests       → Мои заявки
/twa/app/create         → Создание заявки
/twa/app/acceptance     → Приёмка
/twa/app/profile        → Профиль
/twa/app/requests/:num  → Детали заявки
/twa/exec               → Executor TabBar (Задания)
/twa/exec/shift         → Смена
/twa/exec/purchase      → Закуп
/twa/exec/archive       → Архив
/twa/exec/profile       → Профиль
/twa/exec/tasks/:num    → Детали задания
/twa/exec/shifts        → Мои смены
/twa/exec/report/:num   → Отчёт о выполнении
```

### 4.3 Авторизация

Единственный источник правды — раздел 6.4. Краткое описание flow:

1. При каждом открытии Mini App: `initData` → `POST /api/v2/auth/twa` → JWT
2. Access token — в React context (AuthProvider), refresh token — в localStorage как fallback
3. Axios interceptor берёт token из context, не из localStorage
4. Если initData недоступен → redirect на бот

Детали реализации, отличия от дашборда — см. раздел 6.4.

### 4.4 Shared с дашбордом

- `api/client.ts` — HTTP клиент
- `i18n/` — локали ru/uz + apiMaps
- `types/api.ts` — TypeScript типы
- `hooks/useKanban.ts`, `hooks/useShifts.ts` (частично)

---

## 5. UX-паттерны

### 5.1 Мобильные паттерны

- **Tap targets:** минимум 44x44px
- **Pull-to-refresh** на всех списках
- **Skeleton loading** вместо спиннеров
- **Optimistic updates** для статус-переходов
- **Swipe back** через Telegram BackButton
- **Bottom sheets** вместо модальных окон
- **Haptic feedback** на кнопках действий

### 5.2 Offline-поведение

- Показывать кэшированные данные при потере сети
- Визуальный индикатор "Нет подключения"
- Retry на ошибках сети

### 5.3 Переходы

- Slide-left/right для навигации между табами
- Slide-up для push-экранов (детали)
- Fade для модалок/bottom sheets
- Spring animations (не linear)

---

## 6. Обязательные backend-изменения (BLOCKER для TWA)

TWA не может быть реализовано "как есть" на текущих API endpoints. Ниже — список обязательных изменений API, без которых TWA будет либо сломано, либо небезопасно.

### 6.1 CRITICAL: Data isolation в request endpoints

**Проблема:** `GET /api/v2/requests` и `GET /api/v2/requests/{number}` не фильтруют по владельцу/исполнителю. Любой авторизованный пользователь видит все заявки. `GET /api/v2/requests/{number}/comments` не проверяет, что пользователь — участник заявки.

**Требуемые изменения:**

| Endpoint | Текущее поведение | Требуемое |
|----------|------------------|-----------|
| `GET /requests` | Все заявки (для kanban менеджера) | **Applicant (список "Мои заявки"):** `WHERE user_id = current_user.id` — только свои. **Applicant (приёмка):** отдельный endpoint `GET /requests/acceptance` с `WHERE (user_id = me OR apartment_id IN my_apartments) AND status = 'Исполнено'`. **Executor:** `RequestAssignment` (individual + group по специализациям) + fallback `executor_id` (для старых заявок без RequestAssignment). **Manager:** без изменений. |
| `GET /requests/{number}` | Любой видит любую заявку | Проверка: `user_id = me`, executor (через RequestAssignment ИЛИ executor_id), manager role. **Apartment resident — только если `request.status = 'Исполнено'`** (приёмка). Сосед НЕ видит чужие активные заявки. |
| `GET /requests/{number}/comments` | Нет проверки участия | Тот же ACL что и для деталей заявки (owner, assigned executor, manager, apartment resident только при Исполнено) |
| `POST /requests/{number}/comments` | Нет проверки участия | Аналогично |

**Важно:** Executor query ОБЯЗАН включать fallback на `Request.executor_id` (помимо `RequestAssignment`). Текущий бот-хендлер `_get_executor_requests_query` уже реализует эту логику (requests.py line 1175). API должен повторить её, а не упрощать — иначе старые заявки (назначенные до внедрения RequestAssignment) пропадут из executor TWA.

**Реализация:** Добавить dependency `get_request_with_access_check(request_number, current_user)` в `api/requests/router.py`, которая возвращает 403 если пользователь не имеет доступа. Отдельная dependency `filter_requests_by_role(query, user, role)` для списков.

### 6.2 HIGH: Executor actions через API

**Проблема:** `PATCH /api/v2/requests/{number}` допускает смену статуса только для manager. Executor не может менять статус через API (только через бот).

**Требуемые изменения:**

| Действие | Текущее | Требуемое |
|----------|---------|-----------|
| Executor: "В работу" | Нет в API | `PATCH /requests/{number}` с `status: "В работе"` — разрешить для executor, если он назначен на заявку |
| Executor: "Закуп" | Нет | Разрешить переход "В работе" → "Закуп" для назначенного executor |
| Executor: "Уточнение" | Нет | "В работе" → "Уточнение" |
| Executor: "Выполнена" | Нет | "В работе"/"Закуп" → "Выполнена" + `completion_report` |
| Executor: запрос материалов | Нет | `PATCH /requests/{number}` с `requested_materials` |

**Реализация:** Расширить `update_request()` в `api/requests/router.py`:
- Проверка `is_assigned_executor(user, request)` через `RequestAssignment` **ИЛИ** `request.executor_id == user.id` (fallback для старых заявок — тот же принцип что в п. 6.1)
- Executor может менять: `status` (ограниченные переходы), `completion_report`, `requested_materials`
- Manager может менять всё (как сейчас)

### 6.3 MEDIUM: API для переключения active_role

**Проблема:** Пользователь с ролями `[applicant, executor]` должен видеть разный UI. В боте есть переключение `active_role`, но в API нет endpoint'а для смены роли.

**Требуемые изменения:**

```
PATCH /api/v2/profile/role
Body: { "active_role": "executor" }
Response: { "active_role": "executor", "roles": ["applicant", "executor"] }
```

**Реализация:**
- Новый endpoint в `api/profile/router.py`
- Валидация: `active_role` должен быть в `user.roles`
- `useRole()` в TWA читает `active_role` из профиля, не угадывает

### 6.4 MEDIUM: TWA-specific auth flow

**Проблема:** Текущий `useTWAAuth` сохраняет токены в localStorage. В контексте Telegram WebApp это потенциально небезопасно (WebApp может быть закрыт и очищен в любой момент).

**Решение:**
- Access token — в React context (AuthProvider), НЕ в localStorage
- Refresh token — в localStorage (fallback при перезапуске WebApp без полной re-auth)
- При каждом открытии Mini App — первичная авторизация через `initData` (бесшовная). Если initData доступен — всегда auth через него, refresh token как fallback только для случая когда initData недоступен (теоретически невозможно в Telegram, но defensive).
- Axios interceptor в TWA-контексте берёт access token из context, не из localStorage. Отдельный экземпляр `apiClient` или переконфигурация существующего через provider.
- `POST /api/v2/auth/twa` — достаточен, изменений не требует. Поле `last_active_at` убрано из требований (в модели User его нет, и для MVP оно не нужно).

### 6.5 LOW: Новые API endpoints для TWA

| Endpoint | Назначение | Приоритет |
|----------|-----------|-----------|
| `GET /api/v2/announcements` | Объявления УК для главной страницы | Новый endpoint, новая модель |
| `GET /api/v2/profile/apartments` | Квартиры текущего пользователя (через UserApartment) | **Новый endpoint** — существующие address endpoints (`/api/v2/addresses/*`) защищены `require_roles("manager")` и не могут быть переиспользованы. Нужен user-scoped endpoint: `SELECT a.*, b.address, y.name FROM user_apartments ua JOIN apartments a ... WHERE ua.user_id = current_user.id AND ua.status = 'approved'` |
| `POST /api/v2/requests/{number}/complete` | Executor отмечает выполнение (с фото) | Упрощение: вместо PATCH с кучей полей |
| `POST /api/v2/requests/{number}/accept` | Applicant принимает заявку (с рейтингом) | Упрощение: вместо PATCH |
| `POST /api/v2/requests/{number}/return` | Applicant возвращает заявку | Упрощение: с причиной и фото |
| `PATCH /api/v2/profile/role` | Переключение active_role | См. п. 6.3 |

---

## 7. Scope и фазы реализации

### Phase 1: Backend preparation (BLOCKER)
- 6.1: Data isolation в request endpoints
- 6.2: Executor actions через API
- 6.3: API переключения роли
- 6.4: Auth flow cleanup

### Phase 2: Applicant TWA (6 страниц)
- Компоненты: BottomTabBar, RequestCard, StatusBadge, StepWizard, StarRating, PhotoUploader
- Страницы: A1-A6
- Telegram SDK интеграция

### Phase 3: Executor TWA (8 страниц)
- Компоненты: SwipeAction, ShiftTimer, Timeline
- Страницы: E1-E8
- Executor-specific API интеграция

### Phase 4: Polish
- Animations, haptic feedback
- Offline mode
- QA + live-тест

---

## 8. Ресурсы VPS

TWA — фронтенд (тот же nginx контейнер). Backend-изменения — модификация существующих endpoints, не новые сервисы. RAM: +0 MB. Нагрузка на API: минимальная (мобильные запросы легче desktop).
