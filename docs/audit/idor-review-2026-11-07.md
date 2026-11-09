# IDOR/BOLA-ревью API — 2026-11-07

White-box проверка авторизации на уровне объектов во всех HTTP/WS API монорепо: UK API (`uk_management_bot/api`), access-api (`access_control`), media-service, resource-accounting. Снимок `origin/main` 95d652c9. Работа шла только на локальном стенде: sqlite-харнесс тестов и локальные контейнеры. Запросов к profk.uz, infrasafe.uz и прод-БД не было.

## 1. Метод

1. **Инвентарь.** Маршруты сняты интроспекцией живых приложений, а не grep'ом:
   - обход `app.routes`, включая `Mount` и `_IncludedRouter` FastAPI 0.141;
   - обход дерева `dependant`;
   - обёртки slowapi развёрнуты через `inspect.unwrap`, чтобы видеть настоящий файл и строку;
   - ключи `require_action` разворачиваются в роли по `authz/catalog.py`;
   - path-параметры берутся из шаблона пути: edge-хендлеры access-api не объявляют `controller_id`, его читает `authenticate_edge`.

   Результат — `docs/audit/api-route-inventory.md`: **388 маршрутов** (UK 240, access 67, media 29, resource 52). `require_roles`, `require_approved_roles` и `_manager_only` в UK API больше не встречаются: все гейты переведены на `require_action`. Старый `require_roles` остался только в resource-accounting.

2. **Классы.** Каждый маршрут с `{id}` отнесён к классу и прочитан вместе с сервисным слоем:

   | Класс | Что это | UK | access | media | resource |
   |---|---|---|---|---|---|
   | a | только персонал с доступом ко всему разделу | 95 | 23 | — | 25 (внутри тенанта) |
   | b | открыт жителю, исполнителю или инспектору | 13 | 3 | — | — |
   | c | публичный с вложенными id | 2 | — | — | — |
   | d | тикет, устройство, подпись | 2 | 7 | — | (2 без `{id}`: тикеты) |
   | s2s | только сервисный ключ | — | — | 13 | — |

3. **Тесты.** На каждый маршрут классов b–d есть пара «A на объекте B → 403/404, свой объект → 2xx». Новые пары лежат в `tests/api/test_idor_matrix.py` и `resource-accounting/backend/tests/test_tenant_isolation.py`. Если пара уже была в профильном тесте, на неё ссылается реестр `IDOR_COVERAGE`. Ратчет `test_every_object_route_outside_staff_scope_is_covered` требует записи в реестре для каждого маршрута с `{id}`, открытого не только персоналу. Проверено, что он краснеет при удалённой записи.

## 2. Находки

Падения тестов и прочитанный код. Severity указана по шкале бэклога.

| # | Маршрут | Роль | Что было доступно | Severity | Фикс | Тест |
|---|---|---|---|---|---|---|
| IDOR-01 | `PATCH /api/v2/requests/{n}` (edit-ветка) | любая роль, которой админка ролей выдала `requests.update` без исполнения, авторства и `requests.manage` (например, инспектор или своя роль) | Правка `urgency` и `notes` **любой** заявки; ответ 200 отдаёт полную карточку чужой заявки | P3: нужна правка прав суперадмином, но название действия обещает «бизнес-проверки внутри» | Менеджерская ветка стала `elif manages`, иначе 403 (`api/requests/router.py`) | `test_request_edit_role_granted_update_cannot_edit_foreign`: был красный (200), стал зелёный |
| IDOR-02 | `POST /api/v2/executor/shifts/transfers/{id}/respond` и бот `ShiftTransferService.accept/reject_transfer` | исполнитель | По чужой передаче статус проверялся раньше владельца: `wrong_status` (409) против `not_your_transfer` (403) раскрывал статус чужой передачи (в том числе «ещё pending, получатель не назначен»; прежний тест `test_accept_pending_not_yet_assigned_409` закреплял именно это) | P3, оракул без данных | Сначала «чья», потом статус: `api/shifts/service/web_transfers.py`, `services/shift_transfer_service.py`. Коды ответа и тексты фронта не меняются | `test_foreign_transfer_status_is_not_disclosed`, `test_foreign_executor_cannot_learn_transfer_status`: были красные, стали зелёные |

Об IDOR-01 и правиле «фильтр в запросе, а не проверка после выборки». IDOR-01 — дефект ветвления по ролям, а не выборки, поэтому фикс — явный отказ в ветке, без нового фильтра. Карточка и прочие одиночные объекты заявки по-прежнему проходят единый канон `has_request_access_async`: сначала выборка по номеру, отказ до выдачи любых данных. Это осознанная архитектура П5/AUD3-14: один чистый предикат для бота и API, паритет закреплён `test_request_access_parity`. Списки (`list_requests_rows`) фильтруют область видимости в самом SQL.

О IDOR-02. Фильтр по получателю в запросе превратил бы чужую передачу в 404 `transfer_not_found`, а для этого кода у TWA нет текста. Перестановка проверок закрывает оракул без смены контракта.

