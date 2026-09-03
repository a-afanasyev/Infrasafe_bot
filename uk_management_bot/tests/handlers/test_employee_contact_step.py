"""Сотрудник: контакт до токена и контакт вместо ручного телефона в анкете
(спека 2026-09-03 §3.4).

Телефон сотрудника до подтверждения анкеты живёт ТОЛЬКО в FSM
(`employee_phone`): запись в users.phone раньше «закрыла» бы развилку
«житель/сотрудник» для бросившего анкету.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Chat, Contact, Message, User as TgUser

from uk_management_bot.states.registration import RegistrationStates
from uk_management_bot.utils.button_texts import get_cancel_texts
from uk_management_bot.utils.helpers import get_text

CANCEL = get_cancel_texts()[0]


def _t(key):
    return get_text(key, language="ru")


def _state(data=None):
    st = MagicMock()
    st.get_data = AsyncMock(return_value=dict(data or {}))
    st.get_state = AsyncMock(return_value=None)
    st.update_data = AsyncMock()
    st.set_state = AsyncMock()
    st.clear = AsyncMock()
    return st


def _msg(*, text=None, contact_phone=None, own=True):
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = MagicMock(spec=TgUser)
    msg.from_user.id = 123
    if contact_phone is not None:
        msg.contact = MagicMock()
        msg.contact.phone_number = contact_phone
        msg.contact.user_id = 123 if own else 999
    else:
        msg.contact = None
    msg.answer = AsyncMock()
    return msg


def _callback(data="start_role:employee"):
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=123, username="u", first_name="F", last_name="L")
    cb.message = _msg()
    cb.message.edit_reply_markup = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    cb.bot.send_message = AsyncMock()
    return cb


def _has_contact_button(markup):
    return any(getattr(b, "request_contact", False) for row in markup.keyboard for b in row)


# ─── «Я сотрудник» → контакт → токен ─────────────────────────────────────────

class TestEmployeeContactBeforeToken:
    @pytest.mark.asyncio
    async def test_choose_employee_asks_for_contact_first(self):
        from uk_management_bot.handlers.start_role_choice import choose_employee

        cb, st = _callback(), _state()
        await choose_employee(cb, st)

        st.set_state.assert_awaited_with(RegistrationStates.waiting_for_employee_contact)
        kwargs = cb.message.answer.await_args.kwargs
        assert cb.message.answer.await_args.args[0] == _t("start_role.employee_contact_prompt")
        assert _has_contact_button(kwargs["reply_markup"])

    @pytest.mark.asyncio
    async def test_own_contact_stored_in_fsm_then_token_prompt(self):
        from uk_management_bot.handlers.start_role_choice import employee_contact

        msg, st = _msg(contact_phone="998901234567"), _state()
        await employee_contact(msg, st, language="ru")

        st.update_data.assert_awaited_with(employee_phone="+998901234567")
        st.set_state.assert_awaited_with(RegistrationStates.waiting_for_invite_token)
        assert msg.answer.await_args.args[0] == _t("start_role.token_prompt")

    @pytest.mark.asyncio
    async def test_foreign_contact_rejected(self):
        from uk_management_bot.handlers.start_role_choice import employee_contact

        msg, st = _msg(contact_phone="+998901234567", own=False), _state()
        await employee_contact(msg, st, language="ru")

        st.update_data.assert_not_awaited()
        st.set_state.assert_not_awaited()
        assert msg.answer.await_args.args[0] == _t("phone_request_flow.foreign_contact")

    @pytest.mark.asyncio
    async def test_text_instead_of_contact_is_refused(self):
        from uk_management_bot.handlers.start_role_choice import employee_contact_text

        msg, st = _msg(text="+998901234567"), _state()
        await employee_contact_text(msg, st, language="ru")

        st.set_state.assert_not_awaited()
        st.clear.assert_not_awaited()
        assert msg.answer.await_args.args[0] == _t("start_role.employee_contact_required")

    @pytest.mark.asyncio
    async def test_cancel_text_clears_state(self):
        from uk_management_bot.handlers.start_role_choice import employee_contact_text

        msg, st = _msg(text=CANCEL), _state()
        await employee_contact_text(msg, st, language="ru")

        st.clear.assert_awaited_once()
        assert msg.answer.await_args.args[0] == _t("auth.registration_cancelled")


# ─── анкета после токена: контакт вместо ручного телефона ────────────────────

class TestQuestionnaireContactStep:
    @pytest.mark.asyncio
    async def test_full_name_with_phone_in_fsm_goes_to_confirmation(self):
        from uk_management_bot.handlers.auth import handle_full_name_input

        msg = _msg(text="Иван Петров")
        st = _state({"employee_phone": "+998901234567", "invite_role": "manager"})
        await handle_full_name_input(msg, st, language="ru")

        st.set_state.assert_awaited_with(RegistrationStates.waiting_for_position_confirmation)

    @pytest.mark.asyncio
    async def test_full_name_without_phone_asks_for_contact(self):
        from uk_management_bot.handlers.auth import handle_full_name_input

        msg = _msg(text="Иван Петров")
        st = _state({"invite_role": "manager"})
        await handle_full_name_input(msg, st, language="ru")

        st.set_state.assert_awaited_with(RegistrationStates.waiting_for_phone)
        assert msg.answer.await_args.args[0] == _t("auth.phone_contact_prompt")
        assert _has_contact_button(msg.answer.await_args.kwargs["reply_markup"])

    @pytest.mark.asyncio
    async def test_contact_in_phone_state_goes_to_confirmation(self):
        from uk_management_bot.handlers.auth import handle_phone_contact

        msg = _msg(contact_phone="998901234567")
        st = _state({"full_name": "Иван Петров", "invite_role": "manager"})
        await handle_phone_contact(msg, st, language="ru")

        st.update_data.assert_awaited_with(employee_phone="+998901234567")
        st.set_state.assert_awaited_with(RegistrationStates.waiting_for_position_confirmation)

    @pytest.mark.asyncio
    async def test_text_in_phone_state_is_refused(self):
        from uk_management_bot.handlers.auth import handle_phone_text

        msg, st = _msg(text="+998901234567"), _state({"full_name": "Иван Петров"})
        await handle_phone_text(msg, st, language="ru")

        st.update_data.assert_not_awaited()
        assert msg.answer.await_args.args[0] == _t("auth.phone_contact_required")

    @pytest.mark.asyncio
    async def test_cancel_in_phone_state_clears(self):
        from uk_management_bot.handlers.auth import handle_phone_text

        msg, st = _msg(text=CANCEL), _state({"full_name": "Иван Петров"})
        await handle_phone_text(msg, st, language="ru")

        st.clear.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_manual_phone_handler_removed(self):
        from uk_management_bot.handlers import auth
        assert not hasattr(auth, "handle_phone_input")

    @pytest.mark.asyncio
    async def test_confirm_without_phone_refuses(self):
        from uk_management_bot.handlers import auth

        cb = _callback("confirm_position")
        st = _state({"full_name": "Иван Петров", "invite_role": "manager",
                     "invite_token": "invite_v1:x"})
        with patch.object(auth, "run_db", new=AsyncMock()) as run_db:
            await auth.handle_position_confirmation(cb, st, language="ru", _db=MagicMock())

        run_db.assert_not_awaited()
        cb.answer.assert_awaited()
        assert _t("auth.phone_contact_required") in cb.answer.await_args.args[0]

    @pytest.mark.asyncio
    async def test_confirm_passes_fsm_phone_to_registration(self):
        from uk_management_bot.handlers import auth

        cb = _callback("confirm_position")
        st = _state({"full_name": "Иван Петров", "employee_phone": "+998901234567",
                     "invite_role": "manager", "invite_specialization": "",
                     "invite_token": "invite_v1:x"})
        captured = {}

        async def fake_run_db(unit, db=None):
            session = MagicMock()
            with patch.object(auth, "_apply_registration",
                              side_effect=lambda *a: captured.update(phone=a[-1]) or ("used", None)):
                return unit(session)

        with patch.object(auth, "run_db", new=fake_run_db):
            await auth.handle_position_confirmation(cb, st, language="ru", _db=MagicMock())

        assert captured["phone"] == "+998901234567"


# ─── роутинг: контакт и текст в новых состояниях доходят до нужных хендлеров ─

def _main_routers():
    import re
    from pathlib import Path
    import uk_management_bot.main as main_mod

    order = re.findall(r"dp\.include_router\((\w+)\)", Path(main_mod.__file__).read_text())
    return [getattr(main_mod, name) for name in order]


def _contact_message():
    user = TgUser(id=1, is_bot=False, first_name="Тест")
    chat = Chat(id=1, type="private")
    return Message(
        message_id=1, date=datetime.now(timezone.utc), chat=chat, from_user=user,
        contact=Contact(phone_number="+998901234567", first_name="Тест", user_id=1),
    )


@pytest.mark.parametrize("raw_state,expected", [
    ("RegistrationStates:waiting_for_employee_contact",
     ("uk_management_bot.handlers.start_role_choice", "employee_contact")),
    ("RegistrationStates:waiting_for_phone",
     ("uk_management_bot.handlers.auth", "handle_phone_contact")),
    (None, ("uk_management_bot.handlers.phone_share", "receive_shared_contact")),
])
def test_contact_routes_by_state(raw_state, expected):
    from uk_management_bot.tests.handlers.routing_probe import resolve_ctx

    winner = resolve_ctx(_main_routers(), _contact_message(), "message",
                         raw_state=raw_state, roles=["applicant"], user=None)
    assert winner == expected, winner


def test_text_in_employee_contact_state_routes_to_refusal():
    from uk_management_bot.tests.handlers.routing_probe import make_message, resolve_ctx

    winner = resolve_ctx(_main_routers(), make_message("+998901234567"), "message",
                         raw_state="RegistrationStates:waiting_for_employee_contact",
                         roles=["applicant"], user=None)
    assert winner == ("uk_management_bot.handlers.start_role_choice", "employee_contact_text"), winner
