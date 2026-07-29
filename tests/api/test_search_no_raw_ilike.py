"""Гейт: голого `.ilike(` в коде не остаётся — только через `utils/sql_search`.

Почему гейт, а не тест на каждый поиск: прод-кластер в локали `C`, и там
`ILIKE` не сворачивает регистр кириллицы (`docs/bugs-2026-07-28.md`, BUG-1).
Дефект **невидим для сьюта** — он гоняется на sqlite, где `ILIKE` эмулируется
питоновским слоем SQLAlchemy и кириллицу сворачивает. Поэтому единственный
надёжный способ не завести его снова — запретить конструкцию как таковую.

BASELINE пустой. Новый `.ilike(` ломает этот тест ОСОЗНАННО: пользуйтесь
`sql_search.ci_contains(column, pattern, is_postgres=...)`, иначе поиск молча
не найдёт русские имена на проде и будет зелёным в CI.
"""

from __future__ import annotations

import ast
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[2] / "uk_management_bot"

# Единственное место, где `.ilike` легитимен — sqlite-ветка самого хелпера.
ALLOWED = frozenset({PKG_ROOT / "utils" / "sql_search.py"})


def _ilike_sites() -> list[str]:
    found: list[str] = []
    for path in sorted(PKG_ROOT.rglob("*.py")):
        if path in ALLOWED:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover — не наш файл
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "ilike"
            ):
                rel = path.relative_to(PKG_ROOT.parent)
                found.append(f"{rel}:{node.lineno}")
    return found


def test_no_raw_ilike_outside_helper():
    sites = _ilike_sites()
    assert sites == [], (
        "Голый .ilike() не работает с кириллицей в локали C (прод). "
        "Замените на sql_search.ci_contains(...):\n  " + "\n  ".join(sites)
    )
