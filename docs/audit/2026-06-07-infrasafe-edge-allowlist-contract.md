# InfraSafe public edge — prefix-allowlist contract for `/uk/api/*` (SEC-22)

> _Последнее редактирование: 2026-08-22_

**Date:** 2026-06-07
**Status:** ✅ live on prod (deployed by InfraSafe edge side, verified)
**InfraSafe ref:** SEC-22 (pentest round 2) · **UK ref:** SEC-22 coordination
**Related:** ARCH-114 (reconciliation inventory), FIX-007 (inbound alert webhook), [memory] `reference_infrasafe_edge_allowlist`

## Context

The UK web stack is proxied through InfraSafe's public edge:

- `https://infrasafe.uz/uk/` → UK SPA (`uk-frontend`)
- `https://infrasafe.uz/uk/api/*` → UK REST API (`uk-management-api`, rewrite `/uk/api/(.*)` → `/api/$1`)
- `https://infrasafe.uz/uk/ws/*` → UK WebSocket

Before SEC-22 the `^~ /uk/api/` location was an **unconditional passthrough** to the whole FastAPI app (no path allowlist, no edge rate-limit). InfraSafe's pentester flagged this as an "open proxy to the entire UK API". Hardening was coordinated (UK supplies the authoritative path list; InfraSafe enforces it at the edge) so no UK SPA/TWA path breaks.

## Authoritative source of the list

Derived from actual code, not assumptions:
- **Full API surface:** `uk_management_bot/api/main.py` — `app.include_router(...)` prefixes + inline `@app.*` routes.
- **What the SPA/TWA actually call:** grep of `frontend/src` path strings against `apiClient`/`twaClient`/`publicClient` (all use `baseURL = import.meta.env.BASE_URL = /uk`, so relative paths are `/api/...`).
- **External inbound:** only InfraSafe → `POST /api/v2/webhooks/infrasafe/alert` (HMAC-signed). The bot↔API traffic is internal (docker network), never via the public edge.

## Allowlist (prefixes passed through `^~ /uk/api/`)

**Public (no auth, intentional):**
- `/api/v2/public/`
- `/api/v2/board-config` and `/api/v2/public/board-config` (GET public / PUT manager-only)
- `/api/v2/announcements`
- `/api/health` (basic liveness, if edge healthcheck needs it)

**Credential endpoints (stricter edge rate-limit):**
- `/api/v2/auth/`
- `/api/v2/registration/`

**Authenticated app surface (RBAC enforced in-app via `require_role`):**
- `/api/v2/requests/`
- `/api/v2/callcenter/`
- `/api/v2/profile/`
- `/api/v2/shifts/`
- `/api/v2/executor/shifts/`
- `/api/v2/addresses/`
- `/api/v2/feedback/`
- `/api/v2/media/` (upload + `request/{n}` + `{id}/file`)
- `/api/v2/work-reports` — manager API for visual work reports (✅ live на ОБОИХ хостах, verified 2026-08-22; на infrasafe.uz фича DARK — приложение отвечает 404 JSON до включения флага)
- `/api/v2/monitored-groups` — Group Intake: CRUD реестра ТГ-групп из дашборда (manager-only, `require_roles("manager")`; write-методы 30/min в приложении). Роуты `""` и `/{id}` (✅ live на ОБОИХ хостах, verified 2026-08-22; до деплоя фичи приложение отвечает 404 JSON — после деплоя ждём 401)
- `/api/v2/residents` — раздел «Жители» дашборда (manager-only) (✅ live на ОБОИХ хостах, verified 2026-08-22 — пробел на infrasafe.uz закрыт, раздел «Жители» там снова работает)

**External inbound (server-to-server, HMAC):**
- `/api/v2/webhooks/infrasafe/alert` (exact path; no other inbound webhooks exist)

**WebSocket (InfraSafe `/uk/ws/*` block):**
- `/ws/v2/` — canonical prefix for all channels

Everything else → **404 at the edge.**

## Blocked at the edge (NOT publicly reachable)

- `/api/health/ratelimit`, `/api/health/outbox` — internal ops metrics (outbox lag, rate-limit backend state). SPA does not use them. Token-gated in-app (`HEALTH_METRICS_TOKEN`, Bearer) as defense-in-depth.
- `/health` (root) — internal liveness; expose only if edge healthcheck needs it.
- `/api/v2/notifications/` — router exists but the SPA/TWA never call it over HTTP (notifications go via Telegram + WS); confirmed by grep. Excluded to shrink surface.
- `/docs`, `/redoc`, `/openapi.json` — already disabled in-app when `DEBUG=False` (SEC-092); also not proxied (defense-in-depth).
- No separate `/admin` HTTP surface exists: manager/admin operations live inside `requests/shifts/addresses/callcenter` and are gated per-endpoint by `require_role`.

## Форма записи на edge (уточнение 2026-08-22)

InfraSafe держит allowlist РЕГЕКСАМИ с явной границей, а не голыми префиксами:
`~^/uk/api/v2/<prefix>(/|$)`. Следствия для нас:

- запись покрывает голый путь коллекции И под-пути (`""` и `/{id}`) — поэтому
  «слэш-форма» из ранних версий этого дока (`/api/v2/work-reports/`) на edge
  НЕ используется: она бы отдавала 404 на голом POST коллекции (тот же класс
  дефекта, что ломал profile/requests/shifts 08.06);
