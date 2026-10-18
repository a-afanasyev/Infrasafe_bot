"""Уведомления жителю из дашборда несут кнопку следующего шага.

Отказ — «Подать заново» (verif:resubmit); запрос документов — «Загрузить
документы» (docs:upload). Без кнопки текст запроса документов остался голым
(BUG-188 на API-пути), а отклонённому было некуда нажать.
"""
from unittest.mock import AsyncMock, patch

import pytest

from uk_management_bot.api.residents import notify
from uk_management_bot.database.models.user import User

pytestmark = pytest.mark.asyncio


def _resident():
    return User(id=1, telegram_id=7401, language="ru", first_name="Ж")


async def _sent(coro_factory):
    send = AsyncMock(return_value=True)
    with patch.object(notify, "_send", send):
        await coro_factory()
    return send.await_args


async def test_rejection_carries_resubmit_button():
    args = await _sent(lambda: notify.notify_verification_rejected(_resident(), "нечитаемо"))
    markup = args.args[2] if len(args.args) > 2 else args.kwargs["reply_markup"]
    assert markup["inline_keyboard"][0][0]["callback_data"] == "verif:resubmit"


async def test_documents_request_carries_upload_button():
    args = await _sent(lambda: notify.notify_documents_requested(
        _resident(), document_types=["passport"], comment="приложите паспорт"))
    markup = args.args[2] if len(args.args) > 2 else args.kwargs["reply_markup"]
    assert markup["inline_keyboard"][0][0]["callback_data"] == "docs:upload"
