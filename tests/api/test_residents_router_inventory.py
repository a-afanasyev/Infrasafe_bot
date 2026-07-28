"""AST-инвентаризация прямого ORM в роутер-модулях `api/residents/`.

Зеркало `tests/api/test_addresses_router_inventory.py` (ARCH-05b) для нового
домена «Жители». BASELINE пустой С РОЖДЕНИЯ: домен спроектирован так, что весь
data-access живёт в `services/residents/queries.py` (чтения) и
`services/residents/core.py` (мутации), а роутер-модули — тонкий HTTP-слой
(auth-deps, парсинг, сериализация, HTTPException).

Любой НОВЫЙ прямой ORM в роутере ломает этот тест ОСОЗНАННО — перенесите
доступ к данным в services/residents/.
"""

from __future__ import annotations

import ast
from pathlib import Path

RESIDENTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "uk_management_bot" / "api" / "residents"
)
PKG_ROOT = RESIDENTS_DIR.parents[2]  # repo root (parent of uk_management_bot)

# Не роутер-слой — не сканируем.
EXCLUDED_NAMES = frozenset({"schemas.py", "exception_handlers.py", "__init__.py"})

ORM_METHODS = frozenset({
    "execute", "add", "delete", "commit", "refresh", "flush",
    "scalar", "scalars", "get",
})
ORM_RECEIVERS = frozenset({"db", "session"})
QUERY_BUILDERS = frozenset({"select", "update", "delete", "insert"})


def _receiver_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return type(node).__name__


def _route_modules() -> list[Path]:
    return [
        p for p in sorted(RESIDENTS_DIR.glob("*.py"))
        if p.name not in EXCLUDED_NAMES
    ]


def collect_orm_sites() -> set[tuple[str, str]]:
    """→ {(relpath, signal)} прямого ORM во всех роутер-модулях жителей."""
    sites: set[tuple[str, str]] = set()
    for path in _route_modules():
        rel = str(path.relative_to(PKG_ROOT))
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if isinstance(fn, ast.Attribute):
                recv = fn.value
                recv_name = recv.id if isinstance(recv, ast.Name) else None
                if recv_name in ORM_RECEIVERS:
                    if fn.attr in ORM_METHODS:
                        sites.add((rel, f"{recv_name}.{fn.attr}"))
                    elif fn.attr == "query":
                        sites.add((rel, f"{recv_name}.query"))
                elif fn.attr == "query":
                    sites.add((rel, f"{_receiver_name(recv)}.query"))
            elif isinstance(fn, ast.Name) and fn.id in QUERY_BUILDERS:
                sites.add((rel, f"{fn.id}()"))
    return sites


BASELINE: set[tuple[str, str]] = set()


def test_residents_router_modules_have_no_direct_orm():
    actual = collect_orm_sites()
    new_sites = actual - BASELINE
    gone_sites = BASELINE - actual
    msg = []
    if new_sites:
        msg.append(
            "Прямой ORM в api/residents/ роутер-модулях "
            "(вынесите в services/residents/core.py|queries.py):\n"
            + "\n".join(f"  {s!r}," for s in sorted(new_sites))
        )
    if gone_sites:
        msg.append(
            "Исчезнувшие ORM-сайты (обновите BASELINE):\n"
            + "\n".join(f"  {s!r}," for s in sorted(gone_sites))
        )
    assert not msg, "\n\n".join(msg)


def test_residents_router_modules_are_scanned():
    """Sanity: glob действительно видит агрегатор и модули домена."""
    names = {p.name for p in _route_modules()}
    expected = {"router.py", "residents.py"}
    assert expected <= names, f"missing route modules: {expected - names}"
