"""«Закрыть этим фото?» — callback ``exdone:{n}`` основного бота (Фаза 4).

Сервис ``complete_with_photo`` — мок: здесь проверяется адаптер (формат
callback_data, «нажимает тот, кому отправлено», фото из сообщения, стабильный
ключ идемпотентности, маппинг отказов, правка подписи). Сам сервис покрыт
tests/services/test_executor_completion*.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import uk_management_bot.handlers.executor_done as ed
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.executor_completion import (
    CompletionRefused,
    CompletionResult,
)

EXEC_TG = 501
NUMBER = "260925-001"
PHOTO = b"\xff\xd8\xff\xe0jpeg"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=7, telegram_id=EXEC_TG, roles='["executor"]', active_role="executor",
                     status="approved", language="uz"))
    session.add(User(id=8, telegram_id=777, roles='["applicant"]', status="approved"))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def complete(monkeypatch):
    mock = AsyncMock(return_value=CompletionResult(NUMBER, 55, None))
    monkeypatch.setattr(ed, "complete_with_photo", mock)
    monkeypatch.setattr(ed, "_session_factory", lambda: "SESSION_FACTORY")
    post = AsyncMock()
    monkeypatch.setattr(ed, "_post_commit", post)
    mock.post_commit = post
    return mock


def make_callback(data=f"exdone:{NUMBER}", *, from_id=EXEC_TG, chat_id=EXEC_TG,
                  chat_type="private", photo=True, message_id=900):
    async def download_file(path, buffer):
        buffer.write(PHOTO)

    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="photos/a.jpg")),
        download_file=AsyncMock(side_effect=download_file),
    )
    message = SimpleNamespace(
        chat=SimpleNamespace(id=chat_id, type=chat_type),
        message_id=message_id,
        photo=[SimpleNamespace(file_id="s"), SimpleNamespace(file_id="main-big")] if photo else None,
        edit_caption=AsyncMock(),
        answer=AsyncMock(),
    )
    return SimpleNamespace(
        data=data, message=message, bot=bot,
        from_user=SimpleNamespace(id=from_id, language_code="ru"),
        answer=AsyncMock(),
    )


@pytest.mark.parametrize("data,expected", [
    (f"exdone:{NUMBER}", NUMBER),
    ("exdone:260925-0012", "260925-0012"),
    ("exdone:", None),
    ("exdone:abc", None),
    ("exdone:260925-001;drop", None),
    ("exdone:" + "1" * 70, None),
    (None, None),
])
def test_parse_close_callback(data, expected):
    assert ed.parse_close_callback(data) == expected


def test_idempotency_key_is_stable_per_message_and_request():
    a = ed.idempotency_key(EXEC_TG, 900, NUMBER)
    assert a == ed.idempotency_key(EXEC_TG, 900, NUMBER)
    assert a != ed.idempotency_key(EXEC_TG, 901, NUMBER)
    assert a != ed.idempotency_key(EXEC_TG, 900, "260925-002")


async def test_photo_closes_via_service_and_edits_caption(db, complete):
    callback = make_callback()
    await ed.close_with_photo(callback, _db=db)

    callback.bot.get_file.assert_awaited_once_with("main-big")
    complete.assert_awaited_once()
    args, kwargs = complete.call_args
    assert args == ("SESSION_FACTORY", NUMBER, 7, PHOTO,
                    ed.idempotency_key(EXEC_TG, 900, NUMBER))
    assert kwargs == {"source": "bot"}
    callback.answer.assert_awaited_once()
    caption = callback.message.edit_caption.call_args.kwargs
    assert NUMBER in caption["caption"] and caption["reply_markup"] is None
    # Повтор/уже закрыта — outcome None: post-commit не нужен.
    complete.post_commit.assert_not_awaited()


async def test_double_press_uses_same_key(db, complete):
    first, second = make_callback(), make_callback()
    await ed.close_with_photo(first, _db=db)
    await ed.close_with_photo(second, _db=db)
    keys = {c.args[4] for c in complete.call_args_list}
    assert len(keys) == 1


async def test_post_commit_runs_when_transition_happened(db, complete):
    outcome = SimpleNamespace(post_commit_intents=())
    complete.return_value = CompletionResult(NUMBER, 55, outcome)
    await ed.close_with_photo(make_callback(), _db=db)
    complete.post_commit.assert_awaited_once_with(NUMBER, outcome)


async def test_foreign_presser_is_refused(db, complete):
    callback = make_callback(from_id=777, chat_id=EXEC_TG)
    await ed.close_with_photo(callback, _db=db)
    complete.assert_not_awaited()
    assert callback.answer.call_args.kwargs.get("show_alert") is True


async def test_group_chat_is_refused(db, complete):
    callback = make_callback(chat_type="supergroup", chat_id=EXEC_TG)
    await ed.close_with_photo(callback, _db=db)
    complete.assert_not_awaited()


async def test_non_executor_is_refused(db, complete):
    callback = make_callback(from_id=777, chat_id=777)
    await ed.close_with_photo(callback, _db=db)
    complete.assert_not_awaited()
    assert callback.answer.call_args.kwargs.get("show_alert") is True


async def test_crafted_callback_data_is_refused(db, complete):
    callback = make_callback(data="exdone:../../etc")
    await ed.close_with_photo(callback, _db=db)
    complete.assert_not_awaited()
    callback.answer.assert_awaited_once()


async def test_message_without_photo_is_refused(db, complete):
    callback = make_callback(photo=False)
    await ed.close_with_photo(callback, _db=db)
    complete.assert_not_awaited()


@pytest.mark.parametrize("code,expected", [
    ("not_assigned", "Bu sizning arizangiz emas."),
    ("no_active_shift", "Avval smenani boshlang."),
    ("invalid_status", f"#{NUMBER} arizani hozir yopib bo'lmaydi."),
    ("in_progress", "Yopilmoqda, kuting."),
    ("media_unavailable", "Rasm yuborilmadi. Yana urinib ko'ring."),
    ("media_rejected", "Rasm yuborilmadi. Yana urinib ko'ring."),
    ("invalid_idempotency_key", "Bo'lmadi. Keyinroq urinib ko'ring."),
    ("workflow_error", "Bo'lmadi. Keyinroq urinib ko'ring."),
])
async def test_refusal_mapped_to_short_phrase_in_user_language(db, complete, code, expected):
    complete.side_effect = CompletionRefused(code, 409)
    callback = make_callback()
    await ed.close_with_photo(callback, _db=db)
    callback.message.answer.assert_awaited_once_with(expected)
    callback.message.edit_caption.assert_not_awaited()
    callback.answer.assert_awaited_once()