## 3. Проверено и чисто

**UK API, класс b.** Пары отказ/успех зелёные:

- **Заявки:**
  - карточка, комментарии (чтение и запись), правка исполнителем и автором, отмена через workflow-движок — по-настоящему, без мока `run_command_async`;
  - «Проблема», «Готово», «Фото до», взятие из пула;
  - канон доступа: менеджер или инженер, автор, исполнитель (прямой, индивидуальный, групповой на смене), сосед только на «Исполнено».
- **Медиа-прокси:**
  - список, файл и загрузка: отказ происходит **до** похода в media-service;
  - `media_id` резолвится в `request_number`, после чего проверяется канон доступа к заявке;
  - документы жителей и кадры охраны не имеют `request_number`, поэтому дают 404; медиа отзывов (`fb-{id}`) — тоже 404.
- **Смены исполнителя:**
  - завершение чужой смены — 403;
  - передачи — после фикса IDOR-02;
  - `POST /executor/shifts/transfers` проверяет `shift.user_id == from_executor_id`.
- **Лифты дома:** `for-building/{building_id}` пускает жителя только в дом с одобренной квартирой, проверка идёт до выборки.
- **id в теле.** Таких маршрутов без `{id}` в пути три:
  - `POST /requests`: адрес проходит матрицу `resolve_request_address` (свои двор, дом, квартира), `elevator_id` привязывается к дому заявки (`ensure_elevator_usable_async`);
  - `POST /requests/inspector`: любой активный дом по замыслу;
  - `POST /media/upload`: `request_number` и канон доступа, `completion_*` — только исполнитель или менеджер (A9-P2-3).

**UK API, класс c.** `public/work-reports/{id}` и `…/media/{media_id}`: только `published`, `media_id` обязан входить в before/after именно этого отчёта, оба промаха дают одинаковый 404, ETag/304 проверяется после IDOR-гейта. Закреплено `test_work_reports_public.py`.

**Класс d, тикеты:**

- **Регистрация.** JWT `purpose=register`, `iss=uk-management`, `sub=telegram_id`, TTL 30 мин.
  - Тикет многоразовый **по замыслу**: каскад адресов делает несколько вызовов. Он открывает только справочник адресов и создание pending-заявки своего `telegram_id`.
  - Access-токен не проходит как тикет (нет `purpose`), тикет не проходит как access-токен (`verify_access_token` отвергает любой `purpose`), просроченный отвергается.
  - Закреплено `test_registration_cascade_requires_ticket` и `test_registration_ticket_is_not_an_access_token`.
