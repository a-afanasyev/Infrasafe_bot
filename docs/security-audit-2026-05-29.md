# Security Audit — UK Management System (bot + API + frontend + infra)

**Дата:** 2026-05-29
**Охват:** Telegram-бот (`uk_management_bot/`), REST/WebSocket API (`uk_management_api/` + `uk_management_bot/api/`), медиа-сервис (`media_service/`), React-дашборд и TWA (`frontend/`), а также инфраструктурные артефакты (docker-compose, requirements, env-файлы).

> Источник истины — зафиксированный набор подтверждённых находок. Повторного сканирования кода не проводилось.

---

## 1. Сводная таблица по severity

| Severity | Подтверждено | Исправлено (в рабочем дереве) | Пропущено / требует follow-up |
|----------|:------------:|:-----------------------------:|:-----------------------------:|
| CRITICAL | 2  | 2 (частично — нужна ротация + чистка истории) | ротация секретов, git-history purge |
| HIGH     | 7  | 4 полностью + 1 частично | 1 (TWA refresh token) + remind_applicant |
| MEDIUM   | 3  | 3  | — |
| LOW      | 11 | 10 | hash-lock, разные мелкие follow-up |
| **Итого**| **23** | **19 закрыто в рабочем дереве** | остальное — внешние операции |

Категории: `secret` (7), `authz` (8), `info-leak` (5), `validation` (2), `auth-token-storage` (1), `dep` (1).

Отклонено / понижено кандидатов: **10** (см. раздел 4).

---

## 2. Подтверждённые находки

### CRITICAL

#### C-1. Живые токены Telegram-ботов в репозитории
- **Severity:** CRITICAL · **Категория:** secret
- **Файл:** `docs/Archive/Old_Docs/main.file:10` (и `:11`)
- **Риск:** Реальные `BOT_TOKEN` (строка 10) и `MEDIA_BOT_TOKEN` (строка 11) захардкожены в git-tracked файле. Префикс токена совпадает с прод-ботом `infrasafebot`. Любой с доступом на чтение репозитория может полностью захватить бота: читать чаты, слать сообщения от имени сервиса, менять webhook, выдавать себя за сервис.
- **Исправлено:** Реальные значения на строках 10–11 заменены плейсхолдерами (`your_bot_token_here` / `your_media_bot_token_here`), что соответствует заявленному назначению файла как шаблона.
- **Остаётся обязательным (вне правки файла):** ротация обоих токенов через @BotFather (единственное эффективное средство, т.к. токены уже в git history), `git rm` файла и очистка истории (git filter-repo / BFG), gitignore для env-дампов.

#### C-2. INVITE_SECRET (ключ подписи JWT + invite-токенов) в репозитории
- **Severity:** CRITICAL · **Категория:** secret
- **Файл:** `docs/Archive/Old_Docs/main.file:19`
- **Риск:** Реальный `INVITE_SECRET` закоммичен в git. По `uk_management_bot/api/auth/service.py:19` `JWT_SECRET` падает в fallback на `INVITE_SECRET`, поэтому это же значение подписывает access/refresh JWT дашборда (HS256) И invite-токены. Имея его, атакующий может подделать валидный JWT для любого `user_id`/`roles` (например `{"sub":"<id>","roles":["manager"]}`) и подделать invite-токены — полный обход аутентификации веб-панели.
- **Исправлено:** Значение на строке 19 заменено плейсхолдером `changeme_use_openssl_rand_base64_64`.
- **Остаётся обязательным:** ротация `INVITE_SECRET` и `JWT_SECRET` на независимые значения (`openssl rand -hex 32` каждое), инвалидация всех сессий/refresh-токенов, удаление файла и очистка истории. Держать `JWT_SECRET` отдельным от `INVITE_SECRET` (в prod settings это уже требуется).

### HIGH

