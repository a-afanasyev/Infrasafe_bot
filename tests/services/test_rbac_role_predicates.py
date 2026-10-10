"""RBAC этап 0: спецификация ролевых предикатов «как есть».

253 функции принимают решение по роли в своём теле, вызывая эти предикаты
(карта — tests/rbac_baseline/inline_checks.json). Снаружи такие ветвления не
вычислить, поэтому эквивалентность при переходе на действия доказывается здесь:
каждый предикат × каждый ролевой профиль прода → ожидаемый ответ. Замена
`has_admin_access(...)` на проверку действия обязана дать ту же таблицу.

Ожидания записаны ЯВНО, а не вычислены, — это документ поведения, который
читает человек. Профили — те же, что у снимка (`tests/rbac_baseline/builder.py`).

Зафиксированные особенности текущего поведения (НЕ исправлять в этапе 0):
  * ни один предикат не смотрит на статус: pending-менеджер проходит как менеджер;
  * `has_executor_access` расходится сам с собой: через `roles=` пропускает
    executor/manager/admin, через `user=` — только executor;
  * `admin` не равен `manager`: `has_manager_role` и `_is_manager` его не пускают.
"""
from __future__ import annotations

import asyncio
import importlib.util
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

PROFILES = {p.name: p for p in rbac_baseline.PROFILES}

MANAGER_PROFILES = {
    "manager", "applicant+manager", "executor+inspector+manager",
    "applicant+executor+manager", "applicant+executor+manager+system_admin",
    "superuser7", "manager@pending",
}
ADMIN_OR_MANAGER = MANAGER_PROFILES | {"admin"}
EXECUTOR_PROFILES = {
    "executor", "executor+inspector", "executor+resource_meter_entry",
    "executor+inspector+manager", "applicant+executor+manager",
    "applicant+executor+manager+system_admin", "superuser7", "executor@pending",
}


def _allowed(predicate) -> set[str]:
    return {name for name, profile in PROFILES.items() if predicate(profile)}


def _roles(profile):
    return rbac_baseline.resolved_roles(profile)


def _user(profile):
    return rbac_baseline.fake_user(profile)


def test_profiles_cover_every_prod_role_combination():
    """Набор профилей — все сочетания ролей обоих продов на 2026-09-28."""
    assert len(PROFILES) == 19
    combos = {tuple(sorted(p.roles)) for p in PROFILES.values()}
    assert ("admin", "applicant", "executor", "inspector", "manager",
            "resource_meter_entry", "system_admin") in combos
    assert () in combos


def test_get_user_roles_empty_means_applicant():
    from uk_management_bot.utils.auth_helpers import get_user_roles

    for name, profile in PROFILES.items():
        expected = list(profile.roles) or ["applicant"]
        assert get_user_roles(_user(profile)) == expected, name


def test_get_active_role_falls_back_to_first_role():
    from uk_management_bot.utils.auth_helpers import get_active_role

    assert get_active_role(_user(PROFILES["empty_roles"])) == "applicant"
    stale = _user(PROFILES["executor"])
    stale.active_role = "manager"  # устаревший режим не повышает права
    assert get_active_role(stale) == "executor"


@pytest.mark.parametrize("via", ["roles", "user"])
def test_has_admin_access(via):
    from uk_management_bot.utils.auth_helpers import has_admin_access

    if via == "roles":
        allowed = _allowed(lambda p: has_admin_access(roles=_roles(p)))
    else:
        allowed = _allowed(lambda p: has_admin_access(user=_user(p)))
    assert allowed == ADMIN_OR_MANAGER


@pytest.mark.parametrize("via", ["roles", "user"])
def test_has_manager_role_excludes_admin(via):
    from uk_management_bot.utils.auth_helpers import has_manager_role

    if via == "roles":
        allowed = _allowed(lambda p: has_manager_role(roles=_roles(p)))
    else:
        allowed = _allowed(lambda p: has_manager_role(user=_user(p)))
    assert allowed == MANAGER_PROFILES


def test_has_executor_access_disagrees_with_itself():
    """Особенность «как есть»: ответ зависит от способа вызова."""
    from uk_management_bot.utils.auth_helpers import has_executor_access

    via_roles = _allowed(lambda p: has_executor_access(roles=_roles(p)))
    via_user = _allowed(lambda p: has_executor_access(user=_user(p)))
    assert via_roles == EXECUTOR_PROFILES | ADMIN_OR_MANAGER
    assert via_user == EXECUTOR_PROFILES
    assert via_roles - via_user == {"manager", "admin", "applicant+manager", "manager@pending"}


def test_role_gate_default_equals_has_admin_access():
    from uk_management_bot.handlers._role_gate import RoleGate

    gate = RoleGate()
    allowed = _allowed(lambda p: asyncio.run(gate(None, roles=_roles(p), user=_user(p))))
    assert allowed == ADMIN_OR_MANAGER


def test_addresses_is_manager():
    from uk_management_bot.api.addresses._helpers import is_manager

    assert _allowed(lambda p: is_manager(_user(p))) == MANAGER_PROFILES


def test_workflow_is_manager_excludes_admin():
    from uk_management_bot.utils.request_workflow.guards import _is_manager
    from uk_management_bot.utils.request_workflow.types import ActorContext

    def check(profile):
        actor = ActorContext(kind="user", user_id=1, system_actor=None,
                             roles=frozenset(_roles(profile)))
        return _is_manager(actor)

    assert _allowed(check) == MANAGER_PROFILES


def test_require_role_decorator_ignores_status():
    """Декоратор бота пропускает pending так же, как approved."""
    allowed = set(rbac_baseline._require_role_allows(["admin", "manager"]))
    assert allowed == ADMIN_OR_MANAGER
    assert "manager@pending" in allowed
