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
    # A2-хвост волна 1: address_yards сконвертирован целиком. shifts.py
    # сконвертирован в живой части, но в ратчет НЕ входит: 4 мёртвых хендлера
    # (end_shift_yes, end_shift_no, manager_active_shifts, force_end_shift —
    # генераторов их триггеров в проде нет) сохранены байт-в-байт до decision
    # владельца (прецедент BUG-137/148) и трое из них зовут session_scope в
    # async def. После ретайра/оживления — добавить сюда.
    "uk_management_bot/handlers/address_yards.py",
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
    # handlers/request_reports.py в волне 4 конвертирован в ЖИВОЙ части, но в
    # ратчет не входит: мёртвый handle_back_to_report (единственный генератор
    # префикса back_to_report_ — keyboards/request_reports.get_report_details_keyboard
    # — вызывается только в тестах) сохранён байт-в-байт до decision владельца
    # (прецедент BUG-137/148/150) и держит .query( в async def. После
    # ретайра/оживления — добавить сюда.
    # A2-хвост волна 5: комментарии к заявкам. Все восемь хендлеров имеют
    # живые генераторы триггеров (keyboards/requests.get_discussion_rows,
    # keyboards/request_comments.*, keyboards/request_reports.py + FSM-цепочка
    # внутри файла).
    "uk_management_bot/handlers/request_comments.py",
    # A2-хвост волна 5: действия модерации пользователей. Все 13 хендлеров
    # имеют живые генераторы триггеров (keyboards/user_management.py,
    # keyboards/user_verification.py).
    "uk_management_bot/handlers/user_management/actions.py",
    # handlers/user_management/panels.py в волне 5 конвертирован в ЖИВОЙ части
    # (6 хендлеров), но в ратчет не входит: три хендлера мертвы — генераторов
    # "user_mgmt_stats_with_verification", "quick_verify_", "quick_reject_" в
    # репозитории нет вовсе — и сохранены байт-в-байт до decision владельца
    # (прецедент BUG-137/148/150), продолжая держать db/.query( в async def.
    # После ретайра/оживления — добавить сюда.
    # handlers/request_assignment.py волной 5 НЕ конвертирован: инвентарь
    # показал мёртвый кластер целиком — входа "assign_request_" не генерит
    # никто, остальные семь триггеров рождаются только внутри самой цепочки
    # (или в get_report_details_keyboard без прод-вызовов). Живое назначение
    # заявки идёт через assign_duty_/assign_specific_/assign_executor_ из
    # keyboards/admin.py. Файл сохранён байт-в-байт до decision владельца.
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
    # handlers/inspector_requests.py волной 6 конвертирован в БОЛЬШЕЙ части
    # (все три сайта выбора двора/дома + три сайта sync-хелперов, которые
    # раньше открывали свой session_scope и звались из async синхронно), но в
    # ратчет не входит: inspector_confirm сохраняет session_scope, потому что
    # save_request (handlers/requests/create.py, общая с applicant-флоу
    # async-функция) внутри одной транзакции мешает sync-SQL с await'ом.
    # Добавить сюда после раскроя save_request на sync-ядро + async-обёртку.
    # A2-хвост волна 6: роли и специализации пользователя. Все 10 хендлеров
    # живые (генератор триггеров — keyboards/user_management.py: 182 user_roles_,
    # 189 user_specializations_, get_roles_management_keyboard role_add_/
    # role_remove_/roles_save/roles_cancel, get_specializations_selection_keyboard
    # spec_toggle_/spec_save/spec_cancel; оба message-хендлера ловят FSM-состояния,
    # которые ставит сам файл).
    "uk_management_bot/handlers/user_management/roles_specs.py",
]

# Вызовы, запрещённые в async-функциях конвертированных модулей.
_FORBIDDEN_ATTR_CALLS = {"query", "commit"}
_FORBIDDEN_NAME_CALLS = {"session_scope", "SessionLocal"}


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
