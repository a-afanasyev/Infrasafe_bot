"""A9-P3-11: ОДИН канонический резолвер ролей — ``utils.auth_helpers.get_user_roles``.

До правки бот (``get_user_roles``) и API (``api.dependencies._parse_user_roles``)
расходились на пустых ``roles``: бот видел ``applicant``, API — ``active_role``
(вплоть до ``manager``). Канон: роли — только из ``user.roles``; пусто/нечитаемо →
``["applicant"]``; ``active_role`` ролей НЕ добавляет и учитывается лишь когда
входит в ``roles``.
"""
import ast
import pathlib
from types import SimpleNamespace

import pytest

from uk_management_bot.utils.auth_helpers import (
    get_active_role,
    get_user_roles,
    has_executor_access,
    legacy_primary_role,
)

REPO = pathlib.Path(__file__).resolve().parents[3]


def _u(roles=None, active_role=None):
    return SimpleNamespace(telegram_id=1, roles=roles, active_role=active_role)


class TestGetUserRoles:
    @pytest.mark.parametrize("roles", [None, "", "[]", "   "])
    def test_empty_roles_is_applicant(self, roles):
        assert get_user_roles(_u(roles=roles)) == ["applicant"]

    def test_json_string(self):
        assert get_user_roles(_u(roles='["applicant", "executor"]')) == ["applicant", "executor"]

    def test_list_value(self):
        assert get_user_roles(_u(roles=["manager", 1, "executor"])) == ["manager", "executor"]

    @pytest.mark.parametrize("roles", ['{"role": "manager"}', "[1, 2]", '"manager"'])
    def test_invalid_json_shape_is_applicant(self, roles):
        assert get_user_roles(_u(roles=roles)) == ["applicant"]

    @pytest.mark.parametrize("active", ["manager", "executor", "system_admin"])
    def test_active_role_never_grants_a_role(self, active):
        assert get_user_roles(_u(roles=None, active_role=active)) == ["applicant"]
        assert get_user_roles(_u(roles='["applicant"]', active_role=active)) == ["applicant"]


class TestGetActiveRole:
    def test_active_role_in_roles_is_honoured(self):
        assert get_active_role(_u(roles='["applicant", "executor"]', active_role="executor")) == "executor"

    def test_active_role_not_in_roles_falls_back_to_first_role(self):
        assert get_active_role(_u(roles='["executor", "applicant"]', active_role="manager")) == "executor"

    def test_empty_roles_with_privileged_active_role_is_applicant(self):
        assert get_active_role(_u(roles=None, active_role="manager")) == "applicant"


class TestLegacyPrimaryRole:
    def test_active_role_not_in_roles_is_ignored(self):
        assert legacy_primary_role(_u(roles='["applicant"]', active_role="manager")) == "applicant"

    def test_empty_roles_is_none_even_with_active_role(self):
        assert legacy_primary_role(_u(roles=None, active_role="manager")) is None


class TestHasExecutorAccess:
    def test_active_role_alone_does_not_grant_executor(self):
        assert has_executor_access(user=_u(roles='["applicant"]', active_role="executor")) is False

    def test_roles_grant_executor(self):
        assert has_executor_access(user=_u(roles='["executor"]', active_role="applicant")) is True


def test_no_private_api_role_parser_left():
    """Никто не тянет приватный ``_parse_user_roles`` и не держит второй резолвер;
    хендлеры бота не ходят за ролями в HTTP-слой (``api.dependencies``)."""
    offenders = []
    for root in ("uk_management_bot", "access_control"):
        for path in (REPO / root).rglob("*.py"):
            rel = path.relative_to(REPO).as_posix()
            if "/tests/" in rel or path.name.startswith("test_"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_parse_user_roles":
                    offenders.append(f"{rel}:{node.lineno} def _parse_user_roles")
                if isinstance(node, ast.ImportFrom) and node.module:
                    if any(a.name == "_parse_user_roles" for a in node.names):
                        offenders.append(f"{rel}:{node.lineno} import _parse_user_roles")
                    if rel.startswith("uk_management_bot/handlers/") and node.module == "uk_management_bot.api.dependencies":
                        offenders.append(f"{rel}:{node.lineno} handlers → api.dependencies")
    assert not offenders, "\n".join(sorted(offenders))
