# A9-P2-27 — ревью использования кода, живого только в тестах (2026-09-23)

> Решение владельца 2026-09-23: сначала полный ревью использования, удаление — только после этой таблицы и решения.
> Проверено на `origin/main` `a6fb8eb6`: `git grep -w` по всему репо (бот, API, фронт, TWA, access_control, media, compose, скрипты; строковые/динамические ссылки — callback_data, getattr, задачи планировщика), `git log -G` — когда перестал вызываться.

## Итог

- 97 символов перечня (раздел «Чистка — сводка аудита #9», DEAD-4) — **ни одного прод-вызова**. Единственный динамический вызов `getattr(AuthService(db), method_name)` (`handlers/employee_management/_units.py:117`) дёргает только approve_user/block_user/delete_user — их в перечне нет.
- Связи с отложенными фичами (паркинг/`access_rights`, «Лифты», ресурсоучёт, задел #6 P2-40) — **нет ни у одного символа**.
- Следов «оставлено намеренно как задел» в коммитах нет; 17 символов потеряли вызывающих в явных чистках/рефакторах (`241972d6` AUD6, `560c9566` BUG-137, `1acde834` BUG-154, `a02f3aca` ретайр веб-регистрации, `2f86d418`/`6de15516` переход на run_db, ruff autofix), остальные не вызывались ни разу.
- Методы `ShiftSchedule` не совпадают с метрикой PRD §8 «покрытие смен расписанием»: ждут почасовой словарь, а живой `shift_planning_service/planning.py:550` пишет `{'shifts_created': n}` — заделом под PRD считать нельзя.

## Предложение

| Кластер | Строк | Вердикт |
|---|---|---|
| ShiftAssignmentService: `resolve_assignment_conflicts`, `get_best_executor_for_shift`, `handle_executor_preferences` | ~100 | удалить |
| ShiftAssignmentService: `reassign_on_absence` | ~118 | **решение владельца**: описан в `docs/tech/SHIFTS_AND_ASSIGNMENT.md:286,450` как возможность фасада, трижды чинился (REG-01a, AUD3-12, CAS), но вызывающего не было с 2025-09-26 и в PRD/`docs/product` фичи «отсутствие/больничный» нет |
| Методы моделей смен (ShiftSchedule ×7, ShiftAssignment ×5, ShiftTransfer, Shift, RequestAssignment, ShiftTemplate) | ~194 | удалить |
| SpecializationService (7 методов; класс жив) | ~194 | удалить |
| TemplateManager (activate/deactivate, auto_create, apply_to_period, predefined, приватные хелперы) | ~162 | удалить |
| UserManagementService (search_users/search_employees/is_user_staff/is_user_employee/get_user_role_list) | ~156 | удалить; гейт `test_cod01_roles_csv_sites.py:48` перевести на живой `parse_roles_safe` |
| InviteService (`validate_invite_token`, `join_via_invite`) | ~105 | удалить |
| Клавиатуры (18) | ~444 | удалить (`guides/SHIFTS.md:243` сам называет часть «кандидат на ретайр») |
| auth_service (update_user_language, is_user_manager/executor, async-обёртки get_users_by_role/make_admin_by_password, block_user_by_telegram_id, is_user_approved, get_all_users) | ~150 | удалить; 2 теста SEC-06 (`test_auth_service.py:801-825`) перевести на `_sync` |
| comment_service, request_number_service, user_verification_service (без access_rights) | ~55 | удалить |
| Утилиты (helpers, language_helpers, request_helpers, safe_localization — `safe_get_text` жив, health) | ~268 | удалить; поправить `LOCALIZATION_GUIDE.md:36` |

Итого безопасно удаляемо ≈ **1 830 строк** прод-кода (+ ~30 тест-файлов), с `reassign_on_absence` ≈ 1 950. Доки к правке: `docs/tech/SHIFTS_AND_ASSIGNMENT.md:286,450`, `docs/shifts.md:233-234`, `docs/guides/SHIFTS.md:243-245`, `docs/LOCALIZATION_GUIDE.md:36`.
