"""AST-гейт A9-P2-9: Bot API из `uk_management_bot/api/**` — только через `api/telegram_send.py`.

До A9-P2-9 в API было шесть самописных httpx-клиентов к Telegram. Признак
такого клиента в коде — литерал адреса Bot API: ``"https://api.telegram.org…"``
или f-строка с сегментом ``/bot{…}`` (``/bot{token}``, ``/file/bot{token}``).
Гейт ищет их во всех строковых литералах пакета (докстринги не в счёт —
упоминание в тексте не вызов) и пропускает только сам модуль отправки.

Самопроверка на синтетике — ниже: гейт, который ничего не находит, выглядит
так же, как гейт, которому нечего найти.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
API_ROOT = REPO / "uk_management_bot" / "api"
ALLOWED = {API_ROOT / "telegram_send.py"}

_HOST = "api.telegram.org"


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                ids.add(id(body[0].value))
    return ids


def _is_bot_segment(joined: ast.JoinedStr) -> bool:
    """f-строка вида ``…/bot{X}…`` — путь метода Bot API с токеном."""
    parts = joined.values
    for part, following in zip(parts, parts[1:]):
        if (isinstance(part, ast.Constant) and isinstance(part.value, str)
                and part.value.endswith("/bot")
                and isinstance(following, ast.FormattedValue)):
            return True
    return False


def find_violations(source: str) -> list[int]:
    """Номера строк с литералами Bot API (кроме докстрингов)."""
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    in_fstring: set[int] = set()
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for part in node.values:
                in_fstring.add(id(part))
            text = "".join(
                p.value for p in node.values
                if isinstance(p, ast.Constant) and isinstance(p.value, str))
            if _HOST in text or _is_bot_segment(node):
                lines.append(node.lineno)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings and id(node) not in in_fstring
                and _HOST in node.value):
            lines.append(node.lineno)
    return sorted(set(lines))


def _api_sources() -> list[Path]:
    return sorted(
        p for p in API_ROOT.rglob("*.py")
        if p not in ALLOWED and not p.name.startswith("test_")
    )


def test_no_bot_api_literals_outside_send_module():
    offenders = []
    for path in _api_sources():
        for line in find_violations(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(REPO)}:{line}")
    assert not offenders, (
        "Вызов Telegram Bot API мимо uk_management_bot/api/telegram_send.py "
        "(A9-P2-9: общий клиент, таймаут, 403 → bot_blocked_at, лог без токена):\n"
        + "\n".join(offenders)
    )


def test_gate_scans_real_package():
    """Пустой обход (переезд пакета) дал бы ложно-зелёный гейт."""
    sources = _api_sources()
    assert len(sources) > 50
    assert all(p.exists() for p in ALLOWED)
    # Модуль отправки сам по себе гейт бы не прошёл — значит, детектор живой.
    assert find_violations((API_ROOT / "telegram_send.py").read_text(encoding="utf-8"))


@pytest.mark.parametrize("source,expected", [
    ('url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"\n', [1]),
    ('base = "https://api.telegram.org"\n', [1]),
    ('u = f"{base}/bot{token}/getMe"\n', [1]),
    ('u = f"{base}/file/bot{token}/{path}"\n', [1]),
    ('x = 1\ny = client.get(\n    "https://api.telegram.org/bot123/getMe")\n', [3]),
    ('"""Модуль ходит в api.telegram.org."""\n', []),
    ('def f():\n    """Докстринг про api.telegram.org."""\n    return 1\n', []),
    ('u = f"https://media.example/{path}"\n', []),
    ('u = f"/robot{x}"\n', []),  # оканчивается на 'bot', но не на '/bot'
    ('u = f"{a}/api/v2/{b}"\n', []),
])
def test_detector_on_synthetic_sources(source, expected):
    assert find_violations(source) == expected
