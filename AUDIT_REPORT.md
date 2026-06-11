# AUDIT REPORT — UK Management System

Дата: 2026-06-12 · Ревизия: `7ace460` (main = prod) · Метод: 5 параллельных аудит-агентов (архитектура, код бэк/фронт, мёртвый код, безопасность) + аудит зависимостей и практик. Только чтение, без правок. Все находки подтверждены `файл:строка` либо grep-результатом; неподтверждённое помечено «требует подтверждения».

Вне рамок (известные принятые риски, не поднимаются): секреты в истории git (ротированы 2026-05-30, очистка — WONTFIX владельца), eslint-долг фронта как класс (lint в CI non-blocking, отдельный тикет).

---

## 1. Executive summary

Ядро системы — workflow заявок — выстроено образцово: единый канонический writer (`run_command` sync/async с общим чистым `_decide`), transactional outbox с HMAC и replay-защитой, advisory-lock reconciliation, AST-гейты в CI, запрещающие сырые записи/чтения workflow-полей. Безопасность для пилота добротная: bcrypt, `purpose`-клейм в JWT, системный object-level authz, magic-byte валидация загрузок; P0-уязвимостей нет. Тестовый контур после недавней переработки честный: 3 738 зелёных тестов в двух блокирующих CI-наборах.

Главные риски — вокруг ядра, а не в нём. (1) **P0 в доставке вебхуков**: outbox держит `FOR UPDATE SKIP LOCKED` на время HTTP-вызовов — медленный InfraSafe сериализует доставку и блокирует батч до ~8 минут. (2) **Два P0 на фронте**: нарушение rules-of-hooks и дублирующий хук с общим query-кэшем. (3) **Балласт**: ~10–12k строк подтверждённо мёртвого Python (6 async-сервисов с 0 импортов, кластер квартального планирования, pre-alembic миграции), ~45k строк артефактов в git (MemoryBank, скриншоты-сканы, 5 лишних docker-compose), 8 неиспользуемых python- и 2 npm-зависимости. (4) **Уязвимые зависимости**: react-router-dom (3 high: open redirect, XSS, DoS), aiohttp (2 CVE), starlette (1). (5) **Системная утечка слоёв**: 375 ORM-операций в 30 файлах хендлеров и 206 в API-роутерах, плюс паттерн `next(get_db())` (утечка соединений) в 14 файлах. Всё это поддерживаемо точечными PR; фундамент переделывать не нужно.

## 2. Scorecard

| Фаза | Оценка | Обоснование |
|---|---|---|
| Архитектура | **6/10** | SSOT-ядро и outbox эталонные, но хендлеры ходят в БД напрямую (375 операций), а sync/async-дублирование сервисов удваивает поверхность поддержки. |
| Код | **6/10** | Критический путь чистый и хорошо протестирован; P0 в outbox-локе, утечки соединений `next(get_db())`, мёртвая роль `resident`, на фронте — rules-of-hooks и дубль-хук. |
| Простота / лишний код | **4/10** | ~10–12k строк мёртвого Python + ~45k строк артефактов в git + 10 лишних зависимостей; зато ноль абстракций-прослоек (ABC/Protocol в проде нет). |
| Безопасность | **7/10** | P0 нет; HMAC/JWT/IDOR/загрузки сделаны добросовестно; минус за отсутствие rate-limit на `/admin`-пароль бота и уязвимые зависимости (A06). |
| Инженерные практики | **6/10** | Два блокирующих тест-набора в CI + coverage-ratchet фронта + здоровая цепочка миграций (19, один head); но Python-линта в CI нет (pre-commit с black/flake8/mypy не енфорсится), README.md отсутствует, docs/ захламлён историческими отчётами. |

## 3. Находки

Серьёзность: P0 критично · P1 высокая · P2 средняя · P3 низкая. Трудозатраты: S/M/L.

### P0 — критично (3)

