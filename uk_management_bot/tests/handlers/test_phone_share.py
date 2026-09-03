"""Приём контакта вне онбординга (кнопка «Запросить номер телефона» с дашборда).

Менеджер жмёт кнопку на дашборде → API шлёт пользователю сообщение с
request_contact-клавиатурой → пользователь делится контактом БЕЗ активного
FSM-состояния. До этой фичи такой contact-месседж молча проваливался мимо
всех хендлеров (onboarding ловит contact только в waiting_for_phone).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message
from aiogram.types import User as TgUser


def _make_contact_message(*, own: bool = True, phone: str = "+998901234567"):
    msg = MagicMock(spec=Message)
    msg.text = None
    msg.from_user = MagicMock(spec=TgUser)
    msg.from_user.id = 123
    msg.contact = MagicMock()
    msg.contact.phone_number = phone
    msg.contact.user_id = 123 if own else 999
    msg.answer = AsyncMock()
    return msg


class TestPhoneShareHandler:
    @pytest.mark.asyncio
    async def test_own_contact_saved(self):
        from uk_management_bot.handlers.phone_share import receive_shared_contact

        msg = _make_contact_message()
        with patch("uk_management_bot.handlers.phone_share.run_db",
                   new=AsyncMock(return_value=True)) as run_db:
            await receive_shared_contact(msg, language="ru", _db=MagicMock())

        # два юнита: сохранение телефона + контекст для перерисовки (§3.2)
        assert run_db.await_count == 2
        msg.answer.assert_awaited_once()
        # Подтверждение с номером и снятие reply-клавиатуры.
        text = msg.answer.await_args.args[0]
        assert "+998901234567" in text
        assert msg.answer.await_args.kwargs["reply_markup"] is not None

    @pytest.mark.asyncio
    async def test_phone_without_plus_normalized(self):
        from uk_management_bot.handlers.phone_share import receive_shared_contact

        msg = _make_contact_message(phone="998901234567")
        captured: list = []

        async def fake_run_db(unit, db=None):
            fake_session = MagicMock()
            captured.append(unit(fake_session))
            return True

        with patch("uk_management_bot.handlers.phone_share.run_db", new=fake_run_db), \
             patch("uk_management_bot.handlers.phone_share._apply_phone",
                   side_effect=lambda s, tg_id, phone: phone) :
            await receive_shared_contact(msg, language="ru", _db=MagicMock())

        assert [c for c in captured if isinstance(c, str)] == ["+998901234567"]

    @pytest.mark.asyncio
    async def test_foreign_contact_rejected(self):
        from uk_management_bot.handlers.phone_share import receive_shared_contact

        msg = _make_contact_message(own=False)
        with patch("uk_management_bot.handlers.phone_share.run_db",
                   new=AsyncMock(return_value=True)) as run_db:
            await receive_shared_contact(msg, language="ru", _db=MagicMock())

        run_db.assert_not_awaited()
        msg.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_user_gets_error(self):
        from uk_management_bot.handlers.phone_share import receive_shared_contact

        msg = _make_contact_message()
        with patch("uk_management_bot.handlers.phone_share.run_db",
                   new=AsyncMock(return_value=False)):
            await receive_shared_contact(msg, language="ru", _db=MagicMock())

        msg.answer.assert_awaited_once()
        assert "+998901234567" not in msg.answer.await_args.args[0]


# ─── Спека 2026-09-03 §3.2: после контакта — экран онбординга, без FSM ───────

def _ctx(*, status="pending", phone="+998901234567", approved=False, roles=("applicant",)):
    from uk_management_bot.handlers.base import _MenuContext
    return _MenuContext(
        status=status, phone=phone, has_approved_apartment=approved,
        has_any_apartment=False, db_roles=list(roles), active_role=roles[0],
    )


def _run_db_dispatch(ctx):
    """run_db: юнит сохранения телефона → True, юнит контекста → ctx."""
    async def fake(unit, db=None):
        name = getattr(unit, "__name__", "")
        if name == "<lambda>":
            # обе лямбды; различаем по результату вызова с фейковой сессией
            session = MagicMock()
            with patch("uk_management_bot.handlers.phone_share._apply_phone", return_value=True), \
                 patch("uk_management_bot.handlers.phone_share._load_onboarding_redraw", return_value=ctx):
                return unit(session)
        return True
    return fake


class TestOnboardingRedraw:
    @pytest.mark.asyncio
    async def test_pending_applicant_gets_onboarding_screen(self, monkeypatch):
        from uk_management_bot.handlers import base
        from uk_management_bot.handlers.phone_share import receive_shared_contact
        from uk_management_bot.utils.helpers import get_text
        monkeypatch.setattr(base.settings, "FRONTEND_URL", "https://example.test")

        msg = _make_contact_message()
        with patch("uk_management_bot.handlers.phone_share.run_db", new=_run_db_dispatch(_ctx())):
            await receive_shared_contact(msg, language="ru", _db=MagicMock())

        assert msg.answer.await_count == 2
        second = msg.answer.await_args_list[1]
        kb = second.kwargs["reply_markup"]
        texts = [b.text for row in kb.keyboard for b in row]
        assert get_text("base.handlers.btn_select_apartment", language="ru") in texts
        assert get_text("base.handlers.btn_register_webapp", language="ru") in texts

    @pytest.mark.asyncio
    async def test_staff_gets_only_confirmation(self):
        """Тот же хендлер принимает контакт по запросу менеджера с дашборда —
        сотруднику/одобренному жителю экран онбординга не шлём."""
        from uk_management_bot.handlers.phone_share import receive_shared_contact

        for ctx in (
            _ctx(status="approved", roles=("executor",)),
            _ctx(status="pending", roles=("applicant", "manager")),
            _ctx(status="approved", approved=True),
        ):
            msg = _make_contact_message()
            with patch("uk_management_bot.handlers.phone_share.run_db", new=_run_db_dispatch(ctx)):
                await receive_shared_contact(msg, language="ru", _db=MagicMock())
            assert msg.answer.await_count == 1, ctx

    def test_handler_takes_no_fsm_state(self):
        import inspect
        from uk_management_bot.handlers.phone_share import receive_shared_contact
        assert "state" not in inspect.signature(receive_shared_contact).parameters
