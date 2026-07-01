"""ARCH-01 + CODE-04 (PR-29.1): AST-инвентаризация прямого ORM и legacy-сессий
в `handlers/shift_management.py`.

ЗЕЛЁНЫЙ baseline-гейт: фиксирует набор прямых ORM/data-access call-сайтов в
хендлере управления сменами как ПУСТОЙ. После выноса слоя в
`services/shift_management_service.py` хендлер — тонкий FSM/UI-слой (auth-deps,
FSM-переходы, клавиатуры, i18n, роутинг коллбэков). Прямого ORM в нём быть НЕ
должно.

Любой НОВЫЙ прямой ORM в хендлере (db.execute/add/commit/refresh/delete/flush/
scalar/scalars/get/rollback/merge на db|session, top-level select(/update(/
delete(/insert(, либо <recv>.query(...)) ломает этот тест ОСОЗНАННО — перенесите
доступ к данным в shift_management_service.py. Если какой-то ORM-вызов
действительно невозможно вынести, добавьте его в BASELINE с инлайн-обоснованием.

CODE-04: дополнительно проверяем, что в хендлере НЕ осталось ни одного
`next(get_db())` — жизненный цикл сессии переведён на `session_scope()` (через
helper `_db_scope`).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

# AUD3-06: shift_management.py разбит на пакет handlers/shift_management/ —
# сканируем все модули пакета.
HANDLER_DIR = (
    Path(__file__).resolve().parents[2]
    / "uk_management_bot" / "handlers" / "shift_management"
)
PACKAGE_FILES = sorted(HANDLER_DIR.glob("*.py"))


def _relpath(p: Path) -> str:
    return f"uk_management_bot/handlers/shift_management/{p.name}"

# session-методы, считающиеся прямым ORM при вызове на db|session
ORM_METHODS = frozenset({
    "execute", "add", "delete", "commit", "refresh", "flush",
    "scalar", "scalars", "get", "merge", "rollback",
})
ORM_RECEIVERS = frozenset({"db", "session"})
# top-level query-builders SQLAlchemy
QUERY_BUILDERS = frozenset({"select", "update", "delete", "insert"})


def _receiver_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return type(node).__name__


def collect_orm_sites(files: list[Path] = PACKAGE_FILES) -> set[tuple[str, str]]:
    """→ {(relpath, signal)} прямого ORM во всех модулях shift_management-пакета."""
    sites: set[tuple[str, str]] = set()
    for path in files:
        rel = _relpath(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            # db.execute(...) / session.scalars(...) / db.query(...) / db.add(...)
            if isinstance(fn, ast.Attribute):
                recv = fn.value
                recv_name = recv.id if isinstance(recv, ast.Name) else None
                if recv_name in ORM_RECEIVERS:
                    if fn.attr in ORM_METHODS:
                        sites.add((rel, f"{recv_name}.{fn.attr}"))
                    elif fn.attr == "query":
                        sites.add((rel, f"{recv_name}.query"))
                # <recv>.query(...) на любом получателе (legacy Query API)
                elif fn.attr == "query":
                    sites.add((rel, f"{_receiver_name(recv)}.query"))
            # top-level select(/update(/delete(/insert(
            elif isinstance(fn, ast.Name) and fn.id in QUERY_BUILDERS:
                sites.add((rel, f"{fn.id}()"))
    return sites


# ---------------------------------------------------------------------------
# BASELINE — ПУСТО (хендлер полностью очищен от прямого ORM, ARCH-01 PR-29.1).
# Весь data-access вынесен в
# uk_management_bot/services/shift_management_service.py.
# ---------------------------------------------------------------------------
BASELINE: set[tuple[str, str]] = set()


def test_shift_management_handler_has_no_direct_orm():
    actual = collect_orm_sites()
    new_sites = actual - BASELINE
    gone_sites = BASELINE - actual
    msg = []
    if new_sites:
        msg.append(
            "Прямой ORM в handlers/shift_management.py "
            "(вынесите в services/shift_management_service.py):\n"
            + "\n".join(f"  {s!r}," for s in sorted(new_sites))
        )
    if gone_sites:
        msg.append(
            "Исчезнувшие ORM-сайты (обновите BASELINE):\n"
            + "\n".join(f"  {s!r}," for s in sorted(gone_sites))
        )
    assert not msg, "\n\n".join(msg)


def test_shift_management_handler_has_no_next_get_db():
    """CODE-04: ни одного `next(get_db())` — только session_scope()/_db_scope."""
    # Учитываем только живой код: исключаем строки-комментарии и docstring-упоминания
    matches = []
    for path in PACKAGE_FILES:
        rel = _relpath(path)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#") or "``" in line:
                continue
            if re.search(r"next\(\s*get_db\(\)\s*\)", line):
                matches.append((rel, lineno, line.strip()))
    assert not matches, (
        "Найден legacy `next(get_db())` в handlers/shift_management/ "
        "(CODE-04: используйте session_scope()/_db_scope):\n"
        + "\n".join(f"  {rel} L{ln}: {txt}" for rel, ln, txt in matches)
    )
