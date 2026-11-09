# Инвентарь маршрутов API (IDOR-ревью 2026-11-07)

Снято интроспекцией живых приложений (`app.routes` + дерево `dependant`, обёртки slowapi развёрнуты), снимок `origin/main` 95d652c9. Генератор и сырые JSON — вне репо; повторить: `docs/audit/idor-review-2026-11-07.md` §1.

Роли: M manager, A admin, E executor, AP applicant, I inspector, SA system_admin, SO security_operator, EN engineer, RME resource_meter_entry. `(approved)` — действие требует `status=approved`. Роли — дефолты каталога `authz/catalog.py`; админка ролей может их переопределить.

Класс (только для маршрутов с path-параметром): **a** — только персонал с доступом ко всему разделу, вертикальной проверки достаточно; **b** — открыт жителю/исполнителю/инспектору, нужна горизонтальная проверка; **c** — публичный с вложенными id; **d** — тикет/устройство/подпись; **s2s** — только сервисный ключ; **a·tenant** — ролевой доступ внутри тенанта.

## UK API (`uk_management_bot/api`, сервис `api`) — 240 маршрутов

| Метод | Путь | Path-параметры | Авторизация | Класс | Файл |
|---|---|---|---|---|---|
| GET | `/api/health` | — | **без auth** (публичный по замыслу) | — | `uk_management_bot/api/routes/health.py:52` |
| GET | `/api/health/outbox` | — | `require_health_token` | — | `uk_management_bot/api/routes/health.py:127` |
| GET | `/api/health/ratelimit` | — | `require_health_token` | — | `uk_management_bot/api/routes/health.py:59` |
| POST | `/api/v2/addresses/account-owners/import` | — | `require_action(addresses.manage)` → M | — | `uk_management_bot/api/addresses/account_owners.py:28` |
| GET | `/api/v2/addresses/account-owners/summary` | — | `require_action(addresses.manage)` → M | — | `uk_management_bot/api/addresses/account_owners.py:20` |
| POST | `/api/v2/addresses/apartments` | — | `require_action(addresses.manage)` → M | — | `uk_management_bot/api/addresses/apartments.py:57` |
| GET | `/api/v2/addresses/apartments/all` | — | `require_action(addresses.manage)` → M | — | `uk_management_bot/api/addresses/apartments.py:152` |
| POST | `/api/v2/addresses/apartments/bulk` | — | `require_action(addresses.manage)` → M | — | `uk_management_bot/api/addresses/apartments.py:84` |
| DELETE | `/api/v2/addresses/apartments/{apartment_id}` | apartment_id | `require_action(addresses.manage)` → M | a | `uk_management_bot/api/addresses/apartments.py:121` |
| GET | `/api/v2/addresses/apartments/{apartment_id}` | apartment_id | `require_action(addresses.manage)` → M | a | `uk_management_bot/api/addresses/apartments.py:174` |
| PATCH | `/api/v2/addresses/apartments/{apartment_id}` | apartment_id | `require_action(addresses.manage)` → M | a | `uk_management_bot/api/addresses/apartments.py:99` |
| DELETE | `/api/v2/addresses/apartments/{apartment_id}/purge` | apartment_id | `require_action(addresses.manage)` → M | a | `uk_management_bot/api/addresses/apartments.py:131` |
| GET | `/api/v2/addresses/buildings` | — | `require_action(addresses.manage)` → M | — | `uk_management_bot/api/addresses/buildings.py:21` |
| POST | `/api/v2/addresses/buildings` | — | `require_action(addresses.manage)` → M | — | `uk_management_bot/api/addresses/buildings.py:66` |
| DELETE | `/api/v2/addresses/buildings/{building_id}` | building_id | `require_action(addresses.manage)` → M | a | `uk_management_bot/api/addresses/buildings.py:102` |
| PATCH | `/api/v2/addresses/buildings/{building_id}` | building_id | `require_action(addresses.manage)` → M | a | `uk_management_bot/api/addresses/buildings.py:87` |
| GET | `/api/v2/addresses/buildings/{building_id}/apartments` | building_id | `require_action(addresses.manage)` → M | a | `uk_management_bot/api/addresses/apartments.py:30` |
| DELETE | `/api/v2/addresses/buildings/{building_id}/purge` | building_id | `require_action(addresses.manage)` → M | a | `uk_management_bot/api/addresses/buildings.py:112` |
| GET | `/api/v2/addresses/moderation` | — | `require_action(addresses.manage)` → M | — | `uk_management_bot/api/addresses/moderation.py:19` |
| POST | `/api/v2/addresses/moderation/{item_id}/approve` | item_id | `require_action(addresses.manage)` → M | a | `uk_management_bot/api/addresses/moderation.py:73` |
| POST | `/api/v2/addresses/moderation/{item_id}/reject` | item_id | `require_action(addresses.manage)` → M | a | `uk_management_bot/api/addresses/moderation.py:86` |
| GET | `/api/v2/addresses/stats` | — | `require_action(addresses.manage)` → M | — | `uk_management_bot/api/addresses/stats.py:17` |
| GET | `/api/v2/addresses/yards` | — | `require_action(addresses.read)` → I,M (approved) | — | `uk_management_bot/api/addresses/yards.py:19` |
| POST | `/api/v2/addresses/yards` | — | `require_action(addresses.manage)` → M | — | `uk_management_bot/api/addresses/yards.py:37` |
| DELETE | `/api/v2/addresses/yards/{yard_id}` | yard_id | `require_action(addresses.manage)` → M | a | `uk_management_bot/api/addresses/yards.py:66` |
| PATCH | `/api/v2/addresses/yards/{yard_id}` | yard_id | `require_action(addresses.manage)` → M | a | `uk_management_bot/api/addresses/yards.py:54` |
| GET | `/api/v2/addresses/yards/{yard_id}/buildings` | yard_id | `require_action(addresses.read)` → I,M (approved) | a | `uk_management_bot/api/addresses/buildings.py:37` |
| DELETE | `/api/v2/addresses/yards/{yard_id}/purge` | yard_id | `require_action(addresses.manage)` → M | a | `uk_management_bot/api/addresses/yards.py:76` |
| GET | `/api/v2/announcements` | — | **без auth** (публичный по замыслу) | — | `uk_management_bot/api/routes/announcements.py:21` |
| POST | `/api/v2/auth/login` | — | `auth_ratelimit_guard` | — | `uk_management_bot/api/auth/router.py:159` |
| POST | `/api/v2/auth/login/resend-otp` | — | `auth_ratelimit_guard` | — | `uk_management_bot/api/auth/router.py:228` |
| POST | `/api/v2/auth/login/verify-otp` | — | `auth_ratelimit_guard` | — | `uk_management_bot/api/auth/router.py:195` |
| POST | `/api/v2/auth/logout` | — | `auth_ratelimit_guard` | — | `uk_management_bot/api/auth/router.py:298` |
| POST | `/api/v2/auth/refresh` | — | `auth_ratelimit_guard` | — | `uk_management_bot/api/auth/router.py:245` |
| POST | `/api/v2/auth/set-password` | — | `auth_ratelimit_guard`; `get_current_user` | — | `uk_management_bot/api/auth/router.py:320` |
| POST | `/api/v2/auth/telegram-widget` | — | `auth_ratelimit_guard` | — | `uk_management_bot/api/auth/router.py:95` |
| POST | `/api/v2/auth/twa` | — | `auth_ratelimit_guard` | — | `uk_management_bot/api/auth/router.py:128` |
| GET | `/api/v2/auto-manager-config` | — | `require_action(auto_manager.configure)` → A,M | — | `uk_management_bot/api/auto_manager/router.py:51` |
| PUT | `/api/v2/auto-manager-config` | — | `require_action(auto_manager.configure)` → A,M | — | `uk_management_bot/api/auto_manager/router.py:64` |
| POST | `/api/v2/auto-manager-config/ai-breaker/reset` | — | `require_action(auto_manager.configure)` → A,M | — | `uk_management_bot/api/auto_manager/router.py:83` |
| PUT | `/api/v2/board-config` | — | `require_action(board.configure)` → M | — | `uk_management_bot/api/board_config/router.py:49` |
| POST | `/api/v2/callcenter/requests` | — | `require_action(callcenter.use)` → M | — | `uk_management_bot/api/callcenter/router.py:41` |
| GET | `/api/v2/callcenter/search-resident` | — | `require_action(callcenter.use)` → M | — | `uk_management_bot/api/callcenter/router.py:21` |
| GET | `/api/v2/elevators` | — | `_require_elevators_enabled`; `require_action(elevators.read)` → EN,E,M (approved) | — | `uk_management_bot/api/elevators/router.py:75` |
| POST | `/api/v2/elevators` | — | `_require_elevators_enabled`; `require_action(elevators.manage)` → EN,M (approved) | — | `uk_management_bot/api/elevators/router.py:101` |
| GET | `/api/v2/elevators/config` | — | `_require_elevators_enabled`; `require_action(elevators.manage)` → EN,M (approved) | — | `uk_management_bot/api/elevators/router.py:124` |
| PUT | `/api/v2/elevators/config` | — | `_require_elevators_enabled`; `require_action(elevators.manage)` → EN,M (approved) | — | `uk_management_bot/api/elevators/router.py:132` |
| GET | `/api/v2/elevators/for-building/{building_id}` | building_id | `_require_elevators_enabled`; `require_action(elevators.lookup)` → AP,EN,E,I,M (approved) | b | `uk_management_bot/api/elevators/router.py:149` |
| GET | `/api/v2/elevators/occurrences` | — | `_require_elevators_enabled`; `require_action(elevators.read)` → EN,E,M (approved) | — | `uk_management_bot/api/elevators/router_calendar.py:40` |
| PATCH | `/api/v2/elevators/occurrences/{occurrence_id}` | occurrence_id | `_require_elevators_enabled`; `require_action(elevators.manage)` → EN,M (approved) | a | `uk_management_bot/api/elevators/router_calendar.py:60` |
| POST | `/api/v2/elevators/occurrences/{occurrence_id}/cancel` | occurrence_id | `_require_elevators_enabled`; `require_action(elevators.manage)` → EN,M (approved) | a | `uk_management_bot/api/elevators/router_calendar.py:76` |
| POST | `/api/v2/elevators/occurrences/{occurrence_id}/complete` | occurrence_id | `_require_elevators_enabled`; `require_action(elevators.read)` → EN,E,M (approved) | a | `uk_management_bot/api/elevators/router_calendar.py:89` |
| POST | `/api/v2/elevators/requests/bulk-confirm` | — | `_require_elevators_enabled`; `require_action(elevators.manage)` → EN,M (approved) | — | `uk_management_bot/api/elevators/router.py:162` |
| GET | `/api/v2/elevators/summary` | — | `_require_elevators_enabled`; `require_action(elevators.read)` → EN,E,M (approved) | — | `uk_management_bot/api/elevators/router.py:116` |
| GET | `/api/v2/elevators/{elevator_id}` | elevator_id | `_require_elevators_enabled`; `require_action(elevators.read)` → EN,E,M (approved) | a | `uk_management_bot/api/elevators/router.py:206` |
| PATCH | `/api/v2/elevators/{elevator_id}` | elevator_id | `_require_elevators_enabled`; `require_action(elevators.manage)` → EN,M (approved) | a | `uk_management_bot/api/elevators/router.py:219` |
| POST | `/api/v2/elevators/{elevator_id}/archive` | elevator_id | `_require_elevators_enabled`; `require_action(elevators.manage)` → EN,M (approved) | a | `uk_management_bot/api/elevators/router.py:255` |
| POST | `/api/v2/elevators/{elevator_id}/commission` | elevator_id | `_require_elevators_enabled`; `require_action(elevators.manage)` → EN,M (approved) | a | `uk_management_bot/api/elevators/router.py:238` |
| GET | `/api/v2/elevators/{elevator_id}/events` | elevator_id | `_require_elevators_enabled`; `require_action(elevators.read)` → EN,E,M (approved) | a | `uk_management_bot/api/elevators/router.py:293` |
| GET | `/api/v2/elevators/{elevator_id}/occurrences` | elevator_id | `_require_elevators_enabled`; `require_action(elevators.read)` → EN,E,M (approved) | a | `uk_management_bot/api/elevators/router_calendar.py:108` |
| POST | `/api/v2/elevators/{elevator_id}/occurrences` | elevator_id | `_require_elevators_enabled`; `require_action(elevators.manage)` → EN,M (approved) | a | `uk_management_bot/api/elevators/router_calendar.py:129` |
| POST | `/api/v2/elevators/{elevator_id}/occurrences/generate` | elevator_id | `_require_elevators_enabled`; `require_action(elevators.manage)` → EN,M (approved) | a | `uk_management_bot/api/elevators/router_calendar.py:145` |
| GET | `/api/v2/elevators/{elevator_id}/requests` | elevator_id | `_require_elevators_enabled`; `require_action(elevators.read)` → EN,E,M (approved) | a | `uk_management_bot/api/elevators/router.py:307` |
| PUT | `/api/v2/elevators/{elevator_id}/status` | elevator_id | `_require_elevators_enabled`; `require_action(elevators.read)` → EN,E,M (approved) | a | `uk_management_bot/api/elevators/router.py:271` |
| GET | `/api/v2/executor/shifts/current` | — | `require_action(shifts.own)` → E | — | `uk_management_bot/api/shifts/executor_router.py:103` |
| GET | `/api/v2/executor/shifts/me` | — | `require_action(shifts.own)` → E | — | `uk_management_bot/api/shifts/executor_router.py:128` |
| POST | `/api/v2/executor/shifts/start` | — | `require_action(shifts.own)` → E | — | `uk_management_bot/api/shifts/executor_router.py:145` |
| GET | `/api/v2/executor/shifts/transfers` | — | `require_action(shifts.own)` → E | — | `uk_management_bot/api/shifts/executor_router.py:299` |
| POST | `/api/v2/executor/shifts/transfers` | — | `require_action(shifts.own)` → E | — | `uk_management_bot/api/shifts/executor_router.py:314` |
| POST | `/api/v2/executor/shifts/transfers/{transfer_id}/respond` | transfer_id | `require_action(shifts.own)` → E | b | `uk_management_bot/api/shifts/executor_router.py:351` |
| POST | `/api/v2/executor/shifts/{shift_id}/end` | shift_id | `require_action(shifts.own)` → E | b | `uk_management_bot/api/shifts/executor_router.py:164` |
| GET | `/api/v2/feedback` | — | `require_action(feedback.manage)` → M | — | `uk_management_bot/api/feedback/router.py:197` |
| POST | `/api/v2/feedback` | — | `get_current_user` | — | `uk_management_bot/api/feedback/router.py:108` |
| GET | `/api/v2/feedback/{fid}` | fid | `require_action(feedback.manage)` → M | a | `uk_management_bot/api/feedback/router.py:243` |
| PATCH | `/api/v2/feedback/{fid}` | fid | `require_action(feedback.manage)` → M | a | `uk_management_bot/api/feedback/router.py:254` |
| GET | `/api/v2/feedback/{fid}/media/{media_id}/file` | fid, media_id | `require_action(feedback.manage)` → M | a | `uk_management_bot/api/feedback/router.py:298` |
| GET | `/api/v2/materials` | — | `require_action(materials.manage)` → M,SA (approved) | — | `uk_management_bot/api/materials/router.py:85` |
| POST | `/api/v2/materials` | — | `require_action(materials.manage)` → M,SA (approved) | — | `uk_management_bot/api/materials/router.py:99` |
| POST | `/api/v2/materials/adjustments` | — | `require_action(materials.manage)` → M,SA (approved) | — | `uk_management_bot/api/materials/router.py:162` |
| GET | `/api/v2/materials/by-request/{request_number}` | request_number | `require_action(materials.manage)` → M,SA (approved) | a | `uk_management_bot/api/materials/router.py:254` |
| POST | `/api/v2/materials/issues` | — | `require_action(materials.manage)` → M,SA (approved) | — | `uk_management_bot/api/materials/router.py:145` |
| GET | `/api/v2/materials/operations` | — | `require_action(materials.manage)` → M,SA (approved) | — | `uk_management_bot/api/materials/router.py:183` |
| GET | `/api/v2/materials/operations/export` | — | `require_action(materials.manage)` → M,SA (approved) | — | `uk_management_bot/api/materials/router.py:211` |
| GET | `/api/v2/materials/procurement` | — | `require_action(materials.manage)` → M,SA (approved) | — | `uk_management_bot/api/materials/router.py:263` |
| GET | `/api/v2/materials/procurement/export` | — | `require_action(materials.manage)` → M,SA (approved) | — | `uk_management_bot/api/materials/router.py:274` |
| POST | `/api/v2/materials/receipts` | — | `require_action(materials.manage)` → M,SA (approved) | — | `uk_management_bot/api/materials/router.py:127` |
| GET | `/api/v2/materials/stock` | — | `require_action(materials.manage)` → M,SA (approved) | — | `uk_management_bot/api/materials/router.py:117` |
| PATCH | `/api/v2/materials/{material_id}` | material_id | `require_action(materials.manage)` → M,SA (approved) | a | `uk_management_bot/api/materials/router.py:300` |
| GET | `/api/v2/media/request/{request_number}` | request_number | `get_current_user` | b | `uk_management_bot/api/routes/media_proxy.py:318` |
| POST | `/api/v2/media/upload` | — | `get_current_user` | — | `uk_management_bot/api/routes/media_proxy.py:134` |
| GET | `/api/v2/media/{media_id}/file` | media_id | `get_current_user` | b | `uk_management_bot/api/routes/media_proxy.py:359` |
| GET | `/api/v2/monitored-groups` | — | `require_action(group_intake.manage)` → M | — | `uk_management_bot/api/group_intake/router.py:34` |
| POST | `/api/v2/monitored-groups` | — | `require_action(group_intake.manage)` → M | — | `uk_management_bot/api/group_intake/router.py:52` |
| DELETE | `/api/v2/monitored-groups/{group_id}` | group_id | `require_action(group_intake.manage)` → M | a | `uk_management_bot/api/group_intake/router.py:136` |
| PATCH | `/api/v2/monitored-groups/{group_id}` | group_id | `require_action(group_intake.manage)` → M | a | `uk_management_bot/api/group_intake/router.py:92` |
| GET | `/api/v2/news-watch/config` | — | `_require_enabled`; `require_action(board.configure)` → M | — | `uk_management_bot/api/news_watch/router.py:60` |
| PUT | `/api/v2/news-watch/config` | — | `_require_enabled`; `require_action(board.configure)` → M | — | `uk_management_bot/api/news_watch/router.py:65` |
| POST | `/api/v2/news-watch/inbox` | — | `_require_enabled`; `_require_service_token` | — | `uk_management_bot/api/news_watch/router.py:128` |
| GET | `/api/v2/news-watch/items` | — | `_require_enabled`; `require_action(board.configure)` → M | — | `uk_management_bot/api/news_watch/router.py:79` |
| POST | `/api/v2/news-watch/items/{item_id}/publish` | item_id | `_require_enabled`; `require_action(board.configure)` → M | a | `uk_management_bot/api/news_watch/router.py:96` |
| POST | `/api/v2/news-watch/items/{item_id}/reject` | item_id | `_require_enabled`; `require_action(board.configure)` → M | a | `uk_management_bot/api/news_watch/router.py:106` |
| POST | `/api/v2/news-watch/items/{item_id}/retry-broadcast` | item_id | `_require_enabled`; `require_action(board.configure)` → M | a | `uk_management_bot/api/news_watch/router.py:116` |
| GET | `/api/v2/news-watch/sources` | — | `_require_enabled`; `_require_service_token` | — | `uk_management_bot/api/news_watch/router.py:143` |
| POST | `/api/v2/payment-control/account` | — | `require_action(payments.manage)` → A,M (approved) | — | `uk_management_bot/api/payment_control/router.py:84` |
| POST | `/api/v2/payment-control/accounts/balances` | — | `require_action(payments.manage)` → A,M (approved) | — | `uk_management_bot/api/payment_control/router.py:100` |
| GET | `/api/v2/payment-control/apartments/{apartment_id}` | apartment_id | `require_action(payments.manage)` → A,M (approved) | a | `uk_management_bot/api/payment_control/router.py:55` |
| GET | `/api/v2/payment-control/imports` | — | `require_action(payments.manage)` → A,M (approved) | — | `uk_management_bot/api/payment_control/router.py:107` |
| POST | `/api/v2/payment-control/imports/preview` | — | `require_action(payments.manage)` → A,M (approved) | — | `uk_management_bot/api/payment_control/router.py:112` |
| GET | `/api/v2/payment-control/imports/{batch_id}` | batch_id | `require_action(payments.manage)` → A,M (approved) | a | `uk_management_bot/api/payment_control/router.py:125` |
| POST | `/api/v2/payment-control/imports/{batch_id}/activate` | batch_id | `require_action(payments.manage)` → A,M (approved) | a | `uk_management_bot/api/payment_control/router.py:130` |
| POST | `/api/v2/payment-control/imports/{batch_id}/deactivate` | batch_id | `require_action(payments.manage)` → A,M (approved) | a | `uk_management_bot/api/payment_control/router.py:140` |
| GET | `/api/v2/profile` | — | `get_current_user` | — | `uk_management_bot/api/profile/router.py:78` |
| PATCH | `/api/v2/profile` | — | `get_current_user` | — | `uk_management_bot/api/profile/router.py:83` |
| GET | `/api/v2/profile/apartments` | — | `get_current_user` | — | `uk_management_bot/api/profile/router.py:154` |
| GET | `/api/v2/profile/request-addresses` | — | `require_action(requests.create)` → AP (approved) | — | `uk_management_bot/api/profile/router.py:197` |
| PATCH | `/api/v2/profile/role` | — | `get_current_user` | — | `uk_management_bot/api/profile/router.py:128` |
| GET | `/api/v2/public/board` | — | **без auth** (публичный по замыслу) | — | `uk_management_bot/api/public/router.py:79` |
| GET | `/api/v2/public/board-config` | — | **без auth** (публичный по замыслу) | — | `uk_management_bot/api/board_config/router.py:34` |
| GET | `/api/v2/public/elevators` | — | **без auth** (публичный по замыслу) | — | `uk_management_bot/api/elevators/public_router.py:214` |
| GET | `/api/v2/public/work-reports` | — | **без auth** (публичный по замыслу) | — | `uk_management_bot/api/work_reports/public_router.py:109` |
| GET | `/api/v2/public/work-reports/{report_id}` | report_id | **без auth** (публичный по замыслу) | c | `uk_management_bot/api/work_reports/public_router.py:195` |
| GET | `/api/v2/public/work-reports/{report_id}/media/{media_id}` | report_id, media_id | **без auth** (публичный по замыслу) | c | `uk_management_bot/api/work_reports/public_router.py:245` |
| POST | `/api/v2/registration/applicant` | — | `auth_ratelimit_guard`; `require_registration_ticket` | — | `uk_management_bot/api/registration/router.py:156` |
| GET | `/api/v2/registration/buildings/{building_id}/apartments` | building_id | `auth_ratelimit_guard`; `require_registration_ticket` | d | `uk_management_bot/api/registration/router.py:142` |
| GET | `/api/v2/registration/contact-status` | — | `auth_ratelimit_guard`; `require_registration_ticket` | — | `uk_management_bot/api/registration/router.py:105` |
| POST | `/api/v2/registration/start` | — | `auth_ratelimit_guard` | — | `uk_management_bot/api/registration/router.py:69` |
| GET | `/api/v2/registration/yards` | — | `auth_ratelimit_guard`; `require_registration_ticket` | — | `uk_management_bot/api/registration/router.py:118` |
| GET | `/api/v2/registration/yards/{yard_id}/buildings` | yard_id | `auth_ratelimit_guard`; `require_registration_ticket` | d | `uk_management_bot/api/registration/router.py:128` |
| GET | `/api/v2/requests` | — | `get_current_user` | — | `uk_management_bot/api/requests/router.py:242` |
| POST | `/api/v2/requests` | — | `require_action(requests.create)` → AP (approved) | — | `uk_management_bot/api/requests/router.py:322` |
| GET | `/api/v2/requests/acceptance` | — | `get_current_user` | — | `uk_management_bot/api/requests/router.py:289` |
| POST | `/api/v2/requests/inspector` | — | `require_action(requests.create_inspection)` → I (approved) | — | `uk_management_bot/api/requests/router.py:365` |
| GET | `/api/v2/requests/kanban` | — | `require_action(requests.read_all)` → EN,M | — | `uk_management_bot/api/requests/router.py:181` |
| GET | `/api/v2/requests/pool` | — | `require_action(requests.execute)` → E | — | `uk_management_bot/api/requests/pool_router.py:68` |
| GET | `/api/v2/requests/stats` | — | `get_period`; `require_action(requests.stats)` → EN,M | — | `uk_management_bot/api/requests/stats_router.py:98` |
| GET | `/api/v2/requests/stats/addresses` | — | `get_period`; `require_action(requests.stats)` → EN,M | — | `uk_management_bot/api/requests/stats_router.py:348` |
| GET | `/api/v2/requests/stats/backlog` | — | `require_action(requests.stats)` → EN,M | — | `uk_management_bot/api/requests/stats_router.py:319` |
| GET | `/api/v2/requests/stats/channels` | — | `get_period`; `require_action(requests.stats)` → EN,M | — | `uk_management_bot/api/requests/stats_router.py:372` |
| GET | `/api/v2/requests/stats/costs` | — | `get_period`; `require_action(requests.stats)` → EN,M | — | `uk_management_bot/api/requests/stats_router.py:401` |
| GET | `/api/v2/requests/stats/executors` | — | `get_period`; `require_action(requests.stats)` → EN,M | — | `uk_management_bot/api/requests/stats_router.py:139` |
| GET | `/api/v2/requests/stats/export` | — | `get_period`; `require_action(requests.stats)` → EN,M | — | `uk_management_bot/api/requests/stats_router.py:149` |
| GET | `/api/v2/requests/stats/export/executors` | — | `get_period`; `require_action(requests.stats)` → EN,M | — | `uk_management_bot/api/requests/stats_router.py:164` |
| GET | `/api/v2/requests/stats/quality` | — | `get_period`; `require_action(requests.stats)` → EN,M | — | `uk_management_bot/api/requests/stats_router.py:281` |
| POST | `/api/v2/requests/stats/report` | — | `get_period`; `require_action(requests.stats)` → EN,M | — | `uk_management_bot/api/requests/stats_router.py:191` |
| GET | `/api/v2/requests/stats/report/requests` | — | `get_period`; `require_action(requests.stats)` → EN,M | — | `uk_management_bot/api/requests/stats_router.py:232` |
| GET | `/api/v2/requests/{request_number}` | request_number | `get_current_user` | b | `uk_management_bot/api/requests/router.py:299` |
| PATCH | `/api/v2/requests/{request_number}` | request_number | `require_action(requests.update)` → AP,E,M | b | `uk_management_bot/api/requests/router.py:537` |
| POST | `/api/v2/requests/{request_number}/before-photo` | request_number | `require_action(requests.execute)` → E | b | `uk_management_bot/api/requests/executor_actions.py:103` |
| PATCH | `/api/v2/requests/{request_number}/category` | request_number | `require_action(requests.manage)` → M | a | `uk_management_bot/api/requests/router.py:475` |
| POST | `/api/v2/requests/{request_number}/claim` | request_number | `require_action(requests.execute)` → E | b | `uk_management_bot/api/requests/router.py:782` |
| GET | `/api/v2/requests/{request_number}/comments` | request_number | `get_current_user` | b | `uk_management_bot/api/requests/router.py:853` |
| POST | `/api/v2/requests/{request_number}/comments` | request_number | `get_current_user` | b | `uk_management_bot/api/requests/router.py:876` |
| POST | `/api/v2/requests/{request_number}/complete` | request_number | `require_action(requests.execute)` → E | b | `uk_management_bot/api/requests/executor_actions.py:56` |
| GET | `/api/v2/requests/{request_number}/handover-candidates` | request_number | `require_action(requests.engineering)` → EN | a | `uk_management_bot/api/requests/handover.py:36` |
| POST | `/api/v2/requests/{request_number}/problem` | request_number | `require_action(requests.execute)` → E | b | `uk_management_bot/api/requests/executor_actions.py:133` |
| POST | `/api/v2/requests/{request_number}/remind-applicant` | request_number | `require_action(requests.manage)` → M | a | `uk_management_bot/api/requests/router.py:904` |
| GET | `/api/v2/residents` | — | `require_action(residents.manage)` → M | — | `uk_management_bot/api/residents/residents.py:57` |
| GET | `/api/v2/residents/stats` | — | `require_action(residents.manage)` → M | — | `uk_management_bot/api/residents/residents.py:111` |
| GET | `/api/v2/residents/{resident_id}` | resident_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/residents.py:121` |
| POST | `/api/v2/residents/{resident_id}/apartments` | resident_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/moderation.py:207` |
| DELETE | `/api/v2/residents/{resident_id}/apartments/{ua_id}` | resident_id, ua_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/moderation.py:292` |
| PATCH | `/api/v2/residents/{resident_id}/apartments/{ua_id}` | resident_id, ua_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/moderation.py:275` |
| POST | `/api/v2/residents/{resident_id}/apartments/{ua_id}/approve` | resident_id, ua_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/moderation.py:229` |
| POST | `/api/v2/residents/{resident_id}/apartments/{ua_id}/reject` | resident_id, ua_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/moderation.py:251` |
| POST | `/api/v2/residents/{resident_id}/approve` | resident_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/moderation.py:80` |
| POST | `/api/v2/residents/{resident_id}/block` | resident_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/moderation.py:96` |
| GET | `/api/v2/residents/{resident_id}/documents` | resident_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/documents.py:88` |
| GET | `/api/v2/residents/{resident_id}/documents/{doc_id}/file` | resident_id, doc_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/documents.py:129` |
| PATCH | `/api/v2/residents/{resident_id}/name` | resident_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/moderation.py:125` |
| POST | `/api/v2/residents/{resident_id}/request-phone` | resident_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/moderation.py:154` |
| POST | `/api/v2/residents/{resident_id}/send-registration-video` | resident_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/moderation.py:178` |
| POST | `/api/v2/residents/{resident_id}/unblock` | resident_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/moderation.py:113` |
| POST | `/api/v2/residents/{resident_id}/verification/approve` | resident_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/verification.py:57` |
| POST | `/api/v2/residents/{resident_id}/verification/reject` | resident_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/verification.py:85` |
| POST | `/api/v2/residents/{resident_id}/verification/request-documents` | resident_id | `require_action(residents.manage)` → M | a | `uk_management_bot/api/residents/verification.py:38` |
| POST | `/api/v2/resource-accounting/ticket` | — | `require_action(resources.launch)` → A,M,SA | — | `uk_management_bot/api/resource_accounting/router.py:107` |
| POST | `/api/v2/resource-accounting/twa-ticket` | — | в хендлере: `initData` (HMAC bot-token, `auth_date` ≤ 300 с) + `status=approved` + `resources.meter_entry` | — | `uk_management_bot/api/resource_accounting/router.py:117` |
| GET | `/api/v2/shifts` | — | `require_action(shifts.manage)` → M | — | `uk_management_bot/api/shifts/router/shifts_read.py:26` |
| POST | `/api/v2/shifts` | — | `require_action(shifts.manage)` → M | — | `uk_management_bot/api/shifts/router/shift_crud.py:42` |
| GET | `/api/v2/shifts/employees` | — | `require_action(staff.manage)` → M | — | `uk_management_bot/api/shifts/router/employees.py:67` |
| POST | `/api/v2/shifts/employees/invite` | — | `require_action(staff.manage)` → M | — | `uk_management_bot/api/shifts/router/employees.py:138` |
| GET | `/api/v2/shifts/employees/pending` | — | `require_action(staff.manage)` → M | — | `uk_management_bot/api/shifts/router/employees.py:120` |
| GET | `/api/v2/shifts/employees/rbac/catalog` | — | `require_action(rbac.view)` → M | — | `uk_management_bot/api/rbac/router.py:39` |
| GET | `/api/v2/shifts/employees/rbac/roles` | — | `require_action(rbac.view)` → M | — | `uk_management_bot/api/rbac/router.py:50` |
| POST | `/api/v2/shifts/employees/rbac/roles` | — | `require_action(rbac.manage)` → суперадмин | — | `uk_management_bot/api/rbac/router.py:69` |
| DELETE | `/api/v2/shifts/employees/rbac/roles/{key}` | key | `require_action(rbac.manage)` → суперадмин | a | `uk_management_bot/api/rbac/router.py:132` |
| PUT | `/api/v2/shifts/employees/rbac/roles/{key}` | key | `require_action(rbac.manage)` → суперадмин | a | `uk_management_bot/api/rbac/router.py:89` |
| POST | `/api/v2/shifts/employees/rbac/roles/{key}/reset` | key | `require_action(rbac.manage)` → суперадмин | a | `uk_management_bot/api/rbac/router.py:116` |
| GET | `/api/v2/shifts/employees/{user_id}` | user_id | `require_action(staff.manage)` → M | a | `uk_management_bot/api/shifts/router/employees.py:519` |
| PATCH | `/api/v2/shifts/employees/{user_id}/activate` | user_id | `require_action(staff.manage)` → M | a | `uk_management_bot/api/shifts/router/employees.py:292` |
| GET | `/api/v2/shifts/employees/{user_id}/active-requests-count` | user_id | `require_action(staff.manage)` → M | a | `uk_management_bot/api/shifts/router/employees.py:455` |
| PATCH | `/api/v2/shifts/employees/{user_id}/approve` | user_id | `require_action(staff.manage)` → M | a | `uk_management_bot/api/shifts/router/employees.py:228` |
| PATCH | `/api/v2/shifts/employees/{user_id}/block` | user_id | `require_action(staff.manage)` → M | a | `uk_management_bot/api/shifts/router/employees.py:263` |
| PATCH | `/api/v2/shifts/employees/{user_id}/decline` | user_id | `require_action(staff.manage)` → M | a | `uk_management_bot/api/shifts/router/employees.py:329` |
| PATCH | `/api/v2/shifts/employees/{user_id}/delete` | user_id | `require_action(staff.manage)` → M | a | `uk_management_bot/api/shifts/router/employees.py:466` |
| PATCH | `/api/v2/shifts/employees/{user_id}/language` | user_id | `require_action(staff.manage)` → M | a | `uk_management_bot/api/shifts/router/employees.py:418` |
| PATCH | `/api/v2/shifts/employees/{user_id}/meter-entry` | user_id | `require_action(staff.manage)` → M | a | `uk_management_bot/api/shifts/router/employees.py:363` |
| PATCH | `/api/v2/shifts/employees/{user_id}/name` | user_id | `require_action(staff.manage)` → M | a | `uk_management_bot/api/shifts/router/employees.py:343` |
| PATCH | `/api/v2/shifts/employees/{user_id}/reject` | user_id | `require_action(staff.manage)` → M | a | `uk_management_bot/api/shifts/router/employees.py:250` |
| POST | `/api/v2/shifts/employees/{user_id}/request-phone` | user_id | `require_action(staff.manage)` → M | a | `uk_management_bot/api/shifts/router/employees.py:438` |
| GET | `/api/v2/shifts/employees/{user_id}/roles` | user_id | `require_action(rbac.view)` → M | a | `uk_management_bot/api/rbac/router.py:150` |
| PUT | `/api/v2/shifts/employees/{user_id}/roles` | user_id | `require_action(rbac.manage)` → суперадмин | a | `uk_management_bot/api/rbac/router.py:164` |
| PATCH | `/api/v2/shifts/employees/{user_id}/simple-mode` | user_id | `require_action(staff.manage)` → M | a | `uk_management_bot/api/shifts/router/employees.py:396` |
| PATCH | `/api/v2/shifts/employees/{user_id}/unblock` | user_id | `require_action(staff.manage)` → M | a | `uk_management_bot/api/shifts/router/employees.py:276` |
| POST | `/api/v2/shifts/from-template` | — | `require_action(shifts.manage)` → M | — | `uk_management_bot/api/shifts/router/templates.py:83` |
| GET | `/api/v2/shifts/schedule` | — | `require_action(shifts.manage)` → M | — | `uk_management_bot/api/shifts/router/shifts_read.py:51` |
| GET | `/api/v2/shifts/stats` | — | `require_action(shifts.manage)` → M | — | `uk_management_bot/api/shifts/router/shifts_read.py:66` |
| GET | `/api/v2/shifts/templates` | — | `require_action(shifts.manage)` → M | — | `uk_management_bot/api/shifts/router/templates.py:21` |
| POST | `/api/v2/shifts/templates` | — | `require_action(shifts.manage)` → M | — | `uk_management_bot/api/shifts/router/templates.py:44` |
| DELETE | `/api/v2/shifts/templates/{template_id}` | template_id | `require_action(shifts.manage)` → M | a | `uk_management_bot/api/shifts/router/templates.py:70` |
| GET | `/api/v2/shifts/templates/{template_id}` | template_id | `require_action(shifts.manage)` → M | a | `uk_management_bot/api/shifts/router/templates.py:32` |
| PATCH | `/api/v2/shifts/templates/{template_id}` | template_id | `require_action(shifts.manage)` → M | a | `uk_management_bot/api/shifts/router/templates.py:54` |
| GET | `/api/v2/shifts/transfers` | — | `require_action(shifts.manage)` → M | — | `uk_management_bot/api/shifts/router/shifts_read.py:108` |
| POST | `/api/v2/shifts/transfers/{transfer_id}/handle` | transfer_id | `require_action(shifts.manage)` → M | a | `uk_management_bot/api/shifts/router/transfers.py:43` |
| DELETE | `/api/v2/shifts/{shift_id}` | shift_id | `require_action(shifts.manage)` → M | a | `uk_management_bot/api/shifts/router/shift_crud.py:205` |
| GET | `/api/v2/shifts/{shift_id}` | shift_id | `require_action(shifts.manage)` → M | a | `uk_management_bot/api/shifts/router/shift_crud.py:25` |
| PATCH | `/api/v2/shifts/{shift_id}` | shift_id | `require_action(shifts.manage)` → M | a | `uk_management_bot/api/shifts/router/shift_crud.py:81` |
| POST | `/api/v2/shifts/{shift_id}/end` | shift_id | `require_action(shifts.manage)` → M | a | `uk_management_bot/api/shifts/router/shift_crud.py:225` |
| POST | `/api/v2/shifts/{shift_id}/reassign` | shift_id | `require_action(shifts.manage)` → M | a | `uk_management_bot/api/shifts/router/shift_crud.py:171` |
| POST | `/api/v2/webhooks/infrasafe/alert` | — | в хендлере: HMAC-подпись тела (`webhooks/security.verify_signature`) | — | `uk_management_bot/api/webhooks/router.py:38` |
| GET | `/api/v2/work-reports` | — | `_require_work_reports_enabled`; `require_action(work_reports.moderate)` → M (approved) | — | `uk_management_bot/api/work_reports/router.py:143` |
| POST | `/api/v2/work-reports` | — | `_require_work_reports_enabled`; `require_action(work_reports.moderate)` → M (approved) | — | `uk_management_bot/api/work_reports/router.py:250` |
| POST | `/api/v2/work-reports/autofill-pending` | — | `_require_work_reports_enabled`; `require_action(work_reports.moderate)` → M (approved) | — | `uk_management_bot/api/work_reports/router.py:294` |
| POST | `/api/v2/work-reports/reconcile` | — | `_require_work_reports_enabled`; `require_action(work_reports.moderate)` → M (approved) | — | `uk_management_bot/api/work_reports/router.py:369` |
| POST | `/api/v2/work-reports/reject-without-media` | — | `_require_work_reports_enabled`; `require_action(work_reports.moderate)` → M (approved) | — | `uk_management_bot/api/work_reports/router.py:383` |
| GET | `/api/v2/work-reports/settings` | — | `_require_work_reports_enabled`; `require_action(work_reports.moderate)` → M (approved) | — | `uk_management_bot/api/work_reports/router.py:333` |
| PUT | `/api/v2/work-reports/settings` | — | `_require_work_reports_enabled`; `require_action(work_reports.moderate)` → M (approved) | — | `uk_management_bot/api/work_reports/router.py:343` |
| POST | `/api/v2/work-reports/sync` | — | `_require_work_reports_enabled`; `require_action(work_reports.moderate)` → M (approved) | — | `uk_management_bot/api/work_reports/router.py:165` |
| PATCH | `/api/v2/work-reports/{report_id}` | report_id | `_require_work_reports_enabled`; `require_action(work_reports.moderate)` → M (approved) | a | `uk_management_bot/api/work_reports/router.py:433` |
| POST | `/api/v2/work-reports/{report_id}/autofill` | report_id | `_require_work_reports_enabled`; `require_action(work_reports.moderate)` → M (approved) | a | `uk_management_bot/api/work_reports/router.py:403` |
| POST | `/api/v2/work-reports/{report_id}/publish` | report_id | `_require_work_reports_enabled`; `require_action(work_reports.moderate)` → M (approved) | a | `uk_management_bot/api/work_reports/router.py:507` |
| POST | `/api/v2/work-reports/{report_id}/reject` | report_id | `_require_work_reports_enabled`; `require_action(work_reports.moderate)` → M (approved) | a | `uk_management_bot/api/work_reports/router.py:544` |
| POST | `/api/v2/work-reports/{report_id}/reopen` | report_id | `_require_work_reports_enabled`; `require_action(work_reports.moderate)` → M (approved) | a | `uk_management_bot/api/work_reports/router.py:560` |
| POST | `/api/v2/work-reports/{report_id}/unpublish` | report_id | `_require_work_reports_enabled`; `require_action(work_reports.moderate)` → M (approved) | a | `uk_management_bot/api/work_reports/router.py:522` |
| GET | `/health` | — | **без auth** (публичный по замыслу) | — | `uk_management_bot/api/routes/health.py:45` |
| GET | `/metrics` | — | `require_health_token` | — | `uk_management_bot/api/routes/health.py:137` |
| WS | `/ws/v2/apartments` | — | в хендлере: как `/ws/v2/kanban` | — | `uk_management_bot/api/ws/router.py:426` |
| WS | `/ws/v2/buildings` | — | в хендлере: как `/ws/v2/kanban` | — | `uk_management_bot/api/ws/router.py:421` |
| WS | `/ws/v2/kanban` | — | в хендлере: JWT (cookie/первое сообщение) + Origin + `dashboard.live` + перепроверка личности в БД | — | `uk_management_bot/api/ws/router.py:411` |
| WS | `/ws/v2/shifts` | — | в хендлере: как `/ws/v2/kanban` | — | `uk_management_bot/api/ws/router.py:416` |

