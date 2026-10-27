"""Удаление сотрудника с переносом заявок: цель — одобренный исполнитель.

Массовый перенос идёт мимо канона назначения (reassign_executor_bulk), поэтому
цель проверяется тем же предикатом `assignee_unavailable_reason`."""
import json

import pytest
from httpx import ASGITransport, AsyncClient

from uk_management_bot.api.dependencies import get_current_user, get_db
from uk_management_bot.api.main import app
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User


def _user(uid, roles, status="approved"):
    return User(id=uid, telegram_id=1000 + uid, roles=json.dumps(roles), active_role=roles[0],
                status=status, language="ru")


@pytest.mark.asyncio
@pytest.mark.parametrize("target, expected", [
    (_user(4, ["executor"], status="blocked"), 422),
    (_user(4, ["applicant"]), 422),
    (_user(4, ["executor"]), 200),
])
async def test_reassign_target_must_be_approved_executor(db_session_factory, target, expected):
    async with db_session_factory() as s:
        s.add_all([_user(1, ["manager"]), _user(2, ["applicant"]), _user(3, ["executor"]), target])
        s.add(Request(request_number="261027-001", user_id=2, category="plumbing",
                      description="d", status="В работе", executor_id=3))
        await s.commit()
        actor = await s.get(User, 1)

    async def override_get_db():
        async with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: actor
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch("/api/v2/shifts/employees/3/delete",
                              json={"reason": "уволен", "reassign_to": 4})
        assert r.status_code == expected, r.text
    finally:
        app.dependency_overrides.clear()
    async with db_session_factory() as s:
        req = await s.get(Request, "261027-001")
        assert req.executor_id == (4 if expected == 200 else 3)
