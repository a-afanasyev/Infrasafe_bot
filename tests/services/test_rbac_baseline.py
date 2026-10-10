"""RBAC этап 0: текущая матрица прав совпадает со снимком.

Снимок (tests/rbac_baseline/*.json) строит `tests/rbac_baseline/builder.py`: каждый
гейт API ядра, API охраны и бота вызывается с синтетическими пользователями
всех ролевых профилей прода, результат «точка входа × профиль → пропуск»
сравнивается с файлом. Плюс инвентарь inline-проверок по ролям.

Красный тест = изменились полномочия (или карта мест, где они решаются).
Это НЕ повод перегенерировать снимок молча: при переходе на действия матрица
обязана остаться прежней. Осознанное изменение прав — отдельный PR с
решением владельца, перегенерация `python tests/rbac_baseline/builder.py --write`
и разбором диффа в описании.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "rbac_baseline" / "builder.py"
if "rbac_baseline" not in sys.modules:
    # dataclass при exec_module требует модуль уже зарегистрированным.
    _spec = importlib.util.spec_from_file_location("rbac_baseline", _SCRIPT)
    sys.modules["rbac_baseline"] = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(sys.modules["rbac_baseline"])
rbac_baseline = sys.modules["rbac_baseline"]

# Нижние границы охвата: защита от «вакуумного» снимка, если генератор
# перестанет находить точки (переезд пакета, смена способа подключения).
MIN_ENTRIES = {
    "core_api": 200,
    "access_api": 60,
    "bot_handlers": 90,
}
MATRICES = sorted(MIN_ENTRIES)


def _diff(expected: dict, actual: dict) -> str:
    added = sorted(set(actual) - set(expected))
    removed = sorted(set(expected) - set(actual))
    changed = sorted(k for k in set(actual) & set(expected) if actual[k] != expected[k])
    lines = []
    for title, keys in (("новые", added), ("исчезли", removed), ("изменились", changed)):
        if keys:
            lines.append(f"{title} ({len(keys)}):")
            for key in keys[:15]:
                lines.append(f"  {key}: было {expected.get(key)} → стало {actual.get(key)}")
    return "\n".join(lines)


@pytest.mark.parametrize("name", MATRICES)
def test_rights_matrix_matches_baseline(name):
    path = rbac_baseline.baseline_path(name)
    assert path.exists(), f"нет снимка {path}; сгенерируйте --write осознанно"
    expected = json.loads(path.read_text(encoding="utf-8"))
    actual = json.loads(rbac_baseline.dump(rbac_baseline.build(name)))
    assert len(actual["entries"]) >= MIN_ENTRIES[name], "снимок стал вакуумным"
    assert actual.get("_profiles") == expected.get("_profiles"), "изменился набор профилей"
    assert actual["entries"] == expected["entries"], (
        f"матрица прав «{name}» разошлась со снимком — изменение полномочий:\n"
        + _diff(expected["entries"], actual["entries"])
    )


def test_role_literal_comparisons_ratchet():
    """Сравнения роли со строкой в теле функции: только убывают.

    Новое сравнение — это право, захардкоженное мимо матрицы: проверяйте
    действие (`uk_management_bot.authz`). Исключение — доменное правило о
    человеке-объекте («назначить можно только исполнителя»): такое сравнение
    добавляется в снимок осознанно, с обоснованием в PR.
    """
    expected = json.loads(rbac_baseline.baseline_path("inline_checks").read_text())["entries"]
    actual = rbac_baseline.snapshot_inline_checks()
    grown = {k: sorted(set(v) - set(expected.get(k, [])))
             for k, v in actual.items() if set(v) - set(expected.get(k, []))}
    assert not grown, (
        "новые сравнения с именем роли — используйте действие из authz/catalog.py:\n"
        + "\n".join(f"  {k}: {v}" for k, v in sorted(grown.items()))
    )
    assert actual == expected, (
        "сравнений стало меньше — опустите базу: "
        "python tests/rbac_baseline/builder.py --write inline_checks\n"
        + _diff(expected, actual)
    )


# Гейты по именам ролей, вытесненные действиями (RBAC A1). Разрешены только их
# определения (совместимость и тесты самой механики).
_LEGACY_GATES = ("require_roles", "require_approved_roles", "require_role", "RoleGate")
_LEGACY_GATE_HOMES = {
    "uk_management_bot/api/dependencies.py",
    "uk_management_bot/middlewares/auth.py",
    "uk_management_bot/handlers/_role_gate.py",
}


def test_no_role_name_gates_in_production_code():
    """Новые гейты — только через действия: require_action / ActionGate / can."""
    import ast

    root = Path(__file__).resolve().parents[2]
    offenders = []
    for top in ("uk_management_bot", "access_control"):
        for path in sorted((root / top).rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            if (rel in _LEGACY_GATE_HOMES or path.name.startswith("test_")
                    or path.name == "conftest.py" or "/tests/" in rel):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call):
                    func = node.func
                    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                    if name in _LEGACY_GATES:
                        offenders.append(f"{rel}:{node.lineno} {name}(...)")
    assert not offenders, (
        "гейт по именам ролей мимо каталога действий — используйте "
        "require_action / ActionGate / authz.can:\n  " + "\n  ".join(offenders)
    )


def test_core_api_has_no_unexplained_public_routes():
    """Публичный маршрут без единой auth-зависимости — только известные."""
    entries = json.loads(rbac_baseline.baseline_path("core_api").read_text())["entries"]
    public = sorted(k for k, v in entries.items() if v["auth"] == "public")
    # Число зафиксировано снимком; рост — повод проверить, что публичность задумана.
    assert len(public) == 31, public
