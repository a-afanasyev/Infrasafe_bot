"""A9-P2-4: `/admin` + общий ADMIN_PASSWORD — за флагом ADMIN_COMMAND_ENABLED.

Решение владельца 2026-09-23: в проде выключено (дефолт False), менеджеры —
только инвайтами и из дашборда; `/admin` остаётся для первичной настройки.

Контракт:
* флаг выключен — `/admin` не матчится ни одним хендлером (ведёт себя как
  неизвестная команда: ни подсказки о пароле, ни FSM-состояния), а сервис не
  выдаёт роль даже при верном пароле (defence in depth);
* флаг включён — прежняя выдача manager ПЛЮС: сообщение с паролем удаляется
  (сбой удаления логируется, не роняет поток), audit-запись в audit_logs,
  уведомление действующим менеджерам.

Telegram стабится уровнем ниже (bot.send_message / message.delete), БД —
настоящая sqlite, AuthService и юнит хендлера — боевые.
"""
from __future__ import annotations

import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import Chat, Message
from aiogram.types import User as TgUser
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

PASSWORD = "correct-horse-battery-staple-01"
CANDIDATE_TG = 100
MANAGER_TG = 200
APPLICANT_TG = 400


@pytest.fixture()
def db():
    from uk_management_bot.database.models.audit import AuditLog  # noqa: F401
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.session import Base

    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    session.add_all([
        User(id=1, telegram_id=CANDIDATE_TG, first_name="Иван<b>",
             roles='["applicant"]', active_role="applicant", status="approved"),
        User(id=2, telegram_id=MANAGER_TG, first_name="Менеджер",
             roles='["manager"]', active_role="manager", status="approved",
             language="uz"),
        User(id=3, telegram_id=APPLICANT_TG, first_name="Житель",
             roles='["applicant"]', active_role="applicant", status="approved"),
    ])
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _settings_objects():
    """Все инстансы settings, которые реально читает код под тестом.

    test_settings.py перезагружает модуль settings (del sys.modules + import),
    после чего `handlers.base.settings` (захвачен при импорте base) и
    `config.settings.settings` (его читает локальный импорт в AuthService) —
    РАЗНЫЕ объекты. В проде модуль не перезагружается — объект один.
    """
    import uk_management_bot.config.settings as settings_module
    import uk_management_bot.handlers.base as base_module

    objs = [base_module.settings]
    if settings_module.settings is not base_module.settings:
        objs.append(settings_module.settings)
    return objs


@pytest.fixture()
def flag(monkeypatch):
    objs = _settings_objects()
    for obj in objs:
        monkeypatch.setattr(obj, "ADMIN_PASSWORD", PASSWORD)

    def _set(enabled: bool):
        for obj in objs:
            monkeypatch.setattr(obj, "ADMIN_COMMAND_ENABLED", enabled)

    return _set


def _password_message(text=PASSWORD, user_id=CANDIDATE_TG):
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = MagicMock(spec=TgUser)
    msg.from_user.id = user_id
    msg.from_user.full_name = "Иван<b>"
    msg.answer = AsyncMock()
    msg.delete = AsyncMock()
    msg.bot = MagicMock()
    msg.bot.send_message = AsyncMock()
    return msg


def _state():
    state = AsyncMock()
    state.clear = AsyncMock()
    state.set_state = AsyncMock()
    return state


def _no_rate_limit():
    return patch(
        "uk_management_bot.utils.redis_rate_limiter.is_rate_limited",
        new=AsyncMock(return_value=False),
    )


# ─── Маршрутизация /admin ────────────────────────────────────────────────

async def _route_admin_command(state):
    """Прогоняет настоящий Message `/admin` через настоящий router base.py."""
    from uk_management_bot.handlers.base import router

    bot = AsyncMock()
    bot.id = 1
    msg = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=CANDIDATE_TG, type="private"),
        from_user=TgUser(id=CANDIDATE_TG, is_bot=False, first_name="Ivan"),
        text="/admin",
    ).as_(bot)
    result = await router.propagate_event(
        update_type="message", event=msg,
        bot=bot, state=state, raw_state=None, language="ru",
    )
    return result, bot


class TestAdminCommandRouting:
    @pytest.mark.asyncio
    async def test_disabled_admin_is_unknown_command(self, flag):
        flag(False)
        state = _state()

        result, bot = await _route_admin_command(state)

        assert result is UNHANDLED, "выключенный /admin не должен матчиться"
        state.set_state.assert_not_called()
        bot.assert_not_called()  # ни подсказки о пароле, ни иного ответа

    @pytest.mark.asyncio
    async def test_enabled_admin_prompts_for_password(self, flag):
        from uk_management_bot.handlers.base import AdminPasswordStates

        flag(True)
        state = _state()

        result, bot = await _route_admin_command(state)

        assert result is not UNHANDLED
        state.set_state.assert_awaited_once_with(
            AdminPasswordStates.waiting_for_password)
        bot.assert_awaited()  # подсказка о пароле ушла


