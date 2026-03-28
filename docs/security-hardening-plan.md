# План исправления уязвимостей (Security Hardening) v3

Основан на SAST-анализе от 2026-03-21.
Обновлён после ревью: security specialist, senior architect, QA analyst.
v3: аудит — исправлены 7 неточностей.

**Итого: 34 находки. Реалистичная оценка: 8-11 часов.**

---

## Phase 0: Критические уязвимости (блокеры для продакшена)

### 0.1 Media Service — закрыть порт + добавить аутентификацию
**Severity: CRITICAL | Effort: 1.5-2 часа**

**Проблема:** Все эндпоинты media_service открыты. Порт `8009:8000` экспонирован наружу в prod compose (строка 84-85). Бот уже ходит по внутреннему URL `http://media-service:8000` (compose строка 20), внешний порт ему не нужен.

**Решение (порядок критичен — порт закрываем ПЕРВЫМ):**

**Шаг 1 (немедленно):** Убрать `ports: "8009:8000"` из `docker-compose.prod.unified.yml:84-85`. Бот уже использует внутренний `http://media-service:8000`. Пока порт открыт — дыра остаётся независимо от наличия API-key.

**Шаг 2:** API-key middleware.

**Конфиг-зазор (выявлен при ревью):**

`media_service/app/core/config.py:42` использует `pydantic_settings.BaseSettings`. Поле `api_keys: List[str] = []` автоматически маппится на env-переменную `API_KEYS` (uppercase имени поля). Чтобы привязать к docker-compose env `MEDIA_API_KEYS`, нужен явный alias:

**Предварительно:** `config.py:66-68` использует устаревший `class Config:` (pydantic v1 стиль). Поведение `alias`/`validation_alias` может отличаться от документации pydantic v2. Мигрировать на `model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)` перед добавлением alias.

```python
# config.py — после миграции на SettingsConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    api_keys: List[str] = Field(default=[], validation_alias="MEDIA_API_KEYS")
```

**Формат значения для List[str]:** pydantic_settings парсит JSON-строку для списков:
```yaml
# docker-compose env
MEDIA_API_KEYS=["key-abc-123","key-def-456"]
```
Или через разделитель, если настроить `settings_customise_sources`. JSON-формат проще и надёжнее.

**Цепочка конфигов (все 6 файлов):**
- `media_service/app/core/config.py:42` — добавить alias/validation_alias для `api_keys`, зафиксировать формат
- `media_service/app/main.py` — добавить middleware, проверяющий `settings.api_keys`
- `uk_management_bot/config/settings.py` — добавить `MEDIA_SERVICE_API_KEY = os.getenv("MEDIA_SERVICE_API_KEY", "")` (одна строка — бот отправляет один ключ)
- `uk_management_bot/integrations/media_client.py` — отправка `X-API-Key: settings.MEDIA_SERVICE_API_KEY`
- `docker-compose.prod.unified.yml` — добавить `MEDIA_API_KEYS=${MEDIA_API_KEYS}` в env media-service, `MEDIA_SERVICE_API_KEY=${MEDIA_SERVICE_API_KEY}` в env бота
- `docker-compose.unified.yml` — аналогично для dev
- `docker-compose.prod.unified.yml:84-85` — **убрать ports (шаг 1)**

**Исключить из auth:** только `GET /api/v1/health` (базовый healthcheck, `health.py:20`) и `GET /api/v1/health/live` (liveness probe, `health.py:165`). НЕ исключать:
- `/api/v1/health/detailed` (`health.py:38` — раскрывает DB status, error details)
- `/api/v1/health/telegram` (`health.py:113` — раскрывает `bot_username`, `bot_id`)
- `/api/v1/health/database` (`health.py:95` — раскрывает `f"Database error: {str(e)}"` в строке 110)
- `/api/v1/health/ready` (`health.py:142` — раскрывает `f"Service not ready: {str(e)}"` в строке 162)

