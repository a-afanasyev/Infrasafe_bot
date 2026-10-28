# Мониторинг отключений (news-watch)

> _Последнее редактирование: 2026-10-28_ · фаза 3 программы «ИИ-менеджер» (см. `AI_MANAGER.md`). Код в репо, на проды НЕ раскатан; DARK по умолчанию.

## Что делает

Юзербот читает публичные Telegram-каналы и группы коммунальных служб/хокимията, API решает LLM-ом, касается ли новость **нашего** комплекса (по свободному описанию в настройках), менеджер одобряет — объявление появляется на табло жителей (`board_config.announcements`) и уходит рассылкой в личку жителям и чаты домов. `auto_publish` при высокой уверенности публикует без одобрения (по умолчанию выключен).

Фильтр «правила vs LLM»: список источников, ключевые слова префильтра, каналы рассылки — конфиг; LLM — только релевантность и краткое RU/UZ резюме.

## Компоненты

| Компонент | Где | Заметки |
|---|---|---|
| Юзербот `uk-news-watcher` | `news_watcher/` (Telethon, свой образ `news_watcher/Dockerfile`), compose-сервис `news-watcher` за профилем `news-watch`, том `news_watcher_data:/data` | Bot API чужие каналы не читает — нужен отдельный Telegram-аккаунт (StringSession). Только чтение; подписки обновляет раз в 5 мин из `GET /sources`; offsets по источникам в томе; POST с бэкоффом (4xx не повторяет). Риск: лимиты Telegram на юзерботов — не писать, не спамить join/leave |
| API `/api/v2/news-watch` | `api/news_watch/` | DARK: `NEWS_WATCH_ENABLED=false` → 404. Менеджер (`board.configure`): `GET/PUT /config`, `GET /items?status=`, `POST /items/{id}/publish|reject|retry-broadcast`. Юзербот (`X-Service-Token`): `POST /inbox`, `GET /sources`. **Префикс заявить в edge-allowlist на обеих площадках ДО включения** |
| Конвейер | `services/news_watch/pipeline.py` | дедуп по (chat, message) → префильтр `keywords` → LLM (`NEWS_WATCH_MODEL`, плоская схема, валидация в Python) → `pending` / `ignored`; отказ LLM → `pending` без вердикта (менеджер увидит сырой текст); менеджерам — уведомление через httpx-sender |
| Публикация | `pipeline.publish` + `board_config.service.append_announcement` | объявление первым в `announcements` под тем же FOR UPDATE и в той же транзакции; `broadcast_status=pending` |
| Рассылка | `services/news_watch/broadcast.py`, цикл в `api/lifecycle.py` (30 с, при флаге) | outbox: один элемент за цикл, курсор по `users.id` после каждой отправки (рестарт без дублей), 429 → `retry_after`, 5 попыток → `failed` (менеджер может «повторить»), `running` старше 10 мин → бэкофф; получатели — applicant/approved/не удалён/бот не заблокирован; группы `monitored_groups.kind=residents` |
| Дашборд | `frontend/src/pages/NewsWatchPage.tsx`, пункт «Отключения» | за build-arg `VITE_NEWS_WATCH_ENABLED` (как лифты): очередь по статусам + настройки |
| БД | миграция `028_news_watch`: `news_items`, `news_watch_config` | читает только `api`; грантов `access_app_rw` не нужно |

## Конфиг (`news_watch_config`, singleton)

```json
{"sources": [{"chat": "@toshkent_elektr", "title": "Электросети"}],
 "complex_context": "ЖК …, ул. …, район …, махалля …, ориентиры …",
 "keywords": ["отключ", "электр", "вод", "газ", "suv", "elektr", "gaz", "o'chir", …],
 "auto_publish": false, "min_confidence": 0.8,
 "broadcast": {"dm": true, "residents_groups": true}}
```

## Секреты и включение

Doppler (`uk-management`): `NEWS_WATCH_ENABLED=true` (api), `NEWS_WATCH_SERVICE_TOKEN` (api + news-watcher, один и тот же), `TG_API_ID`, `TG_API_HASH`, `NEWS_WATCH_TG_SESSION` (StringSession отдельного аккаунта), опционально `NEWS_WATCH_MODEL`, `NEWS_WATCH_LLM_TIMEOUT`. Фронт: `VITE_NEWS_WATCH_ENABLED=true` (build-arg).

Порядок: edge-allowlist `/api/v2/news-watch` на обеих площадках → `migrate` (028) → `api` с флагом → фронт с build-arg → `COMPOSE_PROFILES=news-watch up -d news-watcher` → в дашборде заполнить описание комплекса и источники. Выключение: флаг `false` у api (404, цикл рассылки не стартует) и `stop news-watcher` — состояние в таблицах, ничего не теряется.

## Тесты

`tests/services/test_news_watch_config.py`, `test_news_watch_pipeline.py`, `test_news_watch_broadcast.py`, `test_news_watcher_unit.py` (без Telethon), `tests/api/test_news_watch.py`; фронт `NewsWatchPage.test.tsx`. Снимок матрицы прав: +8 маршрутов, +2 public под service-token.
