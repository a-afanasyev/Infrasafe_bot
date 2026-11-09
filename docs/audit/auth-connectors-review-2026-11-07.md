# Callback-хендлеры бота и auth-коннекторы — ревью 2026-11-07

Продолжение IDOR-ревью HTTP-маршрутов (`docs/audit/idor-review-2026-11-07.md`).

- **Снимок:** `origin/main` 95d652c9 плюс фиксы этой ветки.
- **Окружение:** только локальный стенд — sqlite-харнесс, одноразовый Redis в контейнере на 127.0.0.1:6390. Вызовов Telegram API, profk.uz и прод-БД не было.
- **Секреты:** в тестах фейковые bot token и ключи. В отчёте упоминаются только имена переменных.

## Таблица находок

Таблица составлена до фиксов: красные тесты подтвердили каждую строку, затем последовал фикс.

| # | Объект | Severity | Что было | Фикс |
|---|---|---|---|---|
| BOT-01 | `executor_complete_<n>` → `executor_finish_completion_<n>` (`handlers/requests/executor.py`) | **P2** | Любой пользователь бота, включая жителя, проходил цепочку по чужому номеру заявки. Его фото уходили в media-service как `completion_*` этой заявки **до** канонической авторизации. Отказ `run_command` наступал позже, а файлы оставались. Фотоотчёт читается из media-service (`services/completion_media.py`), поэтому подложенные фото видели житель при приёмке и менеджер, а автосбор отчётов о работах их подхватывал. Тот же класс, что A9-P2-3, только через бот | Проверка `can_upload_completion_sync` (канон «менеджер или назначенный исполнитель») до загрузки; отказ тем же текстом, что «не найдено» |
| BOT-02 | `matissue_start_<n>` (`services/request_handler_service.guard_executor_issue`) | P3 | Статус проверялся раньше исполнителя: по `wrong_status` против `not_executor` чужой узнавал, в работе ли заявка | Сначала «твоя ли», потом статус |
| AUTH-01 | OTP (`api/auth/service.py`, `_OTP_CONSUME_LUA` + `store_otp`) | P3 | При исчерпании попыток ключ удалялся, и `resend-otp` выдавал 3 свежие попытки. Защиту A10-INT-07 это обходило: второй фактор перебирался без конца, по 3 кода на каждый resend (пароль атакующему всё равно нужен) | Исчерпание помечается `attempts=0` без удаления ключа; resend код меняет, попытки не возвращает; блок до истечения TTL |
| AUTH-02 | Блокировка и удаление пользователя | P3 | Строки refresh не отзывались. Пока аккаунт заблокирован, ротация отказывает, но после разблокировки все прежние сессии (refresh живёт до 30 дней) оживали | Отзыв всех активных refresh (`reason=admin`) в общей точке смены статуса (`services/users/status.py`) и в бот-пути `AuthService.block_user`, при отклонении и удалении сотрудника |
| AUTH-03 | Тикет регистрации (`api/registration/tickets.py`) | P3 | Stateless JWT на 30 минут: не гас ни при завершении регистрации, ни при перевыпуске, активных тикетов на аккаунт могло быть сколько угодно | `jti` в Redis (`reg:ticket:<telegram_id>`): перевыпуск перезаписывает, завершение гасит |
| AUTH-04 | CSRF под cookie-сессией (`uk_access`) | P3 | Явной проверки не было, защищал только `SameSite=Strict`. Он не закрывает same-site: поддомены площадки (`resources.…`, `monitor.…`) могли отправить form/text/multipart-POST с cookie менеджера. Тест подтвердил: запрос с `Sec-Fetch-Site: same-site` доходил до хендлера | Middleware для мутирующих запросов с cookie и без `Authorization`: пропускает `Sec-Fetch-Site: same-origin` и Origin из `CORS_ORIGINS`/`FRONTEND_URL`; чужой Origin, same-site/cross-site и form/text/multipart без Origin → 403 `csrf_rejected` |
| AUTH-05 | Ротация ключей media-service | P3 (документация) | Механизм есть (`MEDIA_API_KEYS` — список), но процедура нигде не описана | Раздел в `.claude/skills/uk-deploy/SKILL.md` |