Все 4 эндпоинта либо закрыть API-key, либо убрать `str(e)` из ответов, либо вынести в Phase 3.3.

**Deploy:**
1. Убрать ports (мгновенный эффект, ничего не ломает — бот ходит по internal)
2. Deploy media_service с middleware в grace mode (принимает И с ключом И без)
3. Deploy бот с отправкой API-key
4. Deploy media_service с обязательным ключом (убрать grace mode)

### 0.2 Bot token в URL — убрать утечку
**Severity: CRITICAL | Effort: 1 час**

**Проблема:** `telegram_client.py:136` формирует URL `https://api.telegram.org/file/bot{TOKEN}/...`, который отдаётся клиенту через API и 302-редиректы.

**Решение (минимальное):** Заменить `RedirectResponse(url=file_url)` на `StreamingResponse` — media_service скачивает файл и стримит байты. Токен остаётся на сервере.

**Файлы (API) — 4 группы по типу утечки:**

**Группа A — upload-ответы (есть media_id):**
- `media.py:83` (upload) и `media.py:134` (upload-report): возвращают `file_url` в `MediaUploadResponse`. Заменить на `/api/v1/media/{media_file.id}/file`.

**Группа B — URL/redirect по media_id (есть media_id):**
- `media.py:252-276` (`GET /{media_id}/file`): `RedirectResponse(url=file_url)` → заменить на `StreamingResponse` (скачать через `bot.download_file()`, стримить клиенту с правильным `Content-Type`)
- `media.py:369` (`GET /{media_id}/url`): возвращает `file_url` в JSON → заменить на `/api/v1/media/{media_id}/file`

**Группа C — lookup по telegram_file_id, НАЙДЕН в БД (есть media_id):**
- `media.py:293-301` (ветка `source="database"`): `media_file` есть, `media_file.id` есть → заменить `file_url` на `/api/v1/media/{media_file.id}/file`

**Группа D — lookup по telegram_file_id, НЕ найден в БД (media_file=None, media_id нет):**
- `media.py:304-320` (ветка `source="telegram"`, fallback): `media_file=None`. Здесь нет `media_id`, поэтому `/api/v1/media/{id}/file` невозможен. Текущий код возвращает сырой telegram URL с токеном.

**Решение для группы D:**

Добавить эндпоинт `GET /api/v1/media/telegram/{telegram_file_id}/file` — стримит файл аналогично `/{media_id}/file`, но резолвит через Telegram API напрямую (без записи в БД). В lookup-ответе `file_url` заменить на `/api/v1/media/telegram/{telegram_file_id}/file`.

- `media_service/app/services/telegram_client.py:136` — `get_file_url()` использовать только server-side (не возвращать клиенту)

**Файлы (media frontend — НЕ выносить за scope):**
- `media_service/frontend/app.js:362-367` — preview: `<img src="${data.file_url}">` — токен утекает в src атрибут
- `media_service/frontend/app.js:381-382` — `window.open(data.file_url)` — токен в адресной строке
- `media_service/frontend/app.js:396-398` — download link с `href=file_url`
- `media_service/frontend/app.js:448-449` — `card.dataset.fileUrl` — токен в DOM
- `media_service/frontend/app.js:480-481` — lookup download link

Все эти места потребляют `file_url` из API-ответа. После того как API перестанет возвращать прямую telegram-ссылку (заменит на `/api/v1/media/{id}/file` или `/api/v1/media/telegram/{file_id}/file` для fallback), media frontend подхватит изменение автоматически — URL-ы в ответе будут уже безопасные. Но нужно убедиться что `StreamingResponse` корректно отдаёт Content-Type для img src и download.

**Effort: 1.5-2 часа** (увеличено из-за media frontend, тестирования img/video/download)

**Примечание:** `_copy_to_archive` (строка 476) использует URL server-side — не трогать, безопасно.

