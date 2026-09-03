"""PATCH /api/v2/requests/{number}/category — смена категории менеджером.

Оркестратор `change_category_async` здесь мокается (его транзакционная логика
и настоящий диспетч — в tests/services/test_category_change.py); здесь —
HTTP-контракт: роль, коды ошибок, форма ответа, realtime и уведомления.
"""
from unittest.mock import AsyncMock

import pytest

import uk_management_bot.api.requests.router as req_router
from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.database.models.request import Request
from uk_management_bot.services.category_change import CategoryChangeResult
from uk_management_bot.services.dispatch import DispatchResult
from uk_management_bot.services.workflow_runner import RequestNotFound
from uk_management_bot.utils.request_workflow import (
    EventIntent,
    InvalidTransition,
    NotAuthorized,
    PayloadInvalid,
)
import uk_management_bot.utils.constants as C

URL = "/api/v2/requests/{number}/category"
NUMBER = "260903-001"


def _result(*, no_op=False, status=C.REQUEST_STATUS_NEW, executor_id=None,
            mismatch=False, can_reassign=True, dispatch=None, intents=()):
    return CategoryChangeResult(
        request_number=NUMBER, no_op=no_op,
        old_category="electricity", new_category="plumbing",
        old_specialization="electrician", new_specialization="plumber",
        specialization_changed=not no_op, dispatch=dispatch,
        status=status, executor_id=executor_id,
        executor_spec_mismatch=mismatch, can_reassign=can_reassign,
        post_commit_intents=tuple(intents),
    )


async def _seed(db, *, owner_id, status=C.REQUEST_STATUS_NEW, category="electricity"):
    db.add(Request(request_number=NUMBER, user_id=owner_id, category=category,
                   description="d", status=status, urgency="low", address="Дом 1"))
    await db.commit()


@pytest.fixture
def _capture(monkeypatch):
    events = []

    async def fake_publish(event_type, data):
        events.append((event_type, data))

    monkeypatch.setattr(req_router, "publish_request_event", fake_publish)
    return events


@pytest.fixture
def _notify(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(req_router, "dispatch_notify_intents_detached", mock)
    return mock


@pytest.mark.asyncio
async def test_manager_changes_category_returns_shape_and_publishes(
    client, db_session, resident_user, _capture, _notify, monkeypatch,
):
    await _seed(db_session, owner_id=resident_user.id)
    intent = EventIntent("notify", {"action": "manager_change_category", "request_number": NUMBER})
    mock = AsyncMock(return_value=_result(
        status=C.REQUEST_STATUS_IN_PROGRESS, executor_id=5,
        dispatch=DispatchResult("assigned", "plumber", 5), intents=(intent,)))
    monkeypatch.setattr(req_router, "change_category_async", mock)

    r = await client.patch(URL.format(number=NUMBER), json={"category": "plumbing"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["no_op"] is False
    assert body["old_category"] == "electricity" and body["new_category"] == "plumbing"
    assert body["specialization_changed"] is True
    assert body["redispatched"] is True
    assert body["executor_id"] == 5 and body["executor_spec_mismatch"] is False
    assert body["can_reassign"] is True
    assert body["request"]["request_number"] == NUMBER   # свежая карточка
    # оркестратор получил канон-ключ и менеджера-принципала
    args = mock.await_args
    assert args.args[1] == NUMBER and args.args[3] == "plumbing"
    assert args.args[2].kind == "user"
    assert any(e[0] == "request.updated" for e in _capture)
    assert _notify.await_count == 1


@pytest.mark.asyncio
async def test_legacy_label_is_normalised_before_orchestrator(
    client, db_session, resident_user, _capture, _notify, monkeypatch,
):
    await _seed(db_session, owner_id=resident_user.id)
    mock = AsyncMock(return_value=_result())
    monkeypatch.setattr(req_router, "change_category_async", mock)
    r = await client.patch(URL.format(number=NUMBER), json={"category": "Сантехника"})
    assert r.status_code == 200, r.text
    assert mock.await_args.args[3] == "plumbing"


@pytest.mark.asyncio
async def test_no_op_publishes_nothing(client, db_session, resident_user, _capture, _notify, monkeypatch):
    await _seed(db_session, owner_id=resident_user.id)
    monkeypatch.setattr(req_router, "change_category_async",
                        AsyncMock(return_value=_result(no_op=True)))
    r = await client.patch(URL.format(number=NUMBER), json={"category": "plumbing"})
    assert r.status_code == 200
    assert r.json()["no_op"] is True
    assert _capture == []
    assert _notify.await_count == 0


@pytest.mark.parametrize("category", ["engineering", "Инженерный разбор", "nope-xyz", "  "])
@pytest.mark.asyncio
async def test_schema_rejects_non_selectable(client, db_session, resident_user, monkeypatch, category):
    await _seed(db_session, owner_id=resident_user.id)
    mock = AsyncMock(return_value=_result())
    monkeypatch.setattr(req_router, "change_category_async", mock)
    r = await client.patch(URL.format(number=NUMBER), json={"category": category})
    assert r.status_code == 422
    assert mock.await_count == 0


@pytest.mark.asyncio
async def test_extra_key_rejected(client, db_session, resident_user):
    await _seed(db_session, owner_id=resident_user.id)
    r = await client.patch(URL.format(number=NUMBER),
                           json={"category": "plumbing", "urgency": "high"})
    assert r.status_code == 422


@pytest.mark.parametrize("exc,code", [
    (RequestNotFound(NUMBER), 404),
    (NotAuthorized("x"), 403),
    (InvalidTransition("terminal"), 422),
    (PayloadInvalid("bad"), 422),
])
@pytest.mark.asyncio
async def test_engine_errors_map_to_http(client, db_session, resident_user, monkeypatch, exc, code):
    await _seed(db_session, owner_id=resident_user.id)
    monkeypatch.setattr(req_router, "change_category_async", AsyncMock(side_effect=exc))
    r = await client.patch(URL.format(number=NUMBER), json={"category": "plumbing"})
    assert r.status_code == code


@pytest.mark.asyncio
async def test_resident_is_forbidden(client, db_session, resident_user, monkeypatch):
    await _seed(db_session, owner_id=resident_user.id)
    mock = AsyncMock(return_value=_result())
    monkeypatch.setattr(req_router, "change_category_async", mock)
    app.dependency_overrides[get_current_user] = lambda: resident_user
    try:
        r = await client.patch(URL.format(number=NUMBER), json={"category": "plumbing"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert r.status_code == 403
    assert mock.await_count == 0


@pytest.mark.asyncio
async def test_plain_patch_with_category_is_still_rejected(client, db_session, resident_user):
    """Старая edit-ветка PATCH категорию не принимает — только новый эндпоинт."""
    await _seed(db_session, owner_id=resident_user.id)
    r = await client.patch(f"/api/v2/requests/{NUMBER}", json={"category": "plumbing"})
    assert r.status_code == 422
