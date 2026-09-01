"""Скоупинг GET /api/v2/requests: параметр `view` — сужение и только.

До правки список решал, что показать, по ОБЪЕДИНЕНИЮ ролей: менеджер-житель
видел весь ЖК и не находил своих заявок, исполнитель-житель своих поданных не
видел вовсе. `view=own` / `view=assigned` выбирает клиент, оба режима привязаны
к `user.id` и расширить выборку не могут; без `view` — прежняя ветка по ролям
(регресс-гард на H-3, docs/security-audit-2026-05-29.md).

Групповое назначение: канон-парсер специализаций (алиасы, CSV) и окно смены
по времени (`utils/shifts.is_on_shift_now_async`), а не голый `status`.
"""
import json
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_current_user, get_db
from uk_management_bot.api.main import app
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.datetime_utils import utc_now

LIST_URL = "/api/v2/requests"


# ─────────────────────────── фикстуры ───────────────────────────


@pytest_asyncio.fixture
async def make_client(db_session_factory):
    """Фабрика AsyncClient с заданным аутентифицированным пользователем."""

    def _make(user: User) -> AsyncClient:
        async def override_get_db():
            async with db_session_factory() as session:
                try:
                    yield session
                except Exception:
                    await session.rollback()
                    raise

        async def override_user():
            return user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield _make
    app.dependency_overrides.clear()


async def _user(db: AsyncSession, telegram_id: int, roles: list[str],
                specialization: str | None = None) -> User:
    u = User(
        telegram_id=telegram_id, username=f"u{telegram_id}", first_name="U",
        roles=json.dumps(roles), active_role=roles[0], status="approved",
        specialization=specialization,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _request(db: AsyncSession, rn: str, owner_id: int,
                   executor_id: int | None = None) -> RequestModel:
    r = RequestModel(
        request_number=rn, user_id=owner_id, executor_id=executor_id,
        category="Электрика", description="desc " + rn, status="Новая",
        source="web", media_files=[],
    )
    db.add(r)
    await db.commit()
    return r


async def _assign_individual(db: AsyncSession, rn: str, executor_id: int, by: int):
    db.add(RequestAssignment(request_number=rn, assignment_type="individual",
                             executor_id=executor_id, status="active", created_by=by))
    await db.commit()


async def _assign_group(db: AsyncSession, rn: str, spec: str, by: int):
    db.add(RequestAssignment(request_number=rn, assignment_type="group",
                             group_specialization=spec, executor_id=None,
                             status="active", created_by=by))
    await db.commit()


async def _shift(db: AsyncSession, user_id: int, *, expired: bool = False):
    now = utc_now()
    db.add(Shift(
        user_id=user_id, status="active",
        start_time=now - timedelta(hours=4),
        end_time=(now - timedelta(hours=1)) if expired else None,
    ))
    await db.commit()


@pytest_asyncio.fixture
async def world(db_session: AsyncSession):
    """Три чужих заявки + по одной «своей» на каждого субъекта тестов.

    manager (id-заявка M), stranger — владелец «чужих» заявок S1..S3.
    Субъект каждого теста создаётся в самом тесте (нужны разные наборы ролей).
    """
    manager = await _user(db_session, 1001, ["manager"])
    stranger = await _user(db_session, 1002, ["applicant"])
    for i in range(1, 4):
        await _request(db_session, f"260901-10{i}", stranger.id)
    return {"manager": manager, "stranger": stranger}


async def _numbers(client: AsyncClient, **params) -> list[str]:
    async with client as ac:
        r = await ac.get(LIST_URL, params=params)
    assert r.status_code == 200, r.text
    return sorted(c["request_number"] for c in r.json())


# ─────────────────────────── view=own ───────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("roles", [
    ["applicant"],
    ["applicant", "manager"],
    ["applicant", "executor"],
    ["manager"],
])
async def test_view_own_returns_only_own_for_any_role_set(db_session, make_client, world, roles):
    subject = await _user(db_session, 2001, roles)
    await _request(db_session, "260901-201", subject.id)
    # Назначение на чужую заявку не должно попадать в «свои».
    await _assign_individual(db_session, "260901-101", subject.id, world["manager"].id)

    assert await _numbers(make_client(subject), view="own") == ["260901-201"]


