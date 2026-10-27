"""Инженер передаёт «Инженерный разбор» мастеру: кандидаты на передачу."""
import json

import pytest
from httpx import ASGITransport, AsyncClient

from uk_management_bot.api.dependencies import get_current_user, get_db
from uk_management_bot.api.main import app
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User

URL = "/api/v2/requests/{}/handover-candidates"


def _user(uid, roles, spec=None, status="approved"):
    return User(id=uid, telegram_id=1000 + uid, roles=json.dumps(roles), active_role=roles[0],
                status=status, language="ru", first_name=f"U{uid}",
                specialization=json.dumps(spec) if spec else None)


@pytest.fixture
async def call(db_session_factory):
    async with db_session_factory() as s:
        s.add_all([
            _user(1, ["executor", "engineer"]),
            _user(2, ["manager"]),
            _user(3, ["executor"], ["electrician"]),
            _user(4, ["executor"], ["repair"]),
            _user(5, ["executor"], ["plumber"], status="blocked"),
            _user(6, ["applicant"]),
        ])
        s.add_all([
            Request(request_number="261027-001", user_id=6, category="Инженерный разбор",
                    description="d", status="В работе", executor_id=1),
            Request(request_number="261027-002", user_id=6, category="plumbing",
                    description="d", status="В работе", executor_id=3),
        ])
        await s.commit()

    async def override_get_db():
        async with db_session_factory() as session:
            yield session

    async def _call(uid, number, **params):
        async with db_session_factory() as s:
            actor = await s.get(User, uid)
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: actor
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            return await c.get(URL.format(number), params=params)

    yield _call
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_engineer_sees_all_approved_executors_with_load(call):
    r = await call(1, "261027-001")
    assert r.status_code == 200, r.text
    body = r.json()
    # себя (текущий исполнитель), заблокированного и не-исполнителей нет;
    # мастера любой специализации, а не только repair
    assert [c["id"] for c in body] == [3, 4]
    assert body[0]["specializations"] == ["electrician"] and body[0]["open_requests"] == 1


@pytest.mark.asyncio
async def test_specialization_filter(call):
    r = await call(1, "261027-001", specialization="electrician")
    assert [c["id"] for c in r.json()] == [3]


@pytest.mark.asyncio
async def test_only_engineers_and_only_engineering(call):
    assert (await call(2, "261027-001")).status_code == 403
    assert (await call(1, "261027-002")).status_code == 404
    assert (await call(1, "261027-999")).status_code == 404