#### H-1. Прод ADMIN_PASSWORD / пароль БД в нескольких tracked-файлах
- **Severity:** HIGH · **Категория:** secret
- **Файл:** `docs/Archive/Old_Docs/main.file:15`
- **Риск:** Реальный пароль администратора `Inf@$afe` (URL-encoded `Inf%40%24afe`) закоммичен на строке 15 и переиспользуется как пароль PostgreSQL. То же значение встречается в `docs/Archive/Deployment/SERVER_SETUP_GUIDE.md:49`, `docs/Archive/Deployment/DEPLOYMENT_FIXES.md:87` и подтверждено как живое значение прод `.env` в `docs/audit/2026-05-20-backlog.md:1023`.
- **Исправлено (только в `main.file`):** `ADMIN_PASSWORD` на строке 15 заменён на `changeme_use_openssl_rand`; `DATABASE_URL` и `POSTGRES_PASSWORD` (в этом файле буквально `uk_bot_password`, не admin-значение) заменены на `your_db_password_here`.
- **Пропущено / follow-up:** другие три файла вне scope единичной правки и всё ещё содержат секрет — их нужно вычистить отдельно. Ротация admin-пароля и пароля Postgres `uk_bot`, обновление прод `.env` и БД, очистка git history. Использовать разные секреты для admin-аутентификации и БД. Примечание: находка указывала на пароль admin в строке 26, но в файле там реально `uk_bot_password` — отредактировано фактическое значение, без догадок.

#### H-2. Колбэки назначения исполнителя без проверки роли
- **Severity:** HIGH · **Категория:** authz
- **Файл:** `uk_management_bot/handlers/admin.py:2517` (а также `:2563`, `:2637`, `:2746`)
- **Риск:** `handle_assign_duty_executor_admin`, `handle_assign_specific_executor_admin`, `handle_final_executor_assignment_admin`, `handle_back_to_assignment_type_admin` зарегистрированы как «голые» `F.data.startswith(...)` колбэки без `has_admin_access` и без `StateFilter`, и даже не принимают `roles`. Они выполняют привилегированные мутации (создание `RequestAssignment`, `AssignmentService.assign_to_executor`). Любой аутентифицированный пользователь, зная/угадав `request_number` (формат `YYMMDD-NNN`), мог отправить `assign_executor_<num>_<executor_id>` и назначить произвольного исполнителя на произвольную заявку.
- **Исправлено:** Во все четыре хендлера добавлен `has_admin_access(roles=roles, user=user)` (alert `admin.handlers.no_access_actions`) до любой мутации; в сигнатуры добавлены недостающие `roles`/`active_role`/`user`.

#### H-3. GET /requests раскрывает все заявки при scope ≠ "my" (BOLA/IDOR)
- **Severity:** HIGH · **Категория:** authz
- **Файлы:** `uk_management_bot/api/requests/router.py:129` (дубль-находки id 13 и id 19)
- **Риск:** `list_requests` зависит только от `get_current_user`, без role-gate. Фильтрация по владельцу/роли применялась ТОЛЬКО в ветке `if scope == "my"`. Параметр `scope` по умолчанию `None`, поэтому обычный заявитель, вызвав `GET /api/v2/requests` без `scope=my`, получал всю таблицу заявок (до limit=200): описания, адреса, `apartment_id`, исполнители, отчёты, внутренние заметки, `return_reason` — кросс-тенантные данные всех жителей.
- **Исправлено:** Скоупинг по владельцу/роли сделан безусловным. `user_roles = _parse_user_roles(user)` вычисляется сверху; при `"manager" not in user_roles` всегда применяются owner/executor/assignment-фильтры (исполнители — по своим назначениям; заявители — `RequestModel.user_id == user.id`). Менеджеры сохраняют полный листинг. `scope` оставлен в сигнатуре (контракт для вызывающих), но больше не используется для авторизации.

#### H-4. GET /requests/kanban — вся доска любому аутентифицированному пользователю
- **Severity:** HIGH · **Категория:** authz
- **Файлы:** `uk_management_bot/api/requests/router.py:102` (дубль-находки id 14 и id 20)
- **Риск:** `get_kanban` зависит только от `get_current_user`, без role/ownership-проверок, и возвращает все заявки (до 500) с полными полями `RequestCard`. WebSocket `/ws/v2/kanban` корректно требует роль `manager` (`ws/router.py:50`) — несоответствие подтверждает, что эндпоинт предназначен только менеджерам.
- **Исправлено:** Зависимость `get_kanban` изменена с `Depends(get_current_user)` на `Depends(require_roles("manager"))` (зеркалит WS-хендшейк и `stats_router`). Не-менеджеры теперь получают 403. `require_roles` уже импортирован в файле — новых импортов не потребовалось.

