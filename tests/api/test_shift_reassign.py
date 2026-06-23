"""REG-02 PR-A2 — веб менеджерский reassign смены + закрытие PATCH-bypass.

Service-level (`reassign_shift_web`): guards (approved/executor/спец/overlap/
same), status-preserving перенос заявок (ShiftAssignment-скоуп + fallback),
запись ShiftTransfer-истории. HTTP-контракт: POST /shifts/{id}/reassign коды,
PATCH user_id→422, approve_transfer assign-only (assigned_by, без смены
shift.user_id), manager-only 403.
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
from uk_management_bot.api.shifts import service

START = datetime(2026, 6, 22, 9, 0, tzinfo=timezone.utc)
END = START + timedelta(hours=8)


async def _user(db, tg, *, roles='["executor"]', status="approved", spec=None):
    u = User(telegram_id=tg, username=f"u{tg}", first_name="E", last_name=str(tg),
             roles=roles, status=status, specialization=spec)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _shift(db, user_id, *, status="active", specs=None):
    s = Shift(user_id=user_id, status=status, start_time=START, end_time=END,
              planned_start_time=START, planned_end_time=END, specialization_focus=specs)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def _request(db, number, executor_id, *, status="В работе"):
    r = Request(request_number=number, user_id=1, category="plumbing",
                description="d", status=status, executor_id=executor_id)
    db.add(r)
    await db.commit()
    return r


# ═══════════════════ Service-level: reassign_shift_web ═══════════════════

@pytest.mark.asyncio
async def test_reassign_web_happy_moves_shift_and_request_via_shift_assignment(db_session):
    old = await _user(db_session, 1001)
    new = await _user(db_session, 1002)
    shift = await _shift(db_session, old.id, status="active")
    await _request(db_session, "W-1", old.id, status="Закуп")
    db_session.add(RequestAssignment(request_number="W-1", assignment_type="individual",
                                     executor_id=old.id, status="active", created_by=old.id))
    db_session.add(ShiftAssignment(shift_id=shift.id, request_number="W-1", status="assigned"))
    await db_session.commit()

    res = await service.reassign_shift_web(
        db_session, shift_id=shift.id, new_executor_id=new.id, manager_id=999
    )
    assert res["success"] is True
    assert res["moved_request_numbers"] == ["W-1"]

    shift_db = (await db_session.execute(select(Shift).where(Shift.id == shift.id))).scalar_one()
    req_db = (await db_session.execute(select(Request).where(Request.request_number == "W-1"))).scalar_one()
    assign_db = (await db_session.execute(select(RequestAssignment).where(RequestAssignment.request_number == "W-1"))).scalar_one()
    hist = (await db_session.execute(select(ShiftTransfer).where(ShiftTransfer.shift_id == shift.id))).scalar_one()
    assert shift_db.user_id == new.id
    assert req_db.executor_id == new.id
    assert req_db.status == "Закуп"          # status-preserving
    assert assign_db.executor_id == new.id
    assert hist.status == "completed" and hist.auto_assigned is True
    assert hist.from_executor_id == old.id and hist.to_executor_id == new.id
    assert hist.assigned_by == 999 and hist.reason == "manager_reassign"


@pytest.mark.asyncio
async def test_reassign_web_fallback_executor_id_active_shift(db_session):
    old = await _user(db_session, 1011)
    new = await _user(db_session, 1012)
    shift = await _shift(db_session, old.id, status="active")
    await _request(db_session, "W-2", old.id, status="В работе")  # no ShiftAssignment

    res = await service.reassign_shift_web(
        db_session, shift_id=shift.id, new_executor_id=new.id, manager_id=999
    )
    assert res["success"] is True
    req_db = (await db_session.execute(select(Request).where(Request.request_number == "W-2"))).scalar_one()
    assert req_db.executor_id == new.id


@pytest.mark.asyncio
async def test_reassign_web_planned_shift_no_fallback(db_session):
    old = await _user(db_session, 1021)
    new = await _user(db_session, 1022)
    shift = await _shift(db_session, old.id, status="planned")
    await _request(db_session, "W-3", old.id, status="В работе")

    res = await service.reassign_shift_web(
        db_session, shift_id=shift.id, new_executor_id=new.id, manager_id=999
    )
    assert res["success"] is True
    assert res["moved_request_numbers"] == []
    req_db = (await db_session.execute(select(Request).where(Request.request_number == "W-3"))).scalar_one()
    assert req_db.executor_id == old.id          # planned → не переносим


@pytest.mark.asyncio
async def test_reassign_web_same_executor(db_session):
    old = await _user(db_session, 1031)
    shift = await _shift(db_session, old.id)
    res = await service.reassign_shift_web(db_session, shift_id=shift.id, new_executor_id=old.id, manager_id=999)
    assert res == {"success": False, "error": "same_executor"}


@pytest.mark.asyncio
async def test_reassign_web_spec_mismatch(db_session):
    old = await _user(db_session, 1041)
    new = await _user(db_session, 1042, spec='["electric"]')
    shift = await _shift(db_session, old.id, specs=["plumbing"])
    res = await service.reassign_shift_web(db_session, shift_id=shift.id, new_executor_id=new.id, manager_id=999)
    assert res["error"] == "spec_mismatch"


@pytest.mark.asyncio
async def test_reassign_web_overlap(db_session):
    old = await _user(db_session, 1051)
    new = await _user(db_session, 1052)
    shift = await _shift(db_session, old.id)
    await _shift(db_session, new.id)             # пересекающаяся смена у нового
    res = await service.reassign_shift_web(db_session, shift_id=shift.id, new_executor_id=new.id, manager_id=999)
    assert res["error"] == "overlap"


@pytest.mark.asyncio
async def test_reassign_web_not_executor(db_session):
    old = await _user(db_session, 1061)
    new = await _user(db_session, 1062, roles='["applicant"]')
    shift = await _shift(db_session, old.id)
    res = await service.reassign_shift_web(db_session, shift_id=shift.id, new_executor_id=new.id, manager_id=999)
    assert res["error"] == "not_executor"


@pytest.mark.asyncio
async def test_reassign_web_unassigned_shift_not_transferable(db_session):
    # Code-review HIGH-4: смена без владельца → from_executor_id=None нарушил бы
    # NOT NULL при записи истории. Должен быть мягкий guard, не IntegrityError.
    new = await _user(db_session, 1071)
    shift = await _shift(db_session, None, status="planned")
    res = await service.reassign_shift_web(db_session, shift_id=shift.id, new_executor_id=new.id, manager_id=999)
    assert res["success"] is False
    assert res["error"] == "shift_not_transferable"


@pytest.mark.asyncio
async def test_reassign_web_completed_shift_not_transferable(db_session):
    # Code-review MED-1: completed/cancelled-смену переназначать нечего.
    old = await _user(db_session, 1081)
    new = await _user(db_session, 1082)
    shift = await _shift(db_session, old.id, status="completed")
    res = await service.reassign_shift_web(db_session, shift_id=shift.id, new_executor_id=new.id, manager_id=999)
    assert res["success"] is False
    assert res["error"] == "shift_not_transferable"


# ═══════════════════ HTTP-контракт ═══════════════════

@pytest.fixture(autouse=True)
def _silence_publish(monkeypatch):
    from unittest.mock import AsyncMock
    import uk_management_bot.api.shifts.router as r
    monkeypatch.setattr(r, "publish_shift_event", AsyncMock())
    monkeypatch.setattr(r, "publish_request_event", AsyncMock())


@pytest.mark.asyncio
async def test_post_reassign_200(client, db_session):
    old = await _user(db_session, 2001)
    new = await _user(db_session, 2002)
    shift = await _shift(db_session, old.id, status="active")

    resp = await client.post(f"/api/v2/shifts/{shift.id}/reassign", json={"executor_id": new.id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["user_id"] == new.id


@pytest.mark.asyncio
async def test_post_reassign_overlap_409(client, db_session):
    old = await _user(db_session, 2011)
    new = await _user(db_session, 2012)
    shift = await _shift(db_session, old.id)
    await _shift(db_session, new.id)
    resp = await client.post(f"/api/v2/shifts/{shift.id}/reassign", json={"executor_id": new.id})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_post_reassign_spec_422(client, db_session):
    old = await _user(db_session, 2021)
    new = await _user(db_session, 2022, spec='["electric"]')
    shift = await _shift(db_session, old.id, specs=["plumbing"])
    resp = await client.post(f"/api/v2/shifts/{shift.id}/reassign", json={"executor_id": new.id})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_user_id_change_rejected_422(client, db_session):
    old = await _user(db_session, 2031)
    new = await _user(db_session, 2032)
    shift = await _shift(db_session, old.id, status="planned")
    resp = await client.patch(f"/api/v2/shifts/{shift.id}", json={"user_id": new.id})
    assert resp.status_code == 422
    # смена исполнителя не применилась
    await db_session.refresh(shift)
    assert shift.user_id == old.id


@pytest.mark.asyncio
async def test_handle_transfer_approve_assign_only(client, db_session, manager_user):
    initiator = await _user(db_session, 2041)
    recipient = await _user(db_session, 2042)
    shift = await _shift(db_session, initiator.id, status="planned")
    transfer = ShiftTransfer(shift_id=shift.id, from_executor_id=initiator.id,
                             status="pending", reason="illness", urgency_level="normal")
    db_session.add(transfer)
    await db_session.commit()
    await db_session.refresh(transfer)

    resp = await client.post(
        f"/api/v2/shifts/transfers/{transfer.id}/handle",
        json={"action": "approve", "to_executor_id": recipient.id},
    )
    assert resp.status_code == 200, resp.text

    await db_session.refresh(transfer)
    await db_session.refresh(shift)
    assert transfer.status == "assigned"
    assert transfer.to_executor_id == recipient.id
    assert transfer.assigned_by == manager_user.id   # аудит менеджера
    assert shift.user_id == initiator.id             # shift НЕ переходит на assign-шаге


@pytest.mark.asyncio
async def test_handle_transfer_approve_notifies_recipient(client, db_session, manager_user):
    """CR-8: web-approve уведомляет получателя в Telegram с клавиатурой ответа,
    иначе приём передачи недостижим (web сам не слал push)."""
    from unittest.mock import patch, AsyncMock

    initiator = await _user(db_session, 2061)
    recipient = await _user(db_session, 2062)
    shift = await _shift(db_session, initiator.id, status="planned")
    transfer = ShiftTransfer(shift_id=shift.id, from_executor_id=initiator.id,
                             status="pending", reason="illness", urgency_level="normal")
    db_session.add(transfer)
    await db_session.commit()
    await db_session.refresh(transfer)

    fake_bot = AsyncMock()
    with patch(
        "uk_management_bot.services.notification_service._get_shared_bot",
        return_value=fake_bot,
    ):
        resp = await client.post(
            f"/api/v2/shifts/transfers/{transfer.id}/handle",
            json={"action": "approve", "to_executor_id": recipient.id},
        )
    assert resp.status_code == 200, resp.text
    fake_bot.send_message.assert_awaited_once()
    kwargs = fake_bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == recipient.telegram_id
    assert kwargs.get("reply_markup") is not None  # клавиатура accept/reject


@pytest.mark.asyncio
async def test_reassign_403_for_non_manager(client, db_session, resident_user):
    from uk_management_bot.api.main import app
    from uk_management_bot.api.dependencies import get_current_user

    old = await _user(db_session, 2051)
    new = await _user(db_session, 2052)
    shift = await _shift(db_session, old.id)

    app.dependency_overrides[get_current_user] = lambda: resident_user
    resp = await client.post(f"/api/v2/shifts/{shift.id}/reassign", json={"executor_id": new.id})
    assert resp.status_code == 403