| ID | Категория | Файл:строка | Описание | Рекомендация | Т |
|---|---|---|---|---|---|
| CODE-01 | Надёжность | `services/webhook_sender.py:241-288` | `FOR UPDATE SKIP LOCKED` удерживается на всё время HTTP-вызовов: 50 записей × 10 с таймаут = до ~500 с лока; второй uvicorn-worker пропускает весь батч → доставка сериализуется при любом замедлении InfraSafe | Брать id под локом / помечать `in_flight` и коммитить; HTTP — вне транзакции; статусы — новой транзакцией | L |
| FE-01 | Корректность | `frontend/src/components/shifts/WeekResourceGrid.tsx:133` | `useMemo` вызывается после раннего `return` (строки 109-117) — нарушение Rules of Hooks, runtime-баг при смене ветки рендера | Поднять `useMemo` до раннего return или вынести empty-state в отдельный компонент | S |
| FE-02 | Корректность | `frontend/src/hooks/useShifts.ts:61` + `useAnalytics.ts:17` | Два разных `useShiftStats` на один `queryKey ['shift-stats', period]` с разными опциями (`keepPreviousData` только в одном); мутации инвалидируют по префиксу и сбрасывают чужой запрос | Удалить версию в `useShifts.ts`, оставить единственную в `useAnalytics.ts` | S |

### P1 — высокая (16)

| ID | Категория | Файл:строка | Описание | Рекомендация | Т |
|---|---|---|---|---|---|
| DEP-01 | Зависимости | `frontend/package.json` (react-router-dom 7.13.1) | 3 high + 1 moderate: open redirect через `//`-путь, XSS через `javascript:`-redirect, stored XSS в prerender, DoS (`GHSA-2j2x…`, `GHSA-8646…`, `GHSA-f22v…`, `GHSA-8x6r…`) | `npm audit fix` (фикс в пределах 7.x) | S |
| DEP-02 | Зависимости | `requirements.txt` (aiohttp 3.13.5, starlette 1.0.0) | aiohttp: CVE-2026-34993, CVE-2026-47265 (фикс 3.14.0); starlette: PYSEC-2026-161 (фикс 1.0.1) — starlette это ядро FastAPI | Поднять пины, перегенерировать hash-pinned requirements.txt | S |
| SEC-01 | AuthN (A07) | `handlers/base.py:508-574` | `/admin` → FSM ждёт пароль; попытки не считаются, throttling 0.5 с = 120 паролей/мин с аккаунта; единственная защита — `len(set(password))>=8` | `is_rate_limited(f"admin_pwd:{tg_id}", 5, 300)` — утилита уже есть (role_switch) | S |
| CODE-04 | Ресурсы | `handlers/*` (14 файлов, 184 вхождения), `keyboards/requests.py:587,629,672,729` | `db = next(get_db())` — `finally: close()` генератора не выполняется детерминированно → утечка соединений | Механическая замена на существующий `with session_scope() as db:` (`database/session.py:81-96`) | L |
| CODE-05 | Корректность | `services/user_management_service.py:46` | `User.roles.contains('resident')` — роли `resident` нет в `USER_ROLES` → выборка всегда пуста, заявители не попадают в списки менеджера | Заменить на `'applicant'` | S |
| CODE-02 | Корректность | `services/auth_service.py:194-233` (+262,315,394,470) | В каждой операции модерации одна и та же строка User грузится дважды (`user` и `target_user`) — лишние SELECT + риск разных версий при параллелизме | Переиспользовать загруженный `user` | S |
| CODE-03 | Корректность | `database/session.py:99-118` | `get_async_db()` делает auto-commit на выходе — двойной commit, если caller уже коммитил; API использует другой `get_db`, функция фактически не используется, но «рекомендована» в docstring | Убрать auto-commit или удалить функцию | S |
| ARCH-01 | Слои | `handlers/requests.py:246,283,411,725,775,783`; `handlers/shift_management.py:519-1890` и др. | 375 ORM-операций в 30/32 файлах хендлеров, 35 прямых `commit()` в 15 — бизнес-логика и транзакции в UI-слое | Вынести в сервисы; закрепить AST-гейтом по образцу `test_workflow_inventory.py` | L |
| ARCH-02 | Дублирование | `services/request_service.py:290-306` ≈ `async_request_service.py:380-394` и 8 пар | Каждое бизнес-правило в двух копиях sync/async с ручной синхронизацией | Большинство async-копий мертвы (DEAD-01/02) — сначала удалить, остаток свести к чистым sync-агностичным функциям + тонкие I/O-обёртки | L |
| FE-03 | Корректность | `pages/twa/TWARequestDetailPage.tsx:35` (vs `components/kanban/RequestDetailModal.tsx:108`) | `['request', n]` через `twaClient` (Bearer) вне TWA-поддерева может разделить QueryClient дашборда (cookie-auth) — перекрёстный кэш | Префикс `['twa', 'request', n]` | S |
| FE-04 | Валидация | `pages/LoginPage.tsx:27` | `window.onTelegramAuth` принимает невалидированный payload и шлёт на сервер as-is (граница внешних данных) | Интерфейс `TelegramUser` + проверка обязательных `id`/`hash` перед отправкой | S |
| FE-05 | UX/ошибки | `hooks/useTWAAuth.ts:16` | `.catch(console.error)` — при сбое TWA-аутентификации пользователь видит пустой экран без сообщения и retry | Вернуть `isError` из хука, показать ошибку | S |
| FE-06 | Утечка данных | `twa/hooks/useTWAAuth.ts:40` | `console.error('TWA auth failed:', err)` — AxiosError содержит `init_data` (hash + query_id, достаточно для replay в окне жизни) | Логировать только `err.message` | S |
| FE-07 | Производительность | `components/kanban/RequestDetailModal.tsx:95` (+5 файлов) | Сброс 7 state внутри `useEffect` при смене `requestNumber` — каскадные синхронные ре-рендеры | `key={requestNumber}` на модалке вместо эффекта; остальным — `useReducer` | M |
| DEAD-01 | Мёртвый код | `services/async_{request,geo_optimizer,shift,shift_planning,shift_assignment,workload_predictor}*.py` | 6 async-сервисов с **0 живых импортов** (проверено grep вне tests), ~3 600 строк иллюзии «async-слоя» | Удалить вместе с их тестами | M |
| DEAD-03 | Мёртвый код | `handlers/quarterly_planning.py` (601), `keyboards/quarterly_planning.py` (325), `services/specialization_planning_service.py` (722) | Кластер не зарегистрирован в `main.py` (grep `quarterly` = 0) — недостижим; согласуется с CODE-13 (сломанный импорт задокументирован в smoke-тесте) | Удалить ~1 650 строк; модель `quarterly_plan` решить отдельно (таблица в БД) | M |