# ─────────────────────────── view=assigned ───────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("roles", [
    ["executor"],
    ["executor", "manager"],
])
async def test_view_assigned_returns_only_assignments(db_session, make_client, world, roles):
    subject = await _user(db_session, 2002, roles)
    await _request(db_session, "260901-202", subject.id)  # своя поданная — НЕ назначение
    await _assign_individual(db_session, "260901-101", subject.id, world["manager"].id)
    await _request(db_session, "260901-203", world["stranger"].id, executor_id=subject.id)  # legacy executor_id

    assert await _numbers(make_client(subject), view="assigned") == ["260901-101", "260901-203"]


@pytest.mark.asyncio
async def test_view_assigned_for_pure_applicant_is_empty(db_session, make_client, world):
    subject = await _user(db_session, 2003, ["applicant"])
    await _request(db_session, "260901-204", subject.id)

    assert await _numbers(make_client(subject), view="assigned") == []


@pytest.mark.asyncio
async def test_unknown_view_is_422(db_session, make_client, world):
    async with make_client(world["manager"]) as ac:
        r = await ac.get(LIST_URL, params={"view": "all"})
    assert r.status_code == 422


# ─────────────────────────── без view: прежний режим по ролям (H-3) ───────────────────────────


@pytest.mark.asyncio
async def test_no_view_manager_sees_everything(db_session, make_client, world):
    assert await _numbers(make_client(world["manager"])) == ["260901-101", "260901-102", "260901-103"]


@pytest.mark.asyncio
async def test_no_view_resident_sees_only_own(db_session, make_client, world):
    subject = await _user(db_session, 2004, ["applicant"])
    await _request(db_session, "260901-205", subject.id)

    assert await _numbers(make_client(subject)) == ["260901-205"]


@pytest.mark.asyncio
@pytest.mark.parametrize("junk_scope", ["all", "my", "everything", ""])
async def test_scope_param_is_dead_h3_regression(db_session, make_client, world, junk_scope):
    """Литеральная форма H-3: прежний `scope` инертен — житель видит только своё."""
    subject = await _user(db_session, 2009, ["applicant"])
    await _request(db_session, "260901-206", subject.id)

    assert await _numbers(make_client(subject), scope=junk_scope) == ["260901-206"]


@pytest.mark.asyncio
async def test_filters_cannot_pivot_off_identity_clause(db_session, make_client, world):
    """`executor_id` — AND-фильтр поверх identity-clause, не замена ей."""
    subject = await _user(db_session, 2010, ["applicant"])
    await _request(db_session, "260901-207", subject.id)
    await _request(db_session, "260901-104", world["stranger"].id, executor_id=world["manager"].id)

    assert await _numbers(make_client(subject), view="own", executor_id=world["manager"].id) == []


# ─────────────────────────── групповое назначение ───────────────────────────


@pytest.mark.asyncio
async def test_group_assignment_visible_with_legacy_specialization_token(db_session, make_client, world):
    subject = await _user(db_session, 2005, ["executor"], specialization="electric")
    await _shift(db_session, subject.id)
    await _assign_group(db_session, "260901-101", "electrician", world["manager"].id)

    assert await _numbers(make_client(subject), view="assigned") == ["260901-101"]


@pytest.mark.asyncio
async def test_group_assignment_visible_with_csv_specializations(db_session, make_client, world):
    subject = await _user(db_session, 2006, ["executor"], specialization="plumber,electrician")
    await _shift(db_session, subject.id)
    await _assign_group(db_session, "260901-102", "electrician", world["manager"].id)

    assert await _numbers(make_client(subject), view="assigned") == ["260901-102"]


@pytest.mark.asyncio
async def test_group_assignment_hidden_when_shift_window_expired(db_session, make_client, world):
    subject = await _user(db_session, 2007, ["executor"], specialization="electrician")
    await _shift(db_session, subject.id, expired=True)  # status=active, end_time в прошлом
    await _assign_group(db_session, "260901-103", "electrician", world["manager"].id)

    assert await _numbers(make_client(subject), view="assigned") == []


@pytest.mark.asyncio
async def test_group_assignment_hidden_without_shift(db_session, make_client, world):
    subject = await _user(db_session, 2008, ["executor"], specialization="electrician")
    await _assign_group(db_session, "260901-101", "electrician", world["manager"].id)

    assert await _numbers(make_client(subject), view="assigned") == []