# ─── Выдача роли ─────────────────────────────────────────────────────────

class TestAdminGrantDisabled:
    def test_service_refuses_even_correct_password(self, db, flag):
        from uk_management_bot.database.models.user import User
        from uk_management_bot.services.auth_service import AuthService

        flag(False)

        assert AuthService(db).make_admin_by_password_sync(
            CANDIDATE_TG, PASSWORD) is False
        assert db.get(User, 1).roles == '["applicant"]'

    @pytest.mark.asyncio
    async def test_stale_password_state_does_not_grant(self, db, flag):
        """FSM-состояние, оставшееся с момента, когда флаг был включён."""
        from uk_management_bot.database.models.audit import AuditLog
        from uk_management_bot.database.models.user import User
        from uk_management_bot.handlers.base import process_admin_password

        flag(False)
        msg = _password_message()
        state = _state()

        with _no_rate_limit(), patch(
            "uk_management_bot.handlers.base.get_user_contextual_keyboard",
            new=AsyncMock(return_value=None),
        ):
            await process_admin_password(msg, state, language="ru", _db=db)

        state.clear.assert_awaited()
        msg.delete.assert_awaited_once()  # пароль не остаётся в чате
        msg.answer.assert_not_called()  # о команде не подсказываем
        assert db.get(User, 1).roles == '["applicant"]'
        assert db.query(AuditLog).count() == 0
        msg.bot.send_message.assert_not_called()


class TestAdminGrantEnabled:
    @pytest.mark.asyncio
    async def test_grant_deletes_password_audits_and_notifies(self, db, flag):
        from uk_management_bot.database.models.audit import AuditLog
        from uk_management_bot.database.models.user import User
        from uk_management_bot.handlers.base import process_admin_password

        flag(True)
        msg = _password_message()

        with _no_rate_limit():
            await process_admin_password(msg, _state(), language="ru", _db=db)

        user = db.get(User, 1)
        assert user.roles == '["manager"]'
        msg.delete.assert_awaited_once()

        audits = db.query(AuditLog).all()
        assert len(audits) == 1
        audit = audits[0]
        assert audit.action == "admin_command_role_grant"
        assert audit.user_id == 1
        assert audit.telegram_user_id == CANDIDATE_TG
        assert audit.details["old_roles"] == ["applicant"]
        assert audit.details["new_roles"] == ["manager"]

        # Уведомлён ровно действующий менеджер — не сам получатель роли и не житель.
        recipients = [c.args[0] for c in msg.bot.send_message.await_args_list]
        assert recipients == [MANAGER_TG]
        text = msg.bot.send_message.await_args_list[0].args[1]
        assert str(CANDIDATE_TG) in text
        assert "/admin" in text
        assert "Иван&lt;b&gt;" in text, "имя из Telegram обязано экранироваться"
        assert "Иван<b>" not in text

    @pytest.mark.asyncio
    async def test_delete_failure_is_logged_and_grant_proceeds(
        self, db, flag, caplog,
    ):
        from uk_management_bot.database.models.user import User
        from uk_management_bot.handlers.base import process_admin_password

        flag(True)
        msg = _password_message()
        msg.delete = AsyncMock(side_effect=RuntimeError("message can't be deleted"))

        with _no_rate_limit(), caplog.at_level(
            logging.WARNING, logger="uk_management_bot.handlers.base",
        ):
            await process_admin_password(msg, _state(), language="ru", _db=db)

        assert db.get(User, 1).roles == '["manager"]'
        assert any(
            "удалить сообщение с паролем" in r.getMessage() for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_wrong_password_deletes_message_no_audit(self, db, flag):
        from uk_management_bot.database.models.audit import AuditLog
        from uk_management_bot.database.models.user import User
        from uk_management_bot.handlers.base import process_admin_password

        flag(True)
        msg = _password_message(text="wrong-password-0123456789")

        with _no_rate_limit(), patch(
            "uk_management_bot.handlers.base.get_user_contextual_keyboard",
            new=AsyncMock(return_value=None),
        ):
            await process_admin_password(msg, _state(), language="ru", _db=db)

        msg.delete.assert_awaited_once()
        assert db.get(User, 1).roles == '["applicant"]'
        assert db.query(AuditLog).count() == 0
        msg.bot.send_message.assert_not_called()
