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

1. `Telegram.WebApp.initDataUnsafe` → extract `user.id`
2. `POST /api/v2/auth/twa` с `initData` → JWT tokens
3. Tokens в memory (не localStorage — Telegram WebApp context)
4. Fallback: если нет initData (QR без Telegram) → redirect на бот

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

## 6. Ресурсы VPS

TWA — это фронтенд (nginx static). Дополнительная нагрузка на API минимальная (те же endpoints). RAM: +0 MB (тот же nginx контейнер). Отдельного сервиса не нужно.