### 0.3 Обход блокировки + бесконечный инвайт
**Severity: CRITICAL | Effort: 45 мин**

**Проблема (3 дыры в одном файле — `invite.py:84-124`):**
1. Заблокированный пользователь с инвайтом получает `status = "pending"` — блокировка сбрасывается
2. Nonce инвайта НЕ расходуется при обновлении существующего пользователя — один токен работает бесконечно
3. Роль перезаписывается из инвайта — возможна эскалация привилегий

**Решение:**
```python
# invite.py — ветка existing user (строки 84-124)
invite_data = validation_result.get("invite_data", {})
nonce = invite_data.get("nonce")

# 1. Блокировка: ДО любых обновлений
if existing_user.status == "blocked":
    raise HTTPException(403, "Пользователь заблокирован")

# 2. После обновления existing user — расходовать nonce:
# Сигнатура: mark_nonce_used(self, nonce: str, user_id: int, invite_data: Dict)
invite_service.mark_nonce_used(nonce, existing_user.id, invite_data)
```

**Файлы:**
- `uk_management_bot/web/api/invite.py:84-124` — основное исправление
- `uk_management_bot/web/api/invite.py:65` — `f"Ошибка валидации: {str(e)}"` в validate endpoint — тоже утечка
- `uk_management_bot/web/api/invite.py:157` — убрать `str(e)` из error response

### 0.4 Refresh token не проверяет блокировку
**Severity: CRITICAL (добавлено по ревью) | Effort: 15 мин**

**Проблема:** `/api/v2/auth/refresh` выдаёт новые токены заблокированному пользователю. Login-эндпоинты проверяют `user.status`, refresh — нет.

**Решение:**
```python
# auth/router.py — после загрузки user в /refresh
if user.status != "approved":
    raise HTTPException(403, "Аккаунт неактивен")
```

**Файл:** `uk_management_bot/api/auth/router.py:99-115`

---

## Phase 1: HIGH — сетевая безопасность

### 1.1 CORS — убрать wildcard
**Severity: HIGH | Effort: 5 мин**

**Уточнение после ревью:** Main API (`api/main.py:39-53`) уже использует whitelist — исправлять НЕ нужно. Wildcard только в:
- `uk_management_bot/web/main.py:22` — `allow_origins=["*"]`
- `media_service/app/main.py:70-76` — `allow_origins=["*"]` (после 0.1 менее критично, но нужно)

### 1.2 Security headers в nginx
**Severity: HIGH | Effort: 15 мин**

**Файл:** `frontend/nginx.conf`

```nginx
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' https://telegram.org; frame-src https://oauth.telegram.org; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; connect-src 'self' wss://$host ws://$host; img-src 'self' data: blob:;" always;
```

**Важно:** CSP — обязательное условие для безопасности localStorage-токенов. Пока CSP нет, дефер httpOnly cookies менее обоснован.

### 1.3 WebSocket — замаскировать токен в логах
**Severity: HIGH | Effort: 15 мин** (снижено с 2-3 часов по рекомендации архитектора)

**Проблема:** `ws://host/ws?token=JWT` логируется в nginx access logs. В browser history НЕ попадает (ревью уточнил).

**Решение (минимальное):** Nginx custom log format без query string:
```nginx
log_format ws_format '$remote_addr - $remote_user [$time_local] "$request_method $uri" $status';

location /ws/ {
    access_log /var/log/nginx/ws.log ws_format;
    # ... proxy config
}
```

**Полноценный auth handshake** — отложить на Phase 2 (можно сделать через `Sec-WebSocket-Protocol` header).

### 1.4 Auth guard на TWA роуты
**Severity: HIGH | Effort: 15 мин**

**Уточнение:** `TWARequestDetailPage.tsx` уже имеет `enabled: isAuthenticated` — исправлять НЕ нужно.

