# Дизайн: Веб-дашборд + Telegram Mini App

**Дата:** 2026-03-10
**Продукт:** UK Management Bot — расширение веб-интерфейсом и TWA
**Статус:** Approved

---

## Контекст

Существующий продукт — Telegram-бот для управляющей компании ЖКХ. Три роли: applicant (жители), executor (исполнители), manager (менеджеры). Стек: Python 3.11, aiogram 3.x, SQLAlchemy 2.x, PostgreSQL, Redis, FastAPI, APScheduler.

Задача: расширить продукт веб-дашбордом для менеджеров и Telegram Mini App для жителей, сохранив параллельную работу с ботом.

---

## Решения по ключевым вопросам

| Вопрос | Решение |
|--------|---------|
| Формат мобильного приложения | Telegram Mini App (TWA) |
| Веб vs бот для менеджеров | Параллельная работа, данные синхронизируются |
| Колл-центр | Форма создания заявки по звонку, без интеграции с АТС |
| Канбан real-time | WebSocket (Redis Pub/Sub) |
| Бэкенд | Расширение существующего FastAPI |
| Авторизация веб | Telegram Login Widget (основной) + email/пароль (резервный) |
| Scope TWA | Расширенный: заявки + история + уведомления + профиль + чат |

---

## Архитектура системы

```
┌──────────────────────────────────────────────────────────────┐
│                        КЛИЕНТЫ                               │
├───────────────────┬──────────────────┬───────────────────────┤
│  Telegram Bot     │  Telegram Mini   │   Web Dashboard       │
│  (существующий)   │  App (новый)     │   (новый)             │
│  Менеджеры +      │  Жители          │   Менеджеры/          │
│  Исполнители      │  (applicant)     │   Диспетчеры          │
└─────────┬─────────┴────────┬─────────┴──────────┬────────────┘
          │       REST API v2 + WebSocket          │
          └──────────────────┴─────────────────────┘
                             │
          ┌──────────────────▼──────────────────────┐
          │           Docker Compose                 │
          │  ┌──────────────┐  ┌────────────────┐   │
          │  │ app          │  │ api            │   │
          │  │ aiogram bot  │  │ FastAPI uvicorn│   │
          │  │ APScheduler  │  │ REST v2        │   │
          │  │ sync SQLAlch │  │ WebSocket      │   │
          │  │              │  │ async SQLAlch  │   │
          │  └──────────────┘  └────────────────┘   │
          │  ┌──────────────┐                        │
          │  │ frontend     │  Nginx, React SPA      │
          │  │ web + TWA    │  (один контейнер)      │
          │  └──────────────┘                        │
          └──────────────┬──────────────────────────┘
                         │
          ┌──────────────┴──────────────┐
          │ postgres      │ redis       │
          │               │ db0: FSM    │
          │               │ db1: Pub/Sub│
          └───────────────┴─────────────┘
```

**Ключевые принципы:**
- Бот (`app`) и REST API (`api`) — два отдельных процесса/контейнера
- Общая PostgreSQL БД, общие SQLAlchemy модели
- Redis db0: FSM + throttling (существующее), db1: Pub/Sub для WebSocket
- Один `frontend` контейнер для Web Dashboard и TWA (разница в рантайме через `window.Telegram?.WebApp`)

---

## Секция 1: Backend расширение

### Новые Docker-сервисы

| Сервис | Описание |
|--------|----------|
| `app` | Существующий (бот + health server) — без изменений |
| `api` | Новый: FastAPI + uvicorn + async SQLAlchemy + REST v2 + WebSocket |
| `frontend` | Новый: React SPA (Nginx), обслуживает web и TWA |
| `postgres` | Без изменений |
| `redis` | Без изменений (добавляется db1 для Pub/Sub) |

### REST API v2 эндпоинты

