# План закрытия бэклога — 2026-06-12

**Источники:** `docs/audit/2026-05-20-backlog.md` (после аудита бэклога 2026-06-12), `AUDIT_REPORT.md`, `docs/audit/2026-06-12-backlog-audit.md`.
**Охват:** **145 живых позиций** (машинно подтверждено): 60 новых entries секции «Аудит 2026-06-12» + 77 старых `####` без `~~` + 8 открытых `###` (FIX-008, MGR-02/03/05🟡/06/07🟡/08/09). Закрытые `###` (FIX-001..007, MGR-01, MGR-04) — вне охвата; FIX-002/FIX-004 — в Marker-hygiene (§6).
**Формат исполнения:** по команде «делай PR-N» — каждый PR самодостаточен (состав, предусловия, DoD, риски).

**Инварианты каждого PR (общий DoD-фундамент):** оба блокирующих pytest-набора зелёные в контейнере (`pytest -q` + `pytest -q tests/api tests/services` с `INFRASAFE_WEBHOOK_ENABLED=true`); frontend `tsc -b && vite build` + vitest; деплой обычным релизом `docker compose -f docker-compose.yml -f docker-compose.media.yml`, без `--remove-orphans`. Не поднимаются принятые риски: секреты в истории git (WONTFIX), eslint-долг (отдельный тикет).

Факты, верифицированные по коду при проектировании: OPS-112 — verifier-log существует (marker-drift); BUG-BOT-038 — 0 потребителей `status_transitions` (obsolete); FIX-008 — 12 read-методов `async def` без await; **BUG-BOT-040 — MetricsManager достижим** (`shift_planning_service.py:16,31` ← `handlers/shift_management.py:19`, `utils/shift_scheduler.py:14`, `services/template_manager.py:199`) → не закрывается политикой DEAD-14.

---

## 1. Порядок волн

| Волна | Содержание | Почему в этом порядке |
|---|---|---|
| **0** | P0 + CVE (PR-1..4) + outbox-редизайн (PR-5) | Runtime-баги и уязвимости — до всего |
| **1** | S-security и корректность (PR-6a/6b/7) | Механические, независимые, дёшево ревьюится |
| **2** | DEAD-чистка (PR-8..11) | **ДО архитектурных рефакторингов** — не рефакторить мёртвое; после неё ARCH-02 сжимается, CODE-09 частично исчезает |
| **2.5** | Actuality-пасс по старым open (без кода) | Чистка инвалидирует часть пунктов; последние полные пассы 2026-05-31/06-01 |
| **3** | Ресурсы/устойчивость + кластеры address/FE/bot (PR-12..25) | Средние независимые PR, параллелятся внутри волны |
| **4** | Архитектурное выпрямление (PR-26..35) | Фоновая серия, по файлу за раз, фиксация AST-гейтами |
| **5** | Практики (PR-36..39) | Линт в CI, README, тестовая раскладка |

**Критический путь:** PR-5 → PR-34 (CHECK-constraint должен знать `in_flight`); PR-8 → PR-12/PR-32; PR-17 → PR-18 → PR-19; PR-30 → PR-31; сверка прод-compose → PR-10. Ориентир: волны 0–2 ≈ 1.5–2 нед; волна 3 ≈ 2 нед; 4–5 фоновые (~3–4 нед по файлу за раз).

---

## 2. PR-нарезка

### Волна 0 — P0 + CVE (4 PR, независимы)

#### ~~PR-1 — Frontend P0 (S)~~ ✅ DONE 2026-06-12 (PR #59, merge `741e9ed`, прод задеплоен)
- **Состав:** FE-01 (`WeekResourceGrid.tsx:133` — поднять `useMemo` над early-return :109-117), FE-02 (удалить дубль `useShiftStats` из `useShifts.ts:61`, оставить `useAnalytics.ts:17`).
- **DoD:** build+vitest; смоук смены ветки рендера WeekResourceGrid (пусто↔данные) без runtime-ошибки.