Все семь находок исправлены в этой ветке, по каждой тест был красным до фикса и стал зелёным после.

## A. Callback-хендлеры бота

**Как снят реестр** (`docs/audit/bot-callback-inventory.md`):
- **Источник.** Живое дерево роутеров обоих ботов: `setup_routers` и `setup_group_intake_dispatcher`. Обход `sub_routers` с наследованием root-фильтров `ActionGate`/`RoleGate`.
- **Объём.** 396 callback-хендлеров. Из них 225 разбирают id из `callback_data`; плюс один deep-link `/start join_<token>`.
- **Staff — 136.** Сюда входят root-гейт `admin_panel.use` (адресный кластер, управление сменами), `@require_action` с ролями персонала и ранний отказ в теле (`if not has_admin_access…` / `_guard`). Маркер авторизации в условии держит существующий `tests/services/test_handler_authz_ratchet.py`.
- **Открытые жителю или исполнителю — 89.** Категория и тест на каждый — в `BOT_IDOR_COVERAGE` (`uk_management_bot/tests/handlers/test_bot_callback_idor.py`).
- **Ратчет.** Новый callback с id вне staff-гейта без записи в реестре даёт красный тест. Устаревшая запись тоже красная, и ссылка на несуществующий тест тоже. Проверено: удалённая запись и битая ссылка роняют тест.

| Объект | Где в коде | Проверка | Тест | Статус |
|---|---|---|---|---|
| Заявка: карточка, комментарии, отчёт, медиа | `requests/listing.py`, `request_comments.py`, `request_reports.py`, `requests/executor.py:executor_view_media` | канон `has_request_access_sync` | `test_bot_callback_idor::test_report_view/test_comments_view`, `test_comment_access_idor`, `test_executor_media_access` | ✅ |
| Заявка: отмена, приёмка, возврат, оценка | `listing.handle_cancel_request`, `request_acceptance.*`, `request_reports.handle_approve_request/handle_request_revision` | канон `run_command` (APPLICANT_* — только owner/сосед); входы без побочных эффектов | `test_completed_view` | ✅ |
| Заявка: правка, ответ на уточнение | `listing.handle_edit_request`, `myrequests.handle_reply_clarify_*` | `request.user_id == user.id`; запись перепроверяет | `test_edit_request_entry`, `test_reply_clarify_does_not_leak_or_write_foreign` | ✅ |
| Заявка: «Готово» исполнителя | `executor.executor_finish_completion` | `can_upload_completion_sync` до загрузки | `test_finish_completion_uploads_only_for_assigned` | ✅ после BOT-01 |
| Заявка: взять, закуп, в работу | `executor.claim_group_request/…purchase/…return_to_work` | канон `run_command` | `tests/api/test_request_claim.py` (тот же канон) | ✅ |
| «Фото до», «Готово с фото» | `requests/executor_before.py`, `executor_done.py` | `check_before_access`; личный чат + `complete_with_photo` | `test_executor_before.py`, `test_executor_done_callback` | ✅ |
| Списание материалов | `requests/materials.py` → `guard_executor_issue` | исполнитель заявки, затем статус | `test_material_issue_handlers`, `test_material_guard_does_not_disclose_foreign_status` | ✅ после BOT-02 |
| Смена, передача смены | `shifts.py`, `shift_transfer.py`, `my_shifts/viewing.py` | `Shift.user_id` в SQL; `create_transfer`/`accept`/`reject` (сначала «чья») | `test_shifts_authz`, `test_shift_transfer_rebuild` | ✅ (IDOR-02 из HTTP-ревью закрыл и бот-путь) |
| Квартиры жителя | `user_apartments.py` | владелец привязки | `test_bug_wave_p2_silent`, `test_user_apartments_admin_guard` | ✅ |
| Пропуска, авто, спорный въезд | `access_control.py` | сервисы `create_resident_*`/`cancel_resident_pass`/`confirm_disputed_entry` (ApartmentNotOwned/PassNotOwned/EntryNotOwned) | `test_access_control_handler`, `test_disputed_entry_callback`, pg-тесты `access_control/tests/test_resident_api.py` | ✅ |
| Переключение роли | `base.switch_role` | целевая роль ∈ ролей пользователя | — (чтение) | ✅ |
| Лифты (лифтёр) | `elevators/*` | root `elevators.technician` (E,M,A,EN) | `test_elevators_repair` | ✅ осознанно (A10-INT-10) |
| Групповой intake | `group_intake.py` (бот групп) | сообщения — только из активной группы `monitored_groups` (`_load_group_sync`); кнопки — кандидат по `(chat_id, message_id)` + `_presser_allowed` | `test_group_intake_callbacks::test_foreign_presser_gets_alert_and_nothing_happens`, `test_group_intake_routing` | ✅ |
| Deep-link `/start join_<token>` | `base.cmd_start` → `invite_service.validate_invite(mark_used_by=…)` | HMAC + `compare_digest`, `expires_at` (по умолчанию 24 ч), одноразовый nonce под UNIQUE, rate-limit, маскирование в логах | `tests/api/test_invite_validation.py`, `test_invite_token_logging.py` | ✅; к `telegram_id` привязывается при погашении (осознанно) |

