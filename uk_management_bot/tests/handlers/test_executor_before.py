"""Бот: «📷 Фото до работ» исполнителя (handlers/requests/executor_before).

Сервис (`upload_before_photo`) мокается — его права/лимит/идемпотентность
проверяет tests/api/test_request_before_photo.py; здесь — формат callback_data,
FSM, ключ идемпотентности и тексты отказов.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from uk_management_bot.handlers.requests import executor_before as eb
from uk_management_bot.services.executor_completion import CompletionRefused

NUMBER = "260705-952"
TG = 6055402868


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(eb, "_before_actor", AsyncMock(return_value=("ru", 41)))
    monkeypatch.setattr(eb, "_session_factory", lambda: "factory")
    monkeypatch.setattr(eb, "_download", AsyncMock(side_effect=lambda bot, fid: f"bytes-{fid}".encode()))


class FakeState:
    def __init__(self, data=None):
        self.data = dict(data or {})
        self.state = None
        self.key = ("chat", TG)

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, data=None, **kw):
        self.data.update(data or {}, **kw)

    async def set_state(self, value):
        self.state = value

    async def clear(self):
        self.data.clear()
        self.state = None


def _callback(data):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = TG
    cb.answer = AsyncMock()
    cb.message.answer = AsyncMock()
    return cb


def _photo_message(fid, uid, mid):
    msg = MagicMock()
    msg.from_user.id = TG
    msg.media_group_id = None
    msg.message_id = mid
    msg.photo = [MagicMock(file_id=fid, file_unique_id=uid)]
    msg.answer = AsyncMock()
    return msg


def test_parse_rejects_foreign_formats():
    assert eb.parse_number(eb._START_RE, f"executor_before_{NUMBER}") == NUMBER
    assert eb.parse_number(eb._START_RE, f"executor_before_done_{NUMBER}") is None
    assert eb.parse_number(eb._DONE_RE, f"executor_before_done_{NUMBER}") == NUMBER
    assert eb.parse_number(eb._START_RE, "executor_before_../etc") is None


def test_idempotency_key_is_stable_per_photo():
    a = eb.idempotency_key(TG, NUMBER, "u1")
    assert a == eb.idempotency_key(TG, NUMBER, "u1")
    assert a != eb.idempotency_key(TG, NUMBER, "u2")
    assert a != eb.idempotency_key(TG, "260705-953", "u1")


@pytest.mark.asyncio
async def test_start_collect_done_uploads_each_photo(monkeypatch):
    upload = AsyncMock()
    monkeypatch.setattr(eb, "upload_before_photo", upload)
    state = FakeState()
    await eb.executor_before_start(_callback(f"executor_before_{NUMBER}"), state)
    assert state.state == eb.ExecutorBeforeStates.waiting_before_media

    for i in (1, 2):
        await eb.executor_before_collect(_photo_message(f"f{i}", f"u{i}", i), state)

    done = _callback(f"executor_before_done_{NUMBER}")
    await eb.executor_before_done(done, state)

    assert upload.await_count == 2
    first = upload.await_args_list[0].args
    assert first[:4] == ("factory", NUMBER, 41, b"bytes-f1")
    assert first[4] == eb.idempotency_key(TG, NUMBER, "u1")
    text = done.message.answer.await_args.args[0]
    assert "Загружено фото «до»: 2" in text
    assert state.data == {}


@pytest.mark.asyncio
async def test_collect_stops_at_limit():
    state = FakeState({"before_request_number": NUMBER, "before_media": []})
    for i in range(1, 6):
        await eb.executor_before_collect(_photo_message(f"f{i}", f"u{i}", i), state)
    assert len(state.data["before_media"]) == eb.BEFORE_PHOTO_LIMIT


@pytest.mark.asyncio
async def test_refusal_is_short_phrase_and_stops(monkeypatch):
    upload = AsyncMock(side_effect=CompletionRefused("before_limit", 409))
    monkeypatch.setattr(eb, "upload_before_photo", upload)
    state = FakeState({"before_request_number": NUMBER,
                       "before_media": [{"file_id": "f1", "file_unique_id": "u1"},
                                        {"file_id": "f2", "file_unique_id": "u2"}]})
    done = _callback(f"executor_before_done_{NUMBER}")
    await eb.executor_before_done(done, state)
    upload.assert_awaited_once()
    assert done.message.answer.await_args.args[0] == "У заявки уже 4 фото «до» — больше нельзя"


@pytest.mark.asyncio
async def test_done_for_other_request_than_collected_is_ignored(monkeypatch):
    upload = AsyncMock()
    monkeypatch.setattr(eb, "upload_before_photo", upload)
    state = FakeState({"before_request_number": "260705-999",
                       "before_media": [{"file_id": "f1", "file_unique_id": "u1"}]})
    await eb.executor_before_done(_callback(f"executor_before_done_{NUMBER}"), state)
    upload.assert_not_awaited()
    assert state.data["before_media"]  # чужой «Готово» не сбрасывает сбор