## Access API (`access_control`, сервис `access-api`) — 67 маршрутов

| Метод | Путь | Path-параметры | Авторизация | Класс | Файл |
|---|---|---|---|---|---|
| GET | `/api/v1/access/admin/barriers` | — | `require_action(access.equipment.manage)` → SA (approved) | — | `access_control/api/equipment.py:532` |
| POST | `/api/v1/access/admin/barriers` | — | `require_action(access.equipment.manage)` → SA (approved) | — | `access_control/api/equipment.py:543` |
| PATCH | `/api/v1/access/admin/barriers/{barrier_id}` | barrier_id | `require_action(access.equipment.manage)` → SA (approved) | a | `access_control/api/equipment.py:564` |
| GET | `/api/v1/access/admin/cameras` | — | `require_action(access.equipment.manage)` → SA (approved) | — | `access_control/api/equipment.py:452` |
| POST | `/api/v1/access/admin/cameras` | — | `require_action(access.equipment.manage)` → SA (approved) | — | `access_control/api/equipment.py:463` |
| PATCH | `/api/v1/access/admin/cameras/{camera_id}` | camera_id | `require_action(access.equipment.manage)` → SA (approved) | a | `access_control/api/equipment.py:484` |
| GET | `/api/v1/access/admin/controllers` | — | `require_action(access.equipment.manage)` → SA (approved) | — | `access_control/api/equipment.py:613` |
| POST | `/api/v1/access/admin/controllers` | — | `require_action(access.equipment.manage)` → SA (approved) | — | `access_control/api/equipment.py:626` |
| PATCH | `/api/v1/access/admin/controllers/{controller_id}` | controller_id | `require_action(access.equipment.manage)` → SA (approved) | a | `access_control/api/equipment.py:654` |
| POST | `/api/v1/access/admin/controllers/{controller_id}/rotate-key` | controller_id | `require_action(access.equipment.manage)` → SA (approved) | a | `access_control/api/equipment.py:675` |
| POST | `/api/v1/access/admin/controllers/{controller_id}/test-event` | controller_id | `require_action(access.diagnostics)` → SA (approved) | a | `access_control/api/diagnostics.py:87` |
| GET | `/api/v1/access/admin/gates` | — | `require_action(access.zones.manage)` → M,SA (approved) | — | `access_control/api/equipment.py:371` |
| POST | `/api/v1/access/admin/gates` | — | `require_action(access.zones.manage)` → M,SA (approved) | — | `access_control/api/equipment.py:382` |
| PATCH | `/api/v1/access/admin/gates/{gate_id}` | gate_id | `require_action(access.zones.manage)` → M,SA (approved) | a | `access_control/api/equipment.py:402` |
| GET | `/api/v1/access/admin/presence` | — | `require_action(access.presence.read)` → M,SO,SA (approved) | — | `access_control/api/parking_admin.py:346` |
| GET | `/api/v1/access/admin/spot-assignments` | — | `require_action(access.zones.manage)` → M,SA (approved) | — | `access_control/api/parking_admin.py:256` |
| POST | `/api/v1/access/admin/spot-assignments` | — | `require_action(access.zones.manage)` → M,SA (approved) | — | `access_control/api/parking_admin.py:276` |
| PATCH | `/api/v1/access/admin/spot-assignments/{assignment_id}` | assignment_id | `require_action(access.zones.manage)` → M,SA (approved) | a | `access_control/api/parking_admin.py:300` |
| GET | `/api/v1/access/admin/spots` | — | `require_action(access.zones.manage)` → M,SA (approved) | — | `access_control/api/parking_admin.py:180` |
| POST | `/api/v1/access/admin/spots` | — | `require_action(access.zones.manage)` → M,SA (approved) | — | `access_control/api/parking_admin.py:197` |
| PATCH | `/api/v1/access/admin/spots/{spot_id}` | spot_id | `require_action(access.zones.manage)` → M,SA (approved) | a | `access_control/api/parking_admin.py:216` |
| GET | `/api/v1/access/admin/zones` | — | `require_action(access.zones.manage)` → M,SA (approved) | — | `access_control/api/equipment.py:270` |
| POST | `/api/v1/access/admin/zones` | — | `require_action(access.zones.manage)` → M,SA (approved) | — | `access_control/api/equipment.py:285` |
| PATCH | `/api/v1/access/admin/zones/{zone_id}` | zone_id | `require_action(access.zones.manage)` → M,SA (approved) | a | `access_control/api/equipment.py:305` |
| GET | `/api/v1/access/admin/zones/{zone_id}/occupancy` | zone_id | `require_action(access.zones.manage)` → M,SA (approved) | a | `access_control/api/parking_admin.py:322` |
| POST | `/api/v1/access/admin/zones/{zone_id}/yards` | zone_id | `require_action(access.zones.manage)` → M,SA (approved) | a | `access_control/api/equipment.py:330` |
| GET | `/api/v1/access/apartments/{apartment_id}/serving-zones` | apartment_id | `require_action(access.events.read)` → M,SO,SA (approved) | a | `access_control/api/registry.py:544` |
| POST | `/api/v1/access/barriers/{barrier_id}/manual-open` | barrier_id | `require_action(access.operator)` → M,SO,SA (approved) | a | `access_control/api/operator.py:216` |
| POST | `/api/v1/access/camera-events/anpr` | — | `authenticate_edge` | — | `access_control/api/camera_events.py:89` |
| GET | `/api/v1/access/edge/{controller_id}/access-snapshot` | controller_id | `authenticate_edge` | d | `access_control/api/edge.py:312` |
| POST | `/api/v1/access/edge/{controller_id}/camera-events/{event_id}/photos` | controller_id, event_id | `authenticate_edge`; `get_access_media_client` | d | `access_control/api/edge.py:182` |
| GET | `/api/v1/access/edge/{controller_id}/commands/next` | controller_id | `authenticate_edge` | d | `access_control/api/commands.py:317` |
| POST | `/api/v1/access/edge/{controller_id}/commands/{command_id}/ack` | controller_id, command_id | `authenticate_edge` | d | `access_control/api/commands.py:345` |
| POST | `/api/v1/access/edge/{controller_id}/heartbeat` | controller_id | `authenticate_edge` | d | `access_control/api/edge.py:63` |
| POST | `/api/v1/access/edge/{controller_id}/sync-events` | controller_id | `authenticate_edge` | d | `access_control/api/edge.py:118` |
| GET | `/api/v1/access/events` | — | `require_action(access.events.read)` → M,SO,SA (approved) | — | `access_control/api/registry.py:349` |
| GET | `/api/v1/access/events/{event_id}` | event_id | `require_action(access.events.read)` → M,SO,SA (approved) | a | `access_control/api/registry.py:431` |
| POST | `/api/v1/access/events/{event_id}/resolve` | event_id | `require_action(access.operator)` → M,SO,SA (approved) | a | `access_control/api/operator.py:165` |
| GET | `/api/v1/access/metrics` | — | `require_action(access.metrics.read)` → M,SA (approved) | — | `access_control/api/metrics.py:71` |
| POST | `/api/v1/access/my/entries/{decision_id}/confirm` | decision_id | `require_action(access.resident.self)` → AP (approved) | b | `access_control/api/resident.py:576` |
| GET | `/api/v1/access/my/events` | — | `require_action(access.resident.self)` → AP (approved) | — | `access_control/api/resident.py:359` |
| GET | `/api/v1/access/my/passes` | — | `require_action(access.resident.self)` → AP (approved) | — | `access_control/api/resident.py:321` |
| GET | `/api/v1/access/my/requests` | — | `require_action(access.resident.self)` → AP (approved) | — | `access_control/api/resident.py:340` |
| POST | `/api/v1/access/my/spot-assignments/{assignment_id}/toggle-limit` | assignment_id | `require_action(access.resident.self)` → AP (approved) | b | `access_control/api/resident.py:398` |
| GET | `/api/v1/access/my/spots` | — | `require_action(access.resident.self)` → AP (approved) | — | `access_control/api/resident.py:380` |
| GET | `/api/v1/access/my/vehicles` | — | `require_action(access.resident.self)` → AP (approved) | — | `access_control/api/resident.py:283` |
| GET | `/api/v1/access/passes` | — | `require_action(access.events.read)` → M,SO,SA (approved) | — | `access_control/api/registry.py:558` |
| POST | `/api/v1/access/passes` | — | `require_action(access.resident.self)` → AP (approved) | — | `access_control/api/resident.py:484` |
| POST | `/api/v1/access/passes/redeem-code` | — | `require_action(access.operator)` → M,SO,SA (approved) | — | `access_control/api/operator.py:320` |
| POST | `/api/v1/access/passes/taxi` | — | `require_action(access.management)` → M,SA (approved) | — | `access_control/api/management.py:322` |
| GET | `/api/v1/access/passes/{pass_id}` | pass_id | `require_action(access.events.read)` → M,SO,SA (approved) | a | `access_control/api/registry.py:577` |
| PATCH | `/api/v1/access/passes/{pass_id}` | pass_id | `require_action(access.management)` → M,SA (approved) | a | `access_control/api/management.py:346` |
| POST | `/api/v1/access/passes/{pass_id}/cancel` | pass_id | `require_action(access.resident.self)` → AP (approved) | b | `access_control/api/resident.py:542` |
| GET | `/api/v1/access/photos/{kind}/{event_id}` | kind, event_id | `get_access_media_client` | d | `access_control/api/registry.py:291` |
| POST | `/api/v1/access/presence/{session_id}/close` | session_id | `require_action(access.operator)` → M,SO,SA (approved) | a | `access_control/api/operator.py:287` |
| GET | `/api/v1/access/requests` | — | `require_action(access.registry.manage)` → M,SA (approved) | — | `access_control/api/registry.py:607` |
| POST | `/api/v1/access/requests` | — | `require_action(access.resident.self)` → AP (approved) | — | `access_control/api/resident.py:442` |
| GET | `/api/v1/access/requests/{request_id}` | request_id | `require_action(access.registry.manage)` → M,SA (approved) | a | `access_control/api/registry.py:628` |
| POST | `/api/v1/access/requests/{request_id}/review` | request_id | `require_action(access.management)` → M,SA (approved) | a | `access_control/api/management.py:371` |
| GET | `/api/v1/access/vehicles` | — | `require_action(access.registry.manage)` → M,SA (approved) | — | `access_control/api/registry.py:477` |
| POST | `/api/v1/access/vehicles` | — | `require_action(access.management)` → M,SA (approved) | — | `access_control/api/management.py:226` |
| GET | `/api/v1/access/vehicles/{vehicle_id}` | vehicle_id | `require_action(access.registry.manage)` → M,SA (approved) | a | `access_control/api/registry.py:516` |
| PATCH | `/api/v1/access/vehicles/{vehicle_id}` | vehicle_id | `require_action(access.management)` → M,SA (approved) | a | `access_control/api/management.py:285` |
| PATCH | `/api/v1/access/vehicles/{vehicle_id}/status` | vehicle_id | `require_action(access.management)` → M,SA (approved) | a | `access_control/api/management.py:260` |
| GET | `/health` | — | **без auth** (публичный по замыслу) | — | `access_control/api/health.py:13` |
| GET | `/metrics` | — | `require_metrics_token` | — | `access_control/api/metrics.py:61` |
| WS | `/ws/v1/access/security` | — | в хендлере: JWT + Origin + `access.live` + личность в БД (approved, не удалён) | — | `access_control/api/ws_security.py:173` |