## B. Auth-коннекторы

| # | Объект | Где в коде | Что проверяется | Тест | Статус |
|---|---|---|---|---|---|
| 1 | TWA initData | `api/auth/service.py:verify_twa_init_data` | HMAC: ключ `HMAC("WebAppData", BOT_TOKEN)`; `auth_date` обязателен, не старше `AUTH_DATE_MAX_AGE_SECONDS = 300`; `compare_digest` | `test_auth_connectors::test_init_data_*` (чужой бот, протух, без auth_date, подмена поля, окно = 300) | ✅; повтор в окне — осознанно (ниже) |
| 2 | Login Widget | `verify_telegram_widget`, `POST /auth/telegram-widget` | ключ `sha256(BOT_TOKEN)`, HMAC над сырым телом, `auth_date` ≤ 300 с, `compare_digest` | `test_widget_signed_with_sha256_of_bot_token`, `test_auth_telegram_widget.py` | ✅ |
| 3 | OTP | `/auth/login`, `/login/verify-otp`, `/login/resend-otp`; `store_otp`/`verify_otp` | `SystemRandom`, 6 цифр; TTL 5 мин; 3 попытки атомарно (Lua, sha1); после исчерпания блок до TTL (AUTH-01); код не в ответе и не в логе; одинаковый 401 и время (dummy bcrypt) для неизвестного email и неверного пароля; лимиты по IP: 10/10/3 в минуту; все три ручки под `auth_ratelimit_guard` (fail-closed при мёртвом Redis-бэкенде) | `test_otp_resend_after_lockout_does_not_refill_attempts`, `test_login_never_returns_or_logs_the_code`, `test_login_same_answer_for_unknown_and_wrong_password`, `test_all_otp_routes_are_behind_auth_ratelimit_guard`, `test_auth_otp_atomic.py` | ✅ после AUTH-01 |
| 4 | Refresh-токены | `_rotate_refresh_token`, `revoke_refresh_token`, `services/users/status.py` | ротация на каждом refresh под `FOR UPDATE`; повтор ротированного → отзыв всего семейства (APIFE-14); хранится sha256; TTL 30 д (веб) / 24 ч (TWA); logout отзывает; не-approved не ротируется; блокировка или удаление отзывают все сессии (AUTH-02) | `test_blocking_user_revokes_refresh_tokens`, `test_auth_refresh_rotation.py`, `test_auth_refresh_pg_concurrency.py` | ✅ после AUTH-02 |
| 5 | Тикет регистрации | `api/registration/tickets.py`, `router.require_registration_ticket` | JWT `purpose=register`, `iss`, `sub=telegram_id`, TTL 30 мин; не принимается как access-токен и наоборот; один активный на аккаунт: перевыпуск и завершение гасят (AUTH-03) | `test_registration_ticket_reissue_and_completion_revoke`, `tests/api/test_idor_matrix.py::test_registration_*` | ✅ после AUTH-03 |
| 6 | Тикет ресурсов | `api/resource_accounting/router.py` → `resource-accounting/backend/app/api/auth.py` | s2s `X-Service-Token` (`compare_digest`); в базе хеш тикета; TTL 60 с; одноразовость — условный UPDATE `used_at IS NULL`; twa-ticket: initData + approved + `resources.meter_entry` | `resource-accounting/backend/tests/test_auth.py::test_ticket_exchange_full_flow` (повторный обмен → `ticket_used`), `::test_ticket_expiry`, `test_tenant_isolation.py` | ✅ (регрессия уже закреплена) |
| 7 | Вебхуки | `api/webhooks/security.py`, `services/inbound_webhooks/replay.py` | Telegram — polling (оба бота), HTTP-входа и секрета `X-Telegram-Bot-Api-Secret-Token` нет. InfraSafe → UK: HMAC-SHA256 над `t.raw_body`, окно ±300 с, `compare_digest`, dual-secret ротация, повтор `event_id` (SET NX, 600 с) → 409; без подписи, с битой или протухшей → 401 | `test_webhook_inbound.py` (no header / bad format / invalid / stale / no secret), `test_inbound_alert.py::test_duplicate_event_returns_409` | ✅ |
| 8 | Cookie-сессия менеджера | `api/auth/router._set_auth_cookies`, `api/main.CsrfGuard` | `HttpOnly`, `Secure` (вне DEBUG), `SameSite=Strict`, узкие `Path`; CSRF — Origin/Sec-Fetch-Site для мутаций под cookie (AUTH-04) | `test_cookie_mutation_from_foreign_origin_is_rejected` ×3, `test_cookie_mutation_from_own_origin_passes` ×3, `test_bearer_is_not_subject_to_csrf` | ✅ после AUTH-04 |
| 9 | access_control edge и фото | `access_control/services/device_auth.authenticate_edge`, `services/photo_urls.py`, `api/equipment.rotate-key` | `X-AC-Controller` + `X-AC-Key` (хранится sha256, `compare_digest`), HMAC тела на пер-устройственном секрете, окно 300 с, nonce (Redis SET NX), IP-allowlist, `controller_id` пути = контроллер device-auth; фото — HMAC над `event_id\nkind\nexp`, TTL 300 с, подмена → 403, протух → 410; ротация API-ключа — `POST /admin/controllers/{id}/rotate-key` (новый ключ отдаётся один раз) | `access_control/tests/test_device_auth.py`, `test_edge_endpoints.py`, `test_photo_urls.py`, `test_equipment_api.py` | ✅; ротация HMAC-секрета — только через env (ниже) |
| 10 | Ключи media-service | `media_service/app/main.api_key_auth`, `api/routes/media_proxy.py`, SKILL | middleware `X-API-Key` на всё, кроме health (`compare_digest`); во фронтенде ключа нет (grep `frontend/src`); в логах только код ответа; в ответах прокси — `file_url` относительный (`/api/v1/media/{id}/file`), ссылка с токеном медиа-бота остаётся внутри media-service; отказ ключа → 502 без тела апстрима; процедура ротации описана (AUTH-05) | `test_media_key_rejection_is_not_echoed`, `media_service/test_log_sanitize.py` | ✅ после AUTH-05 |

