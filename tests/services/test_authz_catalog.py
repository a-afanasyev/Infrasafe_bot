"""RBAC A1: каталог действий и функция `can`.

Состав ролей каждого действия равен прежнему гейту — это доказывает снимок
прав (test_rbac_baseline.py). Здесь — механика: отказ по умолчанию,
неизвестные ключи, статус для approved_only, защита от типичных ошибок.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from uk_management_bot.authz import ACTIONS, actions_for_roles, can, get_action, has_action_roles
from uk_management_bot.authz.catalog import KNOWN_ROLES


def _user(roles, status="approved"):
    return SimpleNamespace(roles=json.dumps(roles), status=status, telegram_id=1)


def test_catalog_is_consistent():
    assert ACTIONS, "каталог пуст"
    for key, action in ACTIONS.items():
        assert key == action.key
        if action.superadmin_only:
            assert not action.default_roles, f"{key}: только суперадмин — роли не выдаются"
        else:
            assert action.default_roles and action.default_roles <= KNOWN_ROLES, key
        assert action.title, f"у действия {key} нет описания"


def test_superadmin_bypass_is_explicit_and_narrow():
    """Обход для суперадмина — только у действий админки ролей и только флагом.

    Новое действие с ключом `rbac.*` обход не получает случайно, а расширение
    списка — осознанная правка этого теста.
    """
    assert {k for k, a in ACTIONS.items() if a.superadmin_bypass} == {"rbac.view", "rbac.manage"}
    assert all(a.superadmin_bypass for a in ACTIONS.values() if a.superadmin_only)


def test_unknown_action_fails_loudly():
    with pytest.raises(KeyError, match="Неизвестное действие"):
        get_action("no.such.action")
    with pytest.raises(KeyError):
        can(_user(["manager"]), "no.such.action")


def test_can_by_roles():
    assert can(["manager"], "staff.manage")
    assert not can(["executor"], "staff.manage")
    assert not can([], "staff.manage")  # пустой набор — отказ, не «всё»


def test_can_by_user_uses_canonical_resolver():
    # Пустые роли пользователя = applicant (A9-P3-11), active_role прав не даёт.
    user = _user([])
    user.active_role = "manager"
    assert not can(user, "staff.manage")
    assert can(_user([]), "requests.update")  # applicant входит в requests.update


def test_string_subject_is_rejected():
    with pytest.raises(TypeError, match="не строку"):
        can("manager", "staff.manage")


def test_approved_only_requires_user_and_status():
    with pytest.raises(TypeError, match="одобренный аккаунт"):
        can(["manager"], "elevators.manage")
    assert can(_user(["manager"]), "elevators.manage")
    assert not can(_user(["manager"], status="pending"), "elevators.manage")
    # has_action_roles проверяет только роли — для меню и предикатов бота.
    assert has_action_roles(_user(["manager"], status="pending"), "elevators.manage")


def test_actions_for_roles_unions_roles():
    executor = actions_for_roles(["executor"])
    manager = actions_for_roles(["manager"])
    both = actions_for_roles(["executor", "manager"])
    assert both == executor | manager
    assert "requests.execute" in executor and "requests.execute" not in manager
    assert actions_for_roles([]) == frozenset()


def test_frontend_catalog_copy_is_fresh():
    """Фронт сверяет ключи действий со своей копией каталога — она не должна устаревать."""
    from uk_management_bot.authz.export import FRONTEND_COPY, render

    assert FRONTEND_COPY.exists(), f"нет {FRONTEND_COPY}: python -m uk_management_bot.authz.export --write"
    assert FRONTEND_COPY.read_text(encoding="utf-8") == render(), (
        "копия каталога во фронтенде устарела: python -m uk_management_bot.authz.export --write"
    )


def test_profile_exposes_actions_of_roles_ignoring_status():
    """Профиль отдаёт интерфейсу действия по ролям (подсказка; решает сервер)."""
    from uk_management_bot.api.profile.router import ProfileOut

    user = SimpleNamespace(
        id=1, telegram_id=1, first_name=None, last_name=None, phone=None, email=None,
        language="ru", status="pending", verification_status="pending",
        roles=json.dumps(["manager"]), active_role="manager", password_hash=None, simple_mode=False,
    )
    profile = ProfileOut.from_user(user)
    assert profile.actions == sorted(actions_for_roles(["manager"]))
    assert "staff.manage" in profile.actions
    assert "requests.execute" not in profile.actions


def test_bot_gates_reject_approved_only_actions():
    """Гейты бота статус не проверяют — approved_only-действие там ошибка."""
    from uk_management_bot.handlers._role_gate import ActionGate
    from uk_management_bot.middlewares.auth import require_action

    with pytest.raises(ValueError):
        ActionGate("elevators.manage")
    with pytest.raises(ValueError):
        require_action("elevators.manage")