#### H-5. Порты Postgres и Redis на 0.0.0.0 в media_service compose
- **Severity:** HIGH · **Категория:** authz
- **Файл:** `media_service/docker-compose.yml:64` (и `:86`)
- **Риск:** `media-db` публикует `5433:5432`, `media-redis` — `6380:6379` без bind на `127.0.0.1`, т.е. доступны на 0.0.0.0 из любой сети хоста. БД использует захардкоженный `media_password`, Redis без `requirepass` (строка 80) — удалённый атакующий мог читать/писать оба хранилища.
- **Исправлено:** Маппинги изменены на `127.0.0.1:5433:5432` и `127.0.0.1:6380:6379`; в команду redis добавлен `--requirepass ${REDIS_PASSWORD:?set me}`. Healthcheck (`redis-cli ping`) не затронут.

#### H-6 (частично). TWA refresh-токен в localStorage на общем origin
- **Severity:** HIGH (заявлено как MEDIUM, id 18) · **Категория:** auth-token-storage
- **Файл:** `frontend/src/twa/hooks/useTWAAuth.ts:35` (а также `:24`, `twaClient.ts:30`)
- **Риск:** Long-lived refresh-токен TWA сохраняется через `localStorage.setItem('twa_refresh_token', …)` на том же origin `infrasafe.uz`, что и дашборд. Любой XSS на этом origin может прочитать `localStorage` и слать украденный refresh-токен на `/api/v2/auth/refresh`, бесконечно ротируя access-токены. Команда сама задокументировала этот риск в `stores/authStore.ts:5-11`, вычищая legacy-токены из `localStorage` — но TWA-флоу его переинтродуцирует.
- **Пропущено (требует координированной правки нескольких файлов):** основной фикс (httpOnly+Secure cookie по модели дашборда) — это backend-изменение (`/api/v2/auth/twa` и `/api/v2/auth/refresh` должны ставить/чистить cookie). Fallback (отказ от `localStorage` + ре-bootstrap из `initData`) нельзя сделать в одном файле, не сломав поведение: `twaClient.ts` (редактировать запрещено) на `:24` читает `localStorage.getItem('twa_refresh_token')` в 401-интерсепторе и на `:30` его перезаписывает. Если `useTWAAuth.ts` перестанет писать токен, 401-ветка `twaClient` получит `null`, не диспатчнет `twa:auth-failed`, и слушатель ре-инициализации не сработает — восстанавливаемые истечения станут тихими сбоями. Рекомендуется координированная правка backend + `twaClient.ts` + `useTWAAuth.ts`.

#### H-7 (частично). remind_applicant утечка строки исключения
- См. также L-5 (info-leak в `main.py`). Конкретно `remind_applicant` в `uk_management_bot/api/requests/router.py` поднимает `HTTPException(500, f'Failed to send reminder: {e}')`.
- **Пропущено:** вне scope правки (файл `requests/router.py`, задача ограничивала правки `api/main.py`). Логировать исключение на сервере, возвращать статический detail.

### MEDIUM

#### M-1. Колбэки создания invite-токена без проверки роли / state-фильтра
- **Severity:** MEDIUM · **Категория:** authz
- **Файл:** `uk_management_bot/handlers/admin.py:1570` (и `:1467`, `:1500`, `:1521`)
- **Риск:** FSM-шаги создания invite (`handle_invite_role_selection`, `handle_invite_specialization_selection`, `handle_invite_expiry_selection`, `handle_invite_confirmation`) зарегистрированы как «голые» колбэки без `StateFilter` и без `has_admin_access`. Только точка входа `start_invite_creation` (1448) защищена. Любой аутентифицированный пользователь мог вручную отправить `invite_role_manager` → `invite_expiry_7d` → `invite_confirm` и сгенерировать валидную manager-invite ссылку/токен (нарушение границы привилегий, вектор для соц-инжиниринга/спама).
- **Исправлено:** Во все четыре хендлера добавлен `has_admin_access(roles=roles, user=user)` (alert `invites.manager_only`) + `roles`/`active_role`/`user` в сигнатуры. Дополнительно spec/expiry/confirm-хендлеры привязаны к своим FSM-состояниям (`waiting_for_specialization`/`waiting_for_expiry`/`waiting_for_confirmation`) вторым декоратор-фильтром. `handle_invite_role_selection` НЕ привязан к state (точка входа не ставит `waiting_for_role` до показа клавиатуры — иначе сломался бы легитимный флоу); там достаточно явной проверки роли.

