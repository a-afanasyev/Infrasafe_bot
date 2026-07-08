# UK ↔ InfraSafe Web Integration

> _Последнее редактирование: 2026-05-21_

**Дата:** 2026-05-14
**Основной домен:** `https://infrasafe.uz` (alias `infrasafe.aisolutions.uz`).

Общий контракт двух репозиториев (`Infrasafe`, `UK`) для размещения UK
под подпутём `/uk/*` единого домена InfraSafe. Каждый агент берёт свой
worklist (§ 6–9) и исполняет до DoD; согласование — через контракты
(§ 3–5), которые меняются только PR в этот файл.

---

## 1. Контекст

### Что уже есть

- **InfraSafe** на 95.46.96.105: `infrasafe-nginx-1` (80/443),
  `infrasafe-app-1` (Express), `infrasafe-postgres-1` (PostGIS),
  `infrasafe-frontend-1` (legacy HTML). См. `CLAUDE.md`.
- **UK Management Bot** в `/Users/andreyafanasyev/Code/UK` — FastAPI бот
  + React/Vite frontend, `docker-compose.production.yml` (6 контейнеров).
  На сервер ещё не задеплоен.
- **Backend-интеграция (HMAC webhooks)** — реализована, спека:
  `docs/superpowers/specs/2026-03-24-infrasafe-uk-integration-v2-design.md`.
- **UK-ссылки в шапке InfraSafe** — уже добавлены 2026-05-14 в
  `index.html`, `about.html`, `documentation.html`, `contacts.html`
  (`<a href="/uk/twa/app">Сервис УК</a>`, `<a href="/uk/login">Вход для УК</a>`).
  Сейчас они ведут на 404 (UK не задеплоен) и **открываются в той же
  вкладке** — нужно добавить `target="_blank" rel="noopener"`.

### Шаг 0: pre-flight (выполняется до всех остальных worklist'ов)

Безопасное изменение, ни от чего не зависит — пусть будет отдельным
коммитом с одним PR. § 9.1 содержит точные diff'ы.

**Сделать первым** (до запуска основной интеграционной работы):

- Добавить `target="_blank" rel="noopener"` + `aria-label` к ссылкам
  «Сервис УК» / «Вход для УК» в 4 HTML-файлах InfraSafe.
- Это превращает текущее «404 в той же вкладке» (плохой UX) в «404 в
  отдельной вкладке» (приемлемо как промежуточное состояние до деплоя UK).
- После этого можно параллельно запускать § 6/7/8.

### Цель плана

Запустить UK под `/uk/*` на том же сервере, чтобы клик из шапки InfraSafe
открывал работающий UK-веб в новой вкладке.

### Не цель

- Не объединение баз (UK и InfraSafe сохраняют свои PostgreSQL).
- Не общий SSO (UK auth остаётся отдельным).
- Не миграция UK на InfraSafe-стек.

---

## 2. Архитектура

```
                          Internet
                             │
                  ┌──────────┴──────────┐
                  │ infrasafe-nginx     │  ← TLS, единственная точка входа
                  │ (leaflet + uk net)  │
                  └──────────┬──────────┘
       ┌──────────────────────┼─────────────────────────────┐
   /  (HTML)              /api/*                          /uk/*
   /admin*                infrasafe-app:3000               ├─ /uk/twa/*    → uk-frontend:80
                          ⚡ HMAC webhook'и от UK           ├─ /uk/login    → uk-frontend:80
   infrasafe-frontend     (через uk-network direct)        ├─ /uk/api/*    → uk-management-api:8080
                                                            └─ /uk/ws/*     → uk-management-api:8080
```

Ключевые решения:

- **Один nginx, один TLS.** Caddy из UK-стека удаляется.
- **Подпуть `/uk/*`** (не поддомен) → один cert, минимум DNS-работы.
- **UK-frontend собирается с `base: '/uk/'`** (single build).
- **`infrasafe-nginx-1` в двух сетях** (`leaflet-network` + `uk-network`).
- **`infrasafe-app-1` тоже в `uk-network`** для direct internal webhook'ов
  (HMAC обязателен, rate-limit 60/min, audit в `integration_log`).
- **HMAC на webhook'ах — всегда**, отключение запрещено.

---

## 3. URL Contract

