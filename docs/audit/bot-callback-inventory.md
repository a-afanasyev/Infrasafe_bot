# Реестр callback-хендлеров бота с id объекта (ревью 2026-11-07)

Снято с живых роутеров: `setup_routers` (основной бот) и `setup_group_intake_dispatcher` (бот групп), обход `sub_routers` с наследованием root-фильтров. В реестр попали callback'и, тело которых разбирает `callback.data` в id: `split`/`replace`/`removeprefix`/`int(…)`/regex/`CallbackData`. Снимок `origin/main` 95d652c9.

Роли: M manager, A admin, E executor, AP applicant, I inspector, SA system_admin, EN engineer. Гейт: `root:` — ActionGate роутера; `@` — декоратор `@require_action`; `тело:` — ранний отказ в хендлере.

Класс **staff** — только персонал, достаточно роли; закреплено `tests/services/test_handler_authz_ratchet.py` (маркер авторизации в условии). Класс **открыт** — житель или исполнитель; категория и тест — из `BOT_IDOR_COVERAGE` в `uk_management_bot/tests/handlers/test_bot_callback_idor.py`. Ратчет этого файла требует запись для каждого такого callback'а.

## Deep-link

| Вход | Файл | Проверка | Тест |
|---|---|---|---|
| `/start join_<token>` (инвайт сотрудника) | `uk_management_bot/handlers/base.py` `cmd_start` → `_apply_invite_start` → `services/invite_service.py` `validate_invite(mark_used_by=telegram_id)` | HMAC-подпись (`compare_digest`), `expires_at` (TTL при выпуске, по умолчанию 24 ч), одноразовый nonce: INSERT под UNIQUE, гонка → `TokenAlreadyUsedError`. Привязка к `telegram_id` — в момент погашения (предъявительский инвайт по замыслу), rate-limit на `/start join_`, токен в логах маскируется (A9-P3-1) | `tests/api/test_invite_validation.py`, `uk_management_bot/tests/test_invite_token_logging.py` |

## Callback'и