- **Resource launch-ticket.**
  - UK выпускает тикет s2s по `X-Service-Token`; роль выводит бэкенд. В TWA — по `initData` (HMAC, `auth_date` ≤ 300 с) + `approved` + `resources.meter_entry`; удалённый сотрудник получает `status=deleted` и отсекается.
  - Resource-сервис хранит хеш тикета, TTL 60 с, расход — условным UPDATE по `used_at IS NULL`. Закреплено `test_auth.py::test_ticket_exchange_full_flow` и `::test_ticket_expiry`.
  - Окно отзыва сессии — 1 ч (AUD7-SEC-03, PR #707).
- **Access edge.**
  - `controller_id` пути обязан совпасть с контроллером из device-auth, иначе 403 (`device_auth.authenticate_edge`).
  - lease/ack идут по CAS `(command_id, controller_id, lease_token)`; закреплено `test_edge_command_consumer::test_ack_foreign_controller_409` и `test_barrier_commands_channel::test_ack_foreign_controller_conflict`.
- **Access фото.** Подпись HMAC над `event_id\nkind\nexp`, TTL 300 с, `compare_digest`; подмена любого поля → 403. Закреплено `test_photo_urls.py`.

**Access-api, класс b (житель).** Отмена пропуска, лимит места и подтверждение спорного въезда проверяют квартиру и автора. Закреплено pg-тестами:

- `test_resident_api::test_cancel_foreign_pass_403`, `::test_create_*_foreign_apartment_403`;
- `test_spot_limit_toggle::test_my_toggle_limit_foreign_403`;
- `test_disputed_entry::test_foreign_resident_403`.

**Resource-accounting.** Все `{id}` — UUID с проверкой `tenant_id` пользователя, на чужое отвечают 404. Новые тесты: чужой тенант получает 404 на 9 маршрутах объектов, счётчиков, показаний, коррекций и аналитики и на патчах каталога ×3; списки не протекают. Своему тенанту отвечает 200.

**Media-service.** Пользовательских субъектов нет: всё, кроме health, закрыто `X-API-Key` (middleware, `compare_digest`). После фазы 3 аудита #11 сервис живёт во внутренней сети. Горизонтальная проверка — на стороне UK-прокси (выше).

**WS.** Каналы `/ws/v2/*` — только `dashboard.live` (менеджер, инженер), закреплено `test_ws_live_authorization`. `/ws/v1/access/security` — `access.live` и личность в БД (approved, не удалён): AUD7-SEC-02 закрыт.

## 4. Осознанно и вне класса находок

- **Исполнитель и инженер видят весь реестр лифтов и их заявки** (`elevators.read`), исполнитель меняет статус лифта и закрывает ТО. Это решение владельца A10-INT-10 (WONTFIX); в ратчете действие отнесено к «широким по замыслу». Инспектор читает любой активный дом (`addresses.read`) — по смыслу обхода.
- **403 против 404 на чужом и несуществующем id** раскрывают только существование номера. Так везде: канон заявки, жильцы access, отмена через workflow (422 «no action maps … for this actor» против 404). Номера заявок `YYMMDD-NNN` и так предсказуемы. Данных не раскрывается; отдельной находкой не заводится.
- **Охрана не привязана к зонам:** модели «оператор ↔ зона» нет, одна площадка = один комплекс. Пункт пентеста «zone-scoping Access API» к текущей модели не применим.
- **Ключи media-service равноправны:** ключ access-api технически читает и документы жителей. Это не пользовательский IDOR, а радиус поражения при утечке ключа. Кандидат в бэклог — ключи со списком разрешённых категорий (P3, hardening).

## 5. Сверка с прошлыми аудитами

| Источник | Пункт | Суть | Статус на 95d652c9 |
|---|---|---|---|
| AUDIT_REPORT.md (#9) | A9-P2-1 | маркер фото под FOR UPDATE без `populate_existing`, мок гейта в тесте | ✅ закрыт (PR #600); канон доступа в прокси настоящий — эта матрица гоняет его без мока |
| #9 | A9-P2-3 | житель грузит `completion_*` в чужой фотоотчёт | ✅ закрыт (PR #600): `can_upload_completion_async` в прокси, «Готово» и «Фото до» |
| #9 | A9-P2-16 | ретеншн фото ANPR не удалял медиа | ✅ закрыт (PR #611) |
| #9 | A9-P2-30 | гонка каскада регистрации → квартира чужого дома | ✅ закрыт (PR #609); сервер дополнительно проверяет `is_apartment_selectable` |
| #9 | A9-P3-2 | `/metrics` access-api без токена | ✅ закрыт (PR #611): `require_metrics_token` в инвентаре |
| #9 | A9-P3-11 | два резолвера ролей, фолбэк на `active_role` эскалировал | ✅ закрыт (PR #623): `require_action`/`require_roles` через `get_user_roles` |
| AUDIT_REPORT+2026-09-08+codex.md (#7) | SEC-02 | удалённый охранник проходил WS | ✅ закрыт (PR #568): личность сверяется в БД до подписки |
| #7 | SEC-03 | отзыв роли в UK не гасил resource-сессию | ✅ закрыт (PR #707): TTL сессии 1 ч |
| #7, §6 сильные стороны | object-level access перед detail; одноразовый launch-ticket; tenant-проверка экспорта | подтверждены и теперь закреплены тестами | ✅ |
| Пентест profk.uz, «ограничение фазы 2» (бэклог) | horizontal-IDOR между жителями, область исполнителя, скачивание чужих файлов, zone-scoping | не проверялось — не было аккаунтов | ✅ покрыто white-box этой матрицей; zone-scoping — см. §4 |
| **Новое** | IDOR-01, IDOR-02 | §2 | ✅ исправлено в этой ветке |

Открытых пунктов по IDOR/BOLA после ветки: **0**. Кандидат в hardening — ключи media по категориям (§4).

## 6. Прогоны

- `tests/api/test_idor_matrix.py`:
  - до фиксов — 38 зелёных и 1 красный (IDOR-01), затем 1 красный по IDOR-02;
  - после фиксов — 40/40.
- `uk_management_bot/tests/test_shift_transfer_rebuild.py` — новый тест был красный, теперь зелёный.
- `resource-accounting/backend/tests` целиком — 119 passed, 4 skipped (pg-only).
- Набор 2 (`tests/api tests/services`) локально:
  - 3297 passed, 2 failed;
  - `test_executor_transfers::test_accept_pending_not_yet_assigned_409` закреплял оракул IDOR-02: посторонний узнавал, что передача pending. Тест переименован в `…_is_not_yours`, теперь ожидает 403 `not_your_transfer`, зелёный;
  - `test_redis_pubsub_timeouts::…test_silence_then_message_via_listen` красный и на чистом `origin/main` — локальное окружение Redis, не регресс; с одноразовым Redis (ревью auth-коннекторов) — зелёный.
- Эталон перед мержем — `make test-ci`.

Повторить инвентарь: скрипт интроспекции (`inspect.unwrap` эндпоинта + обход `route.dependant` + развёртка `_IncludedRouter.effective_route_contexts()`) прогоняется по `uk_management_bot.api.main:app`, `access_control.app.main:create_app()`, `media_service app.main:app` и `resource-accounting app.main:app`. Для двух последних нужен venv с их `requirements.txt`.