## Оставлено осознанно

- **Повтор initData и payload виджета в окне 300 с.** `initData` по протоколу Telegram многоразов в пределах сессии Mini App: им пользуются вход, регистрация и тикет ресурсов. Одноразовость сломала бы законные повторы. Ограничение — короткое окно. Утечка `initData` даёт не больше 5 минут.
- **Код ответа без подписи вебхука — 401, а не 403.** Отсутствие или неверная подпись — это ошибка аутентификации, а контракт с InfraSafe уже на 401. Повтор вебхука при недоступном Redis — fail-open (D3): подлинность уже доказал HMAC.
- **Тикет регистрации при недоступном Redis** принимается по подписи и TTL (fail-open, как D3). Повтор регистрации после потерянного ответа теперь требует нового `/start`: клиент получает 401 и начинает заново.
- **Лимит OTP «на аккаунт».** Логина по номеру нет: вход — email и пароль, затем OTP. Лимиты slowapi — по IP (10 входов и 10 проверок кода в минуту, 3 resend). На аккаунт после AUTH-01 действует блок: 3 неверных кода, затем ждать до истечения 5 минут.
- **Edge HMAC-секрет устройства** ротируется только через `ACCESS_DEVICE_SECRET__<ref>` или общий сид (передеплой). API-ключ ротируется эндпоинтом. Это пилотный профиль; mTLS — этап после пилота (§9.1).
- **`/metrics` access-api** открыт, пока не задан `ACCESS_METRICS_TOKEN` (opt-in ради скрейпа alloy).
- **Ключи media-service равноправны** — разграничение по категориям остаётся кандидатом в бэклог (из IDOR-ревью §4).
- **Лифтёр видит весь реестр лифтов** — A10-INT-10.