Также P1 в кластере чистки: **DEAD-04** `utils/sheets_utils.py` (291 строка, 0 импортов, единственный потребитель structlog) · **DEAD-05** `database/migrations/` (19 pre-alembic скриптов, 2 331 строка, 0 ссылок — alembic давно SSOT) · **DEAD-09** `MemoryBank/` (96 файлов, ~39 600 строк сессионных журналов в git) · **DEAD-11** 8 неиспользуемых позиций `requirements.in` (google-api-python-client/-auth/-oauthlib, asyncio-mqtt, jinja2, aiofiles, requests, structlog; `passlib[bcrypt]` → прямой `bcrypt`). Все — S/M, подтверждены grep «0 ссылок».

### P2 — средняя (выборка значимых, 20)

| ID | Категория | Файл:строка | Описание | Рекомендация | Т |
|---|---|---|---|---|---|
| SEC-02 | Crypto (A02) | `api/auth/service.py:19,22`; `settings.py:113` | `SECRET_KEY = JWT_SECRET or INVITE_SECRET` — при незаданном JWT_SECRET ключи совпадают; в dev hardcoded `"dev-jwt-secret-…"` | Обязательный отдельный JWT_SECRET + убрать dev-fallback | S |
| SEC-03 | Crypto (A02) | `api/ws/router.py:27,81,134` | WS-токен в `?token=` query (попадает в access-логи/историю) — legacy-fallback к cookie | Deprecated-warning + дедлайн; для TWA — токен в первом WS-сообщении | M |
| SEC-04 | Misconfig (A05) | `api/rate_limit.py:33`; `main.py:83-94` | При отказе Redis fallback per-worker умножает лимит на число воркеров (детектится, не митигируется) | Делить лимит на воркеры в fallback или fail-closed для auth-роутов | M |
| SEC-05 | Injection (A03) | `api/profile/router.py:78` | Валидация email = `"@" not in email`; email участвует в MFA-поиске | `pydantic.EmailStr` | S |
| SEC-06 | AuthZ (A01) | `services/auth_service.py:607` | `/admin` выдаёт `["applicant","executor","manager"]` скопом — нарушение least privilege | Выдавать только `["manager"]` | S |
| CODE-06 | Мёртвый код | `services/auth_service.py:36-43` | In-memory `_ROLE_SWITCH_RATE_LIMIT_TS` через `try/except NameError` — мёртв, Redis-лимит уже есть (:650) | Удалить вместе с `__init__` | S |
| CODE-07 | Качество | `services/auth_service.py:580` | Мёртвый `json_pattern`; `contains()` = LIKE по TEXT без индекса; фильтр ролей не учитывает `status=="approved"` | Удалить мёртвое; индекс/нормализация ролей | S |
| CODE-08 | Корректность | `services/auth_service.py:537,542` | Проверки роли `"admin"`, которую никто не выдаёт — dead branch, вводит в заблуждение | Убрать `"admin"` или ввести её явно | S |
| CODE-09 | Корректность | `services/async_shift_service.py:157,210,269,338,393` и др. | `datetime.now()` без TZ в записях БД (workflow/outbox используют UTC — расхождение) | `datetime.now(timezone.utc)` везде, где пишутся метки | M |
| CODE-10 | Корректность | `services/auth_service.py:83-90` | `auto_approve_user` пишет deprecated `user.role`, но не добавляет роль в `roles`-массив, если тот непуст → расхождение role/roles | Логика добавления как в `process_invite_join` (:138-152) | S |
| CODE-11 | Ошибки | `middlewares/auth.py:51-55` | `except Exception` без логирования возвращает `user=None` — маскирует ошибки программирования | Добавить `logger.debug` | S |
| ARCH-03 | Отказоустойчивость | `integrations/media_client.py:103,220`; `api/main.py:426,464,497` | Вызовы media-service без ретраев (таймаут есть) — единичный сбой = ошибка пользователю; SPOF для вложений | Ретрай+backoff на идемпотентные GET; явная деградация | M |
| ARCH-04 | Ошибки | `services/auth_service.py:90,538,561,609`; `request_service.py:301`; `async_request_service.py:390` | `except Exception: pass` на парсинге ролей — битый JSON ролей молча падает в legacy-fallback без лога (в auth-путях!) | Узкий except + warning-лог | S |
| ARCH-05 | Слои | `api/shifts/router.py` (70 ORM-операций; `db.add:232`, `commit:233,307,328`), `api/addresses/router.py` (47) | Бизнес-правила и транзакции в роутерах — асимметрия с SSOT-путём заявок | Сервисный слой для shifts/addresses | M |
| ARCH-06 | Зависимости | `services/workflow_runner.py:304-306`; `webhook_sender.py:222` | Deferred-импорты внутри функций — вероятный обход цикла services↔utils (часть в `api/main.py` — осознанная) | Построить граф (grimp); вынести общие типы в модуль без обратных зависимостей | M |
| FE-08 | Корректность | `pages/KanbanPage.tsx:18`, `pages/AddressesPage.tsx:236`, `hooks/useTheme.ts` | Пропущенные deps → stale closures (кнопки не обновляются при смене языка) | Дополнить deps / `useCallback` | S |
| FE-09 | Размер | `pages/AddressesPage.tsx` (872 строки) | 3 уровня навигации, 2 режима, 9 мутаций в одном компоненте | Выделить `YardGrid`/`BuildingGrid`/`ApartmentGrid` | L |
| FE-10/11 | Производительность | `twa/components/CommentThread.tsx:43`; `RequestDetailModal.tsx:650-684` | Polling 10 с без `refetchIntervalInBackground:false`; media-загрузка мимо Query-кэша (повторные скачивания) | Флаг + `useQuery(['media-blob', id])` | S |
| DEAD-02 | Мёртвый код | `services/async_assignment_service.py:421,466` → `async_smart_dispatcher.py`, `async_assignment_optimizer.py` | Живой только `reassign_executor` (вызов `api/shifts/router.py:447`); остальное — цепочка без call-sites (~1 570 строк). Требует подтверждения | Удалить методы + 2 сервиса | M |
| DEAD-10 | Конфиги | `docker-compose.{dev,prod,prod.unified,production,unified}.yml` + 5 `*-unified.sh` | 6 compose-вариантов; Makefile/доки ссылаются на разные, доки местами упоминают SQLite (устарело). Требует подтверждения | Оставить `docker-compose.yml`(+media override), остальное удалить со стейл-доками | M |

