"""BUG-BOT-041 regression: the application-approved notification (sent to the
END USER) must be localized in the user's own language, not hardcoded Russian.

Two manager-side handlers in user_management.py — quick_verify_user and
process_approval_comment — built the "approved, restart the bot" notification
with a hardcoded ``target_lang = 'ru'`` (despite the comment "Определяем язык
целевого пользователя"). The parallel handler in user_verification.py does it
correctly via ``target_user.language or "ru"``. A uz user got the approval in
Russian. The test drives the success path with a uz target user and asserts
BOTH the message text AND the inline button use the uz translation — it FAILS
against the hardcoded-'ru' code and passes after the fix.

Кейс ``quick_verify_user`` снят вместе с хендлером (BUG-154 ретайр
2026-08-19): генератора префикса ``quick_verify_`` не было ни в одной
клавиатуре, а единственным его вызывающим был этот тест. Регрессия остаётся
покрыта живым ``process_approval_comment`` ниже — путь тот же.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

import uk_management_bot.handlers.user_management as um

_MSG_KEY = "user_mgmt.handlers.application_approved_restart"
_BTN_KEY = "user_mgmt.handlers.restart_bot_btn"


def _uz_target_user():
    u = MagicMock()
    u.language = "uz"
    u.telegram_id = 555
    u.first_name = "Aziz"
    u.username = "aziz"
    return u


def _assert_uz(send_message_mock):
    """The notification text and the restart button must both be in uz."""
    send_message_mock.assert_awaited_once()
    kwargs = send_message_mock.await_args.kwargs
    assert kwargs["text"] == um.panels.get_text(_MSG_KEY, language="uz"), (
        "approval notification text must use the user's language (uz), not hardcoded ru"
    )
    button_text = kwargs["reply_markup"].inline_keyboard[0][0].text
    assert button_text == um.panels.get_text(_BTN_KEY, language="uz"), (
        "restart button must use the user's language (uz), not hardcoded ru"
    )


@pytest.mark.asyncio
async def test_process_approval_comment_notifies_in_user_language(monkeypatch):
    target_user = _uz_target_user()

    fake_auth = MagicMock()
    fake_auth.approve_user = MagicMock(return_value=True)
    monkeypatch.setattr(um.fsm, "AuthService", MagicMock(return_value=fake_auth))

    fake_mgmt = MagicMock()
    fake_mgmt.get_user_by_id = MagicMock(return_value=target_user)
    fake_mgmt.format_user_info = MagicMock(return_value="info")
    monkeypatch.setattr(um.fsm, "UserManagementService", MagicMock(return_value=fake_mgmt))
    # downstream keyboard builder is irrelevant to this test; keep it inert
    monkeypatch.setattr(um.fsm, "get_user_actions_keyboard", lambda *a, **k: None)

    db = MagicMock()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"target_user_id": 5, "manager_id": 1})
    state.clear = AsyncMock()

    message = MagicMock()
    message.text = "ok"
    message.answer = AsyncMock()
    message.bot.send_message = AsyncMock()

    await um.fsm.process_approval_comment(message, state, language="ru", _db=db)

    _assert_uz(message.bot.send_message)
