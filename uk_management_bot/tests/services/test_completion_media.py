"""Тесты чтения фотоотчёта: media-service — SSOT, legacy-поле — фолбэк.

Сценарии решения владельца (2026-08-10):
- фото, загруженное менеджером с дашборда (есть только в media-service),
  видно ботовым читателям;
- media-service выключен/недоступен → работаем по legacy `completion_media`;
- legacy-поле разнородно (строки / dict'ы двух форм / JSON-строка) — парсер
  достаёт telegram file_id и не падает на мусоре;
- файлы media-service уходят БАЙТАМИ (media_id), не file_id media-бота.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import BufferedInputFile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.services import completion_media as cm
from uk_management_bot.services.request_media_entries import MediaEntry
from uk_management_bot.utils.constants import REQUEST_STATUS_COMPLETED


class FakeMediaClient:
    def __init__(self, items=None, exc=None):
        self.items = items if items is not None else []
        self.exc = exc
        self.calls = []

    async def get_request_media(self, request_number, category=None, limit=50, retries=None):
        self.calls.append((request_number, category, retries))
        if self.exc is not None:
            raise self.exc
        return self.items


def _ms_item(media_id, category="completion_photo", file_type="photo"):
    return {"id": media_id, "telegram_file_id": f"media_bot_fid_{media_id}",
            "category": category, "file_type": file_type}


def _fid(file_id, kind="photo"):
    return MediaEntry(kind=kind, file_id=file_id)


def _mid(media_id, kind="photo"):
    return MediaEntry(kind=kind, media_id=media_id)


class TestLegacyParse:
    def test_plain_file_id_strings(self):
        assert cm.legacy_completion_entries(["fid1", "fid2"]) == [_fid("fid1"), _fid("fid2")]

    def test_executor_fallback_dicts_keep_kind(self):
        raw = [{"type": "photo", "file_id": "fid1"}, {"type": "video", "file_id": "fid2"}]
        assert cm.legacy_completion_entries(raw) == [_fid("fid1"), _fid("fid2", "video")]

    def test_media_service_dicts_without_file_id_skipped(self):
        raw = [{"media_id": 7, "file_url": "/api/v1/media/7/file", "type": "photo"}]
        assert cm.legacy_completion_entries(raw) == []

    def test_json_string_form(self):
        assert cm.legacy_completion_entries('["fid1"]') == [_fid("fid1")]

    def test_garbage_and_empty(self):
        assert cm.legacy_completion_entries(None) == []
        assert cm.legacy_completion_entries("") == []
        assert cm.legacy_completion_entries("not json") == []
        assert cm.legacy_completion_entries({"file_id": "x"}) == []


class TestResolver:
    async def test_media_service_wins_filters_categories_and_uses_media_id(self, monkeypatch):
        client = FakeMediaClient(items=[
            _ms_item(1, category="request_photo"),
            _ms_item(2, category="completion_photo"),
            _ms_item(3, category="completion_video", file_type="video"),
        ])
        monkeypatch.setattr(cm, "get_media_client", lambda: client)
        result = await cm.get_completion_media_entries("260810-001", ["legacy_fid"])
        # request_photo отфильтрован; legacy не подмешивается, когда SSOT дал ответ.
        # telegram_file_id media-бота НЕ используется — только media_id (байты).
        assert result == [_mid(2), _mid(3, "video")]
        # Один HTTP-вызов без фильтра категории, fail-fast (retries=1).
        assert client.calls == [("260810-001", None, 1)]

    async def test_kind_falls_back_to_category(self, monkeypatch):
        client = FakeMediaClient(items=[
            {"id": 5, "category": "completion_document", "file_type": None},
        ])
        monkeypatch.setattr(cm, "get_media_client", lambda: client)
        assert await cm.get_completion_media_entries("260810-001", None) == [_mid(5, "document")]

    async def test_client_disabled_falls_back_to_legacy(self, monkeypatch):
        monkeypatch.setattr(cm, "get_media_client", lambda: None)
        result = await cm.get_completion_media_entries("260810-001", ["legacy_fid"])
        assert result == [_fid("legacy_fid")]

    async def test_client_error_falls_back_to_legacy(self, monkeypatch):
        client = FakeMediaClient(exc=ConnectionError("down"))
        monkeypatch.setattr(cm, "get_media_client", lambda: client)
        result = await cm.get_completion_media_entries("260810-001", ["legacy_fid"])
        assert result == [_fid("legacy_fid")]

    async def test_no_completion_items_falls_back_to_legacy(self, monkeypatch):
        # media-service отвечает, но фотоотчёта там нет (только фото заявки) —
        # покрывает старые заявки, где отчёт остался в legacy-поле.
        client = FakeMediaClient(items=[_ms_item(1, category="request_photo")])
        monkeypatch.setattr(cm, "get_media_client", lambda: client)
        result = await cm.get_completion_media_entries("260810-001", ["legacy_fid"])
        assert result == [_fid("legacy_fid")]

    async def test_everything_empty(self, monkeypatch):
        monkeypatch.setattr(cm, "get_media_client", lambda: FakeMediaClient())
        assert await cm.get_completion_media_entries("260810-001", None) == []

    async def test_items_without_int_id_ignored(self, monkeypatch):
        client = FakeMediaClient(items=[
            {"id": None, "category": "completion_photo"},
            {"id": True, "category": "completion_photo"},
            "garbage",
            _ms_item(9),
        ])
        monkeypatch.setattr(cm, "get_media_client", lambda: client)
        assert await cm.get_completion_media_entries("260810-001", None) == [_mid(9)]


# ---------------------------------------------------------------------------
# Сквозной сценарий: фото менеджера с дашборда (только в media-service, legacy
# пуст) доходит до заявителя через кнопку «посмотреть медиа» в боте.
# ---------------------------------------------------------------------------

OWNER_TG = 111


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(bind=engine)
    SF = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SF()
    session.add(User(id=1, telegram_id=OWNER_TG, first_name="Owner",
                     roles='["applicant"]', status="approved", language="ru"))
    session.commit()
    with patch("uk_management_bot.database.session.SessionLocal", SF):
        yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _mk_callback(request_number, telegram_id):
    cb = MagicMock()
    cb.from_user.id = telegram_id
    cb.data = f"view_completion_media_{request_number}"
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.answer_photo = AsyncMock()
    cb.message.answer_document = AsyncMock()
    cb.message.answer_media_group = AsyncMock()
    cb.answer = AsyncMock()
    return cb


async def test_dashboard_uploaded_photo_reaches_bot_viewer(db, monkeypatch):
    from uk_management_bot.handlers import request_acceptance as ra

    req = Request(
        request_number="260810-777",
        user_id=1,
        category="electricity",
        status=REQUEST_STATUS_COMPLETED,
        description="test",
        urgency="low",
        completion_media=None,  # legacy пуст — файл существует только в media-service
        updated_at=datetime.now(timezone.utc),
    )
    db.add(req)
    db.commit()

    client = FakeMediaClient(items=[_ms_item(42)])
    client.download_media_file = AsyncMock(return_value=(b"\xff\xd8jpeg", "image/jpeg"))
    monkeypatch.setattr(cm, "get_media_client", lambda: client)
    monkeypatch.setattr(ra, "get_media_client", lambda: client)

    cb = _mk_callback(req.request_number, OWNER_TG)
    # AUD3-37: тестовый seam db-фазы — keyword-only `_db`.
    await ra.view_completion_media(cb, _db=db)

    # Байты из media-service, а НЕ telegram_file_id media-бота: у основного
    # бота другой токен, чужой file_id Telegram отвергает.
    client.download_media_file.assert_awaited_once_with(42)
    cb.message.answer_photo.assert_awaited_once()
    photo = cb.message.answer_photo.await_args.kwargs.get("photo")
    assert isinstance(photo, BufferedInputFile)
    assert photo.data == b"\xff\xd8jpeg"


async def test_manager_view_sends_completion_bytes(monkeypatch):
    """Менеджерский «Медиа» (admin/views): тот же путь — байты, чанки."""
    from uk_management_bot.handlers.admin import views

    client = FakeMediaClient(items=[_ms_item(i) for i in range(1, 12)])
    client.download_media_file = AsyncMock(return_value=(b"img", "image/jpeg"))
    monkeypatch.setattr(cm, "get_media_client", lambda: client)
    monkeypatch.setattr(views, "get_media_client", lambda: client)

    request = MagicMock(request_number="260810-778", media_files=None, completion_media=None)
    svc = MagicMock()
    svc.return_value.get_request_by_number.return_value = request
    monkeypatch.setattr(views, "AdminHandlerService", svc)
    monkeypatch.setattr(views, "has_admin_access", lambda **kw: True)

    cb = _mk_callback(request.request_number, OWNER_TG)
    cb.data = f"media_{request.request_number}"
    await views.handle_view_request_media(cb, db=MagicMock(), roles=["manager"], user=MagicMock())

    assert client.download_media_file.await_count == 11
    # 11 фото → группа из 10 + одиночное фото (лимит медиагруппы Telegram).
    cb.message.answer_media_group.assert_awaited_once()
    assert len(cb.message.answer_media_group.await_args.kwargs["media"]) == 10
    cb.message.answer_photo.assert_awaited_once()