**Авторизация**

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/v2/auth/telegram-widget` | Верификация Telegram Login Widget (HMAC check) |
| POST | `/api/v2/auth/twa` | Верификация Telegram initData (HMAC-SHA256 с BOT_TOKEN) |
| POST | `/api/v2/auth/login` | Логин по email + пароль |
| POST | `/api/v2/auth/refresh` | Обновление через refresh_token |
| POST | `/api/v2/auth/logout` | Revoke refresh_token |
| POST | `/api/v2/auth/set-password` | Установить/сменить пароль |

**Заявки**

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/v2/requests` | Список с фильтрами + пагинация |
| POST | `/api/v2/requests` | Создать заявку |
| GET | `/api/v2/requests/kanban` | Сгруппировано по статусам |
| GET | `/api/v2/requests/{number}` | Детали заявки |
| PATCH | `/api/v2/requests/{number}` | Обновить статус/данные |
| POST | `/api/v2/requests/{number}/comments` | Добавить комментарий |
| GET | `/api/v2/requests/{number}/comments` | История комментариев |

**Колл-центр**

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/v2/callcenter/search-resident` | Поиск по телефону или ФИО |
| POST | `/api/v2/callcenter/requests` | Создать заявку `source=call_center` |

**Прочее**

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/v2/notifications` | Список уведомлений пользователя |
| PATCH | `/api/v2/notifications/{id}/read` | Отметить прочитанным |
| GET | `/api/v2/profile` | Профиль текущего пользователя |
| PATCH | `/api/v2/profile` | Обновить профиль |
| POST | `/api/v2/profile/documents` | Загрузить документ верификации |

### WebSocket

```
wss://host/ws/v2/kanban?token=<jwt>
```

| Событие | Данные |
|---------|--------|
| `request.created` | Полная карточка заявки |
| `request.status_changed` | `{number, old_status, new_status, updated_by}` |
| `request.assigned` | `{number, executor_id, executor_name}` |
| `request.updated` | Обновлённые поля |
| `notification` | `{type, text, request_number}` |

Redis канал `requests:updates` (db1). Клиент при реконнекте запрашивает `/kanban` для восстановления состояния.

### Изменения в БД (через Alembic)

| Таблица | Изменение |
|---------|-----------|
| `users` | + `password_hash` VARCHAR nullable |
| `users` | + `email` VARCHAR nullable |
| `users` | + `password_reset_token` VARCHAR nullable |
| `users` | + `password_reset_expires_at` TIMESTAMPTZ nullable |
| `requests` | + `source` VARCHAR(20): `bot`/`twa`/`call_center`/`web` + индекс |
| `request_comments` | + `is_internal` BOOLEAN default False |
| `request_comments` | + `media_files` JSON default [] |
| `notifications` | + `request_number` FK (вместо хранения в `meta_data`) |
| `refresh_tokens` | Новая таблица (см. ниже) |

```sql
refresh_tokens:
  id           SERIAL PK
  user_id      INT FK -> users.id
  token_hash   VARCHAR(64)    -- SHA-256 хеш токена
  expires_at   TIMESTAMPTZ
  created_at   TIMESTAMPTZ
  revoked_at   TIMESTAMPTZ nullable
  device_info  TEXT nullable
```

### Обязательные условия перед реализацией (из архитектурного ревью)

1. **Два контейнера** — бот и API разделены. Синхронный SQLAlchemy в боте несовместим с FastAPI WebSocket в одном процессе.
2. **Alembic** — обязателен для всех изменений схемы. Текущий `Base.metadata.create_all()` не делает `ALTER TABLE`.
3. **TWA initData валидация** — HMAC-SHA256 с ключом производным от BOT_TOKEN. Обязательна на серверной стороне.
4. **CORS whitelist** — не `*`, а список доменов фронтенда + `https://web.telegram.org`.
5. **Rate limiting для API** — 100 req/min per user (auth), 10 req/min per IP (login).

---

## Секция 2: Web Dashboard

### Layout

Одностраничное приложение. Навигация: `[Канбан] [Заявки] [Сотрудники] [Отчёты]` в хедере + иконка уведомлений + профиль.

### Авторизация

- Telegram Login Widget (основной способ)
- Email + пароль (резервный)

### Канбан-доска (главный экран)

Колонки по статусам: `Новая | В работе | Закуп | Уточнение | Выполнена | Принято`.

Карточка заявки содержит: номер, категория + иконка, адрес, исполнитель, срочность (цвет), время создания, источник (иконка бот/телефон/веб).