**Файлы:**
- `frontend/src/pages/twa/TWAHomePage.tsx` — добавить `enabled: isAuthenticated` в useQuery
- `frontend/src/pages/twa/TWACreatePage.tsx` — НЕ имеет useQuery (только form submit в `submit()` на строке 22). Защита: обернуть `apiClient.post` проверкой `isAuthenticated` или добавить early return если нет auth. Паттерн `enabled` здесь неприменим.

### 1.5 LIKE injection в media_service
**Severity: HIGH | Effort: 20 мин**

**Файл:** `media_service/app/services/media_search.py:47-53` — 4 вызова `.ilike(f"%{query}%")`

```python
def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
```

### 1.6 Race condition + column overflow в номерах заявок
**Severity: HIGH | Effort: 1 час**

**Проблема (2-в-1):**
1. COUNT + increment не атомарен → дубликаты при конкурентных запросах
2. Колонка `String(10)` → при >999 заявок/день номер YYMMDD-NNNN (11 символов) обрежется

**Решение:**
1. `SELECT ... FOR UPDATE` или advisory lock при генерации
2. Расширить колонку до `String(15)` — **PK + все FK-зависимости** (см. ниже)
3. ~~UNIQUE constraint~~ — не нужен, `request_number` уже primary key (`request.py:11`)

**Файлы (бизнес-логика):**
- `uk_management_bot/services/request_number_service.py` — SELECT FOR UPDATE + расширение формата
- `uk_management_bot/services/request_number_service.py:139` — **обновить regex** `r'^\d{6}-\d{3}$'` на `r'^\d{6}-\d{3,}$'` (текущая регулярка отвергает номера с >3 цифрами, ломая создание заявок при >999/день)
- `uk_management_bot/api/requests/router.py:139-144`
- `uk_management_bot/api/callcenter/router.py:76-81`

**Alembic миграция — затронутые столбцы (все `String(10)` → `String(15)`):**
- `request.py:11` — `request_number` PK
- `request_comment.py:19` — `request_number` FK → `requests.request_number`
- `request_assignment.py:19` — `request_number` FK → `requests.request_number`
- `shift_assignment.py:21` — `request_number` FK → `requests.request_number`
- `rating.py:12` — `request_number` FK → `requests.request_number`
- `notification.py:38` — `request_number_fk` FK → `requests.request_number`

**Миграция:** `ALTER TABLE ... ALTER COLUMN request_number TYPE VARCHAR(15)` для каждой из 6 таблиц. PostgreSQL меняет varchar длину без перезаписи данных (только metadata update), даунтайм минимален.

**Effort: 1.5 часа** (увеличено из-за 6 таблиц в миграции + тестирование FK consistency)

### 1.7 Information disclosure
**Severity: MEDIUM** (понижено по ревью — media_service уже имеет prod handler) | **Effort: 30 мин**

**Проблема:** Явные `HTTPException(500, detail=f"...{str(e)}")` обходят global handler.

**Файлы:**
- `media_service/app/api/v1/media.py` — строки 97, 146, 249, 276, 325, 381
- `media_service/app/main.py:173-183` — `/version` эндпоинт возвращает `"debug": settings.debug` (раскрывает режим деплоя)
- `uk_management_bot/web/api/invite.py:65` — `f"Ошибка валидации: {str(e)}"` в validate endpoint
- `uk_management_bot/web/api/invite.py:157` — `f"Внутренняя ошибка сервера: {str(e)}"`

**Решение:** В production заменить `str(e)` на generic message, логировать оригинал. Убрать `debug` из `/version` ответа.

### 1.8 Mass assignment (defense-in-depth)
**Severity: MEDIUM** (понижено после аудита — Pydantic v2 по умолчанию `extra="ignore"`, лишние поля НЕ попадают в `model_dump()`, реального mass assignment нет) | **Effort: 30 мин**

