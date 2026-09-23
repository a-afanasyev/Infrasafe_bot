"""A9-P3-16: каждый литеральный ключ ``get_text("…")`` в коде бота есть в ru и uz.

Чистка мёртвых ключей (``scripts/locale_key_usage.py``) не должна задеть живой
ключ: ``get_text`` на отсутствующем ключе не падает, а отдаёт пользователю
САМ КЛЮЧ (``requests.foo``). Гейт ловит это на уровне файлов: вызов
``get_text``/``get_text_with_plural`` со строковым литералом первым
аргументом → ключ обязан существовать в обеих локалях.

Динамические ключи (f-строки, словари, префиксы) этим гейтом не покрыты —
их держат профильные ратчеты (``test_bug169_specialization_display`` и др.)
и анализ ``scripts/locale_key_usage.py`` перед каждой чисткой.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

# От файла теста: у пакета в importlib-режиме с conftest-стабами __file__ может быть None.
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
LOCALES = PACKAGE_ROOT / "config" / "locales"
CALLS = {"get_text", "get_text_with_plural"}


def _flatten(tree: dict, prefix: str = "") -> set[str]:
    out: set[str] = set()
    for key, value in tree.items():
        if isinstance(value, dict):
            out |= _flatten(value, f"{prefix}{key}.")
        else:
            out.add(f"{prefix}{key}")
    return out


def _is_test(path: Path) -> bool:
    rel = path.relative_to(PACKAGE_ROOT).parts
    return "tests" in rel or path.name.startswith("test_")


def _literal_keys() -> list[tuple[str, int, str]]:
    found = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if _is_test(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and node.args):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            arg = node.args[0]
            if name in CALLS and isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.append((path.relative_to(PACKAGE_ROOT).as_posix(), node.lineno, arg.value))
    return found


def test_scan_sees_get_text_calls():
    # Защита от «гейт молча ничего не нашёл» (сломался путь/парсинг).
    assert len(_literal_keys()) > 1000


def test_every_literal_get_text_key_exists_in_ru_and_uz():
    for lang in ("ru", "uz"):
        keys = _flatten(json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8")))
        missing = [f"{file}:{line}: {key}" for file, line, key in _literal_keys() if key not in keys]
        assert not missing, f"ключи get_text отсутствуют в {lang}.json:\n" + "\n".join(missing)
