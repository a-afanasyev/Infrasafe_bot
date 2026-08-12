"""ARCH-05a (PR-27): AST-инвентаризация прямого ORM в api/shifts/router/.

ЗЕЛЁНЫЙ baseline-гейт: фиксирует набор прямых ORM/data-access call-сайтов в
роутере смен как ПУСТОЙ. После выноса слоя в `api/shifts/service` роутер —
тонкий HTTP-слой (auth-deps, парсинг, сериализация, HTTPException). Прямого
ORM в нём быть НЕ должно.

AUD5-ARCH-3 волна 8: router.py разнесён block-move на пакет
`api/shifts/router/` — гейт агрегирует ВСЕ .py-файлы пакета (включая
`_helpers.py`/`__init__.py`), чтобы разнос не сузил охват (урок волны 6:
гейт по одному файлу на пакете становится вакуумным).

Любой НОВЫЙ прямой ORM в роутере (db.execute/add/commit/refresh/delete/flush/
scalar/scalars/get на db|session, top-level select(/update(/delete(/insert(,
либо <recv>.query(...)) ломает этот тест ОСОЗНАННО — перенесите доступ к данным
в api/shifts/service. Если какой-то ORM-вызов действительно невозможно вынести,
добавьте его в BASELINE с инлайн-обоснованием.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER_PKG = _REPO_ROOT / "uk_management_bot" / "api" / "shifts" / "router"

# session-методы, считающиеся прямым ORM при вызове на db|session
ORM_METHODS = frozenset({
    "execute", "add", "delete", "commit", "refresh", "flush",
    "scalar", "scalars", "get",
})
ORM_RECEIVERS = frozenset({"db", "session"})
# top-level query-builders SQLAlchemy
QUERY_BUILDERS = frozenset({"select", "update", "delete", "insert"})


def _router_files() -> list[Path]:
    """Все .py пакета роутера. Пустой список = разнос сломал гейт молча."""
    assert ROUTER_PKG.is_dir(), (
        f"{ROUTER_PKG} не найден — пакет роутера переехал? Обнови ROUTER_PKG."
    )
    files = sorted(ROUTER_PKG.glob("*.py"))
    assert files, f"в {ROUTER_PKG} нет .py-файлов — гейт стал вакуумным"
    return files


def _receiver_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return type(node).__name__


def collect_orm_sites() -> set[tuple[str, str]]:
    """→ {(relpath, signal)} прямого ORM по всем файлам пакета роутера."""
    sites: set[tuple[str, str]] = set()
    for path in _router_files():
        rel = path.relative_to(_REPO_ROOT).as_posix()
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
# BASELINE — ПУСТО (роутер полностью очищен от прямого ORM, ARCH-05a 2026-06-18).
# Весь data-access вынесен в uk_management_bot/api/shifts/service.
# ---------------------------------------------------------------------------
BASELINE: set[tuple[str, str]] = set()


def test_shifts_router_has_no_direct_orm():
    actual = collect_orm_sites()
    new_sites = actual - BASELINE
    gone_sites = BASELINE - actual
    msg = []
    if new_sites:
        msg.append(
            "Прямой ORM в api/shifts/router/ (вынесите в api/shifts/service):\n"
            + "\n".join(f"  {s!r}," for s in sorted(new_sites))
        )
    if gone_sites:
        msg.append(
            "Исчезнувшие ORM-сайты (обновите BASELINE):\n"
            + "\n".join(f"  {s!r}," for s in sorted(gone_sites))
        )
    assert not msg, "\n\n".join(msg)
