"""TWA PR-T1 — executor-facing shift-transfer endpoints.

`/api/v2/executor/shifts/transfers`: исполнитель инициирует передачу своей
смены (pending), принимает/отклоняет назначенную ему. Покрывает guards,
status-preserving перенос заявок на accept и список с direction/can_respond.
"""
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select

from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift_assignment import ShiftAssignment
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.api.main import app
from uk_management_bot.api.dependencies import get_current_user

START = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
END = START + timedelta(hours=8)

TR = "/api/v2/executor/shifts/transfers"


async def _user(db, tg, *, roles='["executor"]', status="approved", spec=None):
    u = User(telegram_id=tg, username=f"u{tg}", first_name="E", last_name=str(tg),
             roles=roles, status=status, specialization=spec)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _shift(db, user_id, *, status="active", specs=None, start=START, end=END):
    s = Shift(user_id=user_id, status=status, start_time=start, end_time=end,
              planned_start_time=start, planned_end_time=end, specialization_focus=specs)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def _transfer(db, *, shift_id, from_id, to_id=None, status="pending"):
    t = ShiftTransfer(shift_id=shift_id, from_executor_id=from_id, to_executor_id=to_id,
                      status=status, reason="illness", urgency_level="normal")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


def _as(user):
    app.dependency_overrides[get_current_user] = lambda: user


# ═══════════════════════════ initiate ═══════════════════════════

@pytest.mark.asyncio
async def test_initiate_creates_pending(client, db_session):
    me = await _user(db_session, 3001)
    shift = await _shift(db_session, me.id, status="active")
    _as(me)
    resp = await client.post(TR, json={"shift_id": shift.id, "reason": "illness"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["from_executor_id"] == me.id
    assert body["direction"] == "outgoing"
    assert body["can_respond"] is False


@pytest.mark.asyncio
async def test_initiate_not_your_shift_403(client, db_session):
    me = await _user(db_session, 3011)
    other = await _user(db_session, 3012)
    shift = await _shift(db_session, other.id)
    _as(me)
    resp = await client.post(TR, json={"shift_id": shift.id, "reason": "illness"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "not_your_shift"


@pytest.mark.asyncio
async def test_initiate_terminal_shift_422(client, db_session):
    me = await _user(db_session, 3021)
    shift = await _shift(db_session, me.id, status="completed")
    _as(me)
    resp = await client.post(TR, json={"shift_id": shift.id, "reason": "illness"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "shift_not_transferable"


@pytest.mark.asyncio
async def test_initiate_duplicate_409(client, db_session):
    me = await _user(db_session, 3031)
    shift = await _shift(db_session, me.id)
    await _transfer(db_session, shift_id=shift.id, from_id=me.id, status="pending")
    _as(me)
    resp = await client.post(TR, json={"shift_id": shift.id, "reason": "illness"})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "transfer_already_exists"


# ═══════════════════════════ accept ═══════════════════════════

@pytest.mark.asyncio
async def test_accept_moves_shift_and_request_status_preserving(client, db_session):
    initiator = await _user(db_session, 3041)
    me = await _user(db_session, 3042)
    shift = await _shift(db_session, initiator.id, status="active")
    r = Request(request_number="T-1", user_id=1, category="plumbing", description="d",
                status="Закуп", executor_id=initiator.id)
    db_session.add(r)
    db_session.add(RequestAssignment(request_number="T-1", assignment_type="individual",
                                     executor_id=initiator.id, status="active", created_by=initiator.id))
    db_session.add(ShiftAssignment(shift_id=shift.id, request_number="T-1", status="assigned"))
    transfer = await _transfer(db_session, shift_id=shift.id, from_id=initiator.id,
                               to_id=me.id, status="assigned")

    _as(me)
    resp = await client.post(f"{TR}/{transfer.id}/respond", json={"action": "accept"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "completed"

    # client коммитит в отдельной сессии — обновить объекты db_session.
    await db_session.refresh(shift)
    await db_session.refresh(r)
    assert shift.user_id == me.id
    assert r.executor_id == me.id
    assert r.status == "Закуп"   # status-preserving


@pytest.mark.asyncio
async def test_accept_not_your_transfer_403(client, db_session):
    initiator = await _user(db_session, 3051)
    recipient = await _user(db_session, 3052)
    intruder = await _user(db_session, 3053)
    shift = await _shift(db_session, initiator.id)
    transfer = await _transfer(db_session, shift_id=shift.id, from_id=initiator.id,
                               to_id=recipient.id, status="assigned")
    _as(intruder)
    resp = await client.post(f"{TR}/{transfer.id}/respond", json={"action": "accept"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "not_your_transfer"


@pytest.mark.asyncio
async def test_accept_pending_not_yet_assigned_409(client, db_session):
    initiator = await _user(db_session, 3061)
    me = await _user(db_session, 3062)
    shift = await _shift(db_session, initiator.id)
    transfer = await _transfer(db_session, shift_id=shift.id, from_id=initiator.id, status="pending")
    _as(me)
    resp = await client.post(f"{TR}/{transfer.id}/respond", json={"action": "accept"})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "wrong_status"


# ═══════════════════════════ reject ═══════════════════════════

@pytest.mark.asyncio
async def test_reject_sets_rejected_shift_unchanged(client, db_session):
    initiator = await _user(db_session, 3071)
    me = await _user(db_session, 3072)
    shift = await _shift(db_session, initiator.id, status="active")
    transfer = await _transfer(db_session, shift_id=shift.id, from_id=initiator.id,
                               to_id=me.id, status="assigned")
    _as(me)
    resp = await client.post(f"{TR}/{transfer.id}/respond", json={"action": "reject"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"
    await db_session.refresh(shift)
    assert shift.user_id == initiator.id   # смена не переходила


@pytest.mark.asyncio
async def test_respond_invalid_action_422(client, db_session):
    initiator = await _user(db_session, 3081)
    me = await _user(db_session, 3082)
    shift = await _shift(db_session, initiator.id)
    transfer = await _transfer(db_session, shift_id=shift.id, from_id=initiator.id,
                               to_id=me.id, status="assigned")
    _as(me)
    resp = await client.post(f"{TR}/{transfer.id}/respond", json={"action": "maybe"})
    assert resp.status_code == 422


# ═══════════════════════════ list ═══════════════════════════

@pytest.mark.asyncio
async def test_list_returns_outgoing_and_incoming(client, db_session):
    me = await _user(db_session, 3091)
    other = await _user(db_session, 3092)
    my_shift = await _shift(db_session, me.id)
    other_shift = await _shift(db_session, other.id, start=START + timedelta(days=1),
                               end=END + timedelta(days=1))
    # outgoing — инициировал я
    await _transfer(db_session, shift_id=my_shift.id, from_id=me.id, status="pending")
    # incoming — назначена мне
    await _transfer(db_session, shift_id=other_shift.id, from_id=other.id, to_id=me.id,
                    status="assigned")
    _as(me)
    resp = await client.get(TR)
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 2
    by_dir = {it["direction"]: it for it in items}
    assert by_dir["outgoing"]["can_respond"] is False
    assert by_dir["incoming"]["can_respond"] is True
