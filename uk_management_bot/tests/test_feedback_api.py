"""Тесты API обратной связи (Task 5).

Вызывают функции роутера напрямую с мок-сессией (стиль test_api_profile_router):
проверяют валидацию create, переходы статуса и доставку ответа пользователю.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from uk_management_bot.api.feedback import router as fb_router
from uk_management_bot.database.models.feedback import Feedback


# create_feedback обёрнут @limiter.limit — берём оригинал, чтобы не дёргать rate-limiter.
_create = getattr(fb_router.create_feedback, "__wrapped__", fb_router.create_feedback)


def _user(uid=1, tg=100):
    u = MagicMock()
    u.id = uid
    u.telegram_id = tg
    u.first_name = "Ivan"
    u.last_name = "Petrov"
    u.username = "ivan"
    u.language = "ru"
    u.phone = "+998901112233"
    return u


def _db_for_create():
    db = MagicMock()

    def _add(obj):
        obj.id = 1
        if getattr(obj, "status", None) is None:
            obj.status = "new"

    db.add = MagicMock(side_effect=_add)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_create_no_file_returns_feedback():
    db = _db_for_create()
    with patch.object(fb_router, "manager_telegram_ids_async", new=AsyncMock(return_value=[])), \
         patch.object(fb_router, "deliver_feedback_to_managers", new=AsyncMock()) as deliver, \
         patch.object(fb_router, "_get_shared_bot", new=MagicMock()):
        out = await _create(
            request=MagicMock(), feedback_type="complaint",
            text="Достаточно длинный текст жалобы", file=None, user=_user(), db=db,
        )
    assert out.id == 1
    assert out.type == "complaint"
    assert out.status == "new"
    deliver.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_bad_type_422():
    with pytest.raises(HTTPException) as e:
        await _create(request=MagicMock(), feedback_type="spam", text="x" * 20, file=None, user=_user(), db=_db_for_create())
    assert e.value.status_code == 422


@pytest.mark.asyncio
async def test_create_short_text_422():
    with pytest.raises(HTTPException) as e:
        await _create(request=MagicMock(), feedback_type="wish", text="кратко", file=None, user=_user(), db=_db_for_create())
    assert e.value.status_code == 422


@pytest.mark.asyncio
async def test_create_non_image_file_422():
    bad = MagicMock()
    bad.read = AsyncMock(return_value=b"fakebytes")
    bad.content_type = "image/heic"
    bad.filename = "photo.heic"
    with pytest.raises(HTTPException) as e:
        await _create(request=MagicMock(), feedback_type="complaint", text="Достаточно длинный текст",
                      file=bad, user=_user(), db=_db_for_create())
    assert e.value.status_code == 422


def _result(scalar_one_or_none=None):
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=scalar_one_or_none)
    return r


@pytest.mark.asyncio
async def test_update_invalid_transition_422():
    fb = Feedback(id=5, user_id=1, type="complaint", text="t", status="resolved", source="twa", media_files=[])
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(fb))
    from uk_management_bot.api.feedback.schemas import FeedbackUpdate
    with pytest.raises(HTTPException) as e:
        await fb_router.update_feedback(5, FeedbackUpdate(status="new"), user=_user(), db=db)
    assert e.value.status_code == 422


@pytest.mark.asyncio
async def test_update_valid_status_change():
    fb = Feedback(id=5, user_id=1, type="complaint", text="t", status="new", source="twa", media_files=[])
    author = _user()
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_result(fb), _result(author)])
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    from uk_management_bot.api.feedback.schemas import FeedbackUpdate
    out = await fb_router.update_feedback(5, FeedbackUpdate(status="in_review"), user=_user(), db=db)
    assert fb.status == "in_review"
    assert out.status == "in_review"


@pytest.mark.asyncio
async def test_update_reply_notifies_user():
    fb = Feedback(id=5, user_id=1, type="complaint", text="t", status="new", source="twa", media_files=[])
    author = _user(tg=555)
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_result(fb), _result(author)])
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    from uk_management_bot.api.feedback.schemas import FeedbackUpdate
    with patch.object(fb_router, "send_feedback_reply_to_user", new=AsyncMock()) as reply_send, \
         patch.object(fb_router, "_get_shared_bot", new=MagicMock()):
        out = await fb_router.update_feedback(5, FeedbackUpdate(reply="Спасибо за обращение"), user=_user(), db=db)
    assert fb.reply == "Спасибо за обращение"
    assert out.reply == "Спасибо за обращение"
    reply_send.assert_awaited_once()
    assert reply_send.await_args.kwargs["telegram_id"] == 555