Функциональность:
- Drag & Drop между колонками → смена статуса
- Клик → правый сайдбар с деталями (40% ширины)
- Фильтры: двор, исполнитель, категория
- Real-time обновления через WebSocket
- Кнопка **[+ Создать по звонку]** → колл-центр модал

### Панель деталей заявки (правый сайдбар)

- Статус + dropdown для смены
- Исполнитель + dropdown для назначения
- Описание + медиафайлы
- Чат/комментарии с поддержкой внутренних сообщений (`is_internal`)
- История статусов с таймлайном

### Колл-центр (модальное окно)

Открывается из Канбана. Поиск жителя по телефону или ФИО → автоподстановка адреса и истории. Создание заявки без привязки к жителю (только адрес вручную). Все заявки с `source=call_center`.

### Остальные разделы

| Раздел | Функциональность |
|--------|-----------------|
| Заявки | Табличный вид, расширенные фильтры, экспорт CSV |
| Сотрудники | Одобрение/блокировка, роли, специализации, верификация |
| Отчёты | Метрики по статусам, нагрузка, динамика, графики (Recharts) |
| Смены | Список, назначение, передача, квартальный план |
| Уведомления | Дропдаун в хедере, WS real-time |

---

## Секция 3: Telegram Mini App (TWA)

### Технология

- React 18 + TypeScript + `@twa-dev/sdk`
- Авторизация: `initData` → `POST /api/v2/auth/twa` → JWT (прозрачно, без ввода)
- Тема: адаптируется под тему Telegram
- Язык: из профиля пользователя (ru/uz)
- Определение среды: `window.Telegram?.WebApp?.initData`

### Навигация

Bottom Tab Bar: `🏠 Главная | 📋 Заявки | 🔔 Уведомления | 👤 Профиль`

### Функциональность по экранам

**Главная:** активные заявки жителя + badge "Требует действия" для заявок на приёмке + CTA кнопка "Создать заявку".

**Создание заявки (4 шага):**
1. Адрес (двор/дом/кв из профиля — предзаполнено)
2. Категория (grid) + срочность + описание
3. Фото/видео (необязательно)
4. Подтверждение

**Список заявок:** табы `Все / Активные / Завершённые`, фильтр по статусу и периоду.

**Детали заявки:** статус-таймлайн + чат с диспетчером + медиафайлы.

**Приёмка:** отчёт исполнителя + фото → оценка 1-5 звёзд + комментарий → [Принять] или [Вернуть на доработку].

**Профиль:** данные пользователя, адрес, документы (загрузка), статус верификации, смена языка.

---

## Секция 4: Frontend стек

| Слой | Технология |
|------|-----------|
| Фреймворк | React 18 + TypeScript |
| Роутинг | React Router v6 |
| Состояние | Zustand |
| Канбан | `@dnd-kit/core` |
| WebSocket | Нативный `WebSocket` с реконнектом |
| HTTP | Axios + React Query |
| UI | shadcn/ui + Tailwind CSS |
| Графики | Recharts |
| TWA SDK | `@twa-dev/sdk` |
| Сборка | Vite |

---

## Секция 5: Фазы реализации

| Фаза | Содержание | Срок |
|------|-----------|------|
| 1. Фундамент | Alembic, api-контейнер, JWT auth, TWA initData, CORS | 2-3 нед. |
| 2. REST API | CRUD заявок, kanban endpoint, комментарии, колл-центр, Redis Pub/Sub | 2-3 нед. |
| 3. Real-time | WebSocket endpoint, WS-события | 1 нед. |
| 4. Web Dashboard | Auth, Канбан, детали, колл-центр, пользователи, отчёты | 3-4 нед. |
| 5. TWA | Авторизация, wizard, список, приёмка, чат, профиль | 2-3 нед. |
| 6. Полировка | E2E тесты, нагрузочное тестирование, prod конфиг | 1 нед. |

**Итого: ~12-14 недель для полного MVP**

---

## Вне скоупа v1

- Нативное мобильное приложение (iOS/Android)
- Интеграция с АТС (запись звонков, автоопределение)
- Оплата услуг в TWA
- Показания счётчиков
- Соседский чат
- Google Sheets синхронизация