- граница `(/|$)` значит: СОСЕДНИЙ ресурс с тем же началом и дефисом
  (условный `/api/v2/monitored-groups-admin`) молча НЕ пройдёт — его нужно
  заявлять отдельным запросом;
- **обе площадки**: allowlist действует и на infrasafe.uz, и на profk.uz
  (ранняя пометка «PROFK edge is a plain passthrough» устарела как минимум с
  25.07.2026 — новый префикс заявлять сразу для обоих хостов).

## Edge controls

- **Rate-limit:** ~120 r/min/IP general + 20 r/min/IP on `/api/v2/auth/` and `/api/v2/registration/`. Kept **not below** the UK app-level limits (SEC-019/020: auth 10/min, twa 20/min, set-password 5/min, resend-otp 3/min) so the edge never rejects legitimate traffic before the app.
- **auth_request / token-gate:** NOT used — UK auth is JWT in httpOnly cookies (`uk_access`) validated in-app; no lightweight introspection endpoint, so duplicating validation at the edge adds no value. Allowlist + rate-limit + in-app RBAC is sufficient.

## Standing agreement (important)

Because the edge now enforces a prefix-allowlist, **any NEW `/api/v2/...` prefix consumed by the SPA/TWA through the public edge will return 404 until InfraSafe adds it to the allowlist.** When adding such an endpoint, ping InfraSafe with the prefix ahead of release (minute-level change on their side). Internal-only endpoints (bot→API) are unaffected.

- `/api/v2/work-reports` (visual work reports, manager API) — added to this doc 2026-07-25; **✅ live на обеих площадках, verified 2026-08-22** (на profk стоял с 25.07; на infrasafe был реальный пробел — закрыт). Фича на infrasafe.uz DARK (`WORK_REPORTS_ENABLED=false`).
- `/api/v2/monitored-groups` (Group Intake, реестр ТГ-групп, manager-only) — **✅ live на обеих площадках, verified 2026-08-22**.
- `/api/v2/residents` (раздел «Жители», manager-only) — **✅ live на обеих площадках, verified 2026-08-22** (пробел infrasafe.uz закрыт по встречному вопросу InfraSafe; наборы префиксов площадок сверены ими и идентичны, у них добавлена сборочная проверка на оба конфига).
- `/api/v2/payment-control` (Контроль платежей, manager/admin, требует overlay
  `docker-compose.payments.yml`) — **⏳ ожидает добавления InfraSafe, добавлено в
  этот док 2026-09-05.** До заявки раздел отдаёт 404 на обеих площадках, поэтому
  пункт меню закрыт build-флагом `VITE_PAYMENTS_ENABLED` (по умолчанию выключен):
  фронт не показывает раздел, пока префикс не заявлен и overlay не поднят.

## Verification (2026-08-22, финал) — ✅ подтверждено на обеих площадках

Вторая раскатка InfraSafe (после не подтвердившейся первой, см. ниже) проверена
теми же пробами: `monitored-groups` (+`/{id}`) → 404 JSON от приложения на обоих
хостах; `work-reports` → infrasafe 404 JSON (DARK-флаг) / profk 401 JSON;
`residents` → 401 JSON на обоих (пробел infrasafe закрыт). Негативные контроли
(`monitored-groups-admin`, `residents-export`, `/api/health/outbox`, произвольный
путь) → HTML-404 nginx на обоих: граница `(/|$)` работает, внутренние пути
закрыты. По письму InfraSafe наборы префиксов обеих площадок теперь идентичны, и
у них появилась сборочная проверка, сторожащая ОБА конфига.

## Verification (2026-08-22, первый прогон) — раскатка не подтвердилась (история)

Методика: проксированный ответ приложения — всегда JSON от FastAPI
(`{"detail": ...}`), отказ edge — HTML-страница nginx. Перехвата
проксированных ошибок нет (контроль: `/api/v2/public/no-such-endpoint` →
404 JSON, `/api/v2/requests/` → 401 JSON на обоих хостах).

Замеры (GET без токена):
- `monitored-groups`, `monitored-groups/1` → 404 **HTML nginx** на ОБОИХ хостах (edge режет);
- `work-reports`: profk.uz → 401 JSON ✅ (старая запись 25.07), infrasafe.uz → 404 HTML nginx;
- `residents`: profk.uz → 401 JSON ✅, infrasafe.uz → 404 HTML nginx.

Вывод отправлен InfraSafe 2026-08-22: изменение не применилось (конфиг не
перезагружен либо правка не в том файле) — ждём повторную раскатку. Ожидаемое
после неё: `monitored-groups` → 404 **JSON** до нашего деплоя фичи (401 —
после), `work-reports` на infrasafe → 404 JSON (DARK-флаг), `residents` на
infrasafe → 401 JSON.

## Verification (2026-06-07)

InfraSafe live-tested: resident-board + public APIs return 200 (no browser errors), credential flood hits 429 at the edge, internal ops endpoints closed. UK side re-verified the allowlist is complete against the code (no legitimate SPA/TWA path missing) and that closing `/api/v2/notifications/` is safe (zero HTTP usage in `frontend/src`).
