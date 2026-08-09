"""AUD5-ARCH-2 (волна 1): AST-инвентаризация прямого ORM в api/requests/router.py.

ЗЕЛЁНЫЙ baseline-гейт: фиксирует набор прямых ORM/data-access call-сайтов в
роутере заявок как ПУСТОЙ. После выноса слоя в `api/requests/service.py` роутер —
тонкий HTTP-слой (auth-deps, парсинг, сериализация, HTTPException). Прямого
ORM в нём быть НЕ должно.

Любой НОВЫЙ прямой ORM в роутере (db.execute/add/commit/refresh/delete/flush/
scalar/scalars/get на db|session, top-level select(/update(/delete(/insert(,
либо <recv>.query(...)) ломает этот тест ОСОЗНАННО — перенесите доступ к данным
в service.py. Если какой-то ORM-вызов действительно невозможно вынести, добавьте
его в BASELINE с инлайн-обоснованием.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROUTER_PATH = (
    Path(__file__).resolve().parents[2]
    / "uk_management_bot" / "api" / "requests" / "router.py"
)
ROUTER_REL = "uk_management_bot/api/requests/router.py"

# session-методы, считающиеся прямым ORM при вызове на db|session
ORM_METHODS = frozenset({
    "execute", "add", "delete", "commit", "refresh", "flush",
    "scalar", "scalars", "get",
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


def collect_orm_sites(path: Path = ROUTER_PATH) -> set[tuple[str, str]]:
    """→ {(relpath, signal)} прямого ORM в роутере."""
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
                    sites.add((ROUTER_REL, f"{recv_name}.{fn.attr}"))
                elif fn.attr == "query":
                    sites.add((ROUTER_REL, f"{recv_name}.query"))
            # <recv>.query(...) на любом получателе (legacy Query API)
            elif fn.attr == "query":
                sites.add((ROUTER_REL, f"{_receiver_name(recv)}.query"))
        # top-level select(/update(/delete(/insert(
        elif isinstance(fn, ast.Name) and fn.id in QUERY_BUILDERS:
            sites.add((ROUTER_REL, f"{fn.id}()"))
    return sites


# ---------------------------------------------------------------------------
# BASELINE — ПУСТО (роутер полностью очищен от прямого ORM, AUD5-ARCH-2 2026-08-09).
# Весь data-access вынесен в uk_management_bot/api/requests/service.py.
# ---------------------------------------------------------------------------
BASELINE: set[tuple[str, str]] = set()


def test_requests_router_has_no_direct_orm():
    actual = collect_orm_sites()
    new_sites = actual - BASELINE
    gone_sites = BASELINE - actual
    msg = []
    if new_sites:
        msg.append(
            "Прямой ORM в api/requests/router.py (вынесите в api/requests/service.py):\n"
            + "\n".join(f"  {s!r}," for s in sorted(new_sites))
        )
    if gone_sites:
        msg.append(
            "Исчезнувшие ORM-сайты (обновите BASELINE):\n"
            + "\n".join(f"  {s!r}," for s in sorted(gone_sites))
        )
    assert not msg, "\n\n".join(msg)