#### ~~PR-2 — react-router-dom CVE (S)~~ ✅ DONE 2026-06-12 (PR #60, `ec11761`, прод)
- **Состав:** DEP-01 — `npm audit fix` (в пределах 7.x; 3 high + 1 moderate: open redirect, XSS×2, DoS).
- **DoD:** `npm audit` без high; build+vitest.

#### ~~PR-3 — Backend CVE-пины (S)~~ ✅ DONE 2026-06-12 (PR #61, `b7fb70b`, прод: starlette 1.0.1; aiohttp — defer, CVE неэксплуатируемы, ждём aiogram c aiohttp≥3.14)
- **Состав:** DEP-02 — aiohttp→3.14.0; starlette→**1.0.1 = минимальный patched** (актуальная 1.2.0 — поднять до неё, если оба pytest-набора подтверждают совместимость, иначе 1.0.1); перегенерация hash-pinned `requirements.txt`.
- **DoD:** оба набора в пересобранном контейнере; pip-audit без CVE-2026-34993/47265/PYSEC-2026-161; прод-смоук после деплоя (login + создание заявки + outbox-доставка).
- **Риск:** starlette — ядро FastAPI; гейт — полный CI + контейнерный прогон.

#### PR-4 — TWA namespace sweep + мёртвые npm-deps (S)
- **Состав:** FE-03 — **полный sweep**: ВСЕ query-ключи TWA-страниц/хуков (инвентаризировать grep'ом по `frontend/src/twa/` и `pages/twa/`, не только `TWARequestDetailPage.tsx:35`) получают префикс `['twa', …]`; dashboard **намеренно остаётся** на `['request', n]` и пр. + DEAD-12 (`@twa-dev/sdk`, `@radix-ui/react-select` — 0 импортов).
- **DoD:** grep-инвентаризация ключей до/после в PR-описании; **vitest-тест непересечения**: множества queryKey TWA-поддерева и dashboard дизъюнктны; build+vitest.

### PR-5 — Outbox: claim/lease вместо длинного лока (L, отдельный дизайн-PR)

- **Состав:** CODE-01 (`webhook_sender.py:241-288`) + REFACTOR-091 (lock-scope>commit в reconciliation) + ARCH-011-остаток (oldest-first вместо sort-by-hash).

**Дизайн:**
- **Схема (Alembic):** `claim_token UUID NULL`, `claimed_at timestamptz NULL`, статус `in_flight`; частичный индекс `ON (claimed_at) WHERE status='in_flight'`.
- **Mixed-version deploy (вперёд):** старый код не выбирает `in_flight` (SELECT фильтрует `pending`) — записи не теряются, дозревают по reclaim после полного выката; бот+API одним релизом.
- **Rollback-runbook (строгий порядок):** (1) остановить outbox-воркеры (`INFRASAFE_WEBHOOK_ENABLED=false` + рестарт / stop контейнеров); (2) убедиться в отсутствии активных отправок; (3) `UPDATE … SET status='pending' WHERE status='in_flight'`; (4) alembic downgrade (дроп индекса/колонок); (5) откат кода и запуск. Иначе живой воркер финализирует запись после удаления схемы.
- **Claim:** маленький батч (≤10) под `FOR UPDATE SKIP LOCKED`: `status='in_flight'`, `claimed_at=now()`, уникальный `claim_token` per-запись; commit — лок снят.
- **HTTP вне транзакции, bounded concurrency** внутри батча (semaphore) — хвост батча не протухает за lease.
- **Lease ≥ batch_size × http_timeout × 2** (батч 10 × таймаут 10s → lease 200s; константы в settings).
- **Финализация — compare-and-set:** `UPDATE … WHERE id=:id AND claim_token=:token`; rowcount=0 → запись reclaim'нута, попытка отбрасывается.
- **Reclaim:** `in_flight AND claimed_at < now()-lease` → доступны новому claim (новый token).
- **Семантика attempts:** `attempts += 1` — ТОЛЬКО после **подтверждённого неуспешного HTTP-результата** (HTTP-таймаут = подтверждённый неуспех). Финализация: `attempts < max` → `pending`; `attempts >= max` → `failed` — только по результату последней разрешённой попытки. **Crash/неизвестный результат:** retry-budget НЕ расходуется — reclaim возвращает запись, тот же `event_id` доставляется повторно (at-least-once, получатель идемпотентен). Отдельный `claim_count` (delivery_starts) — только для метрик/алертов (crash-loop), НЕ для dead-letter. Зависший получатель не зацикливает: его таймауты — подтверждённые неуспехи, исчерпывают attempts штатно.
- **`event_id` неизменен** при ретраях/reclaim (ARCH-010 не трогаем). **Health-метрика в этом же PR:** счётчик `in_flight` старше lease.

- **DoD:** `test_webhook_outbox_concurrency.py` зелёный; **новый PostgreSQL-тест двух конкурентных воркеров в контейнере** (sqlite гонку не тестирует — отмечено в существующем тесте): медленный получатель не блокирует второй воркер; stale-finalize отбрасывается (CAS rowcount=0); reclaim после lease; attempts растёт только на подтверждённых неуспехах; `failed` — только после неуспешного результата последней попытки. **Тест идемпотентности получателя: повторная доставка ТОГО ЖЕ event_id** (dev InfraSafe / их inbound-контракт) — без повторных side effects; redelivery после crash допустима, потеря записей — нет. `tests/services/test_reconciliation.py` целиком. Прод-смоук: building create → InfraSafe ≤15s; health-метрика = 0.

### Волна 1 — security/корректность S (3 PR)

#### PR-6a — Security-фиксы (S/M)
- **Состав:** SEC-01 (rate-limit `/admin`-пароля: `is_rate_limited(f"admin_pwd:{tg_id}", 5, 300)` — утилита готова), SEC-05 (`pydantic.EmailStr` в `api/profile/router.py:78`), SEC-06 (`/admin` → только `["manager"]`), SEC-08 (убрать `token[:8]` из `handlers/auth.py:178`), INV-087 (`hmac.digest`), ARCH-04 (узкие except + warning в auth/role-парсинге).
- **DoD:** тест на каждый фикс (lockout, email-валидация, roles-выдача); MCP-смоук: `/admin` 6 неверных паролей → лок.
- **Риск:** SEC-06 меняет выдачу ролей — проверить, что существующие admin-пользователи не теряют доступ.

#### PR-6b — Корректность/cleanup auth-слоя (M)
- **Состав:** CODE-02 (двойная загрузка User), CODE-03 (auto-commit `get_async_db`), CODE-05 (`'resident'`→`'applicant'` + тест), CODE-06 (мёртвый in-memory лимит), CODE-07 (мёртвый `json_pattern`), CODE-08 (мёртвые «admin»-ветки), CODE-10 (roles-массив как в `process_invite_join`), CODE-11 (лог в auth-middleware), CODE-12 (`import json`), ARCH-08 (ложный комментарий settings).
- **DoD:** тесты CODE-05 (выборка applicant) и CODE-10 (roles-консистентность); оба набора зелёные.

#### PR-7 — Frontend auth-гигиена (S)
- **Состав:** FE-04 (валидация `window.onTelegramAuth`: интерфейс + обязательные `id`/`hash`), FE-05 (isError+retry в TWA-auth), FE-06 (логировать `err.message`), FE-047 (login через `publicClient` без 401-interceptor).
- **DoD:** vitest на FE-04/05; смоук: неверный логин → inline-ошибка без редиректа.

### Волна 2 — DEAD-чистка (4 PR; ДО архитектурных рефакторингов)

**Усиленный DoD всей волны:** оба pytest-набора в пересобранном контейнере + frontend build/vitest + **callback/router-инвентаризация**: дамп зарегистрированных aiogram-роутеров/callback-паттернов и FastAPI-routes до/после, diff = только осознанно удалённое; бот стартует, MCP-смоук главного меню.

#### PR-8 — Мёртвый Python (M, −~9.5k строк)
- **Состав:** DEAD-01 (6 async-сервисов + тесты), DEAD-02 (**после grep-подтверждения**: цепочка `smart_assign_request`/`get_assignment_recommendations`; `reassign_executor` сохранить — жив в `api/shifts/router.py:447`), DEAD-03 (quarterly-кластер; таблица `quarterly_plan` — отдельное решение; закрывает CODE-13), DEAD-04 (`sheets_utils.py` + structlog), DEAD-05 (pre-alembic `database/migrations/` — **закрывает SEC-023**), DEAD-11 (8 позиций requirements.in; passlib→bcrypt), DEAD-13 (мёртвые settings-флаги), DEAD-16 (закомментированные блоки `handlers/requests.py:322-364`, `user_management.py:1185-1245`).
- **DoD волны** + grep «0 импортов» на каждое удаление зафиксирован в PR-описании.

#### PR-9 — Артефакты репозитория (S, −~45k строк)
- **Состав:** DEAD-09 (MemoryBank/ 96 файлов), PRAC-03 (scans/, auth_scan.json, requests_export.csv, ru_temp.json, scan_report.txt, merge_*.py ×3, organize_*.sh, interactive_test_report.html, translation_validation*.txt, устаревший openapi.yaml, coverage-audit.md).
- **DoD:** **живые docs/Makefile/CI не ссылаются на удалённое — ссылки обновить; архивные/audit-доки исключены из проверки** (исторические упоминания MemoryBank/ в отчётах не правим); CI зелёный.

#### PR-10 — Compose-консолидация (M)
- **Предусловие (без кода):** ssh-diff прод-копии `docker-compose.yml` с репо, реконсилировать drift **в репо** ДО удаления вариантов.
- **Состав:** DEAD-10 — остаются ровно `docker-compose.yml` + `docker-compose.media.yml` + `docker-compose.dev.yml`; удалить `docker-compose.{prod,prod.unified,production,unified}.yml` + `*-unified.sh`; **обязательно**: обновить/удалить Makefile-цели и живые docs, ссылающиеся на удаляемые файлы (grep по именам → 0 живых упоминаний). + OPS-110 (alembic bind-mount в dev-compose).
- **DoD:** прод-деплой-команда работает без изменений; dev: правка `.py`+`alembic/*` видна без rebuild; при проверочном деплое — без `--remove-orphans`.

#### PR-11 — Мёртвые эндпоинты (S)
- **Состав:** DEAD-07 (`POST /profile/documents`), DEAD-08 (`api/notifications/` — 0 вызовов + закрыт edge-allowlist SEC-22). **После grep-подтверждения** + прод-access-логи, если доступны. DEAD-06 исключён — DECISION (§5).
- **DoD:** grep-фиксация 0 вызовов; удаление + тесты роутера.

#### Шаг 2.5 — Actuality-пасс (без кода)
Перепроверка оставшихся старых open после чистки (список — `2026-06-12-backlog-audit.md` §5), обновление маркеров.

### Волна 3 — ресурсы/устойчивость/кластеры

#### PR-12 — UTC-sweep (S, после PR-8)
- CODE-09: оставшиеся `datetime.now()` без TZ в записях БД (metrics_manager, comment_service и др. — async_shift_service уйдёт в PR-8). DoD: grep-инвентаризация; тест на репрезентативную запись.

#### PR-13 — Media-устойчивость + конфиг-валидатор (M)
- ARCH-03 (ретраи+backoff на идемпотентные GET `media_client.py`; явная деградация), SEC-022-остаток (валидатор: `DEBUG=False` + `ALLOWED_ORIGINS="*"` → fail-fast).
- DoD: юнит-тесты ретраев (mock httpx); тест валидатора (3 кейса из AC SEC-022); смоук вложений на dev.

#### PR-14 — JWT/ratelimit hardening (M)
- SEC-02 (обязательный отдельный JWT_SECRET, убрать dev-fallback; **деплой-нота: проверить prod `.env` ДО релиза** — иначе рестарт уронит API), SEC-04 (fallback-лимит делить на воркеры или fail-closed для auth-роутов), NICE-082 (refresh TTL).
- DoD: тест fail-fast при совпадении секретов в prod-режиме; тест fallback-лимита.
- Риск: возможный force-logout при смене секрета — на пилоте приемлемо, согласовать момент.

#### PR-15 — WS-токен из query (M)
- SEC-03: deprecated-warning + дедлайн; TWA — токен первым WS-сообщением (бэк+фронт), **оба пути работают параллельно** (rollout без поломки клиентов).
- DoD: тест нового handshake; vitest на клиент.

#### PR-16 — Outbox ops (S/M)
- OPS-105 (ежесуточный retention `sent` >30d; prometheus-метрики — опционально/отложить), DOCS-095 (runbook `docs/runbooks/outbox-failures.md`).
- DoD: тест retention-логики; runbook в git.

#### Кластер address_service (последовательно)
- **PR-17** (M): BUG-028 (24× `except Exception` → типизированные + `logger.exception` + generic-ответы), REFACTOR-032 (lazy `%s`, PII через extra), REFACTOR-088 (`Optional`), REFACTOR-089 (status-Enum). DoD: grep `except Exception` по файлу → типизировано; тест отсутствия PII в captured logs; AC BUG-028.
- **PR-18** (M, после PR-17): FIX-008 (**de-async 12 read-методов** + правка call-sites), BUG-126 (`.limit()`), BUG-127 (sentinel для GPS, зеркало BUG-097), PERF-093 (8 SELECT → 1 GROUP BY), NICE-076 (FOR UPDATE в purge), NICE-081 (audit-запись перед purge). DoD: AC FIX-008 (grep `async def` без await → пусто); тесты-зеркала bug090/bug097; контейнерные тесты + MCP-смоук справочника адресов.
- **PR-19** (M, после PR-17): FE-094 — error-code Enum из сервиса → `get_text(code, language)` в хендлерах. DoD: UZ-пользователь видит узбекские ошибки (MCP-смоук); тесты маппинга.

#### FE-батчи
- **PR-20** (S/M): FE-033 (+расширение FE-08: KanbanPage:18, useTheme), FE-034 (+расширение FE-07: `key={requestNumber}` на RequestDetailModal и 4 модалки), FE-035, FE-037, FE-039, FE-14 (JSX в deps useMemo). DoD: build+vitest; смена языка обновляет кнопки (смоук); ratchet-floor не падает.
- **PR-21** (M, допустимо разрезать на perf/UX): FE-036, FE-038, FE-040, FE-042 (React.lazy + manualChunks; AC main <400kB), FE-043 (unsaved guard), FE-045, FE-046, FE-048, FE-100, FE-10 (`refetchIntervalInBackground:false`), FE-11 (`useQuery(['media-blob',id])`). DoD: AC FE-042 по чанку; vitest; визуальный смоук kanban/addresses.
- **PR-22** (S): FE-119 — alert-поля InfraSafe в RequestCard schema → `_make_request_card` → блок в RequestDetailModal, i18n RU/UZ (паттерн разблокирован INT-120 #3). DoD: AC FE-119; тест схемы.

#### Bot-батчи
- **PR-23** (M): MGR-02 (FSM поиска жителей по аналогии employee_mgmt_search), MGR-03 (регистрация `edit_employee_<id>` — листовые хендлеры уже есть, нет входа), BUG-BOT-015 (кнопки на пустых жителях), BUG-BOT-035 (cancel_clarification), BUG-BOT-036 (split counters scheduled/delivered + 2 теста). DoD: контейнерные тесты; MCP-смоук каждого флоу по AC.
- **PR-24** (S): MGR-05-остаток (ре-рендер карточки), MGR-06 (локализация ролей), MGR-07-остаток (второй toggle → `SpecializationService.AVAILABLE_SPECIALIZATIONS`), MGR-08 (двойная 🏠), BUG-BOT-024 (✅✅ + `@не указано`), BUG-BOT-039 (dead get_text). Попутно: удалить мёртвую секцию `status_transitions` из locale (тикет BUG-BOT-038 закрывается отдельно как obsolete). DoD: MCP-смоук; grep на единственный источник меток специализаций.
- **PR-25** (S): BUG-BOT-034 + BUG-BOT-037-остаток — строгие callback-regex `^X_\d{6}-\d{3,}$` для `edit_/approve_/accept_/purchase_` (учесть BUG-122: `\d{3,}`). DoD: юнит-тесты matching/non-matching; MCP-смоук.

### Волна 4 — архитектурное выпрямление (фоновая серия)

- **PR-26** (M): ARCH-012 — декомпозиция `api/main.py`: lifespan → `lifecycle.py`, inline-эндпоинты → `routes/announcements.py`, `routes/media_proxy.py`. DoD: main.py ≤200 строк; тесты роутов без изменений.
- **PR-27** (M/L): ARCH-05a — сервисный слой для `api/shifts/router.py` (70 ORM-операций) + AST-гейт по образцу `test_workflow_inventory.py`. DoD: гейт; tests/api зелёные.
- **PR-28** (M): ARCH-05b + REFACTOR-027 — `api/addresses/router.py` (909 строк) по сущностям + остаточный ORM → core. DoD: файлы ≤700 строк; гейт.
- **PR-29-серия** (L, по файлу за PR): ARCH-01 — вынос ORM из хендлеров: `shift_management.py` (4014) → `requests.py` (2987) → `admin.py` (2829) → хвост. Каждый PR: вынос в сервисы + расширение AST-гейта + **попутная** миграция `next(get_db())`→`session_scope()` в выпрямляемом файле (так закрывается CODE-04/ARCH-013-A без отдельного рискованного sweep). DoD per-PR: гейт фиксирует файл; контейнерные тесты + MCP-смоук затронутых меню.
- **PR-30** (M): ARCH-07 (новые) + NICE-078 — централизация резолва ролей (`User.roles_list` / `utils/auth_helpers`), 42 файла на единый резолв. DoD: grep `user.role` в боевой логике → только резолвер.
- **PR-31** (M, после PR-30 + стабильная неделя): DB-060 + DB-049 — дроп legacy `role`, roles → jsonb+GIN. DoD: prod-safe миграция; sentinel-тест.
- **PR-32** (M, после PR-8): ARCH-02-остаток — оставшиеся sync/async пары → чистые агностичные функции (паттерн `_decide`) + тонкие I/O-обёртки. DoD: бизнес-правила в одном месте (diff-доказательство).
- **PR-33** (L): FE-09 — декомпозиция AddressesPage (872 строки) → YardGrid/BuildingGrid/ApartmentGrid. DoD: ≤400 строк; vitest на компоненты (вклад в TEST-068 Phase 4).
- **PR-34** (M, **после PR-5** — CHECK-constraint должен знать `in_flight`): DB-052-остаток (FK-индексы), DB-056 (jsonb), DB-057 (CHECK outbox.status), DB-058 (дубль-индексы), DB-059 (импорт в upgrade), DB-104 (numeric(8,2)). DoD: идемпотентная миграция, sentinel-тесты по образцу 011/012.
- **PR-35-серия:** TEST-068 Phase 2–5 (stores→hooks→components→pages; счёт уже 93 теста/17 файлов) + FE-12 (MSW-фикстуры — в Phase 2); ratchet-floor поднимается с каждой фазой.

### Волна 5 — практики

- **PR-36** (M): PRAC-01 — шаг ruff в CI (по изменённым файлам) + follow-up REFACTOR-113 (G004 autofix файлами). DoD: CI красный на нарушении в изменённом файле.
- **PR-37** (S): PRAC-02 (README.md: запуск/архитектура/ссылки), SEC-07 (deploy-чеклист: HEALTH_METRICS_TOKEN), SEC-09 (known constraint: 1 воркер бота), DEAD-14 (политика «не удалять, не инвестировать» в AI-диспетчеризацию), ARCH-115 (branch-policy doc), разбор docs/ (живое vs архив).
- **PR-38** (M): DEAD-15 + NICE-114 — перенос 30+ колоцированных тестов в `uk_management_bot/tests/`. **Landmine-гейт: НЕ делать tests/api пакетом; `--import-mode=importlib` сохраняется; `--collect-only` до/после — счёт не уменьшился.**
- **PR-39** (S, после DECISION по untracked `tests/e2e/`): TEST-071 — e2e login fixture.

---

## 3. Трек «закрытия без кода» (исполняется отдельной командой)

Механизм корзин «Предложено закрыть» + Marker-hygiene + DECISIONs:

| Действие | Пункты | Статус |
|---|---|---|
| Зачеркнуть с обоснованием | OPS-112, BUG-BOT-038, NICE-077 (контрольный grep: web/ отсутствует ✓), NOTE-S-M7, NICE-072/073/074, DB-055, DB-103, REFACTOR-026 | ✅ выполнено 2026-06-12 (утверждено владельцем) + BUG-BOT-040 (accepted risk) и DEAD-06 (решение) |
| Marker-hygiene (§6) | FIX-002, FIX-004 — тела обновлены прод-фактами, закрыты | ✅ выполнено 2026-06-12 |
| Переписать тело → PR-18 | FIX-008 (ре-спецификация: de-async 12 read-методов) | открыто (вместе с PR-18) |
| Ручной прод-SQL | BUG-BOT-017 (junk-шаблоны), MGR-09 (дубль здания) | ✅ выполнено 2026-06-12: BUG-BOT-017 — prod/dev junk удалён (дампы сделаны); MGR-09 — obsolete-verified, дубль уже отсутствовал |
| Предусловие PR-10 | ssh-сверка прод-копии docker-compose.yml | открыто |

## 4. Defer (внешние зависимости / отложено осознанно)

| Пункт | Причина |
|---|---|
| ARCH-010 | InfraSafe-координация: конфликт determinism vs reconcile-repair |
| SEC-115 | InfraSafe-сторона (auth на их GET) |
| ARCH-107 | JWT kid-ротация: force-logout на пилоте приемлем; вместе с ARCH-106 |
| ARCH-108 | REASSIGN OWNED — рискованная прод-операция при низкой ценности; FIX-004 закрыл главный риск |
| DB-112 | Address-snapshot: до перехода на реальные данные |
| ARCH-06 | grimp-граф импортов — низкая ценность сейчас |

## 5. DECISION — ✅ все разрешены владельцем 2026-06-12

| Пункт | Решение |
|---|---|
| ARCH-106 | **Deferred** — секреты ротированы 2026-05-30, пилот на одном хосте; вернуться при выходе из пилота (вместе с ARCH-107) |
| DEAD-06 + FE-121 | **Реализовать FE-121**: мини-**PR-40** (волна 3) — UI смены пароля в дашборде; эндпоинт остаётся, DEAD-06 закрыт |
| BUG-BOT-040 | **Accepted risk** (закрыт): путь редкий, блокировка кратковременная, бот однопоточный на пилоте; согласуется с DEAD-14; пересмотреть при жалобах на зависания |
| BUG-BOT-017 | **Выполнено 2026-06-12** — prod: удалены id 1,2 (0 ссылок, дамп); dev: id 1,11 + отвязка 10 смен |
| MGR-09 | **Закрыт 2026-06-12 obsolete-verified** — дубль (id=2) на проде уже отсутствовал, AC выполнен без действий |
| Untracked `tests/e2e/`, `uz-board.yml` | **Закоммитить оба** — разблокирует PR-39 |

**PR-40 — UI смены пароля (S, волна 3, добавлен решением):** форма в profile/settings дашборда → `POST /auth/set-password` (rate-limit SEC-019 уже есть). DoD: vitest формы; смоук смены пароля + повторный логин.

## 6. Marker-hygiene (вне 145, тела устарели)

- **FIX-002** — тело: «dev rotated»; факт: полная прод-ротация выполнена 2026-05-30. Верифицировать и зачеркнуть.
- **FIX-004** — тело: «dev applied»; факт: прод-демоция uk_bot (NOSUPERUSER) выполнена 2026-06-07, recovery-роль создана. Верифицировать и зачеркнуть (NB: отложенный Step 6 NOLOGIN — дедлайн 2026-06-14).

---

## 7. Приложение — Триаж-реестр (145 ID → корзина)

**Валидация (скрипт, 2026-06-12):** expected 145 = assigned 145 · MISSING: [] · EXTRA: [] · дубли исключены конструкцией (dict). Корзины: PR 122 · absorbed 1 · close 10 · defer 6 · decision 6. Старые 85: PR 64 + absorbed 1 + close 10 + defer 5 + decision 5 = 85 ✓

| PR | Пункты |
|---|---|
| PR-1 | FE-01, FE-02 |
| PR-2 | DEP-01 |
| PR-3 | DEP-02 |
| PR-4 | DEAD-12, FE-03 |
| PR-5 | ARCH-011, CODE-01, REFACTOR-091 |
| PR-6a | ARCH-04, INV-087, SEC-01, SEC-05, SEC-06, SEC-08 |
| PR-6b | ARCH-08, CODE-02, CODE-03, CODE-05, CODE-06, CODE-07, CODE-08, CODE-10, CODE-11, CODE-12 |
| PR-7 | FE-04, FE-047, FE-05, FE-06 |
| PR-8 | DEAD-01, DEAD-02, DEAD-03, DEAD-04, DEAD-05, DEAD-11, DEAD-13, DEAD-16 |
| PR-9 | DEAD-09, PRAC-03 |
| PR-10 | DEAD-10, OPS-110 |
| PR-11 | DEAD-07, DEAD-08 |
| PR-12 | CODE-09 |
| PR-13 | ARCH-03, SEC-022 |
| PR-14 | NICE-082, SEC-02, SEC-04 |
| PR-15 | SEC-03 |
| PR-16 | DOCS-095, OPS-105 |
| PR-17 | BUG-028, REFACTOR-032, REFACTOR-088, REFACTOR-089 |
| PR-18 | BUG-126, BUG-127, FIX-008, NICE-076, NICE-081, PERF-093 |
| PR-19 | FE-094 |
| PR-20 | FE-033, FE-034, FE-035, FE-037, FE-039, FE-14 |
| PR-21 | FE-036, FE-038, FE-040, FE-042, FE-043, FE-045, FE-046, FE-048, FE-10, FE-100, FE-11 |
| PR-22 | FE-119 |
| PR-23 | BUG-BOT-015, BUG-BOT-035, BUG-BOT-036, MGR-02, MGR-03 |
| PR-24 | BUG-BOT-024, BUG-BOT-039, MGR-05, MGR-06, MGR-07, MGR-08 |
| PR-25 | BUG-BOT-034, BUG-BOT-037 |
| PR-26 | ARCH-012 |
| PR-27/28 | ARCH-05 |
| PR-28 | REFACTOR-027 |
| PR-29-серия | ARCH-01, CODE-04 |
| PR-30 | NICE-078 |
| PR-31 | DB-049, DB-060 |
| PR-32 | ARCH-02 |
| PR-33 | FE-09 |
| PR-34 | DB-052, DB-056, DB-057, DB-058, DB-059, DB-104 |
| PR-35-серия | FE-12, TEST-068 |
| PR-36 | PRAC-01, REFACTOR-113 |
| PR-37 | ARCH-115, DEAD-14, PRAC-02, SEC-07, SEC-09 |
| PR-38 | DEAD-15, NICE-114 |
| PR-39 | TEST-071 |

**Поглощено:** SEC-023 — DEAD-05 → PR-8.

**Предложено закрыть (утверждает владелец):** OPS-112 (marker-drift: verifier-log 8/8, закрыт 2026-05-31) · BUG-BOT-038 (obsolete: 0 потребителей `status_transitions`) · NICE-077 (obsolete: web/ удалён; после контрольного grep) · NOTE-S-M7 (SEC-017 закрыт — снять маркер) · NICE-072 (WONTFIX: TS-кодоген — низкая ценность для пилота) · NICE-073 (WONTFIX: принятый риск синхронизации) · NICE-074 (WONTFIX: кэш не нужен на пилотном масштабе) · DB-055 (WONTFIX: bigint-PK не нужен на горизонте пилота) · DB-103 (WONTFIX: все записи через ORM) · REFACTOR-026 (снять AC ≤600: критический путь закрыт ARCH-014, остаток после PR-17/18).

**Defer:** см. §4 (ARCH-010, SEC-115, ARCH-107, ARCH-108, DB-112, ARCH-06).

**DECISION:** см. §5 (ARCH-106, FE-121, DEAD-06, BUG-BOT-017, MGR-09, BUG-BOT-040).
