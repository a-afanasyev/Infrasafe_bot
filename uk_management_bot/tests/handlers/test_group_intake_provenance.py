"""Provenance группового источника — сквозь НАСТОЯЩИЙ save_request_sync.

Мок save_request в callback-тестах по построению не ловит рассинхрон ключей
data ↔ create_request_record (урок PR #477: мок CommandOutcome не поймал бы
классовую ошибку). Здесь путь создания проходит целиком на sqlite: валидация →
re-резолв адреса → номер → INSERT c source_chat_id/source_message_id → outbox →
commit.
"""
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models import (
    Apartment,
    Building,
    UserApartment,
    Yard,
)
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.handlers.requests.create import save_request_sync

TELEGRAM_ID = 111


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def apartment(db):
    yard = Yard(name="Двор Тестовый", is_active=True)
    building = Building(address="ул. Тестовая, 12", yard=yard, is_active=True)
    apt = Apartment(apartment_number="7", building=building, is_active=True)
    user = User(
        telegram_id=TELEGRAM_ID, roles='["applicant"]', active_role="applicant",
        status="approved", phone="+998901112233", language="ru",
    )
    db.add_all([yard, building, apt, user])
    db.commit()
    db.add(UserApartment(user_id=user.id, apartment_id=apt.id,
                         status="approved", is_primary=True))
    db.commit()
    return apt


@pytest.fixture(autouse=True)
def _no_dispatch(monkeypatch):
    # авто-dispatch открывает СВОЮ сессию через глобальную фабрику — в
    # sqlite-юните ему делать нечего (best-effort и в проде)
    import uk_management_bot.services.dispatch as dispatch_mod

    monkeypatch.setattr(
        dispatch_mod, "auto_dispatch_new_request_sync", MagicMock()
    )


def _data(apartment, **extra):
    data = {
        "category": "electricity",
        "urgency": "medium",
        "address_type": "apartment",
        "address_id": apartment.id,
        "description": "В подъезде не горит свет уже второй день",
        "media_files": [],
    }
    data.update(extra)
    return data


def test_group_source_persists_provenance(db, apartment):
    saved = save_request_sync(
        _data(apartment, source_chat_id=-100500, source_message_id=42),
        TELEGRAM_ID, db, source="group", role="applicant",
    )
    assert saved is not None
    number, _owner_id, _media = saved
    request = db.query(Request).filter(Request.request_number == number).one()
    assert request.source == "group"
    assert request.source_chat_id == -100500
    assert request.source_message_id == 42
    # адрес пришёл из резолвера, а не из клиента
    assert request.address_type == "apartment"
    assert request.apartment_id == apartment.id


def test_bot_source_leaves_provenance_null(db, apartment):
    saved = save_request_sync(
        _data(apartment), TELEGRAM_ID, db, source="bot", role="applicant"
    )
    assert saved is not None
    number = saved[0]
    request = db.query(Request).filter(Request.request_number == number).one()
    assert request.source_chat_id is None
    assert request.source_message_id is None


# ───────────── A9-P2-5: фото группы — маркер media_id, не чужой file_id ─────────────


@pytest.fixture()
def uploads(monkeypatch):
    """Внешний media-service подменён: загрузка возвращает его настоящий
    конверт ``{"media_file": {"id": …}}`` (плоский стаб прятал дефект PR #559)."""
    from unittest.mock import AsyncMock

    import uk_management_bot.utils.media_helpers as media_helpers

    upload = AsyncMock(return_value=[{"media_file": {"id": 501}, "file_url": "u"}])
    monkeypatch.setattr(media_helpers, "upload_multiple_telegram_files", upload)
    return upload


@pytest.mark.asyncio
async def test_group_photo_is_stored_as_media_marker(db, apartment, uploads):
    from uk_management_bot.handlers.requests.create import save_request
    from uk_management_bot.services.request_media_entries import (
        MediaEntry,
        parse_media_entries,
    )

    group_bot = MagicMock()
    number = await save_request(
        _data(apartment, source_chat_id=-100500, source_message_id=42),
        TELEGRAM_ID, db, group_bot, source="group", role="applicant",
        foreign_media_file_ids=["group-bot-file-id"],
    )
    assert number
    # скачивает ГРУППОВОЙ бот — file_id действителен только для него
    assert uploads.await_args.kwargs["bot"] is group_bot
    assert uploads.await_args.kwargs["file_ids"] == ["group-bot-file-id"]
    request = db.query(Request).filter(Request.request_number == number).one()
    db.refresh(request)
    assert request.media_files == [{"media_id": 501, "type": "photo"}]
    assert "group-bot-file-id" not in str(request.media_files)
    assert parse_media_entries(request.media_files) == [MediaEntry(kind="photo", media_id=501)]


@pytest.mark.asyncio
async def test_group_photo_upload_failure_keeps_request_without_foreign_id(
    db, apartment, uploads
):
    from uk_management_bot.handlers.requests.create import save_request

    uploads.return_value = []
    number = await save_request(
        _data(apartment, source_chat_id=-100500, source_message_id=42),
        TELEGRAM_ID, db, MagicMock(), source="group", role="applicant",
        foreign_media_file_ids=["group-bot-file-id"],
    )
    assert number
    request = db.query(Request).filter(Request.request_number == number).one()
    db.refresh(request)
    assert request.media_files == []
