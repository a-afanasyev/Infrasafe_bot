"""API-двери (``require_roles``/``require_approved_roles``) на каноническом
резолвере ролей ``utils.auth_helpers.get_user_roles`` (A9-P3-11).

Прежний ``api.dependencies._parse_user_roles`` при пустых ``roles`` падал в
``active_role`` — пользователь без ролей, но с ``active_role="manager"``,
проходил менеджерские эндпоинты. Теперь пусто/нечитаемо → только ``applicant``.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from uk_management_bot.api.dependencies import require_approved_roles, require_roles
from uk_management_bot.utils.auth_helpers import get_user_roles


def _u(roles=None, active_role=None, status="approved"):
    return SimpleNamespace(telegram_id=1, roles=roles, active_role=active_role, status=status)


class TestCanonicalParsing:
    def test_json_array_string(self):
        assert get_user_roles(_u(roles='["applicant","executor"]')) == ["applicant", "executor"]

    def test_json_array_with_whitespace(self):
        assert get_user_roles(_u(roles='  ["manager"]  ')) == ["manager"]

    def test_csv_string(self):
        assert get_user_roles(_u(roles=" applicant , executor ")) == ["applicant", "executor"]

    def test_single_role_string(self):
        assert get_user_roles(_u(roles="manager")) == ["manager"]

    def test_non_string_json_items_are_dropped(self):
        assert get_user_roles(_u(roles='["manager", 1, 2]')) == ["manager"]


class TestRequireRoles:
    @pytest.mark.asyncio
    async def test_empty_roles_do_not_escalate_via_active_role(self):
        checker = require_roles("manager")
        with pytest.raises(HTTPException) as exc:
            await checker(user=_u(roles=None, active_role="manager"))
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_active_role_outside_roles_is_ignored(self):
        checker = require_roles("manager")
        with pytest.raises(HTTPException):
            await checker(user=_u(roles='["applicant"]', active_role="manager"))

    @pytest.mark.asyncio
    async def test_empty_roles_are_applicant(self):
        user = _u(roles="", active_role=None)
        assert await require_roles("applicant")(user=user) is user

    @pytest.mark.asyncio
    async def test_role_from_roles_passes(self):
        user = _u(roles='["executor", "manager"]', active_role="executor")
        assert await require_roles("manager")(user=user) is user

    @pytest.mark.asyncio
    async def test_approved_door_uses_same_resolver(self):
        checker = require_approved_roles("manager")
        with pytest.raises(HTTPException) as exc:
            await checker(user=_u(roles=None, active_role="manager"))
        assert exc.value.status_code == 403
