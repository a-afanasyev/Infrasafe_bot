"""A10 — аудит безопасности 2026-10-23: пин-тесты бота.

BOT-01 `/health` только для admin_panel.use и без текста исключения;
BOT-02 детали передачи смены — только участнику; BOT-03 auth-middleware
fail-closed при сбое загрузки пользователя.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message, User as TgUser


def _msg(user_id: int = 1) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(spec=TgUser)
    msg.from_user.id = user_id
    msg.answer = AsyncMock()
    return msg


_HEALTH = "uk_management_bot.handlers.health"


@pytest.mark.asyncio
async def test_health_requires_admin_panel_action():
    from uk_management_bot.handlers.health import health_check_command

    msg = _msg()
    with patch(f"{_HEALTH}.get_user_language", return_value="ru"), patch(
        f"{_HEALTH}.get_text", side_effect=lambda key, language="ru": key
    ), patch(f"{_HEALTH}.check_database_health", new_callable=AsyncMock) as probe:
        await health_check_command(msg, MagicMock(), roles=["applicant"])
        await health_check_command(msg, MagicMock(), roles=None)

    assert msg.answer.call_args_list[0].args[0] == "errors.permission_denied"
    assert msg.answer.call_args_list[1].args[0] == "errors.permission_denied"
    probe.assert_not_called()


@pytest.mark.asyncio
async def test_health_error_branch_does_not_leak_exception_text():
    from uk_management_bot.handlers.health import health_check_command

    msg = _msg()
    leak = "postgresql://uk_app:pw@db-host-internal:5432/uk"
    with patch(f"{_HEALTH}.get_user_language", return_value="ru"), patch(
        f"{_HEALTH}.get_text", side_effect=lambda key, language="ru": key
    ), patch(f"{_HEALTH}.check_database_health", new_callable=AsyncMock, side_effect=Exception(leak)):
        await health_check_command(msg, MagicMock(), roles=["manager"])

    text = msg.answer.call_args.args[0]
    assert "db-host-internal" not in text
    assert "health.error_details" in text


def test_transfer_details_hidden_from_non_participant():
    from uk_management_bot.handlers import shift_transfer as st

    db = MagicMock()
    current = MagicMock()
    current.id = 5
    db.query.return_value.filter.return_value.first.return_value = current
    transfer = MagicMock(from_executor_id=1, to_executor_id=2)

    with patch.object(st, "_lang", return_value="ru"), patch.object(
        st, "ShiftTransferService"
    ) as svc, patch.object(st, "_transfer_details", return_value="DETAILS"):
        svc.return_value.get_transfer.return_value = transfer

        assert st._transfer_response(db, 555, "details", 7)[1] == "not_found"

        current.id = 2  # получатель передачи
        lang, outcome, payload = st._transfer_response(db, 555, "details", 7)

    assert (outcome, payload) == ("details", "DETAILS")


@pytest.mark.asyncio
async def test_auth_middleware_fails_closed_when_user_load_breaks():
    from uk_management_bot.middlewares import auth as auth_mw

    handler = AsyncMock()
    event = _msg(user_id=42)

    async def _db_down(fn):
        raise RuntimeError("database is unreachable")

    with patch.object(auth_mw, "run_db", _db_down):
        result = await auth_mw.auth_middleware(handler, event, {})

    assert result is None
    handler.assert_not_called()
