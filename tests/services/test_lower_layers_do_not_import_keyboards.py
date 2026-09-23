"""A9-P2-10: домен (services), HTTP-пакет (api) и утилиты (utils) не импортируют
UI-слой бота `uk_management_bot.keyboards`.

Справочник категорий/срочности жил в `keyboards/requests.py`, и 14 сервисов +
6 модулей api тянули его оттуда — правка клавиатуры задевала домен и HTTP-схемы.
Справочник переехал в `utils/categories.py` (keyboards ре-экспортирует те же
объекты). Гейт статический (AST), ловит и ленивые импорты внутри функций.

ALLOWED — осознанные рёбра, где нижний слой действительно шлёт Telegram-
клавиатуру (а не пользуется доменными данными). Список только сокращается:
устаревшая запись (ребра больше нет) — тоже красный тест.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "uk_management_bot"
LOWER_LAYERS = ("services", "api", "utils")
KEYBOARDS_PREFIX = "uk_management_bot.keyboards"

# (файл, модуль) — web-передача смены шлёт получателю inline-клавиатуру ответа
# (та же, что рисует бот-хендлер); это UI-артефакт, а не справочник.
ALLOWED: set[tuple[str, str]] = {
    ("uk_management_bot/api/shifts/router/transfers.py", "uk_management_bot.keyboards.shift_transfer"),
}


def _is_keyboards(module: str) -> bool:
    return module == KEYBOARDS_PREFIX or module.startswith(KEYBOARDS_PREFIX + ".")


def _keyboard_imports(source: str, rel: str) -> list[tuple[str, str, int]]:
    tree = ast.parse(source)
    hits: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if _is_keyboards(node.module):
                hits.append((rel, node.module, node.lineno))
            elif node.module == "uk_management_bot" and any(a.name == "keyboards" for a in node.names):
                hits.append((rel, KEYBOARDS_PREFIX, node.lineno))
        elif isinstance(node, ast.Import):
            for a in node.names:
                if _is_keyboards(a.name):
                    hits.append((rel, a.name, node.lineno))
    return hits


def _prod_files():
    for layer in LOWER_LAYERS:
        for path in sorted((PKG / layer).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if "/tests/" in rel or path.name.startswith("test_"):
                continue
            yield path


def _all_hits() -> list[tuple[str, str, int]]:
    return [
        h
        for p in _prod_files()
        for h in _keyboard_imports(p.read_text(encoding="utf-8"), p.relative_to(ROOT).as_posix())
    ]


def test_lower_layers_do_not_import_keyboards():
    offenders = [h for h in _all_hits() if (h[0], h[1]) not in ALLOWED]
    assert not offenders, (
        "services/api/utils импортируют UI-слой keyboards (доменные данные брать "
        "из utils/categories.py):\n"
        + "\n".join(f"{f}:{ln} {m}" for f, m, ln in offenders)
    )


def test_allowlist_has_no_stale_entries():
    present = {(f, m) for f, m, _ in _all_hits()}
    stale = ALLOWED - present
    assert not stale, f"ребро исчезло — убрать из ALLOWED: {sorted(stale)}"


def test_gate_detects_lazy_and_package_imports():
    src = (
        "def f():\n"
        "    from uk_management_bot.keyboards.requests import CATEGORY_KEYS\n"
        "from uk_management_bot import keyboards\n"
        "import uk_management_bot.keyboards.base\n"
    )
    modules = sorted(m for _, m, _ in _keyboard_imports(src, "probe.py"))
    assert modules == [
        "uk_management_bot.keyboards",
        "uk_management_bot.keyboards.base",
        "uk_management_bot.keyboards.requests",
    ]