#### M-2. Захардкоженные креды Postgres в прод media_service compose
- **Severity:** MEDIUM · **Категория:** secret
- **Файл:** `media_service/docker-compose.yml:56` (и `:13`)
- **Риск:** Tracked прод-compose (`DEBUG=false`, `restart: unless-stopped`) хардкодит пароль Postgres `media_password` (строка 56) и встраивает его в `DATABASE_URL` (строка 13). Любой с доступом на чтение репо получает кред БД. В сочетании с открытым портом (строка 64) — напрямую эксплуатируемо.
- **Исправлено:** Литерал заменён на `${POSTGRES_PASSWORD:?set me}`, `DATABASE_URL` — на `postgresql://media_user:${POSTGRES_PASSWORD}@media-db:5432/uk_media`. Пароль теперь из env/.env. (Если значение когда-либо использовалось в реальном деплое — ротировать.)

#### M-3. handle_materials_edit_text мутирует данные без проверки менеджера
- **Severity:** LOW (заявлено id 10; здесь сгруппировано) · **Категория:** authz
- **Файл:** `uk_management_bot/handlers/admin.py:2442`
- **Риск:** `handle_materials_edit_text` (`ManagerStates.waiting_for_materials_edit`) обновляет `request.manager_materials_comment`, `request.purchase_history` и коммитит, но в отличие от соседних manager-хендлеров (`handle_clarification_text:2035`, `handle_cancel_reason_text:2152`) НЕ делает `has_admin_access` — полагается только на FSM-состояние. Несогласованная граница авторизации на мутирующем хендлере.
- **Исправлено:** Добавлены `roles`/`active_role` в сигнатуру и `has_admin_access(roles=roles, user=user)` в начале; при отказе — `admin.handlers.no_access_actions`, очистка FSM и `return` до мутации.

### LOW

#### L-1. Rate-limit вебхука по spoofable X-Real-IP
- **Severity:** LOW · **Категория:** validation
- **Файл:** `uk_management_bot/api/rate_limit_keys.py:29`
- **Риск:** Лимит 60/мин на `POST /infrasafe/alert` бакетится по `client_ip_key`, читающему заголовок `X-Real-IP`. Корректно только при топологии «nginx — единственный ingress». При прямой доступности API атакующий ротирует поддельный `X-Real-IP` и обходит per-IP лимит (HMAC всё ещё блокирует подделку событий, поэтому только обход rate-limit / resource exhaustion).
- **Исправлено:** Добавлен opt-in allowlist доверенных прокси (`env RATE_LIMIT_TRUSTED_PROXIES`, parsed в module-level frozenset). `X-Real-IP` учитывается только когда allowlist не задан (старое поведение) ИЛИ TCP-peer входит в allowlist; иначе ключ падает на `get_remote_address` (реальный peer). Контракт/сигнатура без изменений; при пустом env поведение байт-в-байт прежнее (тест `test_invite_sec020.py` не затронут).
- **Пропущено:** enforcement через Starlette `ProxyHeadersMiddleware` / uvicorn `--forwarded-allow-ips` и инвариант «нет прямого host-port» — это правки ASGI-startup и deploy-config, вне scope одного файла.