**Решение:** Создать базовый класс `StrictSchema` с `model_config = ConfigDict(extra="forbid")`, наследовать все API-схемы от него. Эффект: клиент получит 422 при неожиданных полях вместо молчаливого игнорирования — defense-in-depth, не блокер.

---

## Phase 2: MEDIUM — укрепление

### 2.1 Rate limiting — добавить недостающие
**Effort: 30-45 мин** (не 15 — web app требует настройки limiter)

**Уже есть (в main API):** login 10/min, telegram-widget 10/min, TWA 20/min, logout 10/min (slowapi).
**Добавить:**
- `/api/v2/auth/refresh` — 20/min (slowapi уже подключен в main API, просто добавить декоратор)
- `web/api/invite.py` registration — 3/min. **Проблема:** `web/main.py` (строка 17) — это отдельное FastAPI-приложение, в котором slowapi НЕ подключен (grep подтвердил — ноль результатов по `limiter|slowapi` в `uk_management_bot/web/`). Нужно: (1) инициализировать Limiter в web app, (2) подключить к state, (3) добавить декоратор на invite endpoint. Либо использовать middleware-подход через Redis напрямую.

### 2.2 localStorage.clear() → точечное удаление
**Effort: 5 мин**

### 2.3 Zustand — partialize persistence
**Effort: 15 мин**

### 2.4 Инфраструктурные дефолты (добавлено по ревью)
**Effort: 30 мин**

**Проблемы:**
1. Redis без `--requirepass` в prod compose
2. PostgreSQL с дефолтным паролем `uk_bot_password` в prod compose
3. `media_service/app/core/config.py:40` — `secret_key = "dev_secret_key_change_in_production"` без проверки
4. Prod compose монтирует source code (`./uk_management_bot:/app/uk_management_bot`) вместо baked-in image

**Решение:**
- Redis: добавить `--requirepass ${REDIS_PASSWORD}`, обновить connection URLs
- PostgreSQL: убрать default fallback, fail если не задан
- media_service: проверка `secret_key` при старте в production
- Prod compose: убрать volume mounts, использовать COPY в Dockerfile

### 2.5 Frontend role guards
**Effort: 15 мин**

### 2.6 uploaded_by impersonation (добавлено по ревью)
**Effort: 15 мин**

После добавления API-key auth (0.1), `uploaded_by` всё ещё client-controlled. Валидировать на стороне бота перед отправкой в media_service.

---

## Phase 3: LOW — полировка

### 3.1 Отключить source maps
**Effort: 1 мин** — `build: { sourcemap: false }` в vite.config.ts
(Vite 5+ по умолчанию отключает, но явно лучше)

### 3.2 Убрать console из production
**Effort: 1 мин** — `esbuild: { drop: ['console', 'debugger'] }` в vite.config.ts

### 3.3 Health endpoints — убрать лишнюю информацию (добавлено по ревью)
**Effort: 20 мин**

`media_service/app/api/v1/health.py` — 4 эндпоинта с info disclosure:
- `/health/detailed` (`health.py:38`) — DB status, error details в `f"error: {str(e)}"` (строки 54, 65, 79)
- `/health/telegram` (`health.py:113`) — `bot_username`, `bot_id` (строки 130-131), error в строке 138
- `/health/database` (`health.py:95`) — `f"Database error: {str(e)}"` (строка 110)
- `/health/ready` (`health.py:142`) — `f"Service not ready: {str(e)}"` (строка 162)

Убрать `str(e)` из HTTP-ответов, закрыть API-key, или объединить с auth middleware из 0.1.

---

## Порядок и приоритизация