| Префикс | Владелец |
|---|---|
| `/`, `*.html`, `/admin*`, `/api/*`, `/public/*`, `/css/*`, `/data/*` | InfraSafe |
| `/api/webhooks/uk/*` | InfraSafe API (приём webhook'ов) |
| `/favicon.*`, `/manifest.json`, `/health` | InfraSafe |
| `/uk/` | UK frontend (SPA root) |
| `/uk/twa/app[/...]` | UK TWA (жильцы, Telegram Mini App) |
| `/uk/login`, `/uk/dashboard/*` | UK Web (УК) |
| `/uk/api/*` | UK API |
| `/uk/ws/*` | UK WebSocket |
| `/uk/assets/*`, `/uk/manifest.json` | UK static |

Ссылки в шапке InfraSafe ведут на `/uk/twa/app` и `/uk/login`
(`target="_blank"`).

---

## 4. API & Auth Contract

### 4.1 CORS

**Обязательный prod-список** (origin'ы, без которых интеграция или TWA
ломаются):

| Origin | Зачем |
|---|---|
| `https://infrasafe.uz` | primary domain |
| `https://infrasafe.aisolutions.uz` | alias (legacy) |
| `https://web.telegram.org` | **TWA из Telegram Web** — без этого Mini App не работает |

`http://localhost:5173`, `http://localhost:8080` — только в dev.

```python
# uk_management_bot/api/main.py
allow_origins = os.environ.get("CORS_ORIGINS",
    "https://infrasafe.uz,https://infrasafe.aisolutions.uz,https://web.telegram.org"
).split(",")
allow_credentials = True
# wildcard "*" запрещён при allow_credentials=True
```

В `~/uk/.env`: `FRONTEND_URL=https://infrasafe.uz` (без `/uk/`).

### 4.2 Cookies UK

Атрибуты: `HttpOnly; Secure; SameSite=Strict`, имена с префиксом `uk_*`.

| Cookie | Path | Назначение |
|---|---|---|
| `uk_access` | `/uk/` | передаётся во все UK-запросы (REST и WS handshake) |
| `uk_refresh` | `/uk/api/` | передаётся только в auth endpoints (refresh, logout) |

> **Внимание на path.** Refresh endpoint имеет путь `/uk/api/v2/auth/refresh`
> (см. § 7.2). Cookie `Path=/uk/api/auth/` **не покрывает** `/uk/api/v2/...`
> — браузер не отправит cookie. Поэтому `Path=/uk/api/` (минимально
> ограничивающий путь, который покрывает оба `/uk/api/auth/...` и
> `/uk/api/v2/auth/...`). Альтернатива: переименовать endpoint в
> `/uk/api/auth/refresh` (тогда оставить `Path=/uk/api/auth/`).
> Решение по умолчанию — **Path=/uk/api/**, чтобы не трогать существующую
> URL-семантику UK API.

### 4.3 Запрет `localStorage` для секретов (Web/TWA split)

На общем origin XSS в одной системе даёт доступ к `localStorage` обеих.
Стратегия зависит от клиента — cookie ненадёжен в Telegram WebView, поэтому
TWA остаётся на Bearer:

| Клиент | `access_token` | `refresh_token` | Транспорт refresh |
|---|---|---|---|
| **Web SPA** (`/uk/login`, `/uk/dashboard/*`) | в памяти Zustand store (без `persist`) | **только** httpOnly cookie `uk_refresh` | cookie |
| **TWA** (`/uk/twa/*`, Telegram Mini App) | в памяти + `Authorization: Bearer` для запросов | body JSON (deprecated на 1 релиз) | body |
| **InfraSafe `admin_token`** | `localStorage` (legacy, отдельный план миграции) | — | — |

Подробная реализация — § 6.5 (клиент) и § 7.2 (backend).

### 4.4 Webhook HMAC

- InfraSafe → UK: `UK_API_URL/api/v1/requests`, HMAC-SHA256 + timestamp +
  replay-protection 300s.
- UK → InfraSafe: `http://infrasafe-app:3000/api/webhooks/uk/request`
  (internal через uk-network), тот же формат.
- **HMAC обязателен** независимо от транспорта.

**Ротация секрета — роли по направлениям:**

Канал «InfraSafe → UK» (алерт создаёт заявку):
- **Sender:** InfraSafe `src/clients/ukApiClient.js` подписывает запросы.
  Читает `UK_WEBHOOK_SECRET` (или `UK_WEBHOOK_SECRET_NEXT` если выставлен
  и `UK_USE_NEXT_SECRET=true`).
- **Verifier:** UK `uk_management_bot/api/webhooks/router.py`. Читает оба
  и принимает любой совпавший.

Канал «UK → InfraSafe» (статус заявки → алерт):
- **Sender:** UK `uk_management_bot/services/webhook_sender.py` подписывает
  запросы. Читает `INFRASAFE_WEBHOOK_SECRET` (или
  `INFRASAFE_WEBHOOK_SECRET_NEXT` если выставлен и
  `INFRASAFE_USE_NEXT_SECRET=true`).
- **Verifier:** InfraSafe `src/services/ukIntegrationService.js`. Читает
  оба и принимает любой совпавший.

> **Предусловие R-18.** Если в коде ещё нет логики «принять любой из двух»
> (verifier) и «переключаемый sender» — добавить отдельным PR **до**
> запуска процедуры.

**Процедура (выполняется отдельно для каждого канала или одновременно):**

1. Сгенерить новый секрет: `openssl rand -hex 32`.
2. Прописать `*_NEXT=<new>` в оба `.env` (InfraSafe и UK).
3. Restart обоих сервисов — verifier'ы теперь принимают `OLD || NEW`.
4. Выставить `*_USE_NEXT_SECRET=true` для sender'а той стороны, которая
   шлёт запросы по каналу. Restart sender'а.
5. Подождать ≥1 сутки — убедиться, что входящие запросы успешно
   валидируются NEW.
6. Перенести `*_NEXT` → `*` (без `_NEXT`), удалить `_USE_NEXT_SECRET`.
   Restart обоих сервисов.

### 4.5 CSP

Отдельный header для `/uk/` (Telegram Login Widget требует
`telegram.org` / `oauth.telegram.org`):

```nginx
add_header Content-Security-Policy "
    default-src 'self';
    script-src 'self' https://telegram.org https://oauth.telegram.org;
    frame-src https://oauth.telegram.org;
    connect-src 'self'
                https://infrasafe.uz wss://infrasafe.uz
                https://infrasafe.aisolutions.uz wss://infrasafe.aisolutions.uz;
    style-src 'self' 'unsafe-inline';
    img-src 'self' data: https:;
    font-src 'self' data: https://fonts.gstatic.com;
    object-src 'none'; base-uri 'self'; form-action 'self';
" always;
```

> `connect-src` должен покрывать оба домена — иначе при заходе через
> `infrasafe.aisolutions.uz` WebSocket / fetch к `/uk/api/*` будут
> заблокированы.

### 4.6 Healthcheck

- `https://infrasafe.uz/health` — InfraSafe nginx-уровень.
- `https://infrasafe.uz/uk/api/health` — UK через nginx, отдаёт
  `{"ok": true}` (без service-name, без version).
- `/docs`, `/redoc`, `/openapi.json` FastAPI закрыты в проде:
  `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`.

**Чтобы не сломать docker healthcheck:**

Existing `Dockerfile.api:30-31` и `docker-compose.production.yml:64` делают
HTTP-проверку на `http://localhost:8080/health` (internal, не публикуется).
Сейчас этот endpoint возвращает `{"status":"healthy","service":"api"}` —
**нарушает § 4.6**.

Реализация (предпочтительная — A):

- **A. Два endpoint'а.** Оставить `/health` (internal, для docker) и
  добавить **новый** `/api/health` → `{"ok": true}` (для внешнего
  проксирования). Docker healthcheck не трогаем. nginx правит
  `/uk/api/health` → `/api/health`.
- **B. Альтернатива.** Переименовать `/health` → `/api/health`, обновить
  `docker-compose.production.yml:64` healthcheck-команду. Дополнительный
  координационный шаг.

---

## 5. UI Contract

UK открывается в **новой вкладке** (`target="_blank" rel="noopener"`)
из шапки InfraSafe. Поэтому визуальная унификация не обязательна.

Обязательно:
- `target="_blank" rel="noopener"` + `aria-label` на ссылках InfraSafe → UK.
- `/uk/manifest.json` со `scope: "/uk/"`, `start_url: "/uk/twa/app"` —
  чтобы PWA-install UK не подхватил корневой manifest InfraSafe.
- OG-теги на UK-страницах для шейринга в Telegram:
  `og:site_name="УК · InfraSafe"`, `og:url="https://infrasafe.uz/uk/"`.

Опционально: back-link, Inter font, accent override, title-template —
на усмотрение UK-FE.

---

## 6. Worklist: UK-frontend

**Репо:** `/Users/andreyafanasyev/Code/UK/frontend`

**Файлы:** `vite.config.ts`, `src/App.tsx`, `src/twa/App.tsx`,
`index.html`, `public/manifest.json`, `src/stores/authStore.ts`,
`src/api/client.ts`, `Dockerfile`.

### 6.1 Vite base

```ts
// vite.config.ts
export default defineConfig(({ mode }) => ({
  base: '/uk/',                  // top-level base — обслуживает и dev, и build
  server: {
    proxy: {
      '/uk/api': { target: 'http://localhost:8085', changeOrigin: true,
                   rewrite: p => p.replace(/^\/uk\/api/, '/api') },
      '/uk/ws':  { target: 'ws://localhost:8085', ws: true,
                   rewrite: p => p.replace(/^\/uk\/ws/, '/ws') },
    },
  },
  // ... остальное
}))
```

> `server.base` **не входит** в публичный API Vite (доступно только
> top-level `base`). В dev URL разработчика — `http://localhost:5173/uk/...`.

### 6.2 BrowserRouter basename

```tsx
<BrowserRouter basename={import.meta.env.BASE_URL}>...</BrowserRouter>
```

в `src/App.tsx` и `src/twa/App.tsx`.

### 6.3 Hardcoded пути

```bash
# JSX/HTML атрибуты
grep -rn 'href="/\|to="/\|src="/' frontend/src frontend/index.html

# Programmatic-навигация (BrowserRouter basename её НЕ покрывает!)
grep -rn 'window\.location\.href.*=.*"/\|window\.location\.assign("/' frontend/src
grep -rn 'window\.location\.replace("/\|window\.open("/' frontend/src
grep -rn 'location\.href.*=.*"/' frontend/src
```

Правила правки:

- `<Link to="/login">` / `navigate('/login')` — **не трогать**. React Router
  с `basename` добавит префикс автоматически.
- `<a href="/login">` — заменить на `<a href={`${import.meta.env.BASE_URL}login`}>`
  или конвертировать в `<Link>`.
- `window.location.href = '/login'` — **обходит React Router** → 404 на
  InfraSafe корне. Заменить на `navigate('/login')` или
  `window.location.href = import.meta.env.BASE_URL + 'login'`.
- `<img src="/vite.svg">` (статика из `public/`) — заменить на
  `<img src={`${import.meta.env.BASE_URL}vite.svg`}>`.

### 6.4 Manifest UK (новый файл)

Сейчас `frontend/public/` содержит только `vite.svg` — manifest нужно
**создать**. Файл `frontend/public/manifest.json`:

```json
{
  "name": "УК · InfraSafe", "short_name": "УК",
  "start_url": "/uk/twa/app", "scope": "/uk/",
  "display": "standalone", "theme_color": "#00BFA5",
  "icons": [{ "src": "/uk/favicon.svg", "sizes": "any", "type": "image/svg+xml" }]
}
```

В `frontend/index.html`: `<link rel="manifest" href="/uk/manifest.json">`.

### 6.5 Перенести refresh-token из localStorage в httpOnly cookie

Не одна правка строки — refresh-flow меняется на клиенте И сервере, c
разной стратегией для Web и TWA.

**Web SPA (`/uk/login`, `/uk/dashboard/*`):**

- `frontend/src/stores/authStore.ts:19` — убрать запись refresh в localStorage.
- `frontend/src/api/client.ts:28` — убрать чтение refresh из localStorage.
- Refresh-вызов: `POST /api/v2/auth/refresh` **БЕЗ body** — backend читает
  cookie `uk_refresh` (см. § 7.2).
- `access_token` — в памяти Zustand store **без** `persist`. При перезагрузке
  вкладки SPA вызывает `/api/v2/auth/refresh` и получает новый access из cookie.

**TWA (`/uk/twa/*`, Telegram WebApp):**

- В WebView Telegram cookie-flow ненадёжен (особенно на Android). **Оставить
  `Authorization: Bearer`** для access_token и refresh через body.
- `LoginPage`, `useTWAAuth`, TWA-store **не трогать**.
- Backend (§ 7.2) поддерживает оба пути: cookie (Web) и body (TWA, deprecated
  на 1 релиз).

### 6.6 Внутренний nginx (`frontend/nginx.conf`) — только статика

В UK-frontend образ собирается с внутренним `nginx:alpine`. В существующей
конфигурации `frontend/nginx.conf` могут быть `location /api/` и
`location /ws/` с проксированием на `api:8080` — наследие самостоятельной
архитектуры.

**Контракт префиксации (важно).** Внешний `infrasafe-nginx` проксирует
`location ^~ /uk/ { proxy_pass http://uk-frontend:80/; ... }`. Слэш в
конце `proxy_pass` **срезает префикс `/uk/`** — внутрь контейнера приходят
запросы `/assets/index-abc.js`, `/manifest.json` и т.д. (без `/uk/`).
Поэтому внутренний nginx обслуживает `/assets/`, а не `/uk/assets/`.

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Hashed assets (immutable). Префикс '/assets/' — внешний nginx срезал '/uk/'.
    location ^~ /assets/ {
        expires 1y;
        access_log off;
        add_header Cache-Control "public, immutable";
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

`location /api/` и `/ws/` блоки **удалить** — мёртвый код, который при
локальной отладке (когда uk-frontend поднят без внешнего nginx) направит
запросы в неправильное место.

> **Согласование с § 6.1.** Vite-build с `base: '/uk/'` генерирует HTML
> со ссылками на `/uk/assets/...`. Внешний клиент запрашивает
> `/uk/assets/...`, внешний nginx срезает префикс → внутренний видит
> `/assets/...`. Контракт цельный.

### 6.7 Dockerfile

```dockerfile
# syntax=docker/dockerfile:1.6
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
```

Multi-arch: `docker buildx build --platform linux/amd64,linux/arm64 -t uk-frontend:<sha>`.

### 6.8 DoD

- [ ] `base: '/uk/'` в vite.config.
- [ ] `dist/index.html` ссылается на `/uk/assets/*`.
- [ ] `BrowserRouter basename={import.meta.env.BASE_URL}` в обоих App.
- [ ] Hardcoded paths: `grep -rn 'href="/uk\|href="/api\|src="/[a-z]'`
      чисто (явные абсолютные пути в `<a>`/`<img>`/`<script>` нельзя).
      `<Link to="/...">` и `navigate('/...')` **разрешены** — basename
      добавит префикс автоматически.
- [ ] Programmatic-навигация: `grep -rn 'window\.location\..*=.*"/\|window\.open("/'`
      чисто — обходит React Router и ломает basename.
- [ ] `dist/manifest.json` имеет `scope: "/uk/"`.
- [ ] `refresh_token` отсутствует в `localStorage` Web-SPA (grep).
- [ ] TWA-flow (`useTWAAuth`, `Authorization: Bearer`) не сломан.
- [ ] Refresh-вызов из Web SPA идёт **без** body (cookie-only).
- [ ] WS-auth работает (cookie или ticket — на выбор UK-BE).
- [ ] `frontend/nginx.conf` не содержит `location /api/` / `/ws/`.
- [ ] Multi-arch Dockerfile собирается.

---

## 7. Worklist: UK-backend

**Репо:** `/Users/andreyafanasyev/Code/UK`

**Файлы:** `uk_management_bot/api/main.py`, `api/auth/*`, `config.py`,
`requirements.txt`, `docker-compose.production.yml`, `Caddyfile`,
`Dockerfile`.

### 7.1 CORS

**Это меняет существующую логику.** Сейчас `uk_management_bot/api/main.py:83-89`
читает один `FRONTEND_URL` (и при `DEBUG=False` ограничивается им).
Заменяется на список из env. **Обязательно сохранить `web.telegram.org`** —
без него TWA из Telegram перестанет работать.

```python
CORS_ORIGINS = os.environ.get("CORS_ORIGINS",
    "https://infrasafe.uz,https://infrasafe.aisolutions.uz,https://web.telegram.org"
).split(",")

app.add_middleware(CORSMiddleware,
    allow_origins=CORS_ORIGINS, allow_credentials=True,
    allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"],
    allow_headers=["Authorization","Content-Type","X-Request-ID"],
    expose_headers=["X-Request-ID"])
```

Минимальный prod-список:
- `https://infrasafe.uz` — primary.
- `https://infrasafe.aisolutions.uz` — alias.
- `https://web.telegram.org` — для TWA (обязательно).
- `http://localhost:5173`, `http://localhost:8080` — добавлять только в dev.

### 7.2 Cookies + refresh endpoint

**Login** (`POST /api/auth/login` — для Web SPA):

```python
response.set_cookie("uk_access", access_token,
    httponly=True, secure=True, samesite="strict",
    path="/uk/", max_age=900)
response.set_cookie("uk_refresh", refresh_token,
    httponly=True, secure=True, samesite="strict",
    path="/uk/api/", max_age=604800)         # покрывает /uk/api/v2/auth/refresh
# Тело ответа: только access_token и user-info — БЕЗ refresh.
return {"access_token": access_token, "user": user_info}
```

**Refresh** (`POST /api/v2/auth/refresh` — поддерживает оба клиента):

```python
@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    body: Optional[RefreshBody] = None,
):
    # 1. Web SPA: токен из cookie
    refresh_token = request.cookies.get("uk_refresh")
    source = "cookie"

    # 2. TWA fallback: токен в body (deprecated)
    if not refresh_token and body and body.refresh_token:
        refresh_token = body.refresh_token
        source = "body"
        response.headers["Deprecation"] = "refresh-token in body is deprecated; " \
                                         "migrate to cookie-based flow"

    if not refresh_token:
        raise HTTPException(401, "No refresh token")

    # ... валидация и выпуск нового access + (для cookie) обновление uk_refresh
    new_access = issue_access(...)
    if source == "cookie":
        response.set_cookie("uk_refresh", new_refresh, ...)
        return {"access_token": new_access}
    else:
        # TWA: вернуть в body
        return {"access_token": new_access, "refresh_token": new_refresh}
```

- Через **1 релиз** body-fallback удаляется. TWA к этому моменту должен
  перейти либо на cookie, либо на специальный TWA-flow через
  `Telegram.WebApp.initData` (отдельная задача, вне scope этого плана).

**Какой endpoint что принимает.** UK backend имеет смешанный контракт
auth — не унифицируется единым решением, потому что Web и TWA-клиенты
не пересекаются. Зафиксировать явно:

| Endpoint / транспорт | Web SPA | TWA |
|---|---|---|
| `POST /api/auth/login` | username/password или Telegram Widget → response set-cookies | `Telegram.WebApp.initData` → response в body |
| REST `/api/v2/...` | cookie `uk_access` (через `Path=/uk/`, шлётся автоматически) | `Authorization: Bearer <access>` |
| `POST /api/v2/auth/refresh` | cookie `uk_refresh` (через `Path=/uk/api/`) | body `{"refresh_token": "..."}` (deprecated) |
| WebSocket `/uk/ws/*` | cookie `uk_access` или ticket | ticket (Bearer не пройдёт в WS handshake) |

Backend читает оба источника: если есть header `Authorization: Bearer` —
берёт его (для TWA); иначе — cookie (для Web).

**WebSocket auth.** Web SPA после удаления access_token из **localStorage**
(он живёт только в памяти Zustand) не может прокинуть Bearer header
в WS upgrade-handshake (нет API в браузере). Решение:

- **Ticket-based:** SPA вызывает `POST /api/v2/auth/ws-ticket` (одноразовый
  токен, TTL 30s, использует `uk_access` cookie для auth), затем коннектится
  как `wss://infrasafe.uz/uk/ws/?ticket=<token>`. Backend в `accept()`
  валидирует ticket и удаляет.
- Альтернатива: cookie-based — браузер автоматически шлёт `uk_access` в
  upgrade-запросе, если `Path` и `SameSite` позволяют. Path `/uk/` это
  покрывает. Проверить на staging.

Решение по WS-auth (ticket vs cookie) делает UK-BE с обоснованием в PR.

### 7.3 BotFather (операционно, через @BotFather)

Для `@infrasafebot`:
- **`/setdomain`** → `infrasafe.uz` (Login Widget).
- **`/setmenubutton`** → URL `https://infrasafe.uz/uk/twa/app` (Mini App).

### 7.4 Telegram auth_date

`uk_management_bot/api/auth/service.py:30`: `AUTH_DATE_MAX_AGE_SECONDS = 300`
(было 86400). `auth_date` сделать обязательным в payload.

**Side-effect.** Снижение окна 86400 → 300 секунд означает: пользователи,
чей последний Telegram-Login-Widget hash старше 5 минут, получат **401 при
следующем silent-refresh**. Что нужно:

- **TWA:** перелогинивается автоматически через `Telegram.WebApp.initData`
  на каждом запуске Mini App — пользователь не заметит.
- **Web SPA (`/uk/login` с Telegram widget):** `LoginPage` должен **ловить
  401 от `/api/auth/login`** и показать «Сессия истекла, нажмите Telegram
  снова». Без этого юзер видит белый экран.
- **Существующие активные сессии (через `uk_access`/`uk_refresh` cookies)**
  — не затронуты. `auth_date` проверяется только на свежем Login Widget hash.

### 7.5 Healthcheck и docs

```python
@app.get("/api/health")
async def health(): return {"ok": True}

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
```

### 7.6 Lockfile для Python

Создать `requirements.in`, сгенерить лок:

```bash
# Сохранить текущий pinning как референс
cp requirements.txt requirements.txt.before-lock

# Сгенерировать лок (pin all transitive deps + hashes)
pip-compile requirements.in -o requirements.txt \
    --resolver=backtracking --generate-hashes
# или: uv pip compile requirements.in -o requirements.txt --generate-hashes

# Сравнить — это критично, pip-compile может молча апгрейднуть мажор
diff requirements.txt.before-lock requirements.txt
```

**Гейт:** diff не должен содержать **мажорных апгрейдов** ключевых пакетов
(`fastapi`, `sqlalchemy`, `aiogram`, `pydantic`, `uvicorn`, `alembic`).
Если pip-compile хочет поднять мажор — закрепить старую версию в
`requirements.in` (`fastapi>=0.115,<0.116`), пересгенерить, проверить
заново.

После подтверждения — удалить `requirements.txt.before-lock`, закоммитить
`requirements.in` + `requirements.txt`.

### 7.7 CI/CD

`UK/.github/workflows/ci.yml` с jobs: backend (pytest), frontend
(npm ci + lint + build).

### 7.8 Dockerfile multi-stage

```dockerfile
# syntax=docker/dockerfile:1.6
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --require-hashes --user --no-warn-script-location \
        -r requirements.txt

FROM python:3.11-slim AS runtime
WORKDIR /app
# libpq runtime для psycopg
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Источники приложения
COPY uk_management_bot ./uk_management_bot
COPY scripts ./scripts

# Миграции и runtime-конфиги (необходимы для alembic upgrade head)
COPY alembic ./alembic
COPY alembic.ini ./
# COPY locales ./locales              # если бот использует i18n
# COPY templates ./templates          # если есть Jinja-шаблоны

CMD ["uvicorn", "uk_management_bot.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 7.9 DoD

- [ ] CORS принимает `infrasafe.uz`, `infrasafe.aisolutions.uz`,
      `web.telegram.org`. Список тянется из `CORS_ORIGINS` env.
- [ ] `Set-Cookie` имеет `HttpOnly; Secure; SameSite=Strict` для обеих:
      - `uk_access`: **`Path=/uk/`** (шлётся во все UK-запросы).
      - `uk_refresh`: **`Path=/uk/api/`** (покрывает `/uk/api/v2/auth/refresh`).
- [ ] `POST /api/v2/auth/refresh` читает refresh из cookie `uk_refresh`;
      body-fallback присутствует с `Deprecation` header (для TWA).
- [ ] WS-auth работает через cookie или ticket-endpoint
      (`POST /api/v2/auth/ws-ticket`).
- [ ] `AUTH_DATE_MAX_AGE_SECONDS=300`, `auth_date` обязателен.
- [ ] `/api/health` → `{"ok": true}` (без service-name, version).
- [ ] Docker healthcheck (`localhost:8080/health` или новый `/api/health`)
      не падает. Реализация задокументирована (вариант A или B из § 4.6).
- [ ] `/docs`, `/redoc`, `/openapi.json` → 404 в проде.
- [ ] `requirements.txt` — lockfile с `--generate-hashes` (sha256 на каждом
      пакете). `pip install -r` запускается с `--require-hashes`.
- [ ] `UK/.github/workflows/ci.yml` зелёный.
- [ ] Runtime-образ **измерен**: `docker images uk-api --format '{{.Size}}'`,
      результат записан в DoD-комментарий PR. Целевой бюджет < 250 MB; при
      превышении — обоснование (например, scipy/numpy в зависимостях).
- [ ] BotFather `/setdomain` + `/setmenubutton` настроены.

---

## 8. Worklist: InfraSafe-deploy

**Репо:** `/Users/andreyafanasyev/Code/Infrasafe`, сервер 95.46.96.105.

**Файлы:** `nginx.production.conf`, `docker-compose.unified.yml`, на
сервере `~/uk/`, `~/uk/.env`, `~/infrasafe/.env.prod`.

### 8.1 nginx /uk/* блоки

Обязательно `^~` приоритет (regex `~* \.(html|htm)$` иначе перебьёт):

```nginx
location ^~ /uk/ {
    proxy_pass         http://uk-frontend:80/;
    proxy_set_header   Host $host;
    proxy_set_header   X-Real-IP $remote_addr;
    proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Host $host;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_connect_timeout 2s;
    proxy_read_timeout    30s;
    add_header Content-Security-Policy "..." always;   # см. § 4.5
    error_page 502 503 504 /uk-unavailable.html;
}

location ^~ /uk/api/ {
    proxy_pass         http://uk-management-api:8080/api/;
    proxy_set_header   Host $host;
    proxy_set_header   X-Real-IP $remote_addr;
    proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_connect_timeout 2s;
    proxy_read_timeout    30s;
}

location ^~ /uk/ws/ {
    proxy_pass         http://uk-management-api:8080/ws/;
    proxy_http_version 1.1;
    proxy_set_header   Upgrade $http_upgrade;
    proxy_set_header   Connection "upgrade";
    proxy_set_header   Host $host;
    proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_read_timeout    86400s;
    proxy_send_timeout    86400s;
}

location = /uk-unavailable.html { root /usr/share/nginx/html; internal; }
```

`~/infrasafe/uk-unavailable.html` — статика «УК-сервис временно
недоступен. Мониторинг работает». Bind-mount в nginx-контейнер.

### 8.2 Compose правки

**A. UK production compose** (`~/uk/docker-compose.production.yml`):

```yaml
services:
  app:
    container_name: uk-management-bot      # имя в DNS docker-сети
    mem_limit: 192M
    cpus: 0.5
    networks: { uk-network: { aliases: [uk-management-bot] } }
  api:
    container_name: uk-management-api      # ⚠ nginx ссылается на это имя
    mem_limit: 256M
    cpus: 0.5
    networks: { uk-network: { aliases: [uk-management-api] } }   # без ports
  frontend:
    container_name: uk-frontend
    image: uk-frontend:<sha>
    mem_limit: 32M
    cpus: 0.2
    networks: { uk-network: { aliases: [uk-frontend] } }         # без ports
  postgres:
    container_name: uk-postgres
    mem_limit: 384M
    cpus: 0.5
    networks: { uk-network: { aliases: [uk-postgres] } }
  redis:
    container_name: uk-redis
    mem_limit: 64M
    cpus: 0.2
    networks: { uk-network: { aliases: [uk-redis] } }
  # caddy: REMOVED
volumes:
  # caddy_data:   REMOVED — был только для Caddy
  # caddy_config: REMOVED — был только для Caddy
  postgres_data: {}
  redis_data: {}
networks:
  uk-network: { name: uk-network }
```

При удалении блока `caddy:` обязательно удалить и `caddy_data:` /
`caddy_config:` из top-level `volumes:` — иначе остаются осиротевшие
volume'ы.

**Точечно удалить только реальные Caddy volume'ы.** Имена в Docker
формируются как `<projectName>_<volumeKey>` (project = имя
compose-директории либо `name:` в compose). Сначала найти их:

```bash
docker volume ls --format '{{.Name}}' | grep -i caddy
# Пример вывода: uk_caddy_data, uk_caddy_config
# (или infrasafe_caddy_data — зависит от того, как UK поднимался ранее)
```

Затем удалить **только то, что нашли**:

```bash
for v in $(docker volume ls --format '{{.Name}}' | grep -i caddy); do
    docker volume rm "$v"
done
```

> **Не делать `docker volume prune`** — он удалит **все** unused volumes на
> хосте, включая возможные изолированные dev-volume'ы рядом с InfraSafe
> или другими проектами. Рядом с production-postgres любое prune опасно.

**B. InfraSafe unified compose**:

```yaml
services:
  nginx: { networks: [leaflet-network, uk-network] }
  app:   { networks: [leaflet-network, uk-network] }    # для internal webhook'ов
networks:
  uk-network: { external: true, name: uk-network }
```

### 8.3 Env-файлы

`~/uk/.env`:

```
# Postgres credentials (используются также init-скриптом контейнера)
POSTGRES_DB=uk
POSTGRES_USER=uk_app
POSTGRES_PASSWORD=<random>
POSTGRES_HOST=uk-postgres
POSTGRES_PORT=5432

# DATABASE_URL — единая строка для FastAPI/SQLAlchemy/alembic
DATABASE_URL=postgresql+psycopg://uk_app:<random>@uk-postgres:5432/uk

# Redis credentials
REDIS_PASSWORD=<random>
REDIS_HOST=uk-redis
REDIS_PORT=6379

# REDIS_URL — единая строка для клиента
REDIS_URL=redis://:<random>@uk-redis:6379/0

TELEGRAM_BOT_TOKEN=<from BotFather>

FRONTEND_URL=https://infrasafe.uz
CORS_ORIGINS=https://infrasafe.uz,https://infrasafe.aisolutions.uz,https://web.telegram.org

INFRASAFE_WEBHOOK_ENABLED=true
INFRASAFE_WEBHOOK_URL=http://infrasafe-app:3000/api/webhooks/uk
INFRASAFE_WEBHOOK_SECRET=<тот же что в InfraSafe>
# INFRASAFE_WEBHOOK_SECRET_NEXT=         # для ротации (§ 4.4), пусто в нормальной работе

DEBUG=false
```

> `DATABASE_URL` и `REDIS_URL` — обязательны, потому что код UK
> (`uk_management_bot/db/session.py`, `redis_client.py`) ожидает единые
> connection strings. Host/port-переменные дублируются для
> совместимости со скриптами и docker-init.

Применить **сразу при создании**:

```bash
chmod 600 ~/uk/.env
chown $(id -u):$(id -g) ~/uk/.env       # как user infrasafe, не root
```

`~/infrasafe/.env.prod` (добавить, БЕЗ trailing slash):

```
UK_API_URL=http://uk-management-api:8080
UK_SERVICE_USER=<сервисный логин>
UK_SERVICE_PASSWORD=<секрет>
UK_WEBHOOK_SECRET=<тот же что в UK>
# UK_WEBHOOK_SECRET_NEXT=                # для ротации (§ 4.4)
```

После правки: `chmod 600 ~/infrasafe/.env.prod`.

В БД: `UPDATE integration_config SET value='true' WHERE key='uk_integration_enabled';`

### 8.4 Порядок применения

0. **TLS-сертификат для `infrasafe.uz`** — SAN-cert на оба домена.

   **Preflight: выбрать flow по реальной конфигурации nginx.**
   ```bash
   docker exec infrasafe-nginx-1 nginx -T 2>/dev/null | \
       grep -E 'root |listen 80|.well-known/acme-challenge' | head
   ```
   - Если есть `location /.well-known/acme-challenge/` с `root /var/www/html`
     или подобным — **webroot flow**:
     ```bash
     sudo certbot certonly --webroot -w <реальный root> \
         -d infrasafe.uz -d infrasafe.aisolutions.uz
     ```
   - Если такого блока нет — **предпочтительно** добавить его временно
     (см. ниже), потому что **standalone flow требует остановки nginx
     целиком** — это даунтайм и на 80, и на 443 (HTTPS-сайт InfraSafe
     лежит ~30–60 сек на время выпуска):
     ```bash
     # standalone — ⚠ полный downtime InfraSafe на время certbot
     docker stop infrasafe-nginx-1
     sudo certbot certonly --standalone -d infrasafe.uz -d infrasafe.aisolutions.uz
     docker start infrasafe-nginx-1
     ```
     **Альтернатива без downtime** — временно добавить webroot:
     ```nginx
     # внутри server { listen 80; ... }
     location /.well-known/acme-challenge/ {
         root /var/www/certbot;
     }
     ```
     Создать `~/infrasafe/certbot-webroot/` и bind-mount в nginx-контейнер
     на `/var/www/certbot`. После выписки cert этот блок можно оставить
     для будущих renewals.
   После: `sudo certbot renew --dry-run`. Cron `/etc/cron.d/certbot` —
   проверить что он есть и не вызывает downtime (через `--deploy-hook
   "docker exec infrasafe-nginx-1 nginx -s reload"`).
1. Бенчмарк ресурсов (§ 11). Если >1.0 GB — план B.
2. Backup в `~/uk-deploy-backups/<ts>/`:
   ```bash
   TS=$(date +%Y%m%d-%H%M%S)
   BACKUP=~/uk-deploy-backups/$TS
   mkdir -p $BACKUP && chmod 700 $BACKUP
   cp ~/infrasafe/nginx.production.conf       $BACKUP/
   cp ~/infrasafe/docker-compose.unified.yml  $BACKUP/
   cp ~/infrasafe/.env.prod                   $BACKUP/env.prod.bak
   # Записываем точку отката alembic UK для § 8.5
   if docker ps --format '{{.Names}}' | grep -q '^uk-management-api$'; then
       docker exec uk-management-api alembic current --verbose 2>/dev/null \
           | grep -oE '^[a-f0-9]{12}' > $BACKUP/uk-alembic-head.txt
   else
       echo "base" > $BACKUP/uk-alembic-head.txt   # UK не запущен — точка отката = "base"
   fi
   ```
3. `cd ~ && git clone <UK repo> uk && cd uk`.
4. `~/uk/.env` положить (`chmod 600`, см. § 8.3).
5. Удалить `caddy:` блок из UK compose **и** `caddy_data` / `caddy_config`
   из top-level volumes (см. § 8.2).
6. Доставка образа `uk-frontend:<sha>` — выбрать один из:
   - **a) GHCR** (предпочтительно): CI пушит в `ghcr.io/<org>/uk-frontend:<sha>`,
     на сервере `docker pull`. Требует GHCR token в `~/.docker/config.json`.
   - **b) Локальный registry** (если CI нет): `docker run -d -p 5000:5000
     --restart=always registry:2` на сервере; локально
     `docker push localhost:5000/uk-frontend:<sha>` через ssh-tunnel.
   - **c) `docker save | docker load`** (медленно, только для одноразового
     bootstrap): `docker save uk-frontend:<sha> | ssh server 'docker load'`.
     Образы 200–400 MB → 5–30 мин через средний канал.
7. `docker compose -f ~/uk/docker-compose.production.yml up -d`.
7a. **Проверка миграций UK** (alembic запускается в entrypoint api/app):

```bash
docker logs uk-management-api | grep -E 'alembic|migration' | tail -20
# При ошибке "Can't locate revision" или другой — миграция не накатилась:
docker exec uk-management-api alembic upgrade head
# При конфликте versions — рассмотреть rollback в § 8.5
```

8. `docker network inspect uk-network` — 5 UK-контейнеров.
9. Обновить `~/infrasafe/docker-compose.unified.yml` (§ 8.2 B).
10. Обновить `~/infrasafe/nginx.production.conf` (§ 8.1).
11. `docker exec infrasafe-nginx-1 nginx -t` (обязательно ДО reload).
12. `docker compose -f ~/infrasafe/docker-compose.unified.yml up -d nginx app`.
13. SQL `integration_config`.
14. Smoke (§ 9).

### 8.5 Rollback

Триггер: `/health` не отвечает >30s или `/uk/api/health` ≥500 в течение >60s.

```bash
TS=<timestamp бэкапа>
BACKUP=~/uk-deploy-backups/$TS

# 1. Откатить UK alembic, если миграции успели накатиться.
#    Получить точку отката (запомненную до деплоя в $BACKUP/uk-alembic-head.txt).
PREV_HEAD=$(cat $BACKUP/uk-alembic-head.txt)
docker exec uk-management-api alembic downgrade $PREV_HEAD || \
    echo "alembic downgrade failed — БД остаётся forward-migrated; см. § 8.5.1"

# 2. Останавливаем UK
docker compose -f ~/uk/docker-compose.production.yml down

# 3. Восстанавливаем InfraSafe-конфиги и env
cp $BACKUP/nginx.production.conf ~/infrasafe/nginx.production.conf
cp $BACKUP/docker-compose.unified.yml ~/infrasafe/
cp $BACKUP/env.prod.bak ~/infrasafe/.env.prod

# 4. Отключаем integration flag
docker exec infrasafe-postgres-1 psql -U postgres -d infrasafe -c \
    "UPDATE integration_config SET value='false' WHERE key='uk_integration_enabled';"

# 5. Возвращаем InfraSafe nginx + app в pre-deploy состояние
docker compose -f ~/infrasafe/docker-compose.unified.yml up -d --force-recreate nginx app
docker exec infrasafe-nginx-1 nginx -t && docker exec infrasafe-nginx-1 nginx -s reload
curl -sk https://infrasafe.uz/health | grep -q healthy
```

#### 8.5.1 Что делать если alembic downgrade не удался

UK миграции могут содержать destructive операции (DROP COLUMN, DROP TABLE,
DATA-MIGRATION). Если `alembic downgrade` падает:

1. **Forward-compatibility default**: новые миграции должны быть написаны
   так, чтобы downgrade был безопасен. Это часть code review UK-BE PR
   (зафиксировать как обязательное требование).
2. **Если revert невозможен** — БД остаётся на новой схеме, UK выключен,
   InfraSafe работает. Это допустимое деградированное состояние; следующий
   попытка деплоя пойдёт с тем же DB-state.
3. **`pg_dump` бэкап UK** перед деплоем (см. § 8.6) — последний resort:
   `pg_restore` поверх.

Сохранение `$BACKUP/uk-alembic-head.txt` выполнено в § 8.4 шаг 2 (Backup).
Если UK ещё не запущен на момент первого деплоя — head записывается как
`base`, и rollback `alembic downgrade base` корректно очистит свежие
миграции.

Скрипт в `~/rollback-uk-integration.sh` (0700), тестируется на dev.

### 8.6 Backup strategy

`/etc/cron.daily/infrasafe-backups`:

```sh
#!/bin/sh
set -eu

BACKUP_ROOT=/home/infrasafe/backups        # явная переменная — защита от опечатки
TS=$(date +%Y%m%d)
DIR="$BACKUP_ROOT/$TS"

# Sanity: не работаем за пределами BACKUP_ROOT
case "$DIR" in
    "$BACKUP_ROOT"/*) ;;
    *) echo "FATAL: refuse to write outside $BACKUP_ROOT"; exit 1 ;;
esac

mkdir -p "$DIR" && chmod 700 "$DIR"

docker exec infrasafe-postgres-1 pg_dump -U infrasafe_app -d infrasafe -Fc -f /tmp/i.dump
docker cp infrasafe-postgres-1:/tmp/i.dump "$DIR/"
docker exec uk-postgres            pg_dump -U uk_app        -d uk        -Fc -f /tmp/uk.dump
docker cp uk-postgres:/tmp/uk.dump "$DIR/"
tar -czf "$DIR/configs.tgz" \
    /home/infrasafe/uk/docker-compose.production.yml \
    /home/infrasafe/infrasafe/docker-compose.unified.yml \
    /home/infrasafe/infrasafe/nginx.production.conf

# Retention 7d — только числовые subdirs, никаких rm -rf произвольных путей
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '[0-9]*' -mtime +7 \
    -print0 | xargs -0 -r rm -rf --
```

Demo-grade (без offsite). Production требует S3/rclone.

### 8.7 Очистка legacy

`Dockerfile.unified` (Node 18, `npm run dev` в проде) — переименовать в
`Dockerfile.dev` или удалить. Прод — только `Dockerfile.prod`.

### 8.8 DoD

- [ ] `docker ps | grep caddy` → пусто.
- [ ] `ss -tlnp | grep -E ':80|:443'` → только `infrasafe-nginx`.
- [ ] `nft list ruleset` не изменился.
- [ ] `docker network inspect uk-network` → 7 контейнеров (5 UK +
      nginx + app).
- [ ] `curl -sk https://infrasafe.uz/uk/api/health` → `{"ok": true}`.
- [ ] `curl -sk https://infrasafe.uz/uk/login` → 200, HTML с
      `/uk/assets/...`.
- [ ] `docker exec infrasafe-nginx-1 nginx -t` → OK.
- [ ] `UK_API_URL` без trailing slash.
- [ ] `~/infrasafe/uk-unavailable.html` отдаётся при `docker stop uk-frontend`.
- [ ] Rollback-скрипт протестирован на dev.
- [ ] **Webhook без HMAC отбивается**: из uk-network контейнера
      `curl http://infrasafe-app:3000/api/webhooks/uk/request -d '{}' \
      -H 'Content-Type: application/json'` → 401.
- [ ] **Rate-limit на webhook endpoint работает**: 65 валидных HMAC-запросов
      подряд → последние ≥4 возвращают 429. Если нет — добавить
      `express-rate-limit` middleware или `limit_req_zone` в nginx для
      `/api/webhooks/uk/*`.
- [ ] **Audit trail**: каждый принятый webhook → запись в `integration_log`
      с `source_ip` и `correlation_id`. Проверка:
      `SELECT count(*) FROM integration_log WHERE created_at > NOW() - INTERVAL '5 minutes'`.

---

## 9. Worklist: InfraSafe-frontend

**Репо:** `/Users/andreyafanasyev/Code/Infrasafe`.

### 9.1 target="_blank" на UK-ссылках

Файлы: `index.html:55-56`, `about.html:31-32`, `documentation.html:31-32`,
`contacts.html:34-35`.

```diff
- <li><a href="/uk/twa/app">Сервис УК</a></li>
- <li><a href="/uk/login">Вход для УК</a></li>
+ <li><a href="/uk/twa/app" target="_blank" rel="noopener"
+        aria-label="Сервис УК (открывается в новой вкладке)">Сервис УК</a></li>
+ <li><a href="/uk/login" target="_blank" rel="noopener"
+        aria-label="Вход для УК (открывается в новой вкладке)">Вход для УК</a></li>
```

### 9.2 Mobile-видимость (опционально, follow-up)

`css/style.css:1689-1691` скрывает `.main-nav { display: none }` на
≤768px. Поскольку UK живёт в новой вкладке и мобильные жильцы идут через
Telegram-бота — не блокер деплоя. Решить отдельной задачей: burger-меню
или primary-button.

### 9.3 frontend-redesign (TODO)

При мерже ветки `feature/frontend-redesign` повторить добавление двух
ссылок с `target="_blank"` в её навигации.

### 9.4 DoD

- [ ] Все 4 HTML содержат `target="_blank" rel="noopener"` + `aria-label`.
- [ ] Клик открывает UK в новой вкладке.
- [ ] Lighthouse Accessibility ≥ 95 на главной.
- [ ] TODO для frontend-redesign создан.

---

## 10. QA / verify

После DoD всех агентов:

### 10.1 URL smoke

```bash
BASE=https://infrasafe.uz
for url in / /about.html /uk/login /uk/twa/app /uk/api/health /uk/manifest.json; do
  echo "$url → $(curl -sk -o /dev/null -w '%{http_code}' -m 5 $BASE$url)"
done
# expect: 200 везде
```

### 10.2 Шапка

Desktop: видны «Сервис УК», «Вход для УК», hover = `#00BFA5`.
Клик → новая вкладка с UK SPA.

### 10.3 UK SPA

DevTools → Network: `/uk/twa/app` → 200, все assets под `/uk/assets/*`.

### 10.4 Auth УК

Логин → `/uk/dashboard`. Cookies: `uk_access`, `uk_refresh` —
`HttpOnly; Secure; SameSite=Strict`, `uk_access` с `Path=/uk/`,
`uk_refresh` с `Path=/uk/api/`. В `localStorage`
нет токенов UK.

### 10.5 Telegram

- Из бота `@infrasafebot` → menu button → Mini App открывается.
- Login Widget на `/uk/login` работает без CSP-блокировок.

### 10.6 Webhook end-to-end

1. POST `/api/alerts` в InfraSafe.
2. В UK Kanban появляется заявка с `external_id`.
3. Закрыть в UK → webhook на infrasafe-app.
4. `infrastructure_alerts.status = 'resolved'` в InfraSafe DB.
5. `integration_log` содержит обе записи.

### 10.7 Negative

- `/api/webhooks/uk/request` без HMAC → 401.
- Origin `https://evil.example.com` в UK API → CORS отклоняет.

### 10.8 Load

```bash
wrk -t2 -c20 -d30s https://infrasafe.uz/uk/login
# expect: p99 < 2s, error rate < 1%
```

`docker stats` параллельно — ни один контейнер не превышает `mem_limit`.

### 10.9 Graceful degradation

```bash
docker stop uk-frontend

# Ожидаем: HTTP 502, тело = содержимое /uk-unavailable.html
# error_page без 'recursive' и без сменя статуса возвращает оригинальный 502
curl -sk -o /tmp/body -w 'HTTP=%{http_code}\n' https://infrasafe.uz/uk/login
grep -q "временно недоступен" /tmp/body && echo "fallback body OK"

# Если хочется отдавать 200 + страницу (UX чище), добавить в nginx:
#   error_page 502 503 504 =200 /uk-unavailable.html;
# (тогда ожидание curl выше = HTTP=200)

curl -sk -o /dev/null -w 'InfraSafe HTTP=%{http_code}\n' https://infrasafe.uz/
# expect: 200 (InfraSafe жив независимо от UK)

docker start uk-frontend
```

Выбор `502 + custom body` vs `200 + custom page` — деплой-агент фиксирует
в PR. По умолчанию **502** (честный код для мониторинга/SLO).

---

## 11. Pre-deploy resource benchmark

На dev. **Релевантные цифры получаются только при стационарной нагрузке
с включёнными prod-фичами** — uvicorn workers, Sentry init, первый цикл
outbox-рассылки. Иначе RSS занижен на ~150–250 MB.

### 11.1 Подготовка

В `.env` для бенчмарка должны быть включены prod-фичи (иначе measurement
заниженный):
- `SENTRY_DSN=https://...` — Sentry init добавляет ~30–50 MB.
- `INFRASAFE_WEBHOOK_ENABLED=true` — outbox-worker запускается.
- `UVICORN_WORKERS=2` — как в prod.
- `DEBUG=false`.

### 11.2 Топология бенчмарка

UK production-compose **не публикует порты наружу** (Caddy удалён, ports у
api/frontend срезаны). Прямой `curl localhost/uk/...` не сработает. Два
варианта замера:

**A. Через отдельный wrk-контейнер в `uk-network` (без nginx-уровня):**

`uk-management-api` собран на `python:3.11-slim` (Debian), в нём нет
`apk`, и засорять prod-образ установкой утилит во время теста — плохая
практика. Поднимаем wrk как отдельный контейнер, подключённый к той же
сети — он видит `uk-management-api` и `uk-frontend` по их именам.

```bash
cd ~/uk
docker compose -f docker-compose.production.yml up -d
sleep 90        # warmup uvicorn + Sentry + первый outbox tick

# Нагрузка на API health
docker run --rm --network uk-network williamyeh/wrk \
    -t2 -c20 -d60s http://uk-management-api:8080/api/health &

# Опционально — http GET на frontend (легче)
docker run --rm --network uk-network curlimages/curl \
    -s -o /dev/null -w '%{http_code}\n' http://uk-frontend:80/index.html

wait
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}"
```

Если `williamyeh/wrk` недоступен — альтернатива `skandyla/wrk` или
самосборка: `docker run --rm --network uk-network alpine sh -c
"apk add wrk && wrk -t2 -c20 -d60s http://uk-management-api:8080/api/health"`.

**B. Через временный nginx-прокси** (если хочется тестить полную цепочку
с `/uk/...` префиксом):

```bash
docker run --rm -d --name bench-nginx --network uk-network -p 8888:80 \
    -v $PWD/bench-nginx.conf:/etc/nginx/conf.d/default.conf:ro nginx:alpine
# bench-nginx.conf повторяет блоки из § 8.1 на :80 без TLS

wrk -t2 -c20 -d60s http://localhost:8888/uk/api/health
docker stop bench-nginx
```

Вариант A быстрее, измеряет именно UK-стек. Вариант B даёт sanity-check
nginx-конфига до production-деплоя.

### 11.3 Gate

Суммарный RSS UK-стека < **1.0 GB** (см. § 8.2 `mem_limit` = 928 MB).
Если больше — план B:

- **B1**: managed Postgres (Neon/Supabase free tier) — ~−300 MB.
- **B2**: Redis убрать или `maxmemory 32mb` — ~−50 MB.
- **B3**: UK на отдельную VPS под поддоменом `uk.infrasafe.uz` — снимает
  resource-ограничение полностью.

---

## 12. Risk matrix

| # | Риск | Митигация |
|---|---|---|
| R-1 | Hardcoded `/login` в UK-коде → SPA 404 | grep по § 6.3 (включая `window.location.*`) |
| R-2 | regex location перебивает /uk/ | `^~` (§ 8.1) |
| R-3 | Caddy не удалён → конфликт 443 | DoD § 8.8 |
| R-4 | CORS не настроен → Telegram Widget не работает | DoD UK-BE (§ 7.1, обязательно `web.telegram.org`) |
| R-5 | Webhook secret не синхронизирован | один источник + ротация § 4.4 |
| R-6 | OOM сервера | Benchmark § 11 + `mem_limit` § 8.2 |
| R-7 | BotFather не настроен (setdomain И setmenubutton) | DoD UK-BE |
| R-8 | XSS на shared origin → ключи обеих систем | httpOnly cookies § 4.2, CSP § 4.5 |
| R-9 | Compromised UK-контейнер → infrasafe-app | HMAC обязателен + rate-limit + audit |
| R-10 | Rollback не сработает | § 8.5 тестируется на dev |
| R-11 | `UK_API_URL` с trailing slash | Pre-start validator |
| R-12 | Telegram WebApp init data fails | UK-BE проверяет origin |
| R-13 | Mobile-юзеры не видят UK-ссылки | § 9.2 follow-up (TWA доступен из бота) |
| R-14 | Refresh-эндпоинт читает токен из body, план хочет cookie | § 7.2 backend `/api/v2/auth/refresh` переписан: cookie сначала, body — deprecated fallback. Без этой правки refresh нельзя выкинуть из localStorage |
| R-15 | После переноса access_token из `localStorage` в память Zustand SPA не может прокинуть Bearer в WS handshake | § 7.2 ticket-endpoint `/api/v2/auth/ws-ticket` или cookie-based WS auth. Решение делает UK-BE с тестом на staging |
| R-16 | Python-образ > 250 MB → DoD § 7.9 не закрывается | § 7.9 DoD требует **измерения** размера + обоснования при превышении. Multi-stage Dockerfile § 7.8 — необходимое, но не достаточное условие |
| R-17 | `frontend/nginx.conf` содержит `/api/` proxy на api:8080 → мёртвый код, вводит в заблуждение при локальной отладке | § 6.6 — удалить `location /api/` и `/ws/` из внутреннего nginx UK-frontend |
| R-18 | Webhook secret rotation требует кода с поддержкой двух секретов одновременно — не подтверждено в реализации | Pre-deploy verify: в InfraSafe `src/services/ukIntegrationService.js` и в UK webhook-receiver реально читается `UK_WEBHOOK_SECRET_NEXT` (если нет — добавить отдельным PR до § 8.4 ротации) |
| R-19 | Bot-сервис `uk-management-bot` использует long polling. При переходе на webhook Telegram потребует отдельный nginx-route `/uk/bot/<token>` | **Вне scope** этого плана. При переходе на webhook — отдельный план с конфигом `set_webhook` и `TELEGRAM_WEBHOOK_SECRET_TOKEN` |

---

## Definition of Done (общий план)

1. DoD § 6, § 7, § 8, § 9 — закрыты.
2. § 10 smoke + load + graceful degradation — проходят.
3. § 11 benchmark пройден (или выбран план B).
4. § 8.5 rollback тестирован на dev.
5. § 8.6 backup-cron работает.
6. В `CLAUDE.md` InfraSafe и `README.md` UK отмечено развёртывание.

---

## Приложение A: Файлы для исполнителей

### InfraSafe
- Шапка: `index.html:52-58`, `about.html:27-32`, `documentation.html:27-32`,
  `contacts.html:30-35` (§ 9.1, шаг 0).
- Mobile: `css/style.css:1689-1691` (§ 9.2).
- nginx: `nginx.production.conf` (server-блок 443, CSP строка 127) (§ 8.1).
- Webhook handler: `src/routes/webhookRoutes.js`.
- UK integration service (HMAC verifier для ротации, R-18):
  `src/services/ukIntegrationService.js`.
- UK API client (use of `UK_API_URL`): `src/clients/ukApiClient.js`.
- Миграция: `database/migrations/011_uk_integration.sql`.
- Legacy: `Dockerfile.unified` (§ 8.7, удалить/переименовать).

### UK
- Vite: `frontend/vite.config.ts` (§ 6.1).
- App: `frontend/src/App.tsx:55`, `frontend/src/twa/App.tsx:64-86` (§ 6.2).
- Login: `frontend/src/pages/LoginPage.tsx:10-50` (Telegram widget, § 7.4
  side-effect).
- Tokens — Web:
  - `frontend/src/stores/authStore.ts:19` — запись refresh в localStorage
    (удалить § 6.5).
  - `frontend/src/api/client.ts:28` — чтение refresh из localStorage
    (удалить § 6.5).
- Tokens — TWA (оставить как есть):
  - `frontend/src/twa/...useTWAAuth.ts` (или эквивалент — find by grep) —
    `Authorization: Bearer` flow.
- WS-auth: `uk_management_bot/api/ws/router.py` — handshake endpoint
  для WS-ticket или cookie-based (§ 7.2).
- Webhook sender (HMAC ротация, R-18):
  `uk_management_bot/services/webhook_sender.py` + проверка
  правильной конкатенации `INFRASAFE_WEBHOOK_URL` (§ 8.3 — без trailing slash).
- Internal nginx (cleanup § 6.6): `frontend/nginx.conf`.
- API main: `uk_management_bot/api/main.py:83-89` (CORS § 7.1).
- Auth service: `uk_management_bot/api/auth/service.py:30`
  (`AUTH_DATE_MAX_AGE_SECONDS`, § 7.4).
- Compose: `docker-compose.production.yml` (Caddy + caddy_data/config
  удалить, § 8.2).
- Dockerfiles (оба multi-stage, § 7.8):
  - `UK/Dockerfile` — bot/app образ.
  - `UK/Dockerfile.api` — API образ (внутренний healthcheck `localhost:8080/health`,
    см. § 4.6 вариант A vs B).

## Приложение B: Связанные документы

- Backend интеграция: `docs/superpowers/specs/2026-03-24-infrasafe-uk-integration-v2-design.md`.
- UI-ссылки (выполнено): `~/.claude/plans/hidden-prancing-babbage.md`.
