"""Тесты FeedbackService + доставки обращений (Task 3)."""
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.feedback import Feedback
from uk_management_bot.services.feedback_service import (
    build_manager_notify_text,
    create_feedback_sync,
    manager_telegram_ids_sync,
)
from uk_management_bot.services.notification_service import deliver_feedback_to_managers


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _user(db, uid, tg, *, roles=None, role="applicant", status="approved", deleted_at=None):
    u = User(id=uid, telegram_id=tg, username=f"u{uid}", first_name="U",
             role=role, roles=roles, status=status, language="ru", deleted_at=deleted_at)
    db.add(u)
    db.commit()
    return u


def test_create_feedback_sync(db):
    _user(db, 1, 111)
    fb = create_feedback_sync(db, user_id=1, type_="complaint", text="Тёмный подъезд", source="bot")
    assert isinstance(fb, Feedback)
    assert fb.id is not None
    assert fb.status == "new"
    assert fb.media_files == []


def test_manager_enumeration_includes_json_and_legacy_excludes_inactive(db):
    _user(db, 1, 111, roles='["applicant", "manager"]')      # JSON roles → include
    _user(db, 2, 222, roles=None, role="manager")            # legacy role → include
    _user(db, 3, 333, roles='["applicant"]')                 # not a manager → exclude
    _user(db, 4, 444, role="manager", status="pending")      # pending → exclude
    _user(db, 5, 555, role="manager", deleted_at=__import__("datetime").datetime.utcnow())  # deleted → exclude
    ids = set(manager_telegram_ids_sync(db))
    assert ids == {111, 222}


def test_build_manager_notify_text_escapes_and_labels(db):
    txt = build_manager_notify_text(type_="complaint", text="<b>x</b> & y",
                                    author_name="Иван <a>", has_photo=False, lang="ru")
    assert "&lt;b&gt;x&lt;/b&gt; &amp; y" in txt
    assert "Иван &lt;a&gt;" in txt


@pytest.mark.asyncio
async def test_deliver_text_path():
    bot = Mock()
    bot.send_message = AsyncMock()
    captured = await deliver_feedback_to_managers(bot, telegram_ids=[1, 2], text="hi", photo=None)
    assert captured is None
    assert bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_deliver_photo_bytes_reuses_file_id():
    bot = Mock()
    photo_obj = Mock()
    photo_obj.file_id = "NEWFID"
    msg = Mock()
    msg.photo = [photo_obj]
    bot.send_photo = AsyncMock(return_value=msg)
    captured = await deliver_feedback_to_managers(bot, telegram_ids=[1, 2], text="hi", photo=b"rawbytes")
    assert captured == "NEWFID"
    assert bot.send_photo.await_count == 2
    # Первый вызов — байты (BufferedInputFile), второй — переиспользованный file_id.
    second_media = bot.send_photo.await_args_list[1].args[1]
    assert second_media == "NEWFID"