#### L-2. Content-Disposition из несанитизированного user-controlled filename
- **Severity:** LOW · **Категория:** validation
- **Файл:** `media_service/app/api/v1/media.py:308`
- **Риск:** Эндпоинт стриминга отражает `media_file.original_filename` напрямую в заголовок `Content-Disposition: inline; filename="{…}"`. Имя берётся verbatim из `file.filename` при загрузке без валидации. Двойная кавычка (`evil".html`) ломает quoted-value; control-символы — попытка header-инъекции. В сочетании с `inline` и отсутствием `nosniff` — content-spoofing / stored-XSS.
- **Исправлено:** Введён `safe_filename = (original_filename or "file").replace('"',"").replace("\r","").replace("\n","")[:255]` и использован в заголовке. Добавлен `X-Content-Type-Options: nosniff` в `get_media_file_stream` и в соседний `stream_telegram_file`.
- **Пропущено:** корневая санитизация `original_filename` при загрузке (`media_storage._save_media_metadata`) — другой файл, cross-file. Header-санитизация полностью закрывает риск на границе ответа.

#### L-3. Утечка строки исключения в outbox_health / health (анонимный эндпоинт)
- **Severity:** LOW · **Категория:** info-leak
- **Файл:** `uk_management_bot/api/main.py:226` (находки id 22 и id 24)
- **Риск:** `outbox_health` возвращал `{"enabled": True, "error": str(e)}` на эндпоинте, который всегда отдаёт 200 и доступен анонимно через nginx как `/uk/api/health/outbox`. `str(e)` на SQLAlchemy/asyncpg-исключении обычно содержит имена таблиц/колонок, фрагменты SQL, версии драйвера — fingerprinting схемы и БД.
- **Исправлено:** `except Exception as e: … return {"error": str(e)}` заменён на `except Exception: … return {"enabled": True, "error": "internal_error"}`. Существующий `_logger.exception("outbox_health failed")` сохраняет детали на сервере. Контракт «всегда 200» сохранён.
- **Пропущено (опционально):** gating эндпоинта за monitoring-auth — менял бы публичный контракт probe; сама утечка уже закрыта.

#### L-4. Verbose downstream-ошибка в media-proxy
- **Severity:** LOW · **Категория:** info-leak
- **Файл:** `uk_management_bot/api/main.py:329` (и `:408`)
- **Риск:** `proxy_media_upload` и `proxy_media_file` пробрасывали `resp.text[:200]` из внутреннего Media Service прямо в `HTTPException.detail` клиенту — утечка внутренних сообщений/путей бэкенда для разведки.
- **Исправлено:** `detail` заменён на статический `"Media service error"`; downstream-тело логируется только на сервере (`_logger.error(...)`). Upstream-статус сохранён. Путь meta-resolution уже использовал generic `"Media not found"` и не тронут.

#### L-5. PII (полный телефон) в логах онбординга
- **Severity:** LOW · **Категория:** info-leak
- **Файл:** `uk_management_bot/handlers/onboarding.py:175` (и `:245`)
- **Риск:** `logger.info(f"Сохранен телефон {phone_number} для пользователя {…}")` пишет полный телефон в логи на INFO. `SecurityFilter` в `utils/structured_logger.py` редактирует только password/token/secret/Bearer, телефоны не матчит — PII попадает в `docker logs`/агрегацию, коррелированный с `telegram_id`.
- **Исправлено:** Интерполяция `{phone_number}` убрана из обоих INFO-логов; оставлен только `telegram_id`. User-facing подтверждение (`get_text("onboarding.phone_saved", …)`) не тронуто.

#### L-6. PII (телефон/имя) в builder клавиатуры профиля
- **Severity:** LOW · **Категория:** info-leak
- **Файл:** `uk_management_bot/keyboards/profile.py:33`
- **Риск:** `logger.debug(f"Текущие значения: phone=…, first_name=…, last_name=…")` логирует телефон и ФИО. На DEBUG human-readable форматтер используется БЕЗ `SecurityFilter` (фильтр только в non-DEBUG JSON-ветке). При включённом DEBUG в prod-like окружении PII пишется в логи нередактированной.
- **Исправлено:** Сырые значения заменены на boolean-маркеры из объекта `user`: `phone_set={bool(user and user.phone)}`, `first_name_set=…`, `last_name_set=…`; `language` оставлен. Маркеры читают поля `user` напрямую, а не resolved display-строки.

