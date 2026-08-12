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
    "uk_management_bot/handlers/user_verification.py",
    "uk_management_bot/handlers/request_status_management.py",
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
