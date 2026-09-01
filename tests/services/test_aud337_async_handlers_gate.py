"""AUD3-37 (вариант (б)) — ратчет конвертированных хендлер-модулей.

Инвариант конверсии: DB-фаза хендлера — цельный sync unit-of-work, исполняемый
в worker-потоке через ``run_db`` (database/session.py); event loop не трогает
сессию. Гейт держит два правила для файлов из CONVERTED:

1. Ни одна ``async def`` не работает с сессией напрямую: внутри неё запрещены
   ``.query(...)``, ``session_scope(...)``, ``SessionLocal(...)``, ``.commit()``.
   Всё это — территория sync-юнитов (обычных ``def``), которые run_db уводит
   в поток.

2. Ни одна ``async def`` не объявляет параметр ``db``: объявленный ``db``
   означает, что aiogram DI снова инъецирует middleware-сессию, и юнит
   исполнится синхронно на event loop (run_db с db != None — это тестовый
   seam, в проде так нельзя). Тестовый seam называется ``_db`` и допустим:
   ключа "_db" в data middleware не кладёт, DI его не заполняет.

Новые конвертированные файлы добавлять в CONVERTED — гейт расширяется вместе
с программой (волна за волной, лидеры ``.query(`` в handlers/ первыми).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Волны B1–B4 (2026-08-05..06): лидеры по числу сайтов sync-запросов.
CONVERTED = [
    # AUD5-ARCH-3 волна 7: my_shifts.py разбит на пакет — гейт держит все
    # файлы пакета с хендлерами + модуль sync-юнитов.
    "uk_management_bot/handlers/my_shifts/_units.py",
    "uk_management_bot/handlers/my_shifts/menu.py",
    "uk_management_bot/handlers/my_shifts/viewing.py",
    "uk_management_bot/handlers/my_shifts/lifecycle.py",
    "uk_management_bot/handlers/my_shifts/history.py",
    "uk_management_bot/handlers/my_shifts/transfers.py",
    "uk_management_bot/handlers/shift_transfer.py",
    "uk_management_bot/handlers/request_acceptance.py",
    # AUD5-ARCH-3 волна 1: god-файл employee_management.py разбит на пакет —
    # гейт держит все файлы пакета с хендлерами + модуль sync-юнитов.
    "uk_management_bot/handlers/employee_management/_units.py",
    "uk_management_bot/handlers/employee_management/panels.py",
    "uk_management_bot/handlers/employee_management/lists.py",
    "uk_management_bot/handlers/employee_management/moderation.py",
    "uk_management_bot/handlers/employee_management/editing.py",
    "uk_management_bot/handlers/employee_management/roles_specs.py",
    # AUD5-ARCH-3 волна 11: user_verification.py разбит на пакет — гейт держит
    # все файлы пакета с хендлерами + модуль sync-юнитов.
    "uk_management_bot/handlers/user_verification/_units.py",
    "uk_management_bot/handlers/user_verification/panel.py",
    "uk_management_bot/handlers/user_verification/documents.py",
    "uk_management_bot/handlers/user_verification/info_requests.py",
    "uk_management_bot/handlers/user_verification/document_review.py",
    "uk_management_bot/handlers/user_verification/access_decision.py",
    # AUD5-ARCH-3 волна 12: request_status_management.py разбит на пакет.
    # BUG-137: мёртвый FSM-флоу (status_flow/completion/confirmation/
    # availability) ретайрен — в охвате остались живые файлы пакета.
    "uk_management_bot/handlers/request_status_management/_units.py",
    "uk_management_bot/handlers/request_status_management/executor_actions.py",
    # A2-хвост волна 1: address_yards сконвертирован целиком. shifts.py вошёл
    # после BUG-150 (ретайр 2026-08-19): четыре мёртвых хендлера — end_shift_yes,
    # end_shift_no, manager_active_shifts, force_end_shift — удалены, а
    # session_scope в async def держали ровно они.
    "uk_management_bot/handlers/address_yards.py",
    "uk_management_bot/handlers/shifts.py",
    # A2-хвост волна 2: лидеры остатка. Все хендлеры трёх файлов живые
    # (инвентарь генераторов callback_data: keyboards/profile.py,
    # keyboards/user_management.py, keyboards/address_management.py + in-file).
    "uk_management_bot/handlers/user_apartments.py",
    "uk_management_bot/handlers/address_buildings.py",
    "uk_management_bot/handlers/profile_editing.py",
    # A2-хвост волна 3: регистрация выбора квартиры и модерация адресных
    # заявок. Все хендлеры обоих файлов живые (триггеры генерят
    # keyboards/address_management.py, keyboards/user_management.py и
    # внутрифайловые клавиатуры FSM-цепочки регистрации).
    "uk_management_bot/handlers/user_apartment_selection.py",
    "uk_management_bot/handlers/address_moderation.py",
    # A2-хвост волна 4: непринятые заявки менеджера. Все четыре хендлера
    # живые (триггеры генерит keyboards/admin.py).
    "uk_management_bot/handlers/unaccepted_requests.py",
    # BUG-150 (ретайр 2026-08-19): мёртвый handle_back_to_report удалён вместе
    # с клавиатурой-сиротой get_report_details_keyboard — он единственный
    # держал .query( в async def, файл входит в ратчет.
    "uk_management_bot/handlers/request_reports.py",
    # A2-хвост волна 5: комментарии к заявкам. Все восемь хендлеров имеют
    # живые генераторы триггеров (keyboards/requests.get_discussion_rows,
    # keyboards/request_comments.*, keyboards/request_reports.py + FSM-цепочка
    # внутри файла).
    "uk_management_bot/handlers/request_comments.py",
    # A2-хвост волна 5: действия модерации пользователей. Все 13 хендлеров
    # имеют живые генераторы триггеров (keyboards/user_management.py,
    # keyboards/user_verification.py).
    "uk_management_bot/handlers/user_management/actions.py",
    # BUG-154 (ретайр 2026-08-19): три мёртвых хендлера panels.py
    # ("user_mgmt_stats_with_verification", "quick_verify_", "quick_reject_")
    # удалены — они держали db в async def; остались шесть живых.
    "uk_management_bot/handlers/user_management/panels.py",
    # handlers/request_assignment.py удалён целиком тем же ретайром BUG-154
    # (мёртвый кластер: входа "assign_request_" не генерил никто, остальные
    # семь триггеров рождались внутри самой цепочки). Живое назначение заявки
    # идёт через assign_duty_/assign_specific_/assign_executor_ из
    # keyboards/admin.py и не затронуто.
    # A2-хвост волна 5: ответ заявителя на уточнение. Оба хендлера живые —
    # команду /reply_{номер} диктует живое уведомление об уточнении
    # (admin.handlers.notify_user_clarification), второй ловит FSM-состояние.
    "uk_management_bot/handlers/clarification_replies.py",
    # A2-хвост волна 6: пакет address_apartments (5 файлов одного роутера,
    # разнесён в A3 волне 3). Все хендлеры пакета живые — генераторы триггеров:
    # keyboards/address_management.py (меню адресов, карточки здания/квартиры,
    # список квартир) + внутрипакетные FSM-цепочки создания/поиска/автозаполнения.
    "uk_management_bot/handlers/address_apartments/viewing.py",
    "uk_management_bot/handlers/address_apartments/editing.py",
    "uk_management_bot/handlers/address_apartments/creation.py",
    "uk_management_bot/handlers/address_apartments/autofill.py",
    "uk_management_bot/handlers/address_apartments/details.py",
    # A2-хвост волна 6: роли и специализации пользователя. Все 11 хендлеров
    # живые (генератор триггеров — keyboards/user_management.py: 182 user_roles_,
    # 189 user_specializations_, get_roles_management_keyboard role_add_/
    # role_remove_/roles_save/roles_cancel, get_specializations_selection_keyboard
    # spec_toggle_/spec_save/spec_cancel; оба message-хендлера ловят FSM-состояния,
    # которые ставит сам файл).
    "uk_management_bot/handlers/user_management/roles_specs.py",
    "uk_management_bot/handlers/feedback.py",
    "uk_management_bot/handlers/base.py",
    "uk_management_bot/handlers/user_yards_management.py",
    "uk_management_bot/handlers/user_management/fsm.py",
    "uk_management_bot/handlers/shift_management/templates_b.py",
    # A2-хвост волна 7: создание заявки. save_request РАСКРОЕНА на sync-ядро
    # save_request_sync + async-обёртку (единственный await — загрузка медиа —
    # и раньше стоял строго ПОСЛЕ commit, PR5). Все 11 хендлеров живые.
    "uk_management_bot/handlers/requests/create.py",
    # A2-хвост волна 7: вход и регистрация по инвайту. Все семь функций живые
    # (⚠️ регистрация login_via_button по тексту «🔑 Войти» мертва — генератора
    # кнопки нет в репо — но саму функцию зовёт живой login_command /login).
    "uk_management_bot/handlers/auth.py",
    # Развилка «житель/сотрудник» на /start: собственной DB-фазы нет вовсе —
    # обе ветки делегируют в base.send_onboarding_screen и
    # auth.start_invite_registration, которые уже под run_db.
    "uk_management_bot/handlers/start_role_choice.py",
    # BUG-158 (ретайр 2026-08-19): четыре мёртвых хендлера onboarding
    # (start_onboarding, complete_onboarding, complete_onboarding_without_documents,
    # start_address_input) удалены — параметр db в async def держали ровно они.
    "uk_management_bot/handlers/onboarding.py",
    # BUG-157 механика (2026-08-19): inspector_confirm перестал открывать
    # session_scope — сохранение идёт через seam `_db` (в проде None, сессию
    # открывает run_db в потоке). Блокер был снят раскроем save_request
    # волной 7.
    "uk_management_bot/handlers/inspector_requests.py",
    # BUG-157 механика (2026-08-19): handle_confirmation перестал использовать
    # тестовый seam как прод-механизм (`_db_scope(None)` → сквозной `_db`).
    "uk_management_bot/handlers/requests/create_callbacks.py",
]

# Вызовы, запрещённые в async-функциях конвертированных модулей.
# `_db_scope` добавлен вместе с ратчетом AUD3-07: это тот же открыватель
# sync-сессии (тестовый seam, ставший бы прод-механизмом); в CONVERTED-файлах
# его нет (проверено сканом на добавлении), для неконвертированных он входит
# в метрику baseline.
_FORBIDDEN_ATTR_CALLS = {"query", "commit"}
_FORBIDDEN_NAME_CALLS = {"session_scope", "SessionLocal", "_db_scope"}


def _async_defs(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            yield node


def _violations_in(fn: ast.AsyncFunctionDef, rel: str) -> list[str]:
    problems: list[str] = []

    args = fn.args
    all_args = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    for a in all_args:
        if a.arg == "db":
            problems.append(
                f"{rel}:{fn.lineno}: async def {fn.name} объявляет параметр 'db' — "
                "aiogram DI инъецирует middleware-сессию, юнит исполнится на loop"
            )

    # Вложенные sync-функции внутри async — не территория гейта (их исполняет
    # run_db в потоке), поэтому обходим только узлы, принадлежащие самой
    # async-функции, не спускаясь во вложенные def.
    def _own_nodes(node: ast.AST):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            yield child
            yield from _own_nodes(child)

    for node in _own_nodes(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_ATTR_CALLS:
            problems.append(
                f"{rel}:{node.lineno}: async def {fn.name} зовёт .{func.attr}(...) — "
                "работа с сессией обязана жить в sync-юните под run_db"
            )
        elif isinstance(func, ast.Name) and func.id in _FORBIDDEN_NAME_CALLS:
            problems.append(
                f"{rel}:{node.lineno}: async def {fn.name} зовёт {func.id}(...) — "
                "сессию открывает run_db в worker-потоке, не хендлер"
            )
    return problems


def test_converted_handler_modules_keep_db_off_the_event_loop():
    problems: list[str] = []
    for rel in CONVERTED:
        path = ROOT / rel
        assert path.exists(), f"CONVERTED указывает на несуществующий файл: {rel}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in _async_defs(tree):
            problems.extend(_violations_in(fn, rel))
    assert not problems, "AUD3-37 ratchet:\n" + "\n".join(problems)


def test_converted_list_is_not_empty():
    """Гейт не должен тихо превратиться в пустышку при рефакторинге списка."""
    assert CONVERTED


def _session_opener_registry() -> dict[str, str]:
    """Имена функций handlers/, чьё СОБСТВЕННОЕ тело открывает sync-сессию.

    BUG-157 (транзитивная проверка, один уровень): гейт выше смотрит только на
    прямые вызовы в async-телах — sync/async-хелпер, открывающий сессию у себя
    (`_db_scope(`, `session_scope(`, `SessionLocal(`), оставался невидимым, и
    «конвертированный» модуль всё равно блокировал loop на его вызове (ровно
    так жил `_get_user_language`). Ключ — голое имя: коллизия имён даст ложное
    срабатывание, что для гейта безопаснее пропуска.
    """
    openers: dict[str, str] = {}
    opener_names = {"session_scope", "SessionLocal", "_db_scope"}
    for path in sorted((ROOT / "uk_management_bot" / "handlers").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for call in ast.walk(node):
                if (isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Name)
                        and call.func.id in opener_names):
                    openers[node.name] = f"{rel}:{node.lineno}"
                    break
    # сами открыватели тоже запрещены к вызову из async-тел
    for name in opener_names:
        openers.setdefault(name, "database/session.py")
    return openers


# Известные транзитивные блокировки loop (класс AUD3-07, деферрал владельца
# 2026-08-19): вызываемые хелперы — целые неконвертированные хендлеры
# (myrequests.show_my_requests, templates_a.handle_edit_*), их конверсия —
# отдельные волны программы. Ратчет держит НЕ-РОСТ: новый вызов открывателя из
# async-тела краснеет сразу; после конверсии хелпера строку СНЯТЬ (гейт сам
# потребует — фикс обязан пиниться уменьшением baseline).
_TRANSITIVE_BASELINE = {
    ("uk_management_bot/handlers/my_shifts/viewing.py", "open_shift_requests", "show_my_requests"),
    ("uk_management_bot/handlers/base.py", "executor_active_requests", "show_my_requests"),
    ("uk_management_bot/handlers/base.py", "executor_archive_requests", "show_my_requests"),
    ("uk_management_bot/handlers/shift_management/templates_b.py", "handle_save_template_specializations", "handle_edit_template_details"),
    ("uk_management_bot/handlers/shift_management/templates_b.py", "handle_delete_template_confirm", "handle_edit_templates"),
    ("uk_management_bot/handlers/shift_management/templates_b.py", "handle_force_delete_template", "handle_edit_templates"),
}


def test_no_transitive_session_openers_in_async_bodies():
    """BUG-157: async-тела CONVERTED-модулей не зовут хелперы, открывающие
    sync-сессию у себя, — «конвертирован» значит «loop свободен», а не «прямых
    .query() нет». Первым этим гейтом закрыт `_get_user_language` (30+
    вызывающих блокировали loop на резолве языка незаметно для гейта выше)."""
    openers = _session_opener_registry()
    found: set[tuple[str, str, str]] = set()
    problems: list[str] = []
    for rel in CONVERTED:
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for fn in _async_defs(tree):
            if fn.name in openers:
                continue  # сам открыватель проверяется реестром, не здесь
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id in openers):
                    key = (rel, fn.name, node.func.id)
                    found.add(key)
                    if key not in _TRANSITIVE_BASELINE:
                        problems.append(
                            f"{rel}:{node.lineno}: async def {fn.name} зовёт "
                            f"{node.func.id}() (открывает sync-сессию: "
                            f"{openers[node.func.id]}) — DB-фаза обязана жить "
                            "в run_db-юните"
                        )
    assert not problems, "BUG-157 transitive ratchet:\n" + "\n".join(problems)

    healed = _TRANSITIVE_BASELINE - found
    assert not healed, (
        "Транзитивных блокировок стало меньше — зафиксируйте прогресс, сняв "
        "строки из _TRANSITIVE_BASELINE:\n" + "\n".join(map(str, sorted(healed)))
    )


# ══════════════════════════════════════════════════════════════════════════
# AUD3-07 — ратчет неконвертированного остатка (деферрал владельца 2026-08-19)
# ══════════════════════════════════════════════════════════════════════════
#
# Программа A2-2 (конверсия волнами) отклонена владельцем — масштаб L не
# окупается. Вместо неё класс «sync-БД в async-хендлере» заморожен per-file
# baseline'ом по метрике этого гейта (async def с параметром `db` + запрещённые
# вызовы из _FORBIDDEN_*). Ратчет двунаправленный, по образцу
# test_aud5_arch5_broad_except_ratchet.py:
#
# * счёт ВЫШЕ baseline — регресс: новый sync-сайт в async. Конвертируйте
#   (sync-юнит под run_db) — baseline вверх не двигается никогда;
# * счёт НИЖЕ baseline — прогресс: обновите число вниз; файл, дошедший до
#   нуля, СНИМИТЕ отсюда и добавьте в CONVERTED (полный гейт строже счёта);
# * новый файл handlers/ вне CONVERTED и вне baseline обязан рождаться
#   чистым — счёт 0.
#
# Снимок 2026-09-01 (23 файла / 232 сайта; лидеры — shift_management/*).
_UNCONVERTED_BASELINE: dict[str, int] = {
    "uk_management_bot/handlers/access_control.py": 15,
    "uk_management_bot/handlers/admin/actions.py": 9,
    "uk_management_bot/handlers/admin/assignment.py": 3,
    "uk_management_bot/handlers/admin/invites.py": 6,
    "uk_management_bot/handlers/admin/lists.py": 15,
    "uk_management_bot/handlers/admin/materials.py": 4,
    "uk_management_bot/handlers/admin/shared.py": 1,
    "uk_management_bot/handlers/admin/views.py": 7,
    "uk_management_bot/handlers/auto_manager.py": 10,
    "uk_management_bot/handlers/health.py": 5,
    "uk_management_bot/handlers/requests/executor.py": 11,
    "uk_management_bot/handlers/requests/listing.py": 6,
    "uk_management_bot/handlers/requests/materials.py": 5,
    "uk_management_bot/handlers/requests/myrequests.py": 8,
    "uk_management_bot/handlers/shift_management/analytics.py": 18,
    "uk_management_bot/handlers/shift_management/assignment_a.py": 12,
    "uk_management_bot/handlers/shift_management/assignment_b.py": 16,
    "uk_management_bot/handlers/shift_management/auto_planning.py": 24,
    "uk_management_bot/handlers/shift_management/manual_planning.py": 12,
    "uk_management_bot/handlers/shift_management/schedule.py": 14,
    "uk_management_bot/handlers/shift_management/templates_a.py": 26,
    "uk_management_bot/handlers/user_management/entry.py": 1,
    "uk_management_bot/handlers/user_management/listing.py": 4,
}


def _aud337_count(path: Path, rel: str) -> int:
    """Счёт метрики гейта по файлу: сумма нарушений всех async def."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(len(_violations_in(fn, rel)) for fn in _async_defs(tree))


