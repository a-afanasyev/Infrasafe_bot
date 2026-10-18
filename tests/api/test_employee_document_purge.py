"""Раздел «Сотрудники» тоже закрывает проверку — документы и ключи удаляются.

approve/reject (verification_status), активация (pending→verified) и мягкое
удаление (deleted_at) — каждый путь удаляет документы до смены статуса и
отдаёт PurgeResult; роутер чистит медиа по точным id после commit.
"""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from uk_management_bot.api.shifts import service
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_verification import DocumentType, UserDocument

pytestmark = pytest.mark.asyncio
EP = "/api/v2/shifts/employees"


async def _user_with_doc(db, tg, *, roles='["applicant", "executor"]', verification="pending",
                         status="pending", media_id=None):
    u = User(telegram_id=tg, first_name="S", last_name=str(tg), roles=roles,
             active_role="applicant", status=status, verification_status=verification)
    db.add(u)
    await db.flush()
    media_id = media_id or tg
    db.add(UserDocument(user_id=u.id, document_type=DocumentType.PASSPORT, media_id=media_id,
                        encryption_key=b"k" * 32,
                        document_uuid=f"00000000-0000-4000-8000-{media_id:012d}"))
    await db.commit()
    await db.refresh(u)
    return u


async def _docs(db, user_id):
    return (await db.execute(
        select(func.count()).select_from(UserDocument).where(UserDocument.user_id == user_id)
    )).scalar()


@pytest.mark.parametrize("value", ["verified", "rejected"])
async def test_set_user_verification_purges(db_session, value):
    u = await _user_with_doc(db_session, 3101 if value == "verified" else 3102)
    purge = await service.set_user_verification(db_session, u, value)
    assert purge.media_ids == (u.telegram_id,)
    assert u.verification_status == value
    assert await _docs(db_session, u.id) == 0


async def test_activate_pending_purges(db_session):
    u = await _user_with_doc(db_session, 3103)
    purge = await service.activate_employee(db_session, u)
    assert u.verification_status == "verified"
    assert purge.media_ids == (3103,)
    assert await _docs(db_session, u.id) == 0


async def test_activate_with_open_requested_keeps_documents(db_session):
    """Активация не меняет `requested` — проверка открыта, документы остаются."""
    u = await _user_with_doc(db_session, 3104, verification="requested")
    purge = await service.activate_employee(db_session, u)
    assert purge.empty
    assert await _docs(db_session, u.id) == 1


async def test_soft_delete_purges(db_session):
    u = await _user_with_doc(db_session, 3105, status="approved", verification="verified")
    purge = await service.soft_delete_employee(
        db_session, user=u, reassign_to=None, reason="уволен", deleted_by_id=u.id, active_count=0,
    )
    assert purge.media_ids == (3105,)
    assert await _docs(db_session, u.id) == 0


async def test_delete_endpoint_cleans_media(client, db_session):
    u = await _user_with_doc(db_session, 3106, status="approved", verification="verified")
    with patch("uk_management_bot.api.shifts.router.employees.cleanup_purged_documents",
               new=AsyncMock()) as cleanup:
        r = await client.patch(f"{EP}/{u.id}/delete", json={"reason": "уволен"})
    assert r.status_code == 200, r.text
    assert cleanup.await_args.args[0].media_ids == (3106,)


async def test_reject_endpoint_cleans_media(client, db_session):
    u = await _user_with_doc(db_session, 3107)
    with patch("uk_management_bot.api.shifts.router.employees.cleanup_purged_documents",
               new=AsyncMock()) as cleanup:
        r = await client.patch(f"{EP}/{u.id}/reject")
    assert r.status_code == 200, r.text
    assert cleanup.await_args.args[0].media_ids == (3107,)
