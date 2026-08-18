"""R1/R2/R3 — ратчеты против возврата класса «незащищённый хендлер» (PR III).

R1 (две поверхности): AST извлекает литералы фильтров из адресных модулей и
прогоняет КАЖДЫЙ через разрешение роутинга от жителя. Новый callback или
stateless message-хендлер в адресном модуле обязан ломать ратчет — механизм,
которого не хватало 18 августа (инвентарь тогда сняли неполно).

R2 (структурный): root-фильтры пяти роутеров непусты и содержат RoleGate.

R3 (декораторный): admin_*-хендлеры user_apartments.py несут @require_role.
Критерий — по CALLBACK-ПРЕФИКСУ, не по имени функции (имя обходится
переименованием).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import uk_management_bot.main as main_mod
from uk_management_bot.handlers._role_gate import ADDRESS_CALLBACK_RE, RoleGate
from uk_management_bot.tests.handlers.routing_probe import (
    make_callback,
    resolve_ctx,
)

HANDLERS_DIR = Path(main_mod.__file__).parent / "handlers"
_ORDER = re.findall(r"dp\.include_router\((\w+)\)", Path(main_mod.__file__).read_text())
ROUTERS = [getattr(main_mod, name) for name in _ORDER]

H = "uk_management_bot.handlers"
APPLICANT = {"roles": ["applicant"], "user": None}

# glob, не перечисление: новый top-level address_*.py попадает в скан
# автоматически (находка ревью). Граница ратчета: адресный модуль с именем НЕ
# на address_* и typed CallbackData-фабрики скан не увидит — дисциплина ревью.
ADDRESS_MODULES = sorted([
    *HANDLERS_DIR.glob("address_*.py"),
    *(HANDLERS_DIR / "address_apartments").glob("*.py"),
])

# Жителю разрешённые исходы для адресного callback: deny-роутер, либо штатный
# транзит (user_management ловит cancel_action), либо жительский хендлер отмены.
_ALLOWED_FOR_APPLICANT = {
    (f"{H}._role_gate", "deny_address_callback"),
    (f"{H}.user_management.actions", "handle_cancel_action"),
    (f"{H}.user_apartment_selection", "cancel_apartment_selection_user"),
}


def _iter_handler_decorators(tree: ast.AST, kinds: tuple):
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in fn.decorator_list:
            if (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)
                    and deco.func.attr in kinds):
                yield fn, deco


def _callback_literals() -> set[str]:
    """Литералы F.data == "..." / F.data.startswith("...") адресных модулей."""
    out: set[str] = set()
    for path in ADDRESS_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for _fn, deco in _iter_handler_decorators(tree, ("callback_query",)):
            for node in ast.walk(deco):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    out.add(node.value)
    return {s for s in out if s and not s.isspace()}


def _stateless_message_filters() -> list[tuple[str, str]]:
    """(файл, исходник декоратора) для @router.message БЕЗ StateFilter."""
    out = []
    for path in ADDRESS_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn, deco in _iter_handler_decorators(tree, ("message",)):
            src = ast.unparse(deco)
            if "StateFilter" not in src:
                out.append((path.name, fn.name))
    return out


# ══════════════════════════════════════════════════════════════════════════════
# R1 callback: каждый литерал кластера от жителя → deny либо разрешённый транзит
# ══════════════════════════════════════════════════════════════════════════════

_LITERALS = sorted(_callback_literals())


def test_r1_inventory_is_not_empty_and_matches_snapshot_size():
    """Самозащита: AST реально что-то извлёк (на baseline — 40+ литералов)."""
    assert len(_LITERALS) >= 40


@pytest.mark.parametrize("literal", _LITERALS)
def test_r1_callback_from_applicant_never_reaches_address_handlers(literal):
    data = literal + ("1" if literal.endswith(":") else "")
    winner = resolve_ctx(ROUTERS, make_callback(data), "callback_query", **APPLICANT)
    assert winner is None or winner in _ALLOWED_FOR_APPLICANT, (
        f"житель дотянулся до {winner} через {data!r} — новый незащищённый "
        f"callback в адресном кластере либо дыра в ADDRESS_CALLBACK_RE"
    )


# ══════════════════════════════════════════════════════════════════════════════
# R1 message: stateless message-хендлеры кластера — закрытый список
# ══════════════════════════════════════════════════════════════════════════════

def test_r1_stateless_message_handlers_are_exactly_the_known_two():
    """Новый stateless message-хендлер в адресном модуле обязан ломать ратчет.
    18 хендлеров под StateFilter гейт не меняет (жителю состояния недостижимы),
    но stateless-поверхность — ровно то, на чём споткнулись в августе."""
    assert sorted(_stateless_message_filters()) == [
        ("address_yards.py", "cancel_with_button"),
        ("address_yards.py", "show_address_management_menu"),
    ]


# ══════════════════════════════════════════════════════════════════════════════
# R2: root-фильтры пяти роутеров непусты и несут RoleGate
# ══════════════════════════════════════════════════════════════════════════════

GATED_ROUTER_NAMES = [
    "address_yards_router",
    "address_buildings_router",
    "address_moderation_router",
    "address_apartments_router",
    "shift_management_router_new",
]


@pytest.mark.parametrize("router_name", GATED_ROUTER_NAMES)
@pytest.mark.parametrize("observer_name", ["callback_query", "message"])
def test_r2_root_filters_carry_role_gate(router_name, observer_name):
    router = getattr(main_mod, router_name)
    observer = getattr(router, observer_name)
    root_filters = [f.callback for f in observer._handler.filters or []]
    assert any(isinstance(f, RoleGate) for f in root_filters), (
        f"{router_name}.{observer_name} потерял RoleGate — класс дефекта вернулся"
    )


def test_r2_deny_router_registered_before_base():
    assert "address_deny_router" in _ORDER
    assert _ORDER.index("address_deny_router") < _ORDER.index("base_router")
    assert _ORDER.index("address_deny_router") > _ORDER.index("address_yards_router")


# ══════════════════════════════════════════════════════════════════════════════
# R3: admin_*-префиксы user_apartments.py обязаны нести @require_role
# ══════════════════════════════════════════════════════════════════════════════

ADMIN_CALLBACK_PREFIXES = (
    "admin_manage_apartments_",
    "admin_apartment_detail_",
    "admin_approve_apartment_",
    "admin_reject_apartment_",
    "admin_toggle_owner_",
)


def test_r3_admin_prefixes_of_user_apartments_carry_require_role():
    """Критерий генерический (находка ревью, HIGH): ЛЮБОЙ callback-литерал,
    начинающийся с admin_, обязан нести @require_role — включая новый шестой
    хендлер, которого нет в списке известных. Список известных — только для
    двунаправленности (исчезновение тоже красное)."""
    path = HANDLERS_DIR / "user_apartments.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    seen_prefixes = set()
    for fn, deco in _iter_handler_decorators(tree, ("callback_query",)):
        literals = [n.value for n in ast.walk(deco)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        admin_literals = [s for s in literals if s.startswith("admin_")]
        if not admin_literals:
            continue
        seen_prefixes.update(admin_literals)
        deco_names = {
            d.func.id if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
            else getattr(d, "id", None)
            for d in fn.decorator_list
        }
        assert "require_role" in deco_names, (
            f"{fn.name} ({admin_literals}) без @require_role — находка 3 вернулась"
        )
    # двунаправленность: известная пятёрка обязана существовать
    assert set(ADMIN_CALLBACK_PREFIXES) <= seen_prefixes


def test_r3_scanner_detects_synthetic_sixth_admin_handler():
    """Самозащита R3: новый admin_*-хендлер без @require_role ловится."""
    snippet = (
        '@router.callback_query(F.data.startswith("admin_delete_apartment_"))\n'
        "async def sixth(callback, state):\n    ...\n"
    )
    tree = ast.parse(snippet)
    offenders = []
    for fn, deco in _iter_handler_decorators(tree, ("callback_query",)):
        literals = [n.value for n in ast.walk(deco)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        if any(s.startswith("admin_") for s in literals):
            deco_names = {getattr(getattr(d, "func", d), "id", None)
                          for d in fn.decorator_list}
            if "require_role" not in deco_names:
                offenders.append(fn.name)
    assert offenders == ["sixth"]


# ══════════════════════════════════════════════════════════════════════════════
# Самозащита ратчета R1
# ══════════════════════════════════════════════════════════════════════════════

def test_r1_scanner_detects_synthetic_offender(tmp_path, monkeypatch):
    """Скан ловит синтетического нарушителя: подсунутый модуль с новым
    callback-литералом попадает в инвентарь."""
    mod = tmp_path / "address_synthetic.py"
    mod.write_text(
        "@router.callback_query(F.data == 'addr_synthetic_hole')\n"
        "async def hole(cb):\n    ...\n"
    )
    tree = ast.parse(mod.read_text())
    found = {
        node.value
        for _fn, deco in _iter_handler_decorators(tree, ("callback_query",))
        for node in ast.walk(deco)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "addr_synthetic_hole" in found
    # и такой литерал был бы закрыт deny-регексом
    assert ADDRESS_CALLBACK_RE.match("addr_synthetic_hole")
