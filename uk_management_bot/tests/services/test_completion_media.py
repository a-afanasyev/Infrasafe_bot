"""Тесты чтения фотоотчёта: media-service — SSOT, legacy-поле — фолбэк.

Сценарии решения владельца (2026-08-10):
- фото, загруженное менеджером с дашборда (есть только в media-service),
  видно ботовым читателям;
- media-service выключен/недоступен → работаем по legacy `completion_media`;
- legacy-поле разнородно (строки / dict'ы двух форм / JSON-строка) — парсер
  достаёт telegram file_id и не падает на мусоре.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.services import completion_media as cm
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


def _ms_item(file_id, category="completion_photo"):
    return {"id": 1, "telegram_file_id": file_id, "category": category, "file_type": "photo"}


class TestLegacyParse:
    def test_plain_file_id_strings(self):
        assert cm.legacy_completion_file_ids(["fid1", "fid2"]) == ["fid1", "fid2"]

    def test_executor_fallback_dicts(self):
        raw = [{"type": "photo", "file_id": "fid1"}, {"type": "video", "file_id": "fid2"}]
        assert cm.legacy_completion_file_ids(raw) == ["fid1", "fid2"]

    def test_media_service_dicts_without_file_id_skipped(self):
        raw = [{"media_id": 7, "file_url": "/api/v1/media/7/file", "type": "photo"}]
        assert cm.legacy_completion_file_ids(raw) == []

    def test_json_string_form(self):
        assert cm.legacy_completion_file_ids('["fid1"]') == ["fid1"]

    def test_garbage_and_empty(self):
        assert cm.legacy_completion_file_ids(None) == []
        assert cm.legacy_completion_file_ids("") == []
        assert cm.legacy_completion_file_ids("not json") == []
        assert cm.legacy_completion_file_ids({"file_id": "x"}) == []


class TestResolver:
    async def test_media_service_wins_and_filters_categories(self, monkeypatch):
        client = FakeMediaClient(items=[
            _ms_item("req_fid", category="request_photo"),
            _ms_item("comp_fid", category="completion_photo"),
            _ms_item("comp_vid", category="completion_video"),
        ])
        monkeypatch.setattr(cm, "get_media_client", lambda: client)
        result = await cm.get_completion_media_file_ids("260810-001", ["legacy_fid"])
        # request_photo отфильтрован; legacy не подмешивается, когда SSOT дал ответ.
        assert result == ["comp_fid", "comp_vid"]
        # Один HTTP-вызов без фильтра категории, fail-fast (retries=1).
        assert client.calls == [("260810-001", None, 1)]

    async def test_client_disabled_falls_back_to_legacy(self, monkeypatch):
        monkeypatch.setattr(cm, "get_media_client", lambda: None)
        result = await cm.get_completion_media_file_ids("260810-001", ["legacy_fid"])
        assert result == ["legacy_fid"]

    async def test_client_error_falls_back_to_legacy(self, monkeypatch):
        client = FakeMediaClient(exc=ConnectionError("down"))
        monkeypatch.setattr(cm, "get_media_client", lambda: client)
        result = await cm.get_completion_media_file_ids("260810-001", ["legacy_fid"])
        assert result == ["legacy_fid"]

    async def test_no_completion_items_falls_back_to_legacy(self, monkeypatch):
        # media-service отвечает, но фотоотчёта там нет (только фото заявки) —
        # покрывает старые заявки, где отчёт остался в legacy-поле.
        client = FakeMediaClient(items=[_ms_item("req_fid", category="request_photo")])
        monkeypatch.setattr(cm, "get_media_client", lambda: client)
        result = await cm.get_completion_media_file_ids("260810-001", ["legacy_fid"])
        assert result == ["legacy_fid"]

    async def test_everything_empty(self, monkeypatch):
        monkeypatch.setattr(cm, "get_media_client", lambda: FakeMediaClient())
        assert await cm.get_completion_media_file_ids("260810-001", None) == []

    async def test_items_without_telegram_file_id_ignored(self, monkeypatch):
        client = FakeMediaClient(items=[
            {"id": 1, "category": "completion_photo", "telegram_file_id": None},
            _ms_item("ok_fid"),
        ])
        monkeypatch.setattr(cm, "get_media_client", lambda: client)
        assert await cm.get_completion_media_file_ids("260810-001", None) == ["ok_fid"]


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
    from uk_management_bot.handlers.request_acceptance import view_completion_media

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

    client = FakeMediaClient(items=[_ms_item("dash_fid")])
    monkeypatch.setattr(cm, "get_media_client", lambda: client)

    cb = _mk_callback(req.request_number, OWNER_TG)
    # AUD3-37: тестовый seam db-фазы — keyword-only `_db`.
    await view_completion_media(cb, _db=db)

    cb.message.answer_photo.assert_awaited_once()
    assert cb.message.answer_photo.await_args.kwargs.get("photo") == "dash_fid"
