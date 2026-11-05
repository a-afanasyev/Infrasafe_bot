"""A10-INT-14: выдача роли manager через бота уведомляет суперадминов (как в дашборде)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uk_management_bot.handlers.user_management import roles_specs


def _message():
    msg = MagicMock()
    msg.text = "повышение"
    msg.answer = AsyncMock()
    msg.from_user.id = 777
    msg.from_user.full_name = "Админ"
    msg.bot.send_message = AsyncMock()
    return msg


def _state(original, current):
    state = MagicMock()
    state.get_data = AsyncMock(return_value={
        "target_user_id": 5, "manager_id": 1,
        "original_roles": original, "current_roles": current,
    })
    state.clear = AsyncMock()
    return state


async def _run(msg, state, admins=(11, 22)):
    with patch.object(roles_specs, "has_admin_access", return_value=True), \
         patch.object(roles_specs, "run_db", new=AsyncMock(return_value=(True, "Иван", "info", None))), \
         patch("uk_management_bot.config.settings.settings.ADMIN_USER_IDS", list(admins)):
        await roles_specs.process_role_change_comment(msg, state, language="ru")


@pytest.mark.asyncio
async def test_manager_grant_notifies_each_superadmin():
    msg = _message()
    await _run(msg, _state(["applicant"], ["applicant", "manager"]))
    sent_to = [c.args[0] for c in msg.bot.send_message.await_args_list]
    assert sent_to == [11, 22]
    assert "Иван" in msg.bot.send_message.await_args_list[0].args[1]


@pytest.mark.asyncio
async def test_other_roles_do_not_notify():
    msg = _message()
    await _run(msg, _state(["applicant"], ["applicant", "executor"]))
    msg.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_failure_does_not_break_handler():
    msg = _message()
    msg.bot.send_message = AsyncMock(side_effect=RuntimeError("telegram down"))
    await _run(msg, _state([], ["manager"]))
    msg.answer.assert_awaited()  # пользователь всё равно получил «роли обновлены»