Также P2: **DEAD-06/07/08** — кандидаты в мёртвые эндпоинты (`POST /auth/set-password`, `POST /profile/documents`, весь `api/notifications/` — 0 вызовов из фронта/бота; требует подтверждения) · **DEAD-12** npm: `@twa-dev/sdk`, `@radix-ui/react-select` — 0 импортов; дубль зонтичного `radix-ui` и `@radix-ui/react-*` · **DEAD-13** мёртвые settings-флаги (`GOOGLE_SHEETS_*` ×6, `NOTIFICATION_RETRY_COUNT`, `JOIN_RATE_LIMIT_*` — 0 чтений) · **FE-12** MSW: 2 базовых хендлера при `onUnhandledRequest:'error'` · **PRAC-01** Python-линт (black/flake8/mypy в pre-commit и requirements-dev) не выполняется в CI — фактически не енфорсится.

### P3 — низкая (10)

| ID | Файл:строка | Описание | Т |
|---|---|---|---|
| SEC-07 | `api/main.py:185-198`; `settings.py:89` | `HEALTH_METRICS_TOKEN` пуст по умолчанию → health-эндпоинты открыты до конфигурации (задокументировано); внести в ops-чеклист | XS |
| SEC-08 | `handlers/auth.py:178` | Лог `token[:8]` invite-токена — противоречит и политике, и собственному тесту `test_invite_token_logging.py` | XS |
| SEC-09 | `middlewares/throttling.py:14-36` | In-memory throttling бота — ломается при >1 воркере; зафиксировать как known constraint | S |
| ARCH-07 | `request_service.py:291,305`; `async_request_service.py:381,394`; `user_management_service.py` (23); `auth_service.py` (9) | Deprecated `user.role` читается в боевой логике вопреки CLAUDE.md; резолв ролей размножен | M |
| ARCH-08 | `config/settings.py:151-153` | Комментарий «inbound webhook router не существует» — ложь, он есть (`api/webhooks/`, подключён `api/main.py:213`) | S |
| ARCH-09 | `handlers/shift_management.py` (4014), `requests.py` (2987), `admin.py` (2829) | God-файлы против правила проекта «800 max»; следствие ARCH-01 | L |
| CODE-12 | `services/auth_service.py` (6 мест) | `import json` внутри методов при модульном импорте | S |
| CODE-13 | `tests/test_handlers_smoke.py:31` | Закомментированный smoke с пометкой «broken import: SPECIALIZATION_CONFIGS» — закроется удалением DEAD-03 | — |
| FE-13/14 | `hooks/useAddresses.ts` и др. (~30 мест); `AddressesPage.tsx:217` | `console.error(AxiosError)` в проде; JSX в deps `useMemo` ломает React Compiler | M/S |
| DEAD-14/15/16, PRAC-02/03 | — | «AI-диспетчеризация» ~4 200 строк эвристик для пилота одного ЖК (не удалять, не инвестировать); 30+ test-файлов вперемешку с кодом в `services/`/`utils/`; закомментированные блоки `handlers/requests.py:322-364`, `user_management.py:1185-1245`; README.md отсутствует; docs/ из исторических `*_COMPLETED.md` | S–M |

