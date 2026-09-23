"""``api/residents/notify.send_plain_messages``: считает только доставленные, не роняет рассылку.

Сбой сети проверяется на транспорте общего клиента ``api/telegram_send``
(фикстура ``telegram_api``): один адресат падает httpx-ошибкой с URL и
токеном в тексте — не считается, остальные доставлены, в логе нет текста
исключения. Отказы Telegram (403, 429) — тоже ответами транспорта.
"""
from __future__ import annotations

import logging

import httpx
import pytest

from uk_management_bot.api.residents import notify
from uk_management_bot.services.elevator_service import Message

SECRET_URL = "https://api.telegram.org/bot123:SECRET-TOKEN/sendMessage"


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


class FakeClock:
    """Фейковое время для темпа рассылок: ``sleep`` двигает часы, не ждёт."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        import asyncio

        self.sleeps.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)  # отдать управление — как настоящий sleep


@pytest.fixture
def fake_clock(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(notify, "_monotonic", clock.monotonic)
    monkeypatch.setattr(notify, "_sleep", clock.sleep)
    monkeypatch.setattr(notify, "_PACER", notify._BulkPacer())
    return clock


@pytest.fixture
def no_throttle(fake_clock):
    """Темп рассылки (A9-P2-8) — на фейковых часах, без реального ожидания."""
    return fake_clock


@pytest.mark.asyncio
async def test_non_200_is_not_counted_as_delivered(telegram_api, no_throttle):
    # A9-P2-8: рассылка смотрит на полный результат (429 → retry_after), поэтому
    # отказ подаётся транспортом общего клиента, а не подменой `_send`.
    import json

    telegram_api.handler = lambda r: httpx.Response(
        403, json={"ok": False, "description": "Forbidden: bot was blocked by the user"},
    ) if json.loads(r.content)["chat_id"] == 7 else httpx.Response(
        200, json={"ok": True, "result": {}})
    messages = [Message(telegram_id=7, text="blocked"), Message(telegram_id=8, text="ok")]

    assert await notify.send_plain_messages(messages) == 1
    assert len(telegram_api.calls("sendMessage")) == 2


@pytest.mark.asyncio
async def test_empty_and_plain_mode(telegram_api, no_throttle):
    telegram_api.reply(200, result={})
    assert await notify.send_plain_messages([]) == 0
    assert await notify.send_plain_messages([Message(telegram_id=1, text="x")], parse_mode=None) == 1
    calls = telegram_api.calls("sendMessage")
    assert calls == [{"chat_id": 1, "text": "x"}]  # parse_mode=None — поле не шлётся


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


@pytest.mark.asyncio
async def test_bulk_retries_429_after_retry_after(telegram_api, fake_clock):
    """A9-P2-8(d): 429 → следующее сообщение не раньше ``retry_after``."""
    import json

    sent_at: dict[int, list[float]] = {}

    def handler(request):
        chat_id = json.loads(request.content)["chat_id"]
        sent_at.setdefault(chat_id, []).append(fake_clock.now)
        if chat_id == 2 and len(sent_at[chat_id]) == 1:
            return httpx.Response(429, json={
                "ok": False, "error_code": 429,
                "description": "Too Many Requests: retry after 3",
                "parameters": {"retry_after": 3},
            })
        return httpx.Response(200, json={"ok": True, "result": {}})

    telegram_api.handler = handler
    messages = [Message(telegram_id=i, text=f"msg {i}") for i in (1, 2, 3)]

    assert await notify.send_plain_messages(messages) == 3
    assert {k: len(v) for k, v in sent_at.items()} == {1: 1, 2: 2, 3: 1}
    first_try, retry = sent_at[2]
    assert retry - first_try >= 3, "429 обязан подождать retry_after"
    assert sent_at[3][0] >= retry + notify.BULK_SEND_INTERVAL


@pytest.mark.asyncio
async def test_bulk_429_gives_up_after_limited_retries(telegram_api, fake_clock):
    telegram_api.handler = lambda r: httpx.Response(429, json={
        "ok": False, "error_code": 429, "description": "Too Many Requests",
        "parameters": {"retry_after": 1},
    })

    assert await notify.send_plain_messages([Message(telegram_id=5, text="x")]) == 0
    assert len(telegram_api.calls("sendMessage")) == 1 + notify.BULK_MAX_429_RETRIES


@pytest.mark.asyncio
async def test_parallel_broadcasts_share_one_pace(telegram_api, monkeypatch):
    """Ревью A9-P2-8: темп ОБЩИЙ на процесс. Две параллельные рассылки по 50
    сообщений (две смены статуса лифта подряд) вместе идут не быстрее
    ``BULK_SEND_INTERVAL`` — а не 2 × 25/с. Реальные часы с укороченным
    интервалом: фейковые суммировали бы сны обеих задач и прятали параллелизм."""
    import asyncio
    import time

    interval = 0.005
    monkeypatch.setattr(notify, "BULK_SEND_INTERVAL", interval)
    monkeypatch.setattr(notify, "_PACER", notify._BulkPacer())
    stamps: list[float] = []

    def handler(request):
        stamps.append(time.monotonic())
        return httpx.Response(200, json={"ok": True, "result": {}})

    telegram_api.handler = handler
    first = [Message(telegram_id=1000 + i, text="a") for i in range(50)]
    second = [Message(telegram_id=2000 + i, text="b") for i in range(50)]

    delivered = await asyncio.gather(
        notify.send_plain_messages(first), notify.send_plain_messages(second))

    assert delivered == [50, 50]
    # Раздельный темп дал бы ~49 интервалов на обе; общий — не меньше 99.
    assert stamps[-1] - stamps[0] >= 99 * interval * 0.9, "рассылки обогнали общий темп"
    # Рассылки шли одновременно (перемежались), а не одна после другой.
    first_half = [c["chat_id"] // 1000 for c in telegram_api.calls("sendMessage")][:50]
    assert 0 < first_half.count(2) < 50


@pytest.mark.asyncio
async def test_bulk_stops_at_max_duration(telegram_api, fake_clock, monkeypatch, caplog):
    monkeypatch.setattr(notify, "BULK_MAX_DURATION", 10 * notify.BULK_SEND_INTERVAL)
    telegram_api.reply(200, result={})
    messages = [Message(telegram_id=i, text="x") for i in range(40)]

    with caplog.at_level(logging.WARNING):
        delivered = await notify.send_plain_messages(messages)

    assert 0 < delivered < 40
    assert "Рассылка прервана по потолку" in caplog.text