def test_unconverted_baseline_is_consistent():
    """Baseline не пересекается с CONVERTED и не указывает в пустоту; нулевые
    записи запрещены — файл на нуле обязан переехать в CONVERTED."""
    overlap = set(_UNCONVERTED_BASELINE) & set(CONVERTED)
    assert not overlap, f"файл и в baseline, и в CONVERTED: {sorted(overlap)}"
    missing = [rel for rel in _UNCONVERTED_BASELINE if not (ROOT / rel).exists()]
    assert not missing, f"baseline указывает на несуществующие файлы: {missing}"
    zeros = [rel for rel, n in _UNCONVERTED_BASELINE.items() if n <= 0]
    assert not zeros, (
        "нулевые записи baseline — переведите файлы в CONVERTED: " f"{zeros}"
    )


def test_aud307_unconverted_ratchet():
    grew: list[str] = []
    shrank: list[str] = []
    converted = set(CONVERTED)
    seen: set[str] = set()
    for path in sorted((ROOT / "uk_management_bot" / "handlers").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in converted:
            continue
        actual = _aud337_count(path, rel)
        expected = _UNCONVERTED_BASELINE.get(rel, 0)
        seen.add(rel)
        if actual > expected:
            grew.append(f"{rel}: {actual} > baseline {expected}")
        elif actual < expected:
            shrank.append(f"{rel}: {actual} < baseline {expected}")

    assert not grew, (
        "AUD3-07 ratchet: sync-БД в async-хендлерах выросла — DB-фаза нового "
        "кода обязана жить sync-юнитом под run_db (baseline вверх не "
        "двигается):\n" + "\n".join(grew)
    )
    assert not shrank, (
        "Sync-сайтов стало МЕНЬШЕ — отлично: обновите baseline вниз; файл на "
        "нуле снимите отсюда и добавьте в CONVERTED:\n" + "\n".join(shrank)
    )

    gone = set(_UNCONVERTED_BASELINE) - seen
    assert not gone, (
        "Файлы baseline исчезли из handlers/ (переезд/ретайр) — обновите "
        f"гейт: {sorted(gone)}"
    )


def test_no_handler_mixes_declared_db_with_run_db():
    """F1-ревью follow-up: хендлер с объявленным ``db`` не зовёт run_db напрямую.

    Такой микс держал бы ленивую middleware-сессию открытой, пока worker-поток
    берёт ВТОРОЕ соединение из того же пула — при исчерпании пула это
    самонаведённая задержка до pool_timeout. Конвертированные файлы не
    объявляют db (первый тест), неконвертированные не зовут run_db — инвариант
    держит границу между мирами для ВСЕХ файлов handlers/.
    """
    problems: list[str] = []
    for path in sorted((ROOT / "uk_management_bot" / "handlers").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in _async_defs(tree):
            args = fn.args
            declared = {a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]}
            if "db" not in declared:
                continue
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "run_db"
                ):
                    problems.append(
                        f"{rel}:{node.lineno}: async def {fn.name} объявляет db "
                        "И зовёт run_db — две сессии на один update"
                    )
    assert not problems, "AUD3-37 mix-гейт:\n" + "\n".join(problems)