Чисто по проверенным категориям: десериализация (A08), SSRF (A10 — исходящие URL валидируются `_require_safe_outbound_url`), hardcoded-секреты в рабочем дереве, циклы миграций (19, один head 019, без веток), абстракции-прослойки (ABC/Protocol в проде — 0).

## 4. Top-10 quick wins

| # | Что | Эффект | Т |
|---|---|---|---|
| 1 | `npm audit fix` (DEP-01) | Закрывает 3 high (XSS/open redirect) одной командой | S |
| 2 | Поднять aiohttp→3.14.0, starlette→1.0.1 (DEP-02) | 3 CVE в ядре бота и API | S |
| 3 | Rate-limit на `/admin`-пароль (SEC-01) | Закрывает brute-force админ-эскалацию, утилита готова | S |
| 4 | `'resident'`→`'applicant'` (CODE-05) | Чинит всегда-пустую выборку пользователей у менеджера | S |
| 5 | Поднять `useMemo` над early-return (FE-01) | Снимает P0 rules-of-hooks | S |
| 6 | Удалить дубль `useShiftStats` (FE-02) | Снимает P0 кэш-конфликта | S |
| 7 | PR-чистка: DEAD-01+03+04+05 (+ DEAD-11 deps) | −~8 500 строк мёртвого Python и 8 зависимостей; всё «0 ссылок» | M |
| 8 | Убрать `token[:8]` из лога + `EmailStr` (SEC-08, SEC-05) | Две точечные правки гигиены | XS |
| 9 | Убрать auto-commit из `get_async_db` + мёртвый rate-limit-глобал (CODE-03, CODE-06) | Минус две мины замедленного действия | S |
| 10 | Удалить MemoryBank/ + артефакты корня из git (DEAD-09 + п.3 фазы 3) | −~45k строк шума, клон и навигация легчают | S |

