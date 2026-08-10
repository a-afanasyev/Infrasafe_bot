"""AUD5-ARCH-2 (волны 2–3): AST-инвентаризация прямого ORM в тонких роутерах.

ЗЕЛЁНЫЙ baseline-гейт по образцу test_requests_router_inventory.py (волна 1):
фиксирует набор прямых ORM/data-access call-сайтов в роутерах auth, callcenter,
feedback, materials, profile, public, registration и обоих work_reports как ПУСТОЙ. Data-access каждого вынесен в
соседний `service.py`; роутер — тонкий HTTP-слой (auth-deps, парсинг,
валидация, сериализация, HTTPException, маппинг доменных ошибок).

Любой НОВЫЙ прямой ORM в этих роутерах (db.execute/add/commit/refresh/delete/
flush/scalar/scalars/get на db|session, top-level select(/update(/delete(/
insert(, либо <recv>.query(...)) ломает этот тест ОСОЗНАННО — перенесите
доступ к данным в service.py модуля. Если какой-то ORM-вызов действительно
невозможно вынести, добавьте его в BASELINE с инлайн-обоснованием.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_API_ROOT = Path(__file__).resolve().parents[2] / "uk_management_bot" / "api"

ROUTERS: dict[str, str] = {
    "auth": "uk_management_bot/api/auth/router.py",
    "callcenter": "uk_management_bot/api/callcenter/router.py",
    "feedback": "uk_management_bot/api/feedback/router.py",
    "materials": "uk_management_bot/api/materials/router.py",
    "profile": "uk_management_bot/api/profile/router.py",
    "public": "uk_management_bot/api/public/router.py",
    "registration": "uk_management_bot/api/registration/router.py",
    "work_reports": "uk_management_bot/api/work_reports/router.py",
    "work_reports_public": "uk_management_bot/api/work_reports/public_router.py",
}

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


def collect_orm_sites(rel: str) -> set[tuple[str, str]]:
    """→ {(relpath, signal)} прямого ORM в роутере."""
    path = _API_ROOT.parent.parent / rel
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
# BASELINE — ПУСТО для всех четырёх (роутеры очищены, AUD5-ARCH-2 волна 2).
# Весь data-access — в uk_management_bot/api/<module>/service.py.
# ---------------------------------------------------------------------------
BASELINE: dict[str, set[tuple[str, str]]] = {
    "auth": set(),
    "callcenter": set(),
    "feedback": set(),
    "materials": set(),
    "profile": set(),
    "public": set(),
    "registration": set(),
    "work_reports": set(),
    "work_reports_public": set(),
}


@pytest.mark.parametrize("name", sorted(ROUTERS))
def test_router_has_no_direct_orm(name: str):
    rel = ROUTERS[name]
    actual = collect_orm_sites(rel)
    baseline = BASELINE[name]
    new_sites = actual - baseline
    gone_sites = baseline - actual
    msg = []
    if new_sites:
        msg.append(
            f"Прямой ORM в {rel} (вынесите в api/{name}/service.py):\n"
            + "\n".join(f"  {s!r}," for s in sorted(new_sites))
        )
    if gone_sites:
        msg.append(
            "Исчезнувшие ORM-сайты (обновите BASELINE):\n"
            + "\n".join(f"  {s!r}," for s in sorted(gone_sites))
        )
    assert not msg, "\n\n".join(msg)
