"""`executor_view_media_<номер>` отдавал медиа ЛЮБОЙ заявки без проверки доступа.

`requests/executor.py`: хендлер брал номер из `callback_data` (перебираемый
формат YYMMDD-NNN), грузил заявку и отправлял её `media_files` вопросившему —
ни резолва пользователя, ни проверки прав (аудит 2026-08-18, находка 4 HIGH).

Фикс — канон `has_request_access_sync` (`services/request_access.py`), как в
`requests/listing.py:230`. Отказ — ТЕМ ЖЕ текстом, что «не найдено»: иначе
разница ответов становится оракулом существования заявки для перебора номеров.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uk_management_bot.handlers.requests import executor as ex
from uk_management_bot.utils.helpers import get_text

NOT_FOUND_TEXT = get_text("requests.request_not_found", language="ru")


def _callback(request_number: str = "260818-001", from_id: int = 777):
    cb = MagicMock()
    cb.data = f"executor_view_media_{request_number}"
    cb.from_user.id = from_id
    cb.answer = AsyncMock()
    cb.message.answer_media_group = AsyncMock()
    return cb


def _request_with_media():
    request = MagicMock()
    request.media_files = json.dumps([{"file_id": "AgAC-test", "type": "photo"}])
    return request


def _service(request, user):
    service = MagicMock()
    service.get_request_by_number.return_value = request
    service.get_user_by_telegram_id.return_value = user
    return service


@pytest.mark.asyncio
async def test_foreign_user_gets_not_found_and_no_media():
    """Чужой пользователь: отказ текстом «не найдено», медиа НЕ отправлены."""
    callback = _callback()
    service = _service(_request_with_media(), user=MagicMock())

    with patch.object(ex, "RequestHandlerService", return_value=service), \
         patch.object(ex, "get_user_language", return_value="ru"), \
         patch.object(ex, "has_request_access_sync", return_value=False):
        await ex.executor_view_media(callback, _db=MagicMock())

    callback.answer.assert_awaited_once_with(NOT_FOUND_TEXT, show_alert=True)
    callback.message.answer_media_group.assert_not_awaited()


@pytest.mark.asyncio
async def test_denied_is_indistinguishable_from_missing():
    """Отказ в доступе и несуществующая заявка отвечают ОДИНАКОВО (анти-оракул)."""
    denied_cb = _callback()
    with patch.object(ex, "RequestHandlerService",
                      return_value=_service(_request_with_media(), MagicMock())), \
         patch.object(ex, "get_user_language", return_value="ru"), \
         patch.object(ex, "has_request_access_sync", return_value=False):
        await ex.executor_view_media(denied_cb, _db=MagicMock())

    missing_cb = _callback("999999-999")
    with patch.object(ex, "RequestHandlerService",
                      return_value=_service(None, MagicMock())), \
         patch.object(ex, "get_user_language", return_value="ru"):
        await ex.executor_view_media(missing_cb, _db=MagicMock())

    assert denied_cb.answer.await_args == missing_cb.answer.await_args


@pytest.mark.asyncio
async def test_unknown_user_gets_not_found():
    """Пользователя нет в БД → тот же отказ «не найдено», без падения."""
    callback = _callback()
    service = _service(_request_with_media(), user=None)

    with patch.object(ex, "RequestHandlerService", return_value=service), \
         patch.object(ex, "get_user_language", return_value="ru"):
        await ex.executor_view_media(callback, _db=MagicMock())

    callback.answer.assert_awaited_once_with(NOT_FOUND_TEXT, show_alert=True)
    callback.message.answer_media_group.assert_not_awaited()


@pytest.mark.asyncio
async def test_authorized_user_receives_media():
    """Легитимный путь не сломан: доступ есть → медиагруппа отправлена."""
    callback = _callback()
    service = _service(_request_with_media(), user=MagicMock())

    with patch.object(ex, "RequestHandlerService", return_value=service), \
         patch.object(ex, "get_user_language", return_value="ru"), \
         patch.object(ex, "has_request_access_sync", return_value=True):
        await ex.executor_view_media(callback, _db=MagicMock())

    callback.message.answer_media_group.assert_awaited_once()
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.args[0] != NOT_FOUND_TEXT
