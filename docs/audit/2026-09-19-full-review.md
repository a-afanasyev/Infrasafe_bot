# Полное ревью кода и безопасности — 2026-09-19 (аудит #8)

Снимок: `main` `467fffc4` (после PR #588). Метод: восемь параллельных ревьюеров по зонам (security: ядро API/auth, access_control, media/resource/payment, frontend+TWA, инфра/CI/деплой; code: бот, API+БД, фронт), только подтверждённые по коду находки с `file:line`; семь главных находок перепроверены вручную на HEAD (см. «Сверка»). Известные открытые пункты (`AUD7-SEC-03`, `ARCH-107`, `SEC-115`, `DB-049`, `AUD3-37`, `PENT-F13`) в отчёте помечены KNOWN и повторно не заводятся.

**Итог:** CRITICAL — 0, HIGH — 1 (фронт: устаревание списка «Все квартиры»), MEDIUM — 7, LOW — 12. Постановка в бэклог: раздел «Аудит #8» (`AUD8-*`), 16 пунктов: 14 actionable, 1 decision (шифрование бэкапов — ключи и cron на хостах), 1 deferred (OFFSET-пагинация/батчинг миграции — «при касании»).

## Сверка главных находок на HEAD (вручную, 2026-09-19)

| Находка | Подтверждение |
|---|---|
| media caption без `html.escape` | в `media_storage.py` нет `import html`; `telegram_client.py:67,91` — `parse_mode="HTML"` по умолчанию |
| нет rate-limit на резидентских POST | `access_control/api/resident.py:445,483` без лимитера; в `services/` только `code_rate_limit.py` (redeem) |
| Redis без обязательного пароля | `docker-compose.yml:500` — `${REDIS_PASSWORD:+--requirepass …}`; profk строит `REDIS_URL` из той же переменной |
| глушение уведомлений смен | `handlers/shifts.py:139-140, 307-308, 371-372` — `except Exception: pass` |
| `all-apartments` не инвалидируется | `useAddresses.ts:87` — единственное упоминание ключа; пять инвалидаций `apartments` его не покрывают |
| `kanban.truncatedColumn` | ключ есть только в `KanbanColumn.tsx:195`, в `ru.json`/`uz.json` отсутствует |
| stale `t` в `handleBlockToggle` | `EmployeesPage.tsx:145` — deps `[blockEmployee, unblockEmployee, fullName]` |

## Находки по зонам (отчёты ревьюеров, сокращённо)
## 1. Security: API/auth core — новых находок нет
KNOWN: AUD7-SEC-03, ARCH-107, SEC-115. Verified OK: JWT purpose/kid, refresh rotation FOR UPDATE + family revoke, OTP Lua, cookies, WS origin+identity, webhook HMAC dual-secret, IDOR gates, settings fail-fast, SSRF guard, CORS, sql_search, rate limits fail-closed.

## 2. Security: infra/CI/deploy
- [MEDIUM] Redis password не обязателен в прод-compose — docker-compose.yml:500 `${REDIS_PASSWORD:+--requirepass}`; dev-compose без пароля. Fix: `:?` в прод-файлах.
- [MEDIUM] Бэкапы без шифрования at rest / транспорт не задокументирован — docs/ops/BACKUPS.md. Fix: age/gpg перед записью и копией на peer; транспорт SSH-only явно.
- [LOW] GH Actions по тегам, не по SHA — ci.yml (docker/* actions, images-build с packages: write).
- [LOW] Нет top-level `permissions: contents: read` в ci.yml/payment-control.yml.
- [LOW] Base images без digest-пина: media_service/Dockerfile:2, payment_control/Dockerfile:1, resource-accounting/backend/Dockerfile:1, Dockerfile.dev:6.
- [LOW] dev-compose: порты 5432/6379 на 0.0.0.0 + hardcoded dev-пароль — docker-compose.dev.yml.
Verified OK: нет секретов, dockerignore, non-root везде, 127.0.0.1 binds, healthchecks, hash-locks, bandit/pip-audit/npm-audit, provision_roles, nginx headers, no pull_request_target.

## 3. Security: access_control
- [MEDIUM] Нет rate-limit на резидентских write-эндпоинтах — access_control/api/resident.py:445 (POST /api/v1/access/requests), :486 (POST /passes); services/resident.py:207,:249 без троттлинга (в отличие от redeem-code 5/10 мин). Атака: флуд pending-заявок/гостевых кодов. Fix: per-user/IP sliding window по образцу code_rate_limit/device_auth nonce-store.
- [LOW] Мёртвая legacy-ветка RedirectResponse на raw URL в get_photo — access_control/api/registry.py:631 (сейчас все writer'ы пишут media://). Fix: убрать ветку или allowlist хостов.
- [LOW] ILIKE без экранирования %/_ в поиске по номеру — registry.py:336 `_plate_pat` (только расширение своего поиска, не SQLi). Fix: sql_search-подобное экранирование.
Verified OK: device_auth HMAC/nonce/IP allowlist, barrier lease CAS, WS panel origin+identity, resident ownership boundary, one-time codes, signed photo URLs, media integration без SSRF, pydantic whitelists, api_key показывается один раз, параметризованный SQL, docs off in prod.

## 4. Security: frontend + TWA — новых находок нет
KNOWN: AUD7-SEC-03. Verified OK: cookie-only auth, refresh coordinator, safeNextPath, Telegram widget не доверяется клиентом (origin+source postMessage), нет innerHTML/eval, href через isHttpUrl, tel: санитайз, sourcemap off + drop console, npm audit prod 0, TWA токены только в памяти, sessionStorage без секретов.

## 5. Security: media / resource / payment
- [MEDIUM] media_service: описание/ref/tags без html.escape в Telegram-подписи parse_mode=HTML — media_service/app/services/media_storage.py:558,:596 (_generate_caption/_generate_domain_caption, вызовы :101,:212,:829; archive caption :860-864), telegram_client.py:62-77 send_photo parse_mode=HTML. Класс BUG-174/178 (канон бота — html.escape), не портирован. Атака: инъекция ссылки/тегов в канал менеджеров или TelegramAPIError на битой разметке → срыв загрузки. Fix: html.escape всех свободных полей + pin-тест. НОВОЕ.
- [LOW] resource-accounting XLSX-импорт: cap только на сжатый размер (5 МБ), нет cap на распакованный/число записей — resource-accounting/backend/app/services/imports.py:60; образец в payment_control/imports.py:52-61,83-85 (_assert_unpacked_size). Fix: портировать.
- [LOW] stateless session tokens без server-side revocation (logout только удаляет cookie) — resource-accounting security.py:15-24, auth.py:188-191. KNOWN: AUD7-SEC-03.
Verified OK: media X-API-Key compare_digest, magic-bytes MIME, лимиты, token не в логах, 25 с бюджет, _escape_like; resource tenant scoping везде, ticket single-use UPDATE…WHERE used_at IS NULL, CSRF Origin check, slowapi, fail-fast defaults; payment shared-secret ≥32, не наружу, cap_drop ALL, zip-bomb defenses, account_number ASCII regex, Decimal.

## 6. Code: API + БД — только LOW
- [LOW] N+1 при soft-delete сотрудника — uk_management_bot/api/shifts/service/employees.py:342-343 → services/async_assignment_service.py:38-50 перечитывает Request и RequestAssignment на каждой итерации.
- [LOW] OFFSET-пагинация списков (заявки/отчёты) — api/requests/service.py:249-253, api/work_reports/service.py:33-54,173-198; ORDER BY стабильный, деградация только на больших offset.
- [LOW/info] alembic/versions/0010_specialization_canon.py:99-186 — построчный UPDATE в data-миграции.
- KNOWN: DB-049.
Verified OK: индексы под запросы, партиальный уникальный индекс Group Intake, sql_search, kanban/list без N+1 (aliased User), RequestNumberService UPSERT…RETURNING, period_lock FOR UPDATE + lock_timeout, hashchain/resident SQL с allowlist+bind, acl_reconcile, internal comments фильтруются сервером, auth schemas без секретов.

## 7. Code: бот
- [MEDIUM] Уведомления старт/конец смены глушатся `except Exception: pass` без лога — uk_management_bot/handlers/shifts.py:129-140, :300-308, :363-372 (end-путь :601-602 логирует; есть notification_service/shifts.async_notify_shift_started/ended с логированием). Fix: logger.warning или делегировать в notification_service. НОВОЕ.
- [LOW] print() вместо logger в живом хендлере — handlers/admin/lists.py:156 (test_middleware не за DEBUG). Fix: logger.debug.
- KNOWN: AUD3-37 (sync db.query в event loop — «при касании»).
Verified OK: plan_transition единственная точка инварианта (grep: нет прямых Request.status), business_time, session/middlewares, group_intake CAS, completion_media, work_reports saga, notification_service логирует, html.escape в feedback, shift_assignment CAS, миграции 0015–0019, локали: 0 отсутствующих ключей в ru/uz (~2100 литералов).


## 8. Code: frontend
- [HIGH] `all-apartments` никогда не инвалидируется мутациями квартир — frontend/src/hooks/useAddresses.ts:87 (потребители AddressesPage.tsx:106 «Все квартиры», components/residents/AttachApartmentModal.tsx); мутации :279-281,:297-302,:318-320,:337-339,:355-357 инвалидируют только apartments/buildings/…; WS (useAddresses.ts:406-416) реагирует лишь на `building.*`. Сценарий: создал/удалил квартиру → в «Все квартиры» и пикере привязки жителя старые данные до 30 с staleTime/рефокуса; новая квартира кратко «не привязывается», удалённая — «привязывается». Fix: инвалидировать `['all-apartments']` во всех мутациях квартир (как пара buildings/all-buildings).
- [MEDIUM] Отсутствует ключ i18n `kanban.truncatedColumn` — KanbanColumn.tsx:195, в ru/uz нет → пользователь видит сырой ключ, когда терминальная колонка обрезана (частое состояние). Fix: добавить ключ с `{{shown}}/{{total}}` в обе локали.
- [MEDIUM] `handleBlockToggle` замыкает устаревший `t` — pages/EmployeesPage.tsx:128-145 (deps без `t`, eslint exhaustive-deps предупреждает) → после смены языка диалог блокировки на старом языке. Fix: добавить `t` в deps или убрать useCallback.
- [MEDIUM] `create.mutate(payload as never)` обходит типизацию payload'ов оборудования — pages/access/AccessEquipmentPage.tsx:281,544,629,709,810; расхождение FormField-схемы и `Create*Payload` компилируется, падает 422 в рантайме. Fix: типизировать onSubmit по конкретному payload (`satisfies`) или валидировать схемой.
- [LOW] `localStorage` без try/catch — hooks/useTheme.ts:10,17, hooks/useResizableColumn.ts:28,34,70, components/shifts/AutoManagerCard.tsx:38,43 (остальной код обёрнут). Fix: тот же паттерн.
Verified OK: timezone carrier, api/client refresh, useWebSocket/useAccessSecurityFeed, kanban optimistic + query-key factory, resource api client, useEmployees/useAddresses (кроме квартир), EquipmentFormDialog double-submit guard; tsc чисто, eslint 0 ошибок / 11 warnings exhaustive-deps.