## 5. Roadmap рефакторинга

**Этап 0 — P0 + зависимости (1 PR, до любых других работ).**
FE-01, FE-02 (точечные) + DEP-01/02. CODE-01 (outbox-лок) — отдельный PR с дизайном: claim-фаза (`in_flight` + commit) → HTTP вне транзакции → финализация; покрыть существующим `test_webhook_outbox_concurrency.py` + новый тест на медленного получателя.

**Этап 1 — security/корректность S-размера (1 PR).**
SEC-01, SEC-05, SEC-06, SEC-08, CODE-02, CODE-03, CODE-05, CODE-06, CODE-08, CODE-10, CODE-11, FE-04/05/06, ARCH-04 (узкие except в auth), ARCH-08 (комментарий). Все механические, друг от друга не зависят.

**Этап 2 — большая чистка (1–2 PR; ДО архитектурных рефакторингов, чтобы не рефакторить мёртвое).**
PR-2a: DEAD-01, DEAD-03 (+CODE-13), DEAD-04, DEAD-05, DEAD-09, DEAD-11, DEAD-13, DEAD-16, артефакты корня. PR-2b (после подтверждений InfraSafe/прод-конфига): DEAD-02, DEAD-06/07/08, DEAD-10 (+скрипты), DEAD-12. После 2a ARCH-02 сжимается до 1–2 реальных пар.

**Этап 3 — ресурсы и устойчивость.**
CODE-04 (`next(get_db())`→`session_scope`, механический L — можно частями по файлам), CODE-09 (UTC), ARCH-03 (ретраи media), SEC-02/03/04 (JWT-секрет, WS-токен deprecate, fallback-лимиты), FE-03/07/08/10/11.

**Этап 4 — архитектурное выпрямление (фоновое, по файлу за раз).**
ARCH-01/05/09: вынос ORM из хендлеров/роутеров в сервисы, начиная с `shift_management.py`; каждый вынесенный файл фиксировать AST-гейтом (паттерн уже отработан на workflow). ARCH-06 (граф импортов), ARCH-07 (централизовать резолв ролей → план дропа `user.role`). FE-09 (AddressesPage), FE-12 (MSW-фикстуры).

**Этап 5 — практики.**
PRAC-01: добавить в CI шаг ruff (или black+flake8) хотя бы для изменённых файлов — иначе pre-commit останется декорацией. PRAC-02: README.md (запуск, архитектура, ссылки на docs/audit). Разобрать docs/ (живое vs архив), судьба untracked `tests/e2e/` и `uz-board.yml`.

---
*Отчёт агрегирован из 5 независимых аудит-проходов; ID находок сохранены сквозными (ARCH/CODE/FE/SEC/DEAD/DEP/PRAC). Ничего в коде не менялось.*