#### L-7. Неприпиненные floor'ы зависимостей в media_service
- **Severity:** LOW · **Категория:** dep
- **Файл:** `media_service/requirements.txt:20` (и `:21`, `:33`)
- **Риск:** Только нижние границы `>=` без lockfile/hashes. `python-multipart>=0.0.6` допускает версии < 0.0.18 с multipart-DoS (CVE-2024-53981); `pillow>=10.0.0` — < 10.3.0 с buffer-overflow (CVE-2024-28219); `python-jose>=3.3.0` — версии с algorithm-confusion/DoS. Сборки не воспроизводимы.
- **Исправлено:** `python-multipart==0.0.20`, `pillow>=11.0.0`, `python-jose[cryptography]==3.5.0` (extra сохранён).
- **Пропущено:** hash-locked `requirements.txt` через `pip-compile --generate-hashes` — требует запуска команд (запрещён) и переписывает весь файл с транзитивными пинами; оставлено на отдельный lockfile-проход. CVE-экспозиция закрыта пинами.

#### L-8. Захардкоженный пароль pgAdmin в media_service dev compose
- **Severity:** LOW · **Категория:** secret
- **Файл:** `media_service/docker-compose.dev.yml:89`
- **Риск:** `PGADMIN_DEFAULT_PASSWORD=admin123` (строка 89), pgAdmin на 0.0.0.0:8082; плюс `media_password` (строка 54), Postgres на 5434. Слабый известный кред на web-admin UI на всех интерфейсах — тривиально брутится; файл закоммичен и может запускаться на shared/CI-хостах.
- **Исправлено:** `PGADMIN_DEFAULT_PASSWORD=${PGADMIN_DEFAULT_PASSWORD:?...}`, `POSTGRES_PASSWORD`/`DATABASE_URL` → `${MEDIA_DB_PASSWORD:?...}`. Порты pgAdmin (8082:80) и Postgres (5434:5432) забинжены на 127.0.0.1. Статического слабого дефолта не осталось — отсутствие переменных валит compose с явным сообщением.
- **Пропущено:** создание gitignored `.env` для новых секретов — вне scope одного файла.

#### L-9. Захардкоженный INVITE_SECRET в tracked .env.test
- **Severity:** LOW · **Категория:** secret
- **Файл:** `uk_management_bot/.env.test:1`
- **Риск:** Tracked `uk_management_bot/.env.test` содержит `INVITE_SECRET=test_secret_key_for_comprehensive_testing_purposes_12345`. Это явная тестовая фикстура, prod требует своего значения (settings бросает `ValueError` при отсутствии и `DEBUG=False`), поэтому реальный риск ограничен — но коммит любого секрет-образного значения плох и рискует переиспользованием.
- **Исправлено:** Значение заменено на явно-фейковый плейсхолдер `test-only-placeholder-not-a-real-secret-do-not-reuse` + предупреждающий комментарий. Ключ остаётся truthy — тесты и валидация config не затронуты.
- **Пропущено:** миграция на conftest/CI-инъекцию или ренейм в generated fixture — cross-file/ренейм, вне scope.

---

## 3. Дубли и группировка находок

Несколько id из исходного набора описывают одну и ту же первопричину и сведены вместе во избежание двойного счёта:

- **id 13 + id 19** → одна находка H-3 (`router.py:129`, BOLA на `GET /requests`).
- **id 14 + id 20** → одна находка H-4 (`router.py:102`, BOLA на `/requests/kanban`).
- **id 22 + id 24** → одна находка L-3 (`main.py:226`, утечка `str(e)` на health/outbox).

Соответствие исходных id разделам: 1→C-1, 2→C-2, 3→H-1, 7→M-1, 8→H-2, 10→M-3, 12→L-1, 13/19→H-3, 14/20→H-4, 15→L-2, 18→H-6, 21→L-4, 22/24→L-3, 25→L-5, 26→L-6, 27→M-2, 28→H-5, 29→L-7, 30→L-8, 33→L-9.

---

## 4. Отклонённые / пониженные кандидаты

