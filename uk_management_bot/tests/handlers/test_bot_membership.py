"""Статус «бот заблокирован» — realtime-источник my_chat_member.

Блокировка бота в приватном чате (kicked/left) ставит штамп
``users.bot_blocked_at``, разблокировка (member) снимает. Поле показывает
бейдж в карточках жителей/сотрудников; второй источник — вердикт доставки
запроса номера (tests/api/test_request_phone.py).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def db():
    from uk_management_bot.database.models.user import User  # noqa: F401
    from uk_management_bot.database.session import Base

    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Factory()

    session.add(User(id=1, telegram_id=100, roles='["applicant"]',
                     status="approved"))
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _event(status: str, telegram_id: int = 100) -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=telegram_id),
        new_chat_member=SimpleNamespace(status=status),
        chat=SimpleNamespace(type="private"),
    )


class TestSetBotBlockedUnit:
    def test_kicked_sets_stamp(self, db):
        from uk_management_bot.database.models.user import User
        from uk_management_bot.handlers.bot_membership import _set_bot_blocked

        assert _set_bot_blocked(db, 100, True) is True
        assert db.get(User, 1).bot_blocked_at is not None

    def test_member_clears_stamp(self, db):
        from uk_management_bot.database.models.user import User
        from uk_management_bot.handlers.bot_membership import _set_bot_blocked

        _set_bot_blocked(db, 100, True)
        assert _set_bot_blocked(db, 100, False) is True
        assert db.get(User, 1).bot_blocked_at is None

    def test_same_state_is_a_noop(self, db):
        from uk_management_bot.handlers.bot_membership import _set_bot_blocked

        assert _set_bot_blocked(db, 100, False) is False, \
            "уже разблокирован — без пустого коммита"

    def test_unknown_user_is_ignored(self, db):
        from uk_management_bot.handlers.bot_membership import _set_bot_blocked

        assert _set_bot_blocked(db, 999, True) is False


class TestHandler:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("status,expect_blocked", [
        ("kicked", True),
        ("left", True),
        ("member", False),
    ])
    async def test_statuses_map_to_stamp(self, db, status, expect_blocked):
        from uk_management_bot.database.models.user import User
        from uk_management_bot.handlers.bot_membership import (
            on_private_membership_change,
        )

        if not expect_blocked:  # для member сначала блокируем
            user = db.get(User, 1)
            from datetime import datetime, timezone
            user.bot_blocked_at = datetime.now(timezone.utc)
            db.commit()

        await on_private_membership_change(_event(status), _db=db)
        db.expire_all()
        assert (db.get(User, 1).bot_blocked_at is not None) is expect_blocked

    def test_router_is_registered_in_main(self):
        import inspect

        from uk_management_bot import main

        src = inspect.getsource(main)
        assert "bot_membership_router" in src
        assert "include_router(bot_membership_router)" in src
