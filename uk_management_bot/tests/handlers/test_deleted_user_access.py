"""Удалённый сотрудник сохранял доступ и в боте, и в API.

`soft_delete_employee` ставит `deleted_at`, `deleted_by`, `deletion_reason` и
`status='deleted'`, но РОЛИ намеренно оставляет (нужны для истории заявок).
Гейты же смотрели только на `status == 'blocked'`: удалённый проходил
middleware с прежними ролями и продолжал пользоваться ботом, а с ещё живым
JWT — и дашбордом. Само значение `'deleted'` не проверялось нигде в коде.

Проверяем оба гейта по `deleted_at`, а не по строке статуса: `deleted_at` —
канонический признак (по нему фильтруют все списки), а `status` может быть
переписан другой операцией.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_user(*, deleted=False, status="approved"):
    user = MagicMock()
    user.id = 17
    user.telegram_id = 134502444
    user.status = "deleted" if deleted else status
    user.deleted_at = datetime.now(timezone.utc) if deleted else None
    user.roles = '["applicant", "executor"]'
    user.active_role = "executor"
    user.language = "ru"
    return user


def _make_update(telegram_id=134502444):
    from aiogram.types import Update

    event = MagicMock(spec=Update)
    event.message = MagicMock()
    event.message.from_user = MagicMock()
    event.message.from_user.id = telegram_id
    event.message.from_user.language_code = "ru"
    event.message.answer = AsyncMock()
    event.callback_query = None
    return event


class TestBotGate:
    @pytest.mark.asyncio
    async def test_deleted_user_is_not_let_into_the_bot(self):
        from uk_management_bot.middlewares.auth import auth_middleware

        handler = AsyncMock()
        event = _make_update()

        with patch("uk_management_bot.middlewares.auth.run_db",
                   new=AsyncMock(return_value=_make_user(deleted=True))):
            await auth_middleware(handler, event, {})

        handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deleted_user_gets_an_explanation(self):
        """Ответ уходит только на Message/CallbackQuery — как и для blocked."""
        from aiogram.types import Message

        from uk_management_bot.middlewares.auth import auth_middleware

        handler = AsyncMock()
        event = MagicMock(spec=Message)
        event.from_user = MagicMock()
        event.from_user.id = 134502444
        event.from_user.language_code = "ru"
        event.answer = AsyncMock()

        with patch("uk_management_bot.middlewares.auth.run_db",
                   new=AsyncMock(return_value=_make_user(deleted=True))):
            await auth_middleware(handler, event, {})

        handler.assert_not_awaited()
        event.answer.assert_awaited()
        text = event.answer.await_args.args[0]
        assert text and "auth.deleted" not in text, "ключ локали не подставился"

    @pytest.mark.asyncio
    async def test_live_user_passes(self):
        from uk_management_bot.middlewares.auth import auth_middleware

        handler = AsyncMock()
        event = _make_update()

        with patch("uk_management_bot.middlewares.auth.run_db",
                   new=AsyncMock(return_value=_make_user())):
            await auth_middleware(handler, event, {})

        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_blocked_user_still_blocked(self):
        """Существующее поведение не должно пострадать."""
        from uk_management_bot.middlewares.auth import auth_middleware

        handler = AsyncMock()
        event = _make_update()

        with patch("uk_management_bot.middlewares.auth.run_db",
                   new=AsyncMock(return_value=_make_user(status="blocked"))):
            await auth_middleware(handler, event, {})

        handler.assert_not_awaited()


def _request_with_cookie():
    req = MagicMock()
    req.cookies = {"uk_access": "token"}
    return req


class TestApiGate:
    @pytest.mark.asyncio
    async def test_deleted_user_token_is_rejected(self):
        from fastapi import HTTPException

        from uk_management_bot.api import dependencies

        with patch.object(dependencies, "get_user_by_id",
                          new=AsyncMock(return_value=_make_user(deleted=True))), \
             patch("uk_management_bot.api.auth.service.verify_access_token",
                   return_value={"sub": "17"}):
            with pytest.raises(HTTPException) as exc:
                await dependencies.get_current_user(
                    request=_request_with_cookie(), credentials=None, db=MagicMock(),
                )

        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_live_user_token_passes(self):
        from uk_management_bot.api import dependencies

        user = _make_user()
        with patch.object(dependencies, "get_user_by_id", new=AsyncMock(return_value=user)), \
             patch("uk_management_bot.api.auth.service.verify_access_token",
                   return_value={"sub": "17"}):
            got = await dependencies.get_current_user(
                request=_request_with_cookie(), credentials=None, db=MagicMock(),
            )

        assert got is user