| Phase | Что | Усилия | Блокирует прод? |
|-------|-----|--------|----------------|
| **0.1** | Media Service: закрыть порт + auth | 2 ч | **ДА** |
| **0.2** | Bot token → StreamingResponse + media frontend | 2 ч | **ДА** |
| **0.3** | Invite: блокировка + nonce + роли | 45 мин | **ДА** |
| **0.4** | Refresh token проверка статуса | 15 мин | **ДА** |
| 1.1 | CORS (web + media) | 5 мин | Нет |
| 1.2 | nginx security headers | 15 мин | Нет |
| 1.3 | WebSocket log masking | 15 мин | Нет |
| 1.4 | TWA auth guard | 15 мин | Нет |
| 1.5 | LIKE escape | 20 мин | Нет |
| 1.6 | Request number race + column (6 таблиц) | 1.5 ч | Нет |
| 1.7 | Error disclosure | 30 мин | Нет |
| 1.8 | Mass assignment (defense-in-depth) | 30 мин | Нет |
| 2.* | Medium fixes | 2 ч | Нет |
| 3.* | Low fixes | 20 мин | Нет |

**Phase 0: ~5 часов — без этого в продакшен нельзя.**
**Всё вместе: ~9-11 часов.**

---

## Что НЕ нужно делать сейчас

- **httpOnly cookies** — после добавления CSP (1.2) риск localStorage управляем. Рефакторинг бэкенда непропорционален угрозе на старте.
- **WebSocket auth handshake** — log masking достаточно. Полный хэндшейк если понадобится — через `Sec-WebSocket-Protocol` header.
- **SRI для Telegram widget** — виджет обновляется без версионирования, CSP достаточно.
- **Полный аудит Pydantic** — Pydantic v2 уже игнорирует лишние поля по умолчанию. `extra="forbid"` через базовый класс добавляет 422-reject — достаточно.

---

## Deploy strategy (по рекомендации QA)

### Phase 0 — порядок критичен:
1. **Сначала** убрать `ports: "8009:8000"` из prod compose + redeploy media-service (мгновенно закрывает внешний доступ, бот ходит по internal URL — ничего не ломается)
2. Deploy media_service с middleware в grace mode (принимает И с ключом И без)
3. Deploy бот с отправкой API-key
4. Deploy media_service с обязательным ключом (убрать grace mode)

### Остальные фазы — стандартный deploy:
Phase 1-3 не требуют координации фронт/бэк (кроме 1.3 если делать handshake — но мы его отложили).

---

## Верификация

### Phase 0
1. `curl -s http://host:8009/api/v1/health` → connection refused (порт закрыт)
2. `curl media-service:8000/api/v1/media/upload -X POST -H "X-API-Key: wrong"` → 401
3. `curl media-service:8000/api/v1/media/upload -X POST -H "X-API-Key: correct"` → 200/422 (принял запрос)
4. `curl media-service:8000/api/v1/health` → 200 (без ключа, healthcheck работает)
5. Ответы API не содержат `api.telegram.org/file/bot` нигде (grep по JSON ответам)
6. Media frontend: preview/download работают через `/api/v1/media/{id}/file`; lookup fallback — через `/api/v1/media/telegram/{file_id}/file`. Ни один ответ API не содержит `api.telegram.org`
7. Заблокированный пользователь + инвайт → 403
8. Повторное использование того же nonce → ошибка
9. Заблокированный пользователь + refresh token → 403

### Phase 1
10. `curl -H "Origin: https://evil.com" web-api` → нет Access-Control-Allow-Origin
11. `curl -I frontend` → все security headers присутствуют
12. nginx ws.log не содержит `?token=`
13. TWA: страницы без auth не делают API-запросы
14. Поиск в media_service с `%` → корректный результат, не wildcard
15. 2 конкурентных POST /requests → разные номера
16. API ошибка 500 в prod → `{"detail": "Internal server error"}`, без деталей
17. POST с лишним полем `{"is_admin": true}` → 422
18. `GET /version` не содержит `"debug"` в ответе

### Phase 2-3
19. После logout localStorage содержит только нетокеновые ключи
20. `localStorage.getItem('auth-store')` не содержит roles
21. Redis требует пароль
22. Source maps недоступны в production
23. Browser console пуст в production