| callback_data | Хендлер | Гейт → роли | Класс | Категория / тест |
|---|---|---|---|---|
| `@deny_router.callback_query(F.data.regexp(ADDRESS_CALLBACK_RE` | `_role_gate.py:125` `deny_address_callback` | — | открыт | NO-OBJECT (deny-роутер: только отказ) |
| `F.data.startswith("ac_rel:"), VehicleRequestStates.waiting_for_relation` | `access_control.py:256` `ac_vehicle_relation` | — | открыт | NO-OBJECT (тип связи) |
| `F.data.startswith("ac_veh_apt:"), VehicleRequestStates.waiting_for_apartment` | `access_control.py:281` `ac_vehicle_apartment` | — | открыт | OWNER: create_resident_request (ApartmentNotOwned); test_access_control_handler::test_vehicle_foreign_apartment_shows_error |
| `F.data.startswith("ac_pass_type:"), PassOrderStates.waiting_for_type` | `access_control.py:348` `ac_pass_type` | — | открыт | NO-OBJECT (тип пропуска) |
| `F.data.startswith("ac_pass_dur:"), PassOrderStates.waiting_for_valid_until` | `access_control.py:388` `ac_pass_duration` | — | открыт | NO-OBJECT (срок) |
| `F.data.startswith("ac_pass_apt:"), PassOrderStates.waiting_for_apartment` | `access_control.py:414` `ac_pass_apartment` | — | открыт | OWNER: create_resident_pass (ApartmentNotOwned); access_control/tests/test_resident_api.py::test_create_pass_foreign_apartment_403 |
| `F.data.startswith("ac_cancel_pass:"` | `access_control.py:474` `ac_cancel_pass` | — | открыт | OWNER: cancel_resident_pass (PassNotOwned); access_control/tests/test_resident_api.py::test_cancel_foreign_pass_403 |
| `F.data.startswith("acc_dispute:"` | `access_control.py:508` `ac_dispute_response` | — | открыт | OWNER: confirm_disputed_entry (EntryNotOwned); test_disputed_entry_callback |
| `F.data.startswith("addr_building_autofill:"` | `address_apartments/autofill.py:70` `start_autofill_apartments` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("apartment_create_bpage:"),` | `address_apartments/creation.py:111` `show_create_buildings_page` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("apartment_create_building:"` | `address_apartments/creation.py:141` `process_apartment_building_selection` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_apartment_view:"` | `address_apartments/details.py:122` `show_apartment_details` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_apartment_residents:"` | `address_apartments/details.py:185` `show_apartment_residents` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_apartment_edit:"` | `address_apartments/editing.py:79` `show_apartment_edit_menu` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_apartment_toggle:"` | `address_apartments/editing.py:91` `toggle_apartment_status` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_apartment_delete:"` | `address_apartments/editing.py:133` `confirm_apartment_deletion` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_apartment_delete_confirm:"` | `address_apartments/editing.py:168` `delete_apartment` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_apartment_edit_area:"` | `address_apartments/editing.py:201` `start_edit_apartment_area` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_apartments_by_building:"` | `address_apartments/viewing.py:186` `show_apartments_by_building` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_apartments_by_building_page:"` | `address_apartments/viewing.py:218` `paginate_apartments_by_building` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_buildings_page:"` | `address_buildings.py:209` `show_buildings_page` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_buildings_by_yard:"` | `address_buildings.py:231` `show_buildings_by_yard` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_buildings_by_yard_page:"` | `address_buildings.py:264` `show_buildings_by_yard_page` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_building_view:"` | `address_buildings.py:310` `show_building_details` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("building_create_yard:"` | `address_buildings.py:392` `process_building_yard_selection` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_building_edit:"` | `address_buildings.py:607` `show_building_edit_menu` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_building_toggle:"` | `address_buildings.py:619` `toggle_building_status` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_building_delete:"` | `address_buildings.py:663` `confirm_building_deletion` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_building_delete_confirm:"` | `address_buildings.py:704` `delete_building` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_moderation_page:"` | `address_moderation.py:292` `show_moderation_page` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_moderation_view:"` | `address_moderation.py:317` `show_moderation_details` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_moderation_approve:"` | `address_moderation.py:391` `start_approve_request` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_moderation_reject:"` | `address_moderation.py:492` `start_reject_request` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_yards_page:"` | `address_yards.py:283` `show_yards_page` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_yard_view:"` | `address_yards.py:309` `show_yard_details` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_yard_edit:"` | `address_yards.py:509` `show_yard_edit_menu` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_yard_edit_name:"` | `address_yards.py:521` `start_yard_name_edit` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_yard_toggle:"` | `address_yards.py:578` `toggle_yard_status` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_yard_delete:"` | `address_yards.py:622` `confirm_yard_deletion` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("addr_yard_delete_confirm:"` | `address_yards.py:663` `delete_yard` | root:admin_panel.use → A,M | staff | — |
| `F.data.regexp(_ACCEPT_REQUEST_NUMBER_RE` | `admin/actions.py:44` `handle_accept_request` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("mgr_deny_"` | `admin/actions.py:90` `handle_deny_request` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("clarify_"` | `admin/actions.py:135` `handle_clarify_request` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.regexp(_PURCHASE_REQUEST_NUMBER_RE` | `admin/actions.py:215` `handle_purchase_request` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("mgr_complete_"` | `admin/actions.py:300` `handle_complete_request` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("mgr_delete_"` | `admin/actions.py:364` `handle_delete_request` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("assign_duty_"` | `admin/assignment.py:61` `handle_assign_duty_executor_admin` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("assign_specific_"` | `admin/assignment.py:125` `handle_assign_specific_executor_admin` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.regexp(rf"^assign_executor_{REQUEST_NUMBER_CORE}_\d+$"` | `admin/assignment.py:213` `handle_final_executor_assignment_admin` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("back_to_assignment_type_"` | `admin/assignment.py:268` `handle_back_to_assignment_type_admin` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith(MENU_PREFIX` | `admin/category.py:237` `handle_category_menu` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.regexp(SET_PATTERN` | `admin/category.py:263` `handle_category_set` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.regexp(STATUS_PATTERN` | `admin/elevator_hint.py:162` `handle_elevator_status_hint` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("invite_role_"` | `admin/invites.py:51` `handle_invite_role_selection` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("invite_spec_"), InviteCreationStates.waiting_for_specialization` | `admin/invites.py:91` `handle_invite_specialization_selection` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("invite_expiry_"), InviteCreationStates.waiting_for_expiry` | `admin/invites.py:117` `handle_invite_expiry_selection` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("mreq_back_"` | `admin/lists.py:117` `handle_manager_back_to_list` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("purchase_return_to_work_"` | `admin/materials.py:81` `handle_return_to_work` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("edit_materials_"` | `admin/materials.py:184` `handle_edit_materials` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith(MENU_PREFIX` | `admin/reassignment.py:483` `handle_reassign_menu` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith(PICK_PREFIX` | `admin/reassignment.py:526` `handle_reassign_pick` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith(DUTY_PREFIX` | `admin/reassignment.py:570` `handle_reassign_duty` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.regexp(TO_PATTERN` | `admin/reassignment.py:591` `handle_reassign_to` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("mview_"` | `admin/views.py:48` `handle_manager_view_request` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("media_"` | `admin/views.py:233` `handle_view_request_media` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("confirm_completed_"` | `admin/views.py:334` `handle_manager_confirm_completed` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("reconfirm_completed_"` | `admin/views.py:434` `handle_manager_reconfirm_completed` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("return_to_work_"` | `admin/views.py:510` `handle_manager_return_to_work` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("rtw_cancel_"` | `admin/views.py:554` `handle_return_to_work_cancel` | — | открыт | NO-OBJECT (сброс своего FSM, БД не читается) |
| `F.data.startswith("mreq_page_"` | `admin/views.py:636` `handle_manager_request_pagination` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("tutorial:"` | `base.py:815` `send_tutorial_video` | — | открыт | NO-OBJECT (ключ ролика) |
| `RoleSwitchCB.filter(` | `base.py:880` `switch_role` | — | открыт | OWNER: целевая роль ∈ roles пользователя |
| `F.data.regexp(CARD_PATTERN` | `elevators/card.py:27` `handle_card` | root:elevators.technician → A,EN,E,M | открыт | BY-DESIGN A10-INT-10 |
| `F.data.regexp(_LIST_RE.pattern` | `elevators/maintenance.py:91` `handle_occurrences` | root:elevators.technician → A,EN,E,M | открыт | BY-DESIGN A10-INT-10 |
| `F.data.regexp(_PICK_RE.pattern` | `elevators/maintenance.py:108` `handle_occurrence_pick` | root:elevators.technician → A,EN,E,M | открыт | BY-DESIGN A10-INT-10 |
| `F.data.regexp(_YARD_RE.pattern` | `elevators/menu.py:73` `handle_yard` | root:elevators.technician → A,EN,E,M | открыт | BY-DESIGN A10-INT-10 (elevators.technician: реестр целиком) |
| `F.data.regexp(_BUILDING_RE.pattern` | `elevators/menu.py:90` `handle_building` | root:elevators.technician → A,EN,E,M | открыт | BY-DESIGN A10-INT-10 |
| `F.data.regexp(_START_RE.pattern` | `elevators/repair.py:78` `handle_repair_start` | root:elevators.technician → A,EN,E,M | открыт | BY-DESIGN A10-INT-10 |
| `StateFilter(ElevatorStates.repair_urgency), F.data.regexp(_URGENCY_RE.pattern` | `elevators/repair.py:118` `handle_urgency` | root:elevators.technician → A,EN,E,M | открыт | BY-DESIGN A10-INT-10 |
| `F.data.regexp(_OFFER_RE.pattern` | `elevators/repair.py:154` `handle_repair_status_offer` | root:elevators.technician → A,EN,E,M | открыт | BY-DESIGN A10-INT-10; test_elevators_repair::test_repair_status_offer_foreign_number_rejected |
| `F.data.regexp(_MENU_RE.pattern` | `elevators/status.py:84` `handle_status_menu` | root:elevators.technician → A,EN,E,M | открыт | BY-DESIGN A10-INT-10 |
| `F.data.regexp(_PICK_RE.pattern` | `elevators/status.py:103` `handle_status_pick` | root:elevators.technician → A,EN,E,M | открыт | BY-DESIGN A10-INT-10 |
| `F.data.regexp(r"^edit_employee_\d+$"` | `employee_management/editing.py:43` `edit_employee_entry` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("edit_employee_phone_"` | `employee_management/editing.py:80` `edit_employee_phone` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("employee_mgmt_list_"` | `employee_management/lists.py:37` `show_employee_list` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("employee_mgmt_employee_"` | `employee_management/lists.py:96` `show_employee_actions` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("approve_employee_"` | `employee_management/moderation.py:31` `approve_employee` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("reject_employee_"` | `employee_management/moderation.py:89` `reject_employee` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("block_employee_"` | `employee_management/moderation.py:148` `block_employee` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("unblock_employee_"` | `employee_management/moderation.py:205` `unblock_employee` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("delete_employee_"` | `employee_management/moderation.py:265` `delete_employee` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("change_employee_role_"` | `employee_management/roles_specs.py:38` `change_employee_role` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("change_employee_specialization_"` | `employee_management/roles_specs.py:109` `change_employee_specialization` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("role_toggle_"), EmployeeManagementStates.selecting_roles` | `employee_management/roles_specs.py:251` `toggle_role` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("spec_toggle_"), EmployeeManagementStates.selecting_specializations` | `employee_management/roles_specs.py:411` `toggle_specialization` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `(фильтр в коде)` | `executor_done.py:132` `close_with_photo` | — | открыт | OWNER: личный чат + executor_by_telegram + complete_with_photo (not_assigned); test_executor_done_callback::test_foreign_presser_is_refused |
| `F.data.startswith("fb_type:"), FeedbackStates.waiting_for_type` | `feedback.py:141` `feedback_type` | — | открыт | NO-OBJECT (тип отзыва) |
| `(фильтр в коде)` | `group_intake.py:1013` `group_intake_callback` | — | открыт | OWNER: кандидат по (chat_id, message_id) из monitored-группы + _presser_allowed; test_group_intake_callbacks::test_foreign_presser_gets_alert_and_nothing_happens |
| `F.data.startswith("insp_yard_page:"), InspectorRequestStates.yard` | `inspector_requests.py:222` `inspector_yard_page` | — | открыт | NO-OBJECT (страница) |
| `F.data.startswith("insp_yard:"), InspectorRequestStates.yard` | `inspector_requests.py:233` `inspector_yard_selected` | — | открыт | BY-DESIGN: обходчик — любой активный двор/дом (requests.create_inspection) |
| `F.data.startswith("insp_bld_page:"), InspectorRequestStates.building` | `inspector_requests.py:251` `inspector_building_page` | — | открыт | NO-OBJECT (страница) |
| `F.data.startswith("insp_bld:"), InspectorRequestStates.building` | `inspector_requests.py:263` `inspector_building_selected` | — | открыт | BY-DESIGN: обходчик — любой активный дом; resolve_request_address(inspector) |
| `F.data.startswith("insp_cat:"), InspectorRequestStates.category` | `inspector_requests.py:292` `inspector_category_selected` | — | открыт | NO-OBJECT (ключ категории) |
| `F.data.startswith("insp_urg:"), InspectorRequestStates.urgency` | `inspector_requests.py:373` `inspector_urgency_selected` | — | открыт | NO-OBJECT (срочность) |
| `F.data.startswith("shift_details:"` | `my_shifts/viewing.py:233` `handle_shift_details` | @execution.work → E | открыт | OWNER: execution.work + Shift.user_id; test_aud337_my_shifts_offload |
| `F.data.startswith("set_language_"` | `profile_editing.py:325` `handle_language_choice` | — | открыт | NO-OBJECT (код языка, свой профиль) |
| `F.data.startswith("view_completed_"` | `request_acceptance.py:292` `view_completed_request` | — | открыт | OWNER: _load_completed_view → forbidden; test_completed_view |
| `F.data.startswith("view_completion_media_"` | `request_acceptance.py:387` `view_completion_media` | — | открыт | OWNER: _load_completion_media → forbidden |
| `F.data.startswith("accept_request_"` | `request_acceptance.py:447` `accept_request` | — | открыт | ENTRY: только клавиатура оценки |
| `F.data.startswith("rate_"` | `request_acceptance.py:471` `save_rating` | — | открыт | CANON: APPLICANT_ACCEPT (owner/сосед) |
| `F.data.startswith("return_request_"` | `request_acceptance.py:567` `return_request` | — | открыт | ENTRY: финал — process_return_request → APPLICANT_RETURN (только owner) |
| `F.data.startswith("add_comment_"` | `request_comments.py:294` `handle_add_comment_start` | — | открыт | ACCESS: has_request_access_sync; test_comment_access_idor |
| `RequestCommentStates.waiting_for_comment_type, F.data.startswith("comment_type_"` | `request_comments.py:352` `handle_comment_type_selection` | — | открыт | ACCESS: _apply_comment перепроверяет; test_comment_access_idor::test_apply_comment_rejects_foreign_request |
| `F.data.regexp(_VIEW_COMMENTS_RE` | `request_comments.py:515` `handle_view_comments` | — | открыт | ACCESS; test_comments_view |
| `F.data.startswith("view_comments_by_type_"` | `request_comments.py:564` `handle_view_comments_by_type` | — | открыт | ACCESS (_load_comments_by_type_view) |
| `F.data.startswith("back_to_comments_"` | `request_comments.py:612` `handle_back_to_comments` | — | открыт | ACCESS; test_comments_view |
| `F.data.startswith("view_report_"` | `request_reports.py:213` `handle_view_report` | — | открыт | ACCESS; test_report_view |
| `F.data.startswith("approve_request_"` | `request_reports.py:257` `handle_approve_request` | — | открыт | OWNER + CANON (_load_applicant_action_context, not_owner) |
| `F.data.startswith("request_revision_"` | `request_reports.py:358` `handle_request_revision` | — | открыт | OWNER + CANON (APPLICANT_RETURN) |
| `F.data.startswith("addr:"), RequestStates.address` | `requests/create.py:203` `handle_address_selection` | — | открыт | OWNER: resolve_request_address(applicant) — свои двор/дом/квартира; tests/api/test_inspector_requests.py::test_resolver_foreign_apartment_403 |
| `F.data.startswith("addr_page:"), RequestStates.address` | `requests/create.py:262` `handle_address_page` | — | открыт | SELF (свои адреса; номер страницы) |
| `F.data.startswith("category_"` | `requests/create_callbacks.py:41` `handle_category_selection` | — | открыт | SELF (свои адреса; ключ категории) |
| `F.data.startswith("urgency_"` | `requests/create_callbacks.py:149` `handle_urgency_selection` | — | открыт | NO-OBJECT (срочность) |
| `F.data.in_({"confirm_yes", "confirm_no"}` | `requests/create_callbacks.py:214` `handle_confirmation` | — | открыт | NO-OBJECT (да/нет; данные из своего FSM) |
| `F.data.startswith("executor_view_media_"` | `requests/executor.py:68` `executor_view_media` | — | открыт | ACCESS: has_request_access_sync; test_executor_media_access::test_foreign_user_gets_not_found_and_no_media |
| `F.data.startswith("claim_request_"` | `requests/executor.py:227` `claim_group_request` | — | открыт | CANON: EXECUTOR_CLAIM (смена + группа + unclaimed) |
| `F.data.startswith("executor_purchase_"` | `requests/executor.py:268` `executor_request_purchase` | — | открыт | ENTRY: финал — run_command (назначение + смена) |
| `F.data.startswith("executor_complete_"` | `requests/executor.py:352` `executor_complete_request` | — | открыт | ENTRY: финал — executor_finish_completion |
| `F.data.startswith("executor_finish_completion_"` | `requests/executor.py:454` `executor_finish_completion` | — | открыт | ACCESS: can_upload_completion_sync ДО загрузки в media (BOT-01); test_finish_completion_uploads_only_for_assigned |
| `F.data.startswith("executor_work_"` | `requests/executor.py:574` `executor_return_to_work` | — | открыт | CANON: run_command (исполнитель заявки) |
| `F.data.regexp(_START_RE` | `requests/executor_before.py:107` `executor_before_start` | — | открыт | ACCESS: check_before_access; test_executor_before.py |
| `F.data.regexp(_DONE_RE` | `requests/executor_before.py:176` `executor_before_done` | — | открыт | ACCESS: check_before_access до скачивания; test_executor_before.py |
| `F.data.startswith("page_"` | `requests/listing.py:66` `handle_pagination` | — | открыт | SELF (свои заявки; страница) |
| `(фильтр в коде)` | `requests/listing.py:189` `handle_view_request` | — | открыт | ACCESS: has_request_access_sync; test_handler_permissions |
| `F.data.startswith("back_list_"` | `requests/listing.py:364` `handle_back_to_list` | — | открыт | SELF (свои заявки; страница) |
| `F.data.regexp(_EDIT_REQUEST_NUMBER_RE` | `requests/listing.py:541` `handle_edit_request` | — | открыт | OWNER: request.user_id == user.id; test_edit_request_entry |
| `F.data.regexp(_CANCEL_REQUEST_NUMBER_RE.pattern` | `requests/listing.py:625` `handle_cancel_request` | — | открыт | CANON: RequestService.update_status_by_actor → run_command_sync (NotAuthorized) |
| `F.data.regexp(_APPROVE_REQUEST_NUMBER_RE` | `requests/listing.py:663` `handle_approve_request` | — | открыт | ENTRY: только клавиатура оценки; приёмка — save_rating → APPLICANT_ACCEPT |
| `F.data.regexp(_MATISSUE_START_RE` | `requests/materials.py:62` `start_material_issue` | — | открыт | OWNER: guard_executor_issue (executor_id); test_material_issue_handlers::test_start_rejects_stranger_executor, test_material_guard_does_not_disclose_foreign_status |
| `MaterialIssueStates.selecting_material, F.data.regexp(_MATPAGE_RE` | `requests/materials.py:95` `paginate_materials` | — | открыт | NO-OBJECT (страница справочника) |
| `MaterialIssueStates.selecting_material, F.data.regexp(_MATPICK_RE` | `requests/materials.py:117` `pick_material` | — | открыт | OWNER: confirm перепроверяет guard; test_material_issue_handlers::test_confirm_recheck_guards_after_status_change |
| `F.data.startswith("replyclarify_"` | `requests/myrequests.py:187` `handle_reply_clarify_start` | — | открыт | OWNER: диалог только владельцу, запись перепроверяет; test_reply_clarify_does_not_leak_or_write_foreign |
| `F.data.startswith("status_"` | `requests/myrequests.py:261` `handle_status_filter` | — | открыт | SELF (фильтр своих заявок) |
| `F.data.startswith("categoryfilter_"` | `requests/myrequests.py:378` `handle_category_filter` | — | открыт | SELF (фильтр своих заявок) |
| `F.data.startswith("period_"` | `requests/myrequests.py:425` `handle_period_filter` | — | открыт | SELF (фильтр своих заявок) |
| `F.data.startswith("executorfilter_"` | `requests/myrequests.py:441` `handle_executor_filter` | — | открыт | SELF (фильтр своих заявок) |
| `F.data.startswith("select_shift_for_assignment:"` | `shift_management/assignment_b.py:320` `handle_select_shift_for_assignment` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("assign_executor_to_shift:"` | `shift_management/assignment_b.py:415` `handle_assign_executor_to_shift` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("force_assign:"` | `shift_management/assignment_b.py:588` `handle_force_assign` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("select_template:"` | `shift_management/manual_planning.py:66` `handle_template_selection` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("select_date:"` | `shift_management/manual_planning.py:107` `handle_date_selection` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("schedule_date:"` | `shift_management/schedule.py:60` `handle_schedule_date` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("reassign_shift_pick:"` | `shift_management/schedule.py:147` `handle_reassign_shift_pick` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("reassign_executor:"` | `shift_management/schedule.py:187` `handle_reassign_executor` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `lambda c: c.data.startswith("template_edit_") and c.data.replace("template_edit_", "").isd` | `shift_management/templates_a.py:359` `handle_edit_template_details` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("template_toggle_active_"` | `shift_management/templates_a.py:433` `handle_toggle_template_active` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("template_edit_name_"` | `shift_management/templates_a.py:471` `handle_edit_template_name` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("template_edit_description_"` | `shift_management/templates_a.py:504` `handle_edit_template_description` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("template_edit_time_"` | `shift_management/templates_a.py:538` `handle_edit_template_time` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("template_edit_duration_"` | `shift_management/templates_a.py:571` `handle_edit_template_duration` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("template_create_spec_"` | `shift_management/templates_b.py:180` `handle_template_create_specialization_toggle` | root:admin_panel.use → A,M | staff | — |
| `F.data.startswith("template_edit_specializations_"` | `shift_management/templates_b.py:288` `handle_edit_template_specializations` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("template_spec_toggle_"` | `shift_management/templates_b.py:329` `handle_toggle_template_specialization` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("template_spec_save_"` | `shift_management/templates_b.py:381` `handle_save_template_specializations` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `lambda c: c.data.startswith("template_delete_") and not c.data.startswith("template_delete` | `shift_management/templates_b.py:412` `handle_delete_template` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `lambda c: c.data.startswith("template_delete_confirm_") and c.data.replace("template_delet` | `shift_management/templates_b.py:448` `handle_delete_template_confirm` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("template_force_delete_"` | `shift_management/templates_b.py:489` `handle_force_delete_template` | root:admin_panel.use → A,M; @admin_panel.use → A,M | staff | — |
| `F.data.startswith("transfer_shift:"` | `shift_transfer.py:356` `handle_shift_selection` | — | открыт | OWNER: фильтр Shift.user_id в SQL (_check_shift_selectable) |
| `F.data.startswith("transfer_reason:"` | `shift_transfer.py:386` `handle_reason_selection` | — | открыт | NO-OBJECT (причина) |
| `F.data.startswith("transfer_urgency:"` | `shift_transfer.py:407` `handle_urgency_selection` | — | открыт | NO-OBJECT (срочность) |
| `F.data.startswith("transfer_confirm:"` | `shift_transfer.py:506` `handle_transfer_confirmation` | — | открыт | OWNER: create_transfer (not_your_shift) |
| `F.data.startswith("transfer_assign_executor:"` | `shift_transfer.py:613` `handle_transfer_assign_executor` | @shift_transfers.approve → M | staff | — |
| `F.data.startswith("transfer_response:"` | `shift_transfer.py:650` `handle_transfer_response` | @shift_transfers.respond → E,M | открыт | OWNER: accept/reject_transfer (not_your_transfer до статуса); test_shift_transfer_rebuild::test_foreign_executor_cannot_learn_transfer_status |
| `F.data.startswith("view_transfer:"` | `shift_transfer.py:693` `handle_view_transfer` | @shift_transfers.respond → E,M | открыт | OWNER: менеджер — все, иначе участник; test_shift_transfer_rebuild::test_unit_view_transfer_idor_guard |
| `F.data.startswith("end_shift_select:"` | `shifts.py:534` `handle_shift_selection` | — | открыт | OWNER: _load_shift_end_view; test_shifts_authz::test_shift_end_view_foreign_shift_is_invisible |
| `F.data.startswith("shift_end_confirm_yes:"` | `shifts.py:560` `end_shift_yes_with_id` | — | открыт | OWNER: _end_shift_by_id_unit (Shift.user_id) |
| `F.data.startswith("shifts_page_"` | `shifts.py:688` `shifts_history_page` | — | открыт | SELF |
| `F.data.startswith("shifts_period_"` | `shifts.py:706` `shifts_filter_period` | — | открыт | SELF |
| `F.data.startswith("shifts_status_"` | `shifts.py:714` `shifts_filter_status` | — | открыт | SELF |
| `F.data.startswith("unaccepted_remind_"` | `unaccepted_requests.py:237` `handle_remind_applicant` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("unaccepted_accept_"` | `unaccepted_requests.py:296` `handle_manager_accept_request` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("user_apartment_yard:"` | `user_apartment_selection.py:314` `process_yard_selection` | — | открыт | BY-DESIGN: регистрация — выбор из справочника, привязка уходит на модерацию |
| `F.data.startswith("user_apartment_building:"` | `user_apartment_selection.py:362` `process_building_selection` | — | открыт | BY-DESIGN: то же |
| `(фильтр в коде)` | `user_apartment_selection.py:413` `process_apartment_page` | — | открыт | NO-OBJECT (страница) |
| `F.data.startswith("user_apartment_final:"` | `user_apartment_selection.py:445` `process_apartment_selection` | — | открыт | BY-DESIGN: заявка на привязку (pending → модерация) |
| `F.data.startswith("set_primary:"` | `user_apartments.py:452` `set_primary_apartment` | — | открыт | OWNER: _set_primary_apartment (access_denied); test_bug_wave_p2_silent |
| `F.data.startswith("view_apartment:"` | `user_apartments.py:489` `view_apartment_details` | — | открыт | OWNER; test_user_apartments_admin_guard |
| `F.data.startswith("admin_manage_apartments_"` | `user_apartments.py:664` `admin_manage_user_apartments` | @admin_panel.use → A,M | staff | — |
| `F.data.startswith("admin_apartment_detail_"` | `user_apartments.py:743` `admin_apartment_detail` | @admin_panel.use → A,M | staff | — |
| `F.data.startswith("admin_approve_apartment_"` | `user_apartments.py:808` `admin_approve_apartment` | @admin_panel.use → A,M | staff | — |
| `F.data.startswith("admin_reject_apartment_"` | `user_apartments.py:847` `admin_reject_apartment` | @admin_panel.use → A,M | staff | — |
| `F.data.startswith("admin_toggle_owner_"` | `user_apartments.py:885` `admin_toggle_owner_status` | @admin_panel.use → A,M | staff | — |
| `F.data.startswith("user_action_approve_"` | `user_management/actions.py:180` `handle_approve_user` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("user_action_block_"` | `user_management/actions.py:229` `handle_block_user` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("user_action_unblock_"` | `user_management/actions.py:276` `handle_unblock_user` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("user_action_delete_"` | `user_management/actions.py:323` `handle_delete_user` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("user_action_view_documents_"` | `user_management/actions.py:370` `handle_view_user_documents` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("user_action_request_docs_"` | `user_management/actions.py:422` `handle_request_documents` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("check_document_"` | `user_management/actions.py:480` `handle_check_document` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("uncheck_document_"` | `user_management/actions.py:527` `handle_uncheck_document` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("req_docs_"` | `user_management/actions.py:574` `handle_request_selected_documents` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("cancel_document_selection_"` | `user_management/actions.py:640` `handle_cancel_document_selection` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("back_to_user_details_"` | `user_management/actions.py:724` `handle_back_to_user_details` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("user_mgmt_list_"` | `user_management/listing.py:28` `show_user_list` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("user_mgmt_user_"` | `user_management/listing.py:172` `show_user_details` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("approve_user_"` | `user_management/panels.py:275` `handle_approve_user_from_notification` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("reject_user_"` | `user_management/panels.py:335` `handle_reject_user_from_notification` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.regexp(_VIEW_USER_ID_RE` | `user_management/panels.py:394` `handle_view_user_from_notification` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("user_roles_"` | `user_management/roles_specs.py:191` `show_user_roles_management` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("role_add_"), UserManagementStates.selecting_roles` | `user_management/roles_specs.py:249` `add_role_to_user` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("role_remove_"), UserManagementStates.selecting_roles` | `user_management/roles_specs.py:285` `remove_role_from_user` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("user_specializations_"` | `user_management/roles_specs.py:468` `show_user_specializations_management` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("spec_toggle_"), UserManagementStates.selecting_specializations` | `user_management/roles_specs.py:527` `toggle_specialization` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.regexp(ENTRY_PATTERN) \| F.data.regexp(LEGACY_EMPLOYEE_PATTERN` | `user_rename.py:158` `handle_rename_start` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("access_rights_"` | `user_verification/access_decision.py:33` `manage_access_rights` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("verify_approve_"` | `user_verification/access_decision.py:94` `approve_user_verification` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("verify_reject_"` | `user_verification/access_decision.py:170` `reject_user_verification` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("verification_request_"` | `user_verification/documents.py:30` `request_additional_info` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("view_user_documents_"` | `user_verification/documents.py:62` `view_user_documents` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("request_info_"` | `user_verification/info_requests.py:27` `select_info_type` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("verification_user_"` | `user_verification/panel.py:65` `show_user_verification` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("manage_user_yards_"` | `user_yards_management.py:213` `handle_manage_user_yards` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("add_user_yard_"` | `user_yards_management.py:252` `handle_add_user_yard` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("user_yard_add_confirm_"` | `user_yards_management.py:283` `handle_confirm_add_yard` | тело: has_admin_access / has_action_roles → A,M | staff | — |
| `F.data.startswith("remove_user_yard_"` | `user_yards_management.py:327` `handle_remove_user_yard` | тело: has_admin_access / has_action_roles → A,M | staff | — |
