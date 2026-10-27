"""PATCH /api/v2/profile/role: переключиться можно только в режим меню."""
import json

import pytest
from httpx import ASGITransport, AsyncClient

from uk_management_bot.api.dependencies import get_current_user, get_db
from uk_management_bot.api.main import app
from uk_management_bot.database.models.user import User


@pytest.mark.asyncio
async def test_switch_role_refuses_capability(db_session_factory):
    async with db_session_factory() as s:
        s.add(User(id=1, telegram_id=101, roles=json.dumps(["executor", "engineer", "applicant"]),
                   active_role="executor", status="approved", language="ru"))
        await s.commit()
        actor = await s.get(User, 1)

    async def override_get_db():
        async with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: actor
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            refused = await c.patch("/api/v2/profile/role", json={"active_role": "engineer"})
            assert refused.status_code == 422
            ok = await c.patch("/api/v2/profile/role", json={"active_role": "applicant"})
            assert ok.status_code == 200, ok.text
            assert ok.json()["active_role"] == "applicant"
    finally:
        app.dependency_overrides.clear()
