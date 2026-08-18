"""RoleGate (аудит 2026-08-18, волны A и D): гейт 5 роутеров + deny-роутер.

Поведенческие тесты идут через разрешение роутинга (`resolve_ctx`) на РЕАЛЬНОМ
списке роутеров в порядке `main.py` — порядок не копируется, а ИЗВЛЕКАЕТСЯ из
исходника `main.py` (при дрейфе регистрации тесты гоняются против фактической
конфигурации, а не против фикции). Прямой вызов хендлера гейт не видит по
построению — root-фильтр отрабатывает до хендлера.

Победитель сверяется ПАРОЙ (module, name): имена дублируются
(`cancel_action` — base.py И address_yards.py).
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import uk_management_bot.main as main_mod
from uk_management_bot.handlers._role_gate import ADDRESS_CALLBACK_RE, RoleGate
from uk_management_bot.tests.handlers.routing_probe import (
    make_callback,
    make_message,
    resolve_ctx,
)
from uk_management_bot.utils.auth_helpers import has_admin_access
from uk_management_bot.utils.button_texts import (
    get_address_directory_texts,
    get_cancel_texts,
)

# Порядок роутеров — из САМОГО main.py (SSOT), не копия.
_ORDER = re.findall(r"dp\.include_router\((\w+)\)", Path(main_mod.__file__).read_text())
ROUTERS = [getattr(main_mod, name) for name in _ORDER]

H = "uk_management_bot.handlers"
DENY = (f"{H}._role_gate", "deny_address_callback")

APPLICANT = {"roles": ["applicant"], "user": None}
MANAGER = {"roles": ["manager"], "user": None}


def _user_with_roles(raw):
    user = MagicMock()
    user.roles = raw
    return user


def _cb(data: str, **ctx):
    return resolve_ctx(ROUTERS, make_callback(data), "callback_query", **ctx)


def _msg(text: str, raw_state=None, **ctx):
    return resolve_ctx(ROUTERS, make_message(text), "message", raw_state=raw_state, **ctx)


# ══════════════════════════════════════════════════════════════════════════════
# RoleGate — юнит: тождество предикату has_admin_access
# ══════════════════════════════════════════════════════════════════════════════

_MATRIX_ROLES = [None, [], ["applicant"], ["manager"], ["admin"],
                 ["system_admin"], ["applicant", "executor"]]
_MATRIX_USERS = [None, _user_with_roles('["manager"]'), _user_with_roles('["applicant"]')]


@pytest.mark.asyncio
@pytest.mark.parametrize("roles", _MATRIX_ROLES)
@pytest.mark.parametrize("user", _MATRIX_USERS)
async def test_role_gate_equals_has_admin_access(roles, user):
    """Семантика гейта = has_admin_access (тот же предикат, что у @require_role),
    включая fallback на user.roles при roles без admin|manager."""
    gate = RoleGate()
    assert await gate(MagicMock(), roles=roles, user=user) == has_admin_access(roles=roles, user=user)


@pytest.mark.asyncio
async def test_system_admin_denied_deliberately():
    """ОСОЗНАННАЯ фиксация (не желаемое поведение): system_admin — каноническая
    роль (constants.py), но админ-контур бота её никогда не пропускал
    (has_admin_access знает только admin|manager), и на обоих продах она живёт
    только в паре с manager/admin. Расширение — решение владельца по всему
    админ-контуру сразу (пункт бэклога «system_admin в боте»), не тихо здесь."""
    assert await RoleGate()(MagicMock(), roles=["system_admin"], user=None) is False


@pytest.mark.asyncio
async def test_role_gate_explicit_roles_param():
    gate = RoleGate(allowed_roles=("manager",))
    assert await gate(MagicMock(), roles=["manager"], user=None) is True
    assert await gate(MagicMock(), roles=["admin"], user=None) is False


# ══════════════════════════════════════════════════════════════════════════════
# Вектор атаки: адресные callback от жителя → deny, сервисы не тронуты
# ══════════════════════════════════════════════════════════════════════════════

ATTACK_VECTORS = [
    "addr_yard_delete:1",
    "addr_apartment_delete:1",
    "addr_autofill_confirm",
    "addr_moderation_approve:1",
    "addr_moderation_view:1",
    "addr_apartment_residents:1",
]


@pytest.mark.parametrize("data", ATTACK_VECTORS)
def test_address_callbacks_denied_for_applicant(data):
    assert _cb(data, **APPLICANT) == DENY


@pytest.mark.parametrize("data", ATTACK_VECTORS)
def test_address_callbacks_reach_handlers_for_manager(data):
    winner = _cb(data, **MANAGER)
    assert winner is not None and winner != DENY
    assert winner[0].startswith(f"{H}.address_")


@pytest.mark.parametrize("ctx", [
    {"roles": None, "user": None},
    {"roles": [], "user": None},
])
def test_fail_closed_without_roles(ctx):
    assert _cb("addr_moderation_approve:1", **ctx) == DENY


# ══════════════════════════════════════════════════════════════════════════════
# Житель не сломан: транзит и жительская отмена
# ══════════════════════════════════════════════════════════════════════════════

def test_resident_cancel_selection_reaches_resident_handler():
    assert _cb("cancel_apartment_selection", **APPLICANT) == (
        f"{H}.user_apartment_selection", "cancel_apartment_selection_user")


def test_admin_cancel_selection_denied_for_applicant_allowed_for_manager():
    assert _cb("addr_cancel_selection", **APPLICANT) == DENY
    assert _cb("addr_cancel_selection", **MANAGER) == (
        f"{H}.address_apartments.navigation", "cancel_apartment_action")


def test_transit_to_routers_after_address_cluster_intact():
    """Гейт не стал перехватчиком: access_control включён ПОСЛЕ адресных."""
    winner = _cb("ac_menu:vehicles", **APPLICANT)
    assert winner is not None and winner[0] == f"{H}.access_control"


# ══════════════════════════════════════════════════════════════════════════════
# A5: четыре stateless-строки — обе стороны каждой
# ══════════════════════════════════════════════════════════════════════════════

CANCEL_TEXT = get_cancel_texts()[0]
DIRECTORY_TEXT = get_address_directory_texts()[0]


def test_a5_cancel_message_applicant_falls_to_base():
    """Находка 10: раньше житель получал менеджерскую клавиатуру из
    address_yards:cancel_with_button. Теперь гейт отдаёт апдейт дальше —
    штатному fallback base.cancel_action (тот же фильтр, роутер последний)."""
    assert _msg(CANCEL_TEXT, **APPLICANT) == (f"{H}.base", "cancel_action")


def test_a5_cancel_message_manager_stays_on_yards():
    assert _msg(CANCEL_TEXT, **MANAGER) == (f"{H}.address_yards", "cancel_with_button")


def test_a5_directory_button_applicant_not_yards():
    winner = _msg(DIRECTORY_TEXT, **APPLICANT)
    assert winner is None or winner[0] != f"{H}.address_yards"


def test_a5_directory_button_manager_reaches_menu():
    assert _msg(DIRECTORY_TEXT, **MANAGER) == (
        f"{H}.address_yards", "show_address_management_menu")


def test_a5_admin_menu_callback_applicant_denied_manager_kept():
    """Находка 11: admin_menu — менеджерское главное меню; единственный хендлер
    в боте. Без deny апдейт жителя умер бы молча — поэтому он в ADDRESS_CALLBACK_RE."""
    assert _cb("admin_menu", **APPLICANT) == DENY
    assert _cb("admin_menu", **MANAGER) == (f"{H}.address_yards", "back_to_admin_menu")


def test_a5_cancel_action_callback_applicant_transits_to_user_management():
    """Находка 12: stateless-ветка cancel_action в navigation.py отдавала
    админское меню справочника любому. После гейта апдейт жителя транзитом
    доходит до user_management/actions (has_admin_access → permission_denied) —
    штатный последний рубеж. deny-роутер cancel_action НЕ ловит намеренно."""
    assert _cb("cancel_action", **APPLICANT) == (
        f"{H}.user_management.actions", "handle_cancel_action")


def test_a5_cancel_action_callback_manager_stays_on_navigation():
    assert _cb("cancel_action", **MANAGER) == (
        f"{H}.address_apartments.navigation", "cancel_generic_action")


# ══════════════════════════════════════════════════════════════════════════════
# FSM-шаг модерации и волна D
# ══════════════════════════════════════════════════════════════════════════════

def test_moderation_fsm_step_unreachable_for_applicant():
    """Сообщение жителя в состоянии waiting_for_approval_comment не должно
    достаться модерации (одобрение чужой квартиры комментарием)."""
    winner = _msg("одобряю", raw_state="ApartmentModerationStates:waiting_for_approval_comment",
                  **APPLICANT)
    assert winner is None or winner[0] != f"{H}.address_moderation"


SHIFT_DENY_CB = (f"{H}._role_gate", "deny_shift_callback")
SHIFT_DENY_MSG = (f"{H}._role_gate", "deny_shift_message")


@pytest.mark.parametrize("data", ["back_to_shifts", "shift_planning"])
def test_d1_shift_callbacks_get_explicit_deny_for_applicant(data):
    """Не тишина: до гейта 62/71 хендлеров пакета отвечали «нет прав» сами
    (@require_role). Deny-фолбэк сохраняет явный отказ — иначе у callback
    зависал бы спиннер."""
    assert _cb(data, **APPLICANT) == SHIFT_DENY_CB


def test_d1_shifts_command_gets_explicit_deny_for_applicant():
    assert _msg("/shifts", **APPLICANT) == SHIFT_DENY_MSG


def test_d1_shift_management_denied_for_applicant():
    winner = _cb("back_to_shifts", **APPLICANT)
    assert winner is None or not winner[0].startswith(f"{H}.shift_management")


def test_d1_auto_manager_back_button_still_works_for_manager():
    """auto_manager.py переиспользует back_to_shifts из shift_management/schedule —
    после D1 кнопка «Назад» в UI автоменеджера обязана остаться живой для менеджера."""
    assert _cb("back_to_shifts", **MANAGER) == (
        f"{H}.shift_management.schedule", "handle_back_to_shifts")


# ══════════════════════════════════════════════════════════════════════════════
# ADDRESS_CALLBACK_RE: жительские исключения
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("data", ["addr_page:2", "addr_page_noop", "addr:some_id"])
def test_resident_address_prefixes_not_denied(data):
    """Жительские литералы создания заявки (requests/create.py) deny не ловит."""
    assert not ADDRESS_CALLBACK_RE.match(data)


@pytest.mark.parametrize("data", ["addr_yard_delete:1", "admin_menu",
                                  "apartment_create_building:5", "building_create_yard:2",
                                  "addr_cancel_selection"])
def test_gated_literals_covered_by_deny_regex(data):
    assert ADDRESS_CALLBACK_RE.match(data)


@pytest.mark.parametrize("data", ["cancel_action", "cancel_apartment_selection", "admin_menu_x"])
def test_transit_literals_not_covered_by_deny_regex(data):
    assert not ADDRESS_CALLBACK_RE.match(data)
