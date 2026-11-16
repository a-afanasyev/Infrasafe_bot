"""Согласие на обработку персональных данных: сервис и middleware бота.

Новый житель даёт согласие в форме регистрации (tests/api/test_registration_pd_consent.py).
Здесь — путь уже зарегистрированных: бот один раз показывает уведомление, а
следующее действие пользователя засчитывается как согласие.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User
from uk_management_bot.middlewares.pd_consent import pd_consent_middleware
from uk_management_bot.services import pd_consent

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


# ─── Сервис ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    AuditLog.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _user(db, **fields) -> User:
    user = User(telegram_id=7001, status="approved", **fields)
    db.add(user)
    db.commit()
    return user


def test_accept_records_time_version_and_audit(db):
    user = _user(db)

    pd_consent.accept_sync(db, user.id, pd_consent.SOURCE_CONTINUED_USE)

    db.refresh(user)
    assert user.pd_consent_at is not None
    assert user.pd_consent_version == pd_consent.PD_CONSENT_VERSION
    log = db.query(AuditLog).filter(AuditLog.action == "pd_consent_given").one()
    assert log.user_id == user.id
    assert log.details == {"version": pd_consent.PD_CONSENT_VERSION, "source": "continued_use"}


def test_accept_does_not_overwrite_existing_consent(db):
    user = _user(db, pd_consent_at=NOW, pd_consent_version="old")

    pd_consent.accept_sync(db, user.id, pd_consent.SOURCE_CONTINUED_USE)

    db.refresh(user)
    assert user.pd_consent_version == "old"
    assert db.query(AuditLog).count() == 0


def test_notice_claim_is_won_once_and_can_be_released(db):
    user = _user(db)

    assert pd_consent.claim_notice_sync(db, user.id) is True
    assert pd_consent.claim_notice_sync(db, user.id) is False  # параллельный апдейт молчит

    pd_consent.release_notice_sync(db, user.id)
    db.refresh(user)
    assert user.pd_consent_notified_at is None
    assert pd_consent.claim_notice_sync(db, user.id) is True


# ─── Middleware ──────────────────────────────────────────────────────────────

def _event(chat_type: str = "private"):
    from aiogram.types import Update

    event = MagicMock(spec=Update)
    event.message = MagicMock()
    event.message.chat.type = chat_type
    event.callback_query = None
    return event


def _mw_user(**fields):
    user = MagicMock()
    user.id = 5
    user.telegram_id = 7001
    user.status = "approved"
    user.language = "ru"
    user.pd_consent_at = None
    user.pd_consent_notified_at = None
    for name, value in fields.items():
        setattr(user, name, value)
    return user


async def _run(user, event=None, claim_won=True):
    """→ (bot, имена вызванных юнитов БД, вызван ли хендлер)."""
    bot = MagicMock()
    bot.send_message = AsyncMock()
    handler = AsyncMock(return_value="handled")
    units: list[str] = []

    async def fake_run_db(unit, **_):
        units.append(unit.__name__)
        return claim_won if unit.__name__ == "claim_notice" else None

    with patch("uk_management_bot.middlewares.pd_consent.run_db", fake_run_db):
        result = await pd_consent_middleware(handler, event or _event(), {"user": user, "bot": bot})
    return bot, units, result == "handled" and handler.await_count == 1


@pytest.mark.asyncio
async def test_first_contact_sends_notice_and_marks_notified():
    bot, units, handled = await _run(_mw_user())

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.args[0] == 7001
    assert units == ["claim_notice"]
    assert handled


@pytest.mark.asyncio
async def test_parallel_update_that_lost_the_claim_sends_nothing():
    bot, units, handled = await _run(_mw_user(), claim_won=False)

    bot.send_message.assert_not_awaited()
    assert units == ["claim_notice"]
    assert handled


@pytest.mark.asyncio
async def test_next_action_after_notice_is_accepted_silently():
    user = _mw_user(pd_consent_notified_at=datetime.now(timezone.utc) - timedelta(hours=1))

    bot, units, handled = await _run(user)

    bot.send_message.assert_not_awaited()
    assert units == ["accept"]
    assert handled


@pytest.mark.asyncio
async def test_same_burst_as_notice_is_not_acceptance():
    """Альбом из нескольких фото приходит пачкой апдейтов: вторая секунда — не «продолжил пользоваться»."""
    user = _mw_user(pd_consent_notified_at=datetime.now(timezone.utc))

    bot, units, handled = await _run(user)

    bot.send_message.assert_not_awaited()
    assert units == []
    assert handled


@pytest.mark.asyncio
@pytest.mark.parametrize("user", [
    None,
    _mw_user(pd_consent_at=NOW),
    _mw_user(status="pending"),
])
async def test_untouched_cases_do_nothing(user):
    bot, units, handled = await _run(user)

    bot.send_message.assert_not_awaited()
    assert units == []
    assert handled


@pytest.mark.asyncio
async def test_group_chat_gets_no_notice():
    """Уведомление в общий чат раскрыло бы статус пользователя соседям."""
    bot, units, handled = await _run(_mw_user(), _event("supergroup"))

    bot.send_message.assert_not_awaited()
    assert units == []
    assert handled


@pytest.mark.asyncio
async def test_failed_notice_releases_the_claim_and_does_not_block_handler():
    user = _mw_user()
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=RuntimeError("telegram down"))
    handler = AsyncMock(return_value="handled")
    units: list[str] = []

    async def fake_run_db(unit, **_):
        units.append(unit.__name__)
        return True

    with patch("uk_management_bot.middlewares.pd_consent.run_db", fake_run_db):
        result = await pd_consent_middleware(handler, _event(), {"user": user, "bot": bot})

    assert result == "handled"
    assert units == ["claim_notice", "release_notice"]
