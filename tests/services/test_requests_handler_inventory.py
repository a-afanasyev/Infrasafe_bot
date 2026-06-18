"""ARCH-01 + CODE-04 (PR-29.2): AST-инвентаризация прямого ORM и legacy-сессий
в `handlers/requests.py`.

ЗЕЛЁНЫЙ baseline-гейт: фиксирует набор прямых ORM/data-access call-сайтов в
resident/executor-хендлере заявок как ПУСТОЙ. После выноса слоя в
`services/request_handler_service.py` хендлер — тонкий FSM/UI-слой (auth-deps,
FSM-переходы, клавиатуры, i18n, роутинг коллбэков, ветвление по статусу УЖЕ
ЗАГРУЖЕННОГО объекта). Прямого ORM (db.query/add/commit/... или <recv>.query)
в нём быть НЕ должно.

Любой НОВЫЙ прямой ORM в хендлере (db.execute/add/commit/refresh/delete/flush/
scalar/scalars/get/rollback/merge на db|session, top-level select(/update(/
delete(/insert(, либо <recv>.query(...)) ломает этот тест ОСОЗНАННО — перенесите
доступ к данным в request_handler_service.py. Если какой-то ORM-вызов
действительно невозможно вынести, добавьте его в BASELINE с инлайн-обоснованием.

ВНИМАНИЕ — что НЕ является ORM (и тест это не ловит): сравнения статуса на уже
загруженном объекте (`request.status == "В работе"`) — это UI-логика выбора
клавиатуры, она ОСТАЁТСЯ в хендлере. Тест ловит только query/session-вызовы.

CODE-04: дополнительно проверяем, что в хендлере НЕ осталось ни одного
`next(get_db())` — жизненный цикл сессии переведён на `session_scope()` (через
helper `_db_scope`).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

HANDLER_PATH = (
    Path(__file__).resolve().parents[2]
    / "uk_management_bot" / "handlers" / "requests.py"
)
HANDLER_REL = "uk_management_bot/handlers/requests.py"

# session-методы, считающиеся прямым ORM при вызове на db|session|db_session
ORM_METHODS = frozenset({
    "execute", "add", "delete", "commit", "refresh", "flush",
    "scalar", "scalars", "get", "merge", "rollback",
})
ORM_RECEIVERS = frozenset({"db", "session", "db_session"})
# top-level query-builders SQLAlchemy
QUERY_BUILDERS = frozenset({"select", "update", "delete", "insert"})


def _receiver_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return type(node).__name__


def collect_orm_sites(path: Path = HANDLER_PATH) -> set[tuple[str, str]]:
    """→ {(relpath, signal)} прямого ORM в хендлере."""
    sites: set[tuple[str, str]] = set()
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
                    sites.add((HANDLER_REL, f"{recv_name}.{fn.attr}"))
                elif fn.attr == "query":
                    sites.add((HANDLER_REL, f"{recv_name}.query"))
            # <recv>.query(...) на любом получателе (legacy Query API)
            elif fn.attr == "query":
                sites.add((HANDLER_REL, f"{_receiver_name(recv)}.query"))
        # top-level select(/update(/delete(/insert(
        elif isinstance(fn, ast.Name) and fn.id in QUERY_BUILDERS:
            sites.add((HANDLER_REL, f"{fn.id}()"))
    return sites


# ---------------------------------------------------------------------------
# BASELINE — ПУСТО (хендлер полностью очищен от прямого ORM, ARCH-01 PR-29.2).
# Весь data-access вынесен в
# uk_management_bot/services/request_handler_service.py.
# ---------------------------------------------------------------------------
BASELINE: set[tuple[str, str]] = set()


def test_requests_handler_has_no_direct_orm():
    actual = collect_orm_sites()
    new_sites = actual - BASELINE
    gone_sites = BASELINE - actual
    msg = []
    if new_sites:
        msg.append(
            "Прямой ORM в handlers/requests.py "
            "(вынесите в services/request_handler_service.py):\n"
            + "\n".join(f"  {s!r}," for s in sorted(new_sites))
        )
    if gone_sites:
        msg.append(
            "Исчезнувшие ORM-сайты (обновите BASELINE):\n"
            + "\n".join(f"  {s!r}," for s in sorted(gone_sites))
        )
    assert not msg, "\n\n".join(msg)


def test_requests_handler_has_no_next_get_db():
    """CODE-04: ни одного `next(get_db())` — только session_scope()/_db_scope."""
    source = HANDLER_PATH.read_text(encoding="utf-8")
    # Учитываем только живой код: исключаем строки-комментарии и docstring-упоминания
    matches = []
    for lineno, line in enumerate(source.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#") or "``" in line:
            continue
        if re.search(r"next\(\s*get_db\(\)\s*\)", line):
            matches.append((lineno, line.strip()))
    assert not matches, (
        "Найден legacy `next(get_db())` в handlers/requests.py "
        "(CODE-04: используйте session_scope()/_db_scope):\n"
        + "\n".join(f"  L{ln}: {txt}" for ln, txt in matches)
    )
