"""``api/residents/notify.send_plain_messages``: считает только доставленные, не роняет рассылку.

Сбой сети проверяется на транспорте общего клиента ``api/telegram_send``
(фикстура ``telegram_api``): один адресат падает httpx-ошибкой с URL и
токеном в тексте — не считается, остальные доставлены, в логе нет текста
исключения. Отказы Telegram — через подмену ``_send``.
"""
from __future__ import annotations

import logging

import httpx
import pytest

from uk_management_bot.api.residents import notify
from uk_management_bot.services.elevator_service import Message

SECRET_URL = "https://api.telegram.org/bot123:SECRET-TOKEN/sendMessage"


def _fake_send(fail_ids: set[int], rejected_ids: set[int], calls: list):
    assert not fail_ids, "сетевой сбой — через транспорт (telegram_api), не через _send"

    async def fake(chat_id: int, text: str, reply_markup=None, *, parse_mode=None) -> bool:
        calls.append((chat_id, text, parse_mode))
        return chat_id not in rejected_ids
    return fake


@pytest.mark.asyncio
async def test_one_failure_does_not_stop_others_and_is_not_counted(telegram_api, caplog):
    import json

    def handler(request):
        if json.loads(request.content)["chat_id"] == 2:
            raise httpx.ConnectError(f"boom for url {SECRET_URL}", request=request)
        return httpx.Response(200, json={"ok": True, "result": {}})

    telegram_api.handler = handler
    messages = [Message(telegram_id=i, text=f"msg {i}") for i in (1, 2, 3)]

    with caplog.at_level(logging.WARNING):
        delivered = await notify.send_plain_messages(messages)

    assert delivered == 2
    calls = telegram_api.calls("sendMessage")
    assert [c["chat_id"] for c in calls] == [1, 2, 2, 3]  # connect-сбой: один ретрай
    assert all(c["parse_mode"] == "HTML" for c in calls)
    log_text = caplog.text
    assert "ConnectError" in log_text and "SECRET-TOKEN" not in log_text and "boom" not in log_text


@pytest.mark.asyncio
async def test_non_200_is_not_counted_as_delivered(monkeypatch):
    calls: list = []
    monkeypatch.setattr(notify, "_send", _fake_send(set(), {7}, calls))
    messages = [Message(telegram_id=7, text="blocked"), Message(telegram_id=8, text="ok")]

    assert await notify.send_plain_messages(messages) == 1
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_empty_and_plain_mode(monkeypatch):
    calls: list = []
    monkeypatch.setattr(notify, "_send", _fake_send(set(), set(), calls))
    assert await notify.send_plain_messages([]) == 0
    assert await notify.send_plain_messages([Message(telegram_id=1, text="x")], parse_mode=None) == 1
    assert calls == [(1, "x", None)]


@pytest.mark.asyncio
async def test_send_returns_false_on_non_200(telegram_api):
    """Контракт ``_send``: 2xx → True, иначе False (без исключения).

    A9-P2-9: ``_send`` идёт через общий модуль — подменяется транспорт httpx."""
    telegram_api.handler = lambda r: httpx.Response(
        403, json={"ok": False, "description": "Forbidden: bot was blocked by the user"},
    ) if b'"chat_id":1,' in r.content.replace(b" ", b"") else httpx.Response(
        200, json={"ok": True, "result": {}})
    assert await notify._send(1, "blocked") is False
    assert await notify._send(2, "ok", parse_mode="HTML") is True
    assert telegram_api.calls("sendMessage")[1]["parse_mode"] == "HTML"
