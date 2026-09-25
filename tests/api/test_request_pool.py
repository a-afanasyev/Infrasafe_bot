"""GET /api/v2/requests/pool — вкладка «Взять» простого режима исполнителя.

Пул = заявки, которые текущий исполнитель может взять ПРЯМО СЕЙЧАС:
активное групповое назначение без исполнителя, он на смене, специализация
совпадает. Решает тот же канон, что и `POST /claim` (`allowed_actions` →
`_executor_can_claim`); SQL здесь только предфильтр. Поэтому тесты гоняют
настоящий канон на aiosqlite и сверяют пул со взятием.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
import uk_management_bot.api.requests.router as req_router
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
import uk_management_bot.utils.constants as C

POOL_URL = "/api/v2/requests/pool"
T0 = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)


def _executor(uid: int, *, spec: str = "plumber", roles: str = '["executor"]') -> User:
    return User(id=uid, telegram_id=80000 + uid, first_name=f"Exec{uid}",
                roles=roles, active_role="executor",
                status="approved", language="ru", specialization=spec)


def _on_shift(uid: int) -> Shift:
    return Shift(user_id=uid, status="active",
                 start_time=datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc))


def _request(number: str, owner: int, *, status: str = C.REQUEST_STATUS_NEW,
             urgency: str = "low", minutes: int = 0, executor_id=None,
             description: str = "течёт кран", **extra) -> Request:
    return Request(request_number=number, user_id=owner, category="plumbing",
                   description=description, status=status,
                   urgency=urgency, executor_id=executor_id,
                   created_at=T0 + timedelta(minutes=minutes), **extra)


def _group(number: str, by: int, spec: str = "plumber", executor_id=None,
           kind: str = "group") -> RequestAssignment:
    return RequestAssignment(request_number=number, assignment_type=kind,
                             group_specialization=spec, executor_id=executor_id,
                             created_by=by, status="active")


@pytest_asyncio.fixture
async def world(db_session, manager_user, monkeypatch):
    """Дежурные сантехники 41 (на смене) и 43 (без смены), электрик 44 на смене."""
    m = manager_user.id
    db_session.add_all([
        _executor(41), _executor(43), _executor(44, spec="electric"),
        _on_shift(41), _on_shift(44),
        Yard(id=1, name="Двор 1"),
        Building(id=1, address="ул. Лесная, 5", yard_id=1),
        Apartment(id=1, building_id=1, apartment_number="12", entrance=3, floor=4),
        # 1) Свободная, со структурированным адресом и фото жителя.
        _request("260920-001", m, address="ул. Лесная, 5, кв. 12",
                 address_type="apartment", apartment_id=1,
                 description="Течёт кран на кухне\nВторая строка",
                 media_files=["AgAC-telegram", {"media_id": 7, "type": "photo"}]),
        _group("260920-001", m),
        # 2) Чужая специализация.
        _request("260920-002", m, minutes=1),
        _group("260920-002", m, spec="electrician"),
        # 3) Уже взята (individual).
        _request("260920-003", m, minutes=2, status=C.REQUEST_STATUS_IN_PROGRESS,
                 executor_id=41),
        _group("260920-003", m, executor_id=41, kind="individual"),
        # 4) Терминальный статус с (осиротевшим) групповым назначением.
        _request("260920-004", m, minutes=3, status=C.REQUEST_STATUS_CANCELLED),
        _group("260920-004", m),
        # 5) Критичная, но позже первой — срочность важнее времени.
        _request("260920-005", m, minutes=10, urgency="critical"),
        _group("260920-005", m),
        # 6) Обычная, позже первой.
        _request("260920-006", m, minutes=20),
        _group("260920-006", m),
    ])
    await db_session.commit()

    async def noop(*_a, **_k):
        return None

    monkeypatch.setattr(req_router, "publish_request_event", noop)
    monkeypatch.setattr(req_router, "dispatch_notify_intents_detached", noop)
    monkeypatch.setattr(req_router, "notify_group_pool_claimed_detached", noop)


@pytest.fixture
def act_as(client, db_session_factory, world, monkeypatch):
    monkeypatch.setattr(req_router, "AsyncSessionLocal", db_session_factory)

    async def _switch(uid: int):
        async with db_session_factory() as s:
            user = await s.get(User, uid)
        app.dependency_overrides[get_current_user] = lambda: user
        return client

    return _switch


def _numbers(body) -> list[str]:
    return [i["request_number"] for i in body["items"]]


@pytest.mark.asyncio
async def test_pool_lists_only_claimable_sorted_by_urgency_then_time(act_as):
    client = await act_as(41)
    r = await client.get(POOL_URL)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["on_shift"] is True
    assert _numbers(body) == ["260920-005", "260920-001", "260920-006"]


@pytest.mark.asyncio
async def test_pool_item_carries_tile_fields(act_as):
    client = await act_as(41)
    body = (await client.get(POOL_URL)).json()
    item = next(i for i in body["items"] if i["request_number"] == "260920-001")
    assert item["category"] == "plumbing"
    assert item["urgency"] == "low"
    assert item["status"] == C.REQUEST_STATUS_NEW
    assert item["description_first_line"] == "Течёт кран на кухне"
    assert item["address"] == "ул. Лесная, 5, кв. 12"
    assert item["address_type"] == "apartment"
    assert item["building_address"] == "ул. Лесная, 5"
    assert item["entrance"] == 3
    assert item["floor"] == 4
    assert item["apartment_number"] == "12"
    # Первый файл медиа-сервиса: telegram file_id байтами через API не отдать.
    assert item["photo_media_id"] == 7
    assert item["created_at"].startswith("2026-09-20T08:00")


@pytest.mark.asyncio
async def test_pool_off_shift_is_empty_with_flag(act_as):
    client = await act_as(43)
    r = await client.get(POOL_URL)
    assert r.status_code == 200, r.text
    assert r.json() == {"on_shift": False, "items": []}


@pytest.mark.asyncio
async def test_pool_foreign_specialization_sees_only_own_group(act_as):
    client = await act_as(44)
    body = (await client.get(POOL_URL)).json()
    assert body["on_shift"] is True
    assert _numbers(body) == ["260920-002"]


@pytest.mark.asyncio
async def test_pool_requires_executor_role(act_as, manager_user):
    client = await act_as(manager_user.id)
    assert (await client.get(POOL_URL)).status_code == 403


@pytest.mark.asyncio
async def test_pool_limit(act_as):
    client = await act_as(41)
    body = (await client.get(POOL_URL, params={"limit": 1})).json()
    assert _numbers(body) == ["260920-005"]
    assert (await client.get(POOL_URL, params={"limit": 0})).status_code == 422


@pytest.mark.asyncio
async def test_pool_final_check_is_the_claim_predicate(act_as, db_session_factory, manager_user):
    """SQL-предфильтр сравнивает специализацию сырым `IN` и пропускает группу
    `universal` исполнителю-универсалу; канон взятия (`allowed_actions` →
    `executor_in_claim_pool`, `allow_universal=False`) — нет. Пул обязан
    ответить как `POST /claim`, а не как предфильтр."""
    async with db_session_factory() as s:
        s.add_all([
            _executor(45, spec="universal"), _on_shift(45),
            _request("260920-007", manager_user.id),
            _group("260920-007", manager_user.id, spec="universal"),
        ])
        await s.commit()
    client = await act_as(45)
    body = (await client.get(POOL_URL)).json()
    assert "260920-007" not in _numbers(body)
    assert (await client.post("/api/v2/requests/260920-007/claim")).status_code == 403


@pytest.mark.asyncio
async def test_every_pool_item_is_claimable_and_leaves_pool(act_as):
    client = await act_as(41)
    numbers = _numbers((await client.get(POOL_URL)).json())
    assert numbers
    for n in numbers:
        r = await client.post(f"/api/v2/requests/{n}/claim")
        assert r.status_code == 200, (n, r.text)
    assert _numbers((await client.get(POOL_URL)).json()) == []
