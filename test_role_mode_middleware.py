from uk_management_bot.middlewares.auth import role_mode_middleware

import asyncio


class DummyEvent:
    pass


class DummyUser:
    def __init__(self, roles: str | None, role: str | None, active_role: str | None):
        self.roles = roles
        self.role = role
        self.active_role = active_role


async def noop_handler(event, data):
    # Возвращаем data для удобной проверки
    return data


def run(coro):
    return asyncio.run(coro)


def test_role_mode_defaults_when_no_user():
    data = {"user": None}
    result = run(role_mode_middleware(noop_handler, DummyEvent(), data))
    assert result["roles"] == ["applicant"]
    assert result["active_role"] == "applicant"


def test_role_mode_parse_roles_json_and_active_in_list():
    user = DummyUser(roles='["applicant", "executor"]', role=None, active_role="executor")
    data = {"user": user}
    result = run(role_mode_middleware(noop_handler, DummyEvent(), data))
    assert result["roles"] == ["applicant", "executor"]
    assert result["active_role"] == "executor"


def test_role_mode_fallback_old_role_and_active_normalization():
    # roles пусто, используем старое поле role, active_role не входит — должен нормализоваться
    user = DummyUser(roles=None, role="manager", active_role="executor")
    data = {"user": user}
    result = run(role_mode_middleware(noop_handler, DummyEvent(), data))
    assert result["roles"] == ["manager"]
    assert result["active_role"] == "manager"