## Media service (`media_service`, внутренний, `X-API-Key` middleware на всё, кроме health) — 29 маршрутов

| Метод | Путь | Path-параметры | Авторизация | Класс | Файл |
|---|---|---|---|---|---|
| GET | `/` | — | **без auth** | — | `media_service/app/main.py:246` |
| GET | `/api/v1/health` | — | **без auth** | — | `media_service/app/api/v1/health.py:19` |
| GET | `/api/v1/health/detailed` | — | `X-API-Key` (middleware) | — | `media_service/app/api/v1/health.py:37` |
| GET | `/api/v1/health/ready` | — | **без auth** | — | `media_service/app/api/v1/health.py:92` |
| GET | `/api/v1/media/maintenance/preview-cache` | — | `X-API-Key` (middleware) | — | `media_service/app/api/v1/media.py:563` |
| POST | `/api/v1/media/maintenance/resolve-stale-transitions` | — | `X-API-Key` (middleware); `get_storage_service` | — | `media_service/app/api/v1/media.py:576` |
| POST | `/api/v1/media/previews/warm` | — | `X-API-Key` (middleware); `get_storage_service` | — | `media_service/app/api/v1/media.py:508` |
| GET | `/api/v1/media/publication-locks` | — | `X-API-Key` (middleware); `get_storage_service` | — | `media_service/app/api/v1/media.py:487` |
| GET | `/api/v1/media/request/{request_number}` | request_number | `X-API-Key` (middleware); `get_storage_service` | s2s | `media_service/app/api/v1/media.py:1051` |
| GET | `/api/v1/media/request/{request_number}/timeline` | request_number | `X-API-Key` (middleware); `get_search_service` | s2s | `media_service/app/api/v1/media.py:1075` |
| GET | `/api/v1/media/search` | — | `X-API-Key` (middleware); `get_search_service` | — | `media_service/app/api/v1/media.py:382` |
| GET | `/api/v1/media/statistics` | — | `X-API-Key` (middleware); `get_search_service` | — | `media_service/app/api/v1/media.py:454` |
| GET | `/api/v1/media/tags/popular` | — | `X-API-Key` (middleware); `get_search_service` | — | `media_service/app/api/v1/media.py:470` |
| GET | `/api/v1/media/telegram/{telegram_file_id}` | telegram_file_id | `X-API-Key` (middleware); `get_storage_service` | s2s | `media_service/app/api/v1/media.py:776` |
| GET | `/api/v1/media/telegram/{telegram_file_id}/file` | telegram_file_id | `X-API-Key` (middleware); `get_storage_service` | s2s | `media_service/app/api/v1/media.py:813` |
| POST | `/api/v1/media/upload` | — | `X-API-Key` (middleware); `get_storage_service` | — | `media_service/app/api/v1/media.py:125` |
| POST | `/api/v1/media/upload-access` | — | `X-API-Key` (middleware); `get_storage_service` | — | `media_service/app/api/v1/media.py:256` |
| POST | `/api/v1/media/upload-report` | — | `X-API-Key` (middleware); `get_storage_service` | — | `media_service/app/api/v1/media.py:191` |
| POST | `/api/v1/media/upload-resident-document` | — | `X-API-Key` (middleware); `get_storage_service` | — | `media_service/app/api/v1/media.py:329` |
| DELETE | `/api/v1/media/{media_id}` | media_id | `X-API-Key` (middleware); `get_storage_service` | s2s | `media_service/app/api/v1/media.py:972` |
| GET | `/api/v1/media/{media_id}` | media_id | `X-API-Key` (middleware) | s2s | `media_service/app/api/v1/media.py:851` |
| POST | `/api/v1/media/{media_id}/archive` | media_id | `X-API-Key` (middleware); `get_storage_service` | s2s | `media_service/app/api/v1/media.py:927` |
| GET | `/api/v1/media/{media_id}/file` | media_id | `X-API-Key` (middleware); `get_storage_service` | s2s | `media_service/app/api/v1/media.py:708` |
| GET | `/api/v1/media/{media_id}/preview` | media_id | `X-API-Key` (middleware); `get_storage_service` | s2s | `media_service/app/api/v1/media.py:668` |
| DELETE | `/api/v1/media/{media_id}/publication-lock` | media_id | `X-API-Key` (middleware); `get_storage_service` | s2s | `media_service/app/api/v1/media.py:1034` |
| POST | `/api/v1/media/{media_id}/publication-lock` | media_id | `X-API-Key` (middleware); `get_storage_service` | s2s | `media_service/app/api/v1/media.py:1012` |
| PUT | `/api/v1/media/{media_id}/tags` | media_id | `X-API-Key` (middleware); `get_storage_service` | s2s | `media_service/app/api/v1/media.py:893` |
| GET | `/api/v1/media/{media_id}/url` | media_id | `X-API-Key` (middleware) | s2s | `media_service/app/api/v1/media.py:870` |
| GET | `/version` | — | **без auth** | — | `media_service/app/main.py:260` |

