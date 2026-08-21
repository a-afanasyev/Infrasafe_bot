"""Юнит-матрица callback-фазы Group Intake (кнопки gint:yes|no|other).

Контракты: ровно один callback.answer() на нажатие; решает только автор;
GETDEL-идемпотентность двойного «Да»; ре-гейт при «Да»; provenance в data
для save_request.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import uk_management_bot.handlers.group_intake as gi
from uk_management_bot.config.settings import settings
from uk_management_bot.database.session import Base
from uk_management_bot.database.models import MonitoredGroup
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User

CHAT_ID = -100500
PROMPT_ID = 777
AUTHOR_ID = 111


def make_candidate(**overrides):
    candidate = {
        "v": 1,
        "kind": "residents",
        "author_id": AUTHOR_ID,
        "source_message_id": 42,
        "text": "В подъезде не горит свет",
        "truncated": False,
        "category": "electricity",
        "urgency": "medium",
        "confidence": 0.9,
        "location_scope": "building",
        "photo_file_id": None,
        "selected_address": {
            "type": "building", "id": 5,
            "label_public": "ул. Тестовая, 12",
            "label_full": "ул. Тестовая, 12 (Двор Тестовый)",
        },
        "lang": "ru",
    }
    candidate.update(overrides)
    return candidate


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
def env(monkeypatch):
    monkeypatch.setattr(settings, "GROUP_INTAKE_ENABLED", True)
    monkeypatch.setattr(settings, "BOT_USERNAME", "test_bot")
    mocks = SimpleNamespace(
        get_candidate=AsyncMock(return_value=make_candidate()),
        pop_candidate=AsyncMock(return_value=make_candidate()),
        save_request=AsyncMock(return_value="260821-001"),
    )
    monkeypatch.setattr(gi.pending, "get_candidate", mocks.get_candidate)
    monkeypatch.setattr(gi.pending, "pop_candidate", mocks.pop_candidate)
    monkeypatch.setattr(
        "uk_management_bot.handlers.requests.create.save_request", mocks.save_request
    )
    return mocks


def make_callback(action="yes", from_id=AUTHOR_ID):
    return SimpleNamespace(
        data=f"gint:{action}",
        from_user=SimpleNamespace(id=from_id, language_code="ru"),
        message=SimpleNamespace(
            chat=SimpleNamespace(id=CHAT_ID, type="supergroup"),
            message_id=PROMPT_ID,
            edit_text=AsyncMock(),
        ),
        answer=AsyncMock(),
    )


def seed(db, *, kind="residents", is_active=True, user_status="approved",
         roles='["applicant"]', phone="+998901112233"):
    db.add(MonitoredGroup(chat_id=CHAT_ID, title="Дом", kind=kind, is_active=is_active))
    db.add(User(telegram_id=AUTHOR_ID, roles=roles, active_role="applicant",
                status=user_status, phone=phone, language="ru"))
    db.commit()


async def run_cb(callback, db):
    await gi.group_intake_callback(callback, bot=SimpleNamespace(), _db=db)


# ───────────────────────── доступ к кандидату ─────────────────────────


async def test_flag_off_single_empty_answer(monkeypatch, env, db):
    monkeypatch.setattr(settings, "GROUP_INTAKE_ENABLED", False)
    callback = make_callback()
    await run_cb(callback, db)
    callback.answer.assert_awaited_once_with()
    env.get_candidate.assert_not_awaited()


async def test_expired_candidate_alerts_once(env, db):
    env.get_candidate.return_value = None
    callback = make_callback()
    await run_cb(callback, db)
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()


async def test_foreign_presser_gets_alert_and_nothing_happens(env, db):
    callback = make_callback(from_id=999)
    await run_cb(callback, db)
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    env.pop_candidate.assert_not_awaited()
    env.save_request.assert_not_awaited()
    callback.message.edit_text.assert_not_awaited()


# ───────────────────────── no / other ─────────────────────────


async def test_no_pops_and_edits_cancelled(env, db):
    callback = make_callback("no")
    await run_cb(callback, db)
    callback.answer.assert_awaited_once_with()
    env.pop_candidate.assert_awaited_once()
    edited = callback.message.edit_text.await_args.args[0]
    assert "не создана" in edited
    env.save_request.assert_not_awaited()


async def test_other_edits_with_deeplink(env, db):
    callback = make_callback("other")
    await run_cb(callback, db)
    callback.answer.assert_awaited_once_with()
    edited = callback.message.edit_text.await_args.args[0]
    assert "https://t.me/test_bot?start=group" in edited
    env.save_request.assert_not_awaited()


# ───────────────────────── yes ─────────────────────────


async def test_double_yes_second_pop_none_shows_expired(env, db):
    seed(db)
    env.pop_candidate.return_value = None  # GETDEL уже случился
    callback = make_callback("yes")
    await run_cb(callback, db)
    callback.answer.assert_awaited_once_with()
    env.save_request.assert_not_awaited()
    edited = callback.message.edit_text.await_args.args[0]
    assert "устарело" in edited


@pytest.mark.parametrize("breakage", [
    {"kind": "staff"},          # kind сменили за жизнь кандидата
    {"is_active": False},       # группу выключили
    {"user_status": "blocked"},
    {"roles": '["executor"]'},
    {"phone": None},
])
async def test_regate_failure_shows_expired_not_creates(env, db, breakage):
    seed(db, **breakage)
    callback = make_callback("yes")
    await run_cb(callback, db)
    env.save_request.assert_not_awaited()
    edited = callback.message.edit_text.await_args.args[0]
    assert "устарело" in edited


async def test_candidate_kind_mismatch_is_expired(env, db):
    seed(db)  # группа residents
    env.pop_candidate.return_value = make_candidate(kind="staff")
    callback = make_callback("yes")
    await run_cb(callback, db)
    env.save_request.assert_not_awaited()


async def test_yes_creates_request_with_provenance(env, db):
    seed(db)
    env.pop_candidate.return_value = make_candidate(photo_file_id="photo123")
    callback = make_callback("yes")
    await run_cb(callback, db)

    callback.answer.assert_awaited_once_with()
    env.save_request.assert_awaited_once()
    data, user_id = env.save_request.await_args.args[:2]
    kwargs = env.save_request.await_args.kwargs
    assert user_id == AUTHOR_ID
    assert kwargs["source"] == "group"
    assert kwargs["role"] == "applicant"
    assert data["category"] == "electricity"
    assert data["address_type"] == "building"
    assert data["address_id"] == 5
    assert data["media_files"] == ["photo123"]
    assert data["source_chat_id"] == CHAT_ID
    assert data["source_message_id"] == 42

    edited = callback.message.edit_text.await_args.args[0]
    assert "260821-001" in edited
    # best-effort audit-строка написана
    log = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    assert log is not None
    assert log.action == "request.created_from_group"
    assert log.details["request_number"] == "260821-001"


async def test_save_failure_shows_error_not_silence(env, db):
    seed(db)
    env.save_request.return_value = None
    callback = make_callback("yes")
    await run_cb(callback, db)
    edited = callback.message.edit_text.await_args.args[0]
    assert "Не удалось" in edited
    assert db.query(AuditLog).count() == 0
