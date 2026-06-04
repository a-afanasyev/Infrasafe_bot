"""Тесты FSM-обработчиков обратной связи (Task 4)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.feedback import Feedback
from uk_management_bot.handlers import feedback as fb_handlers
from uk_management_bot.states.feedback import FeedbackStates


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    session.add(User(id=1, telegram_id=111, username="u", first_name="U",
                     role="applicant", status="approved", language="ru"))
    session.add(User(id=2, telegram_id=222, first_name="Mgr",
                     role="manager", status="approved", language="ru"))
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _state(data=None):
    st = AsyncMock()
    st.get_data = AsyncMock(return_value=data or {})
    return st


@pytest.mark.asyncio
async def test_text_too_short_does_not_advance():
    msg = MagicMock()
    msg.text = "коротко"  # < 10
    msg.answer = AsyncMock()
    st = _state()
    await fb_handlers.feedback_text(msg, st, language="ru")
    msg.answer.assert_awaited()           # показали ошибку валидации
    st.set_state.assert_not_called()      # состояние не сменили


@pytest.mark.asyncio
async def test_text_valid_advances_to_photo():
    msg = MagicMock()
    msg.text = "Лифт не работает уже целую неделю"
    msg.answer = AsyncMock()
    st = _state()
    await fb_handlers.feedback_text(msg, st, language="ru")
    st.update_data.assert_awaited_with(text="Лифт не работает уже целую неделю")
    st.set_state.assert_awaited_with(FeedbackStates.waiting_for_photo)


@pytest.mark.asyncio
async def test_confirm_creates_feedback_and_notifies(db):
    cb = MagicMock()
    cb.from_user.id = 111
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    st = _state({"type_": "complaint", "text": "Очень тёмный подъезд вечером", "photo_file_id": None})
    bot = MagicMock()

    with patch.object(fb_handlers, "deliver_feedback_to_managers", new=AsyncMock()) as deliver:
        await fb_handlers.feedback_confirm(cb, st, db, bot, language="ru")

    rows = db.query(Feedback).all()
    assert len(rows) == 1
    assert rows[0].type == "complaint"
    assert rows[0].source == "bot"
    deliver.assert_awaited_once()
    # менеджер 222 в списке получателей
    assert 222 in deliver.await_args.kwargs["telegram_ids"]
    st.clear.assert_awaited()


@pytest.mark.asyncio
async def test_confirm_with_photo_uploads_media(db):
    cb = MagicMock()
    cb.from_user.id = 111
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    st = _state({"type_": "wish", "text": "Хочется больше зелени во дворе", "photo_file_id": "FILEID"})
    bot = MagicMock()

    media_resp = {"media_file": {"id": 77, "telegram_file_id": "TGFID"}}
    with patch.object(fb_handlers, "deliver_feedback_to_managers", new=AsyncMock()), \
         patch.object(fb_handlers, "upload_telegram_file_to_media_service",
                      new=AsyncMock(return_value=media_resp)) as upload:
        await fb_handlers.feedback_confirm(cb, st, db, bot, language="ru")

    upload.assert_awaited_once()
    assert upload.await_args.kwargs["request_number"].startswith("fb-")
    assert upload.await_args.kwargs["category"] == "feedback_photo"
    fb = db.query(Feedback).one()
    assert fb.media_files == [77]
