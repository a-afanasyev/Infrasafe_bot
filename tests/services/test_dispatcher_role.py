"""Роль «Диспетчер»: приём заявок по телефону (TWA /twa/dispatch).

Режим меню (как обходчик), а не капабилити: человек только с этой ролью
работает в боте с одной кнопкой. Права — ровно то, что нужно экрану приёма
звонка; дашборд и управление заявками роли не выданы.
"""
import pytest

from uk_management_bot.authz import ACTIONS
from uk_management_bot.authz.catalog import CAPABILITY_ROLES, DISPATCHER, KNOWN_ROLES, is_menu_mode
from uk_management_bot.utils.constants import ROLE_DISPATCHER, USER_ROLES


def test_dispatcher_is_a_menu_mode_system_role():
    assert DISPATCHER == ROLE_DISPATCHER == "dispatcher"
    assert DISPATCHER in KNOWN_ROLES
    assert DISPATCHER in USER_ROLES
    assert DISPATCHER not in CAPABILITY_ROLES
    assert is_menu_mode(DISPATCHER)


@pytest.mark.parametrize("action", ["callcenter.use", "addresses.read", "elevators.lookup"])
def test_dispatcher_has_call_intake_actions(action):
    assert DISPATCHER in ACTIONS[action].default_roles


def test_dispatcher_has_nothing_else():
    granted = {key for key, a in ACTIONS.items() if DISPATCHER in a.default_roles}
    assert granted == {"callcenter.use", "addresses.read", "elevators.lookup"}
