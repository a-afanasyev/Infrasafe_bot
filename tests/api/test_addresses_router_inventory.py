"""ARCH-05b / REFACTOR-027 (PR-28): AST-инвентаризация прямого ORM в
роутер-модулях api/addresses/.

ЗЕЛЁНЫЙ baseline-гейт: фиксирует набор прямых ORM/data-access call-сайтов во
ВСЕХ модулях роутера адресов (aggregator router.py + entity-модули stats.py /
yards.py / buildings.py / apartments.py / moderation.py + общий _helpers.py)
как ПУСТОЙ. Весь data-access вынесен в services/addresses/core.py (мутации) и
services/addresses/queries.py (чтения + hard-purge). Роутер-модули — тонкий
HTTP-слой (auth-deps, парсинг, сериализация ответа, HTTPException).

Любой НОВЫЙ прямой ORM в роутер-модулях (db.execute/add/commit/refresh/delete/
flush/scalar/scalars/get на db|session, top-level select(/update(/delete(/
insert(, либо <recv>.query(...)) ломает этот тест ОСОЗНАННО — перенесите доступ
к данным в core.py/queries.py. Если какой-то ORM-вызов действительно невозможно
вынести, добавьте его в BASELINE с инлайн-обоснованием.

Зеркало tests/api/test_shifts_router_inventory.py (PR-27).
"""

from __future__ import annotations

import ast
from pathlib import Path

ADDRESSES_DIR = (
    Path(__file__).resolve().parents[2]
    / "uk_management_bot" / "api" / "addresses"
)
PKG_ROOT = ADDRESSES_DIR.parents[2]  # repo root (parent of uk_management_bot)

# Модули, которые НЕ являются роутер-слоем (схемы / обработчики исключений /
# пакетный __init__) — их не сканируем.
EXCLUDED_NAMES = frozenset({"schemas.py", "exception_handlers.py", "__init__.py"})

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


def _route_modules() -> list[Path]:
    return [
        p for p in sorted(ADDRESSES_DIR.glob("*.py"))
        if p.name not in EXCLUDED_NAMES
    ]


def collect_orm_sites() -> set[tuple[str, str]]:
    """→ {(relpath, signal)} прямого ORM во всех роутер-модулях адресов."""
    sites: set[tuple[str, str]] = set()
    for path in _route_modules():
        rel = str(path.relative_to(PKG_ROOT))
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
# BASELINE — ПУСТО (роутер-модули полностью очищены от прямого ORM, ARCH-05b
# 2026-06-18). Весь data-access вынесен в services/addresses/core.py (мутации) и
# services/addresses/queries.py (чтения + hard-purge).
# ---------------------------------------------------------------------------
BASELINE: set[tuple[str, str]] = set()


def test_addresses_router_modules_have_no_direct_orm():
    actual = collect_orm_sites()
    new_sites = actual - BASELINE
    gone_sites = BASELINE - actual
    msg = []
    if new_sites:
        msg.append(
            "Прямой ORM в api/addresses/ роутер-модулях "
            "(вынесите в services/addresses/core.py|queries.py):\n"
            + "\n".join(f"  {s!r}," for s in sorted(new_sites))
        )
    if gone_sites:
        msg.append(
            "Исчезнувшие ORM-сайты (обновите BASELINE):\n"
            + "\n".join(f"  {s!r}," for s in sorted(gone_sites))
        )
    assert not msg, "\n\n".join(msg)


def test_addresses_router_modules_are_scanned():
    """Sanity: the glob picks up the aggregator + all entity modules."""
    names = {p.name for p in _route_modules()}
    expected = {
        "router.py", "stats.py", "yards.py",
        "buildings.py", "apartments.py", "moderation.py", "_helpers.py",
    }
    assert expected <= names, f"missing route modules: {expected - names}"
