"""Ратчет: карту «категория → специализация» читать ТОЛЬКО через хелпер.

`get_specialization_for_category` резолвит legacy RU-лейблы и даёт дефолт
`repair`; прямой `CATEGORY_TO_SPECIALIZATION.get(...)` в `dispatch.py`,
`handlers/admin/shared.py` и `api/requests/router.py` обходил и то, и другое:
неизвестная (или legacy «Интернет») категория молча оставляла заявку «Новая».

Проверка по AST, а не подстроке: имя карты живёт в докстрингах
`dispatch.py`, `schemas.py`, `router.py` — grep был бы красным навсегда.
"""

import ast
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MAP_NAME = "CATEGORY_TO_SPECIALIZATION"
_ALLOWED = {
    _ROOT / "constants" / "categories.py",       # владелец карты
    _ROOT / "constants" / "test_categories.py",  # её собственные тесты
}


def _sources():
    for path in sorted(_ROOT.rglob("*.py")):
        if "tests" in path.parts or path in _ALLOWED:
            continue
        yield path


@pytest.mark.parametrize("path", list(_sources()), ids=lambda p: str(p.relative_to(_ROOT)))
def test_map_is_not_read_directly(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if (isinstance(node, ast.Name) and node.id == _MAP_NAME)
        or (isinstance(node, ast.ImportFrom)
            and any(alias.name == _MAP_NAME for alias in node.names))
    ]
    assert offenders == [], (
        f"{path.relative_to(_ROOT)}: строки {offenders} — карту читать только через "
        f"`get_specialization_for_category` (резолв legacy + дефолт repair)"
    )


def test_dispatch_resolves_unknown_and_legacy_like_the_helper():
    from uk_management_bot.services.dispatch import _specialization_for

    assert _specialization_for("нет-такой") == "repair"
    assert _specialization_for("Интернет") == "electrician"
    assert _specialization_for("") is None
    assert _specialization_for(None) is None
