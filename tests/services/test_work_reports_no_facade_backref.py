"""AUD7-SIMP-03: модули пакета work_reports не ходят обратно к фасаду.

`services/work_report_service.py` — публичный фасад-реэкспорт (AUD6-P2-56).
Ради monkeypatch старых тестов подмодули пакета звали друг друга через
`_svc()` → фасад: граф зависимостей шёл по кругу «модуль → фасад → модуль»,
а тесты подменяли атрибуты не там, где они используются. Теперь подмодули
импортируют зависимости напрямую, тесты патчат точку использования
(`services.work_reports.<module>.<name>`), фасад остаётся только для внешних
потребителей. Гейт статический (AST): импорт фасада из пакета — красный.
"""
from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "uk_management_bot" / "services" / "work_reports"
FACADE = "uk_management_bot.services.work_report_service"


def _facade_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [a.name for a in node.names]
            if node.module == FACADE or (
                node.module == "uk_management_bot.services" and "work_report_service" in names
            ):
                hits.append(f"{path.name}:{node.lineno}")
        elif isinstance(node, ast.Import):
            if any(a.name == FACADE for a in node.names):
                hits.append(f"{path.name}:{node.lineno}")
    return hits


def test_package_modules_do_not_import_the_facade():
    hits = [h for p in sorted(PACKAGE.glob("*.py")) for h in _facade_imports(p)]
    assert not hits, f"подмодули work_reports импортируют собственный фасад: {hits}"


def test_no_svc_indirection_left():
    left = [p.name for p in sorted(PACKAGE.glob("*.py")) if "_svc()" in p.read_text(encoding="utf-8")]
    assert not left, f"обратный доступ к фасаду через _svc(): {left}"