Проверено и признано НЕ реальной (или пониженной) уязвимостью — для демонстрации полноты проверки:

1. **`settings.py` — ADMIN_PASSWORD «URL-encoded length bypass» (заявл. HIGH → FALSE POSITIVE).** `ADMIN_PASSWORD` нигде не URL-декодируется: хранится verbatim (`settings.py:42`), длина меряется на сырой строке (`:184`), сравнение `secrets.compare_digest` без декода (`auth_service.py:574`). Единственный `unquote` (`api/auth/service.py:136`) относится к Telegram WebApp `user` JSON, не к паролю. Механизм «декод укорачивает до 8 символов» в коде не существует.

2. **`docker-compose.dev.yml` — hardcoded DB password (заявл. MEDIUM → LOW/hygiene).** Файл явно dev-only; прод-compose fail-closed через `${POSTGRES_PASSWORD:?}`. `uk_bot_password` — самоописательный плейсхолдер (тот же в `.env.unified.example`), реальный кред не утекает. Риск только при операторском misuse dev-файла в интернете — гипотетика, не reachable.

3. **`api/auth/service.py` — dev-only fallback JWT/secret (заявл. LOW → NONE).** Литерал `dev-jwt-secret-...` только внутри `if settings.DEBUG:`; else-ветка бросает `RuntimeError`. `DEBUG` по умолчанию `False`; settings бросает `ValueError` при отсутствии секретов в prod. media `secret_key` так же fail-fast (`config.py:80-84`). Secure-by-default + fail-fast, в prod не reachable.

4. **`handlers/employee_management.py` — role-change handlers полагаются только на FSM (заявл. MEDIUM → LOW/defense-in-depth).** Структурно верно (нет `has_admin_access` на `toggle_role`/`save_employee_roles`/`process_role_change_comment`), но `EmployeeManagementStates.selecting_roles` ставится ровно в одном месте (`:810`) ниже admin-gate (`:771`). FSM строго per-user (Redis/Memory, ключ по user_id). Альтернативной точки входа нет — privilege-escalation не reachable сегодня. Рекомендуется hardening (re-check на write-points).

5. **`services/auth_service.py` — deprecated `user.role` всё ещё пишется/читается (заявл. LOW → NONE).** Tech-debt, не reachable. Fallback на `user.role` срабатывает только при пустом/битом `roles[]`; каждый путь, ставящий привилегированный `role`, в той же транзакции пишет полный `roles[]`. Новые юзеры получают `applicant`. Атакующий не может выставить свой `role`-столбец. Все привилегированные проверки сначала гейтят `status == "approved"`.

6. **`media_service/.../media.py` — content-type из клиента, нет magic-byte валидации при upload (заявл. MEDIUM → LOW/defense-in-depth).** Механика верна, но IMPACT (reachable stored-XSS) не держится: storage — Telegram Bot API, который ре-энкодит фото и валидирует видео; HTML/SVG, помеченный как image/png, отвергается `sendPhoto`. `image/svg+xml` не в allowlist. Путь `send_document` недостижим из валидированного upload. Disguised HTML не может стать re-servable байтами.

7. **`media_service/.../media.py` — `/upload-report` без boundary size/content-type checks (заявл. LOW → не reachable).** Size и content-type всё равно энфорсятся downstream в `_validate_file` (`media_storage.py:284,288`). Ранний `file.size`-чек на `/upload` тривиально обходится (chunked/без Content-Length) и есть на обоих эндпоинтах. Cap 50MB, spooling на диск, X-API-Key gating. Code-consistency nit.

8. **`api/rate_limit.py` — limiter fail-open при сбое storage (заявл. LOW → NONE).** `in_memory_fallback_enabled=True` + `swallow_errors=True` реальны, но OTP-brute-force защищён независимым per-OTP cap (`store_otp`/`verify_otp`, attempts=3, TTL 5 мин), который НЕ зависит от slowapi-limiter и использует свой Redis без `swallow_errors`. Сбой Redis ломает auth-флоу, а не открывает его. Осознанный документированный trade-off.