## Изменения контракта, о которых нужно знать

- **CSRF (AUTH-04).** Мутация под cookie с чужого Origin, со `Sec-Fetch-Site: same-site/cross-site`, а также form/multipart/text без Origin получает 403 `{"detail": "csrf_rejected"}`. Дашборд не затронут: его запросы идут со своего origin (`Sec-Fetch-Site: same-origin`, Origin = `FRONTEND_URL`). TWA и сервисы ходят с Bearer и проверку не проходят. Реализация — чистый ASGI-класс `CsrfGuard`: вариант через `@app.middleware` сдвигал BackgroundTasks раньше ответа, это поймали `test_network_outside_tx` и `test_elevators_status_calendar`.
- **Тикет регистрации (AUTH-03).** Повторная отправка `/registration/applicant` **тем же** тикетом после успешной регистрации даёт 401. Повтор с новым тикетом из `/start` идемпотентен, как и раньше: `test_applicant_double_submit_idempotent` переведён на этот путь. Тесты, где ожидание расходилось с требованием, правлены явно: `test_registration_document_offer.py`, `test_registration_applicant.py`.
- **OTP (AUTH-01).** После 3 неверных кодов действует блок до истечения 5 минут, повторный вход его не снимает. Текст ответа — «Too many attempts. Try again in 5 minutes.» Во время блока `/login` и `/login/resend-otp` отвечают 429 и код не отправляют; блок не продлевается (правка по ревью PR #718). Без Redis выдача и гашение тикета регистрации не падают, а работают по подписи (fail-open, как проверка).
- **Списание материалов (BOT-02).** Чужой исполнитель всегда получает «не ваша заявка», статус ему не раскрывается.

## Прогоны

- **Бот:** `uk_management_bot/tests/handlers/test_bot_callback_idor.py` — до фиксов красные BOT-01 (житель и чужой исполнитель загружали фото) и BOT-02. После фиксов все зелёные, вместе с ратчетом реестра и проверкой ссылок. Ратчет краснеет на удалённой записи и на битой ссылке — проверено временной копией.
- **Auth:** `tests/api/test_auth_connectors.py` — до фиксов 6 красных (AUTH-01, AUTH-02, AUTH-03, AUTH-04 ×3), после — 21 из 21.
- **Локальный набор 2** (`tests/api tests/services`, одноразовый Redis): регресс от первой версии CSRF-middleware найден и исправлен (см. выше).
- **`make test-ci` — эталон, зелёный:**
  - гейт дампов ПДн, alembic upgrade + check;
  - набор 1 — 6427 passed;
  - набор 2 — 3351 passed;
  - OpenAPI-снапшот и порог покрытия.

  Первый прогон был красным: ратчет оставлял роутеры aiogram подключёнными (4 ошибки в `test_group_intake_routing`), а `test_applicant_double_submit_idempotent` закреплял повтор старым тикетом. Оба исправлены, второй прогон зелёный.
- **resource-accounting:** 119 passed, 4 skipped. Код сервиса этим этапом не менялся.
- **ruff** по всем изменённым файлам чистый.
