"""AUD8-CODE-02: в коде бота (handlers/services) нет `print(` — только logger.

`print` идёт в stdout мимо structured_logging и агрегации; в живом хендлере
(`handlers/admin/lists.py:156`) он выводил результат проверки доступа.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "uk_management_bot"
SCOPES = (ROOT / "handlers", ROOT / "services")


def _print_calls(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    ]


def test_no_print_calls_in_handlers_and_services() -> None:
    offenders = []
    for scope in SCOPES:
        for path in sorted(scope.rglob("*.py")):
            if "/tests/" in str(path):
                continue
            for line in _print_calls(path):
                offenders.append(f"{path.relative_to(ROOT.parent)}:{line}")
    assert not offenders, "print() вместо logger: " + ", ".join(offenders)