9. **`media_service/docker-compose.dev.yml` — uvicorn `--reload` + DEBUG на 0.0.0.0 (заявл. MEDIUM → FALSE POSITIVE).** Файл — dev-вариант; репо уже содержит отдельный hardened прод-compose (`docker-compose.yml`: `DEBUG=false`, без `--reload`, restricted ALLOWED_ORIGINS, без admin-UI). `--host 0.0.0.0` — стандартный container-internal bind; экспозиция определяется `ports`, идентичными в prod (8001:8000). Default `docker compose up` использует hardened файл. By-design dev-конфиг.

10. **`docker-compose.unified.yml` — слабый дефолтный пароль Postgres (заявл. LOW → NONE).** Дефолт `uk_bot_password` реален, но файл — dev-артефакт; прод-аналоги fail-closed (`${POSTGRES_PASSWORD:?}`). БД и Redis забинжены на `127.0.0.1` (строки 140/160); на 0.0.0.0 открыты только media-API (8009) и media-frontend (8010), не БД. Off-host атакующий не достаёт БД. Тот же литерал уже в `docker-compose.dev.yml` — устоявшаяся dev-конвенция.

---

## 5. Остаточные риски / рекомендации (не закрыты автоматически)

Следующее требует операций вне правки рабочего дерева и остаётся **обязательными follow-up**:

1. **Ротация всех скомпрометированных секретов** (КРИТИЧНО): `BOT_TOKEN` и `MEDIA_BOT_TOKEN` через @BotFather; `INVITE_SECRET` и `JWT_SECRET` на независимые `openssl rand -hex 32`; admin-пароль и пароль Postgres `uk_bot`. Все они уже в git history — замена плейсхолдеров в рабочем дереве НЕ удаляет их из истории.
2. **Очистка git history** (`git filter-repo` / BFG) для `docs/Archive/Old_Docs/main.file` и инвалидация всех активных сессий/refresh-токенов после ротации `JWT/INVITE_SECRET`.
3. **Зачистка секрета в трёх других tracked-файлах:** `docs/Archive/Deployment/SERVER_SETUP_GUIDE.md:49`, `docs/Archive/Deployment/DEPLOYMENT_FIXES.md:87`, `docs/audit/2026-05-20-backlog.md:1023` — содержат тот же admin/DB-пароль.
4. **TWA refresh-токен (H-6):** перевести на httpOnly+Secure cookie (backend `/api/v2/auth/twa` + `/api/v2/auth/refresh`), согласованно с `twaClient.ts` и `useTWAAuth.ts`. Не делать односторонней правкой одного файла — иначе тихие сбои 401-флоу.
5. **`remind_applicant` (H-7):** убрать `f'Failed to send reminder: {e}'` из detail (`uk_management_bot/api/requests/router.py`), логировать на сервере.
6. **Enforcement trusted-proxy (L-1):** Starlette `ProxyHeadersMiddleware` / uvicorn `--forwarded-allow-ips`, инвариант «API не экспонирует host-port» — в deploy-config.
7. **Hash-locked requirements (L-7):** `pip-compile --generate-hashes` для `media_service/requirements.txt` по образцу root-requirements.
8. **Корневая санитизация `original_filename` при upload (L-2):** в `media_storage._save_media_metadata`, в дополнение к header-фиксу.
9. **gitignored `.env`-файлы** для новых `${VAR:?}`-переменных media compose (M-2, L-8): `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `MEDIA_DB_PASSWORD`, `PGADMIN_DEFAULT_PASSWORD`.
10. **Миграция тестовых секретов (L-9):** инъекция через conftest/CI вместо committed `.env.test`.

---

## 6. Условия проведения аудита

- Все правки внесены **только в рабочее дерево**. Коммитов и пушей не делалось.
- Деплой не выполнялся; миграции, docker/docker-compose, ssh/scp, alembic и любые сетевые/серверные/БД-команды не запускались.
- **Прод-сервер не затрагивался** — он в этот момент тестировался другим агентом.
- Вендорные/генерируемые пути (`node_modules/`, `venv/`, `.git/`, `dist/`, `build/`, `__pycache__/`, `*.session`, `*.lock`, `*.min.js`, lock-файлы) исключены из охвата.