## Resource accounting (`resource-accounting/backend`, сессия по launch-ticket, все выборки по `tenant_id`) — 52 маршрутов

| Метод | Путь | Path-параметры | Авторизация | Класс | Файл |
|---|---|---|---|---|---|
| GET | `/health` | — | **без auth** (публичный по замыслу) | — | `resource-accounting/backend/app/main.py:89` |
| GET | `/v1/analytics/meters-sparklines` | — | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer')` | — | `resource-accounting/backend/app/api/analytics.py:96` |
| GET | `/v1/analytics/meters/{meter_id}` | meter_id | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer')` | a·tenant | `resource-accounting/backend/app/api/analytics.py:19` |
| GET | `/v1/analytics/summary` | — | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer')` | — | `resource-accounting/backend/app/api/analytics.py:128` |
| GET | `/v1/anomaly-rules` | — | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer')` | — | `resource-accounting/backend/app/api/periods.py:342` |
| PUT | `/v1/anomaly-rules` | — | `require_roles('resource_admin',)` | — | `resource-accounting/backend/app/api/periods.py:348` |
| GET | `/v1/audit` | — | `require_roles('resource_admin',)` | — | `resource-accounting/backend/app/api/audit.py:14` |
| POST | `/v1/auth/dev-login` | — | выключен в проде (`RESOURCE_DEV_AUTH_ENABLED=false` → 404) | — | `resource-accounting/backend/app/api/auth.py:157` |
| POST | `/v1/auth/logout` | — | **без auth** | — | `resource-accounting/backend/app/api/auth.py:191` |
| GET | `/v1/auth/me` | — | `get_current_user` | — | `resource-accounting/backend/app/api/auth.py:186` |
| POST | `/v1/auth/session/exchange` | — | тикет в теле: хеш, TTL 60 с, одноразовый (условный UPDATE) | — | `resource-accounting/backend/app/api/auth.py:92` |
| POST | `/v1/auth/tickets` | — | в хендлере: `X-Service-Token` (compare_digest) | — | `resource-accounting/backend/app/api/auth.py:54` |
| GET | `/v1/exports` | — | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer')` | — | `resource-accounting/backend/app/api/exports.py:102` |
| POST | `/v1/exports` | — | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer')` | — | `resource-accounting/backend/app/api/exports.py:52` |
| GET | `/v1/exports/{export_id}` | export_id | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer')` | a·tenant | `resource-accounting/backend/app/api/exports.py:137` |
| POST | `/v1/exports/{export_id}/cancel` | export_id | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer')` | a·tenant | `resource-accounting/backend/app/api/exports.py:194` |
| GET | `/v1/exports/{export_id}/download` | export_id | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer')` | a·tenant | `resource-accounting/backend/app/api/exports.py:147` |
| POST | `/v1/exports/{export_id}/mark-sent` | export_id | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer')` | a·tenant | `resource-accounting/backend/app/api/exports.py:172` |
| POST | `/v1/imports/readings/commit` | — | `require_roles('resource_admin', 'resource_operator')` | — | `resource-accounting/backend/app/api/imports.py:110` |
| POST | `/v1/imports/readings/preview` | — | `require_roles('resource_admin', 'resource_operator')` | — | `resource-accounting/backend/app/api/imports.py:68` |
| GET | `/v1/meters` | — | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer')` | — | `resource-accounting/backend/app/api/meters.py:131` |
| POST | `/v1/meters` | — | `require_roles('resource_admin', 'resource_operator')` | — | `resource-accounting/backend/app/api/meters.py:182` |
| GET | `/v1/meters/{meter_id}` | meter_id | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer')` | a·tenant | `resource-accounting/backend/app/api/meters.py:212` |
| PATCH | `/v1/meters/{meter_id}` | meter_id | `require_roles('resource_admin', 'resource_operator')` | a·tenant | `resource-accounting/backend/app/api/meters.py:221` |
| POST | `/v1/meters/{meter_id}/archive` | meter_id | `require_roles('resource_admin',)` | a·tenant | `resource-accounting/backend/app/api/meters.py:256` |
| POST | `/v1/meters/{meter_id}/correct-number` | meter_id | `require_roles('resource_admin',)` | a·tenant | `resource-accounting/backend/app/api/meters.py:274` |
| PUT | `/v1/meters/{meter_id}/readings/{month}` | meter_id, month | `require_roles('resource_admin', 'resource_operator', 'resource_meter_entry')` | a·tenant | `resource-accounting/backend/app/api/periods.py:178` |
| POST | `/v1/meters/{meter_id}/replace` | meter_id | `require_roles('resource_admin', 'resource_operator')` | a·tenant | `resource-accounting/backend/app/api/meters.py:298` |
| GET | `/v1/object-types` | — | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer')` | — | `resource-accounting/backend/app/api/catalog.py:38` |
| POST | `/v1/object-types` | — | `require_roles('resource_admin',)` | — | `resource-accounting/backend/app/api/catalog.py:46` |
| PATCH | `/v1/object-types/{type_id}` | type_id | `require_roles('resource_admin',)` | a·tenant | `resource-accounting/backend/app/api/catalog.py:63` |
| GET | `/v1/objects` | — | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer')` | — | `resource-accounting/backend/app/api/objects.py:59` |
| POST | `/v1/objects` | — | `require_roles('resource_admin',)` | — | `resource-accounting/backend/app/api/objects.py:89` |
| GET | `/v1/objects/{object_id}` | object_id | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer')` | a·tenant | `resource-accounting/backend/app/api/objects.py:126` |
| PATCH | `/v1/objects/{object_id}` | object_id | `require_roles('resource_admin',)` | a·tenant | `resource-accounting/backend/app/api/objects.py:135` |
| POST | `/v1/objects/{object_id}/archive` | object_id | `require_roles('resource_admin',)` | a·tenant | `resource-accounting/backend/app/api/objects.py:180` |
| GET | `/v1/periods` | — | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer', 'resource_meter_entry')` | — | `resource-accounting/backend/app/api/periods.py:86` |
| POST | `/v1/periods` | — | `require_roles('resource_admin', 'resource_operator')` | — | `resource-accounting/backend/app/api/periods.py:96` |
| POST | `/v1/periods/{month}/close` | month | `require_roles('resource_admin', 'resource_reviewer')` | a·tenant | `resource-accounting/backend/app/api/periods.py:300` |
| POST | `/v1/periods/{month}/move-to-review` | month | `require_roles('resource_admin', 'resource_operator')` | a·tenant | `resource-accounting/backend/app/api/periods.py:251` |
| POST | `/v1/periods/{month}/readings/bulk` | month | `require_roles('resource_admin', 'resource_operator', 'resource_meter_entry')` | a·tenant | `resource-accounting/backend/app/api/periods.py:202` |
| POST | `/v1/periods/{month}/reopen` | month | `require_roles('resource_admin', 'resource_reviewer')` | a·tenant | `resource-accounting/backend/app/api/periods.py:263` |
| POST | `/v1/periods/{month}/submit` | month | `require_roles('resource_admin', 'resource_reviewer')` | a·tenant | `resource-accounting/backend/app/api/periods.py:275` |
| POST | `/v1/periods/{month}/validate` | month | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer')` | a·tenant | `resource-accounting/backend/app/api/periods.py:228` |
| GET | `/v1/periods/{month}/worksheet` | month | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer', 'resource_meter_entry')` | a·tenant | `resource-accounting/backend/app/api/periods.py:119` |
| GET | `/v1/providers` | — | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer')` | — | `resource-accounting/backend/app/api/catalog.py:138` |
| POST | `/v1/providers` | — | `require_roles('resource_admin',)` | — | `resource-accounting/backend/app/api/catalog.py:146` |
| PATCH | `/v1/providers/{provider_id}` | provider_id | `require_roles('resource_admin',)` | a·tenant | `resource-accounting/backend/app/api/catalog.py:163` |
| POST | `/v1/readings/{reading_id}/corrections` | reading_id | `require_roles('resource_admin', 'resource_reviewer')` | a·tenant | `resource-accounting/backend/app/api/periods.py:312` |
| GET | `/v1/tags` | — | `require_roles('resource_admin', 'resource_operator', 'resource_reviewer', 'resource_viewer')` | — | `resource-accounting/backend/app/api/catalog.py:88` |
| POST | `/v1/tags` | — | `require_roles('resource_admin',)` | — | `resource-accounting/backend/app/api/catalog.py:96` |
| PATCH | `/v1/tags/{tag_id}` | tag_id | `require_roles('resource_admin',)` | a·tenant | `resource-accounting/backend/app/api/catalog.py:113` |
