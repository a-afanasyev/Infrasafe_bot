"""A9-P2-10: доменный справочник категорий/срочности — `utils/categories.py`.

`keyboards/requests.py` ре-экспортирует ТЕ ЖЕ объекты (identity), чтобы
хендлеры и monkeypatch по старому пути продолжали работать.
"""
import ast
from pathlib import Path
from unittest.mock import patch

import pytest

from uk_management_bot.utils import categories

GET_TEXT_PATH = "uk_management_bot.utils.categories.get_text"

REEXPORTED = (
    "CATEGORY_KEYS",
    "CATEGORY_DEFINITIONS",
    "CATEGORY_INTERNAL_KEYS",
    "CANONICAL_CATEGORY_KEYS",
    "SELECTABLE_CATEGORY_KEYS",
    "URGENCY_KEYS",
    "URGENCY_INTERNAL_KEYS",
    "get_category_display",
    "resolve_category_key",
    "get_urgency_display",
)


def _echo(key, language="ru", **kwargs):
    return key


@pytest.mark.parametrize("name", REEXPORTED)
def test_keyboards_reexports_same_object(name):
    from uk_management_bot.keyboards import requests as kb

    assert getattr(kb, name) is getattr(categories, name)


def test_categories_module_has_no_ui_imports():
    src = Path(categories.__file__).read_text(encoding="utf-8")
    modules = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(a.name for a in node.names)
    bad = [m for m in modules if m.startswith(("aiogram", "uk_management_bot.keyboards"))]
    assert not bad, bad


def test_selectable_excludes_service_categories():
    assert "engineering" in categories.CANONICAL_CATEGORY_KEYS
    assert "engineering" not in categories.SELECTABLE_CATEGORY_KEYS
    assert set(categories.CATEGORY_INTERNAL_KEYS) <= set(categories.CANONICAL_CATEGORY_KEYS)


class TestGetCategoryDisplay:
    def test_known_key_returns_localized(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            assert categories.get_category_display("electricity") == "categories.electricity"

    def test_unknown_key_returns_as_is(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            assert categories.get_category_display("unknown_cat") == "unknown_cat"


class TestResolveCategoryKey:
    def test_internal_key_passthrough(self):
        assert categories.resolve_category_key("electricity") == "electricity"

    def test_legacy_text_resolved(self):
        assert categories.resolve_category_key("Электрика") == "electricity"

    def test_unknown_value_returned_as_is(self):
        assert categories.resolve_category_key("НеизвестноеЗначение") == "НеизвестноеЗначение"

    def test_internet_legacy_text(self):
        assert categories.resolve_category_key("Интернет/ТВ") == "internet"


class TestGetUrgencyDisplay:
    def test_known_key_returns_localized(self):
        with patch(GET_TEXT_PATH, side_effect=lambda k, language="ru": f"L:{k}"):
            assert categories.get_urgency_display("low") == "L:urgency.low"

    def test_missing_locale_falls_back_to_key(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            assert categories.get_urgency_display("low") == "low"

    def test_unknown_key_returned_as_is(self):
        assert categories.get_urgency_display("bogus") == "bogus"
