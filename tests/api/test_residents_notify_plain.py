"""``api/residents/notify.send_plain_messages``: считает только доставленные, не роняет рассылку.

Сендер ``_send`` подменяется: один адресат падает httpx-ошибкой (URL с
токеном в тексте), другой получает не-200 от Telegram — оба не считаются,
остальные доставлены, в логе нет текста исключения.
"""
from __future__ import annotations

import logging

import httpx
import pytest

from uk_management_bot.api.residents import notify
from uk_management_bot.services.elevator_service import Message

SECRET_URL = "https://api.telegram.org/bot123:SECRET-TOKEN/sendMessage"


def _fake_send(fail_ids: set[int], rejected_ids: set[int], calls: list):
    async def fake(chat_id: int, text: str, reply_markup=None, *, parse_mode=None) -> bool:
        calls.append((chat_id, text, parse_mode))
        if chat_id in fail_ids:
            raise httpx.ConnectError(f"boom for url {SECRET_URL}")
        return chat_id not in rejected_ids
    return fake


@pytest.mark.asyncio
async def test_one_failure_does_not_stop_others_and_is_not_counted(monkeypatch, caplog):
    calls: list = []
    monkeypatch.setattr(notify, "_send", _fake_send({2}, set(), calls))
    messages = [Message(telegram_id=i, text=f"msg {i}") for i in (1, 2, 3)]

    with caplog.at_level(logging.ERROR, logger=notify.__name__):
        delivered = await notify.send_plain_messages(messages)

    assert delivered == 2
    assert [c[0] for c in calls] == [1, 2, 3]
    assert all(c[2] == "HTML" for c in calls)
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
async def test_send_returns_false_on_non_200(monkeypatch):
    """Контракт ``_send``: 200 → True, иначе False (без исключения)."""
    class _Resp:
        def __init__(self, code):
            self.status_code = code

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json):
            return _Resp(403 if json["chat_id"] == 1 else 200)

    monkeypatch.setattr(notify.httpx, "AsyncClient", _Client)
    assert await notify._send(1, "blocked") is False
    assert await notify._send(2, "ok", parse_mode="HTML") is True
