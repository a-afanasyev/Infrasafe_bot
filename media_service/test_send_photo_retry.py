"""send_photo: один повтор при сетевом сбое/таймауте Telegram (profk 2026-10-24).

Одна попытка с таймаутом 15 с роняла завершение заявки в 503, хотя обычная
загрузка занимает ~1 с. Ошибки API не повторяются; худший случай укладывается
в read-таймаут клиента UK.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import SendPhoto
from aiogram.types import BufferedInputFile

from app.core.config import settings
from app.services import telegram_client as tc

# executor_completion.UPLOAD_TIMEOUT.read в основном сервисе.
UK_UPLOAD_READ_TIMEOUT = 25.0


async def _instant_sleep(_delay):
    return None


@pytest.fixture
def svc(monkeypatch):
    s = tc.TelegramClientService.__new__(tc.TelegramClientService)
    s.bot = SimpleNamespace(send_photo=AsyncMock())
    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)
    return s


def _photo():
    return BufferedInputFile(b"jpeg", filename="a.jpg")


def _network_error():
    return TelegramNetworkError(method=SendPhoto(chat_id=1, photo="x"), message="Request timeout error")


@pytest.mark.asyncio
async def test_network_error_retried_once(svc):
    ok = SimpleNamespace(message_id=7)
    svc.bot.send_photo.side_effect = [_network_error(), ok]
    assert await svc.send_photo(-100, _photo()) is ok
    assert svc.bot.send_photo.await_count == 2


@pytest.mark.asyncio
async def test_timeout_retried_then_raised(svc):
    svc.bot.send_photo.side_effect = [TimeoutError(), TimeoutError()]
    with pytest.raises(TimeoutError):
        await svc.send_photo(-100, _photo())
    assert svc.bot.send_photo.await_count == 2


@pytest.mark.asyncio
async def test_api_error_not_retried(svc):
    svc.bot.send_photo.side_effect = TelegramBadRequest(
        method=SendPhoto(chat_id=1, photo="x"), message="Bad Request: chat not found")
    with pytest.raises(TelegramBadRequest):
        await svc.send_photo(-100, _photo())
    assert svc.bot.send_photo.await_count == 1


def test_worst_case_fits_uk_client_timeout():
    attempts = len(tc.SEND_PHOTO_BACKOFF_SECONDS)
    worst = attempts * settings.telegram_send_photo_attempt_timeout_seconds + sum(tc.SEND_PHOTO_BACKOFF_SECONDS)
    assert worst < UK_UPLOAD_READ_TIMEOUT
