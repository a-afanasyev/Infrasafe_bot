"""AUD6-P2-03: ретрай с backoff в download_file.

Раньше внутри media ретраев к Telegram не было вовсе — транзиентный сетевой
сбой сразу превращался в 502 витрины/прогрева. Клиентские 4xx (файл удалён)
ретраить бессмысленно — они пробрасываются сразу.
"""
import asyncio
from types import SimpleNamespace

import httpx

from app.core.log_sanitize import TelegramDownloadError
import pytest

from app.services.telegram_client import TelegramClientService


@pytest.fixture
def client(monkeypatch):
    svc = TelegramClientService.__new__(TelegramClientService)
    # Без реального бота: get_file подменяется в каждом тесте.
    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)
    return svc


async def _instant_sleep(_delay):
    return None


class _FakeResponse:
    def __init__(self, status_code=200, content=b"bytes"):
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": "image/jpeg"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "err", request=httpx.Request("GET", "http://x"),
                response=httpx.Response(self.status_code),
            )


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url):
        return _FakeResponse()


@pytest.mark.asyncio
async def test_transient_failure_retried_then_succeeds(client, monkeypatch):
    calls = {"n": 0}

    async def flaky_get_file(file_id):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("blip")
        return SimpleNamespace(file_path="photos/1.jpg")

    monkeypatch.setattr(client, "get_file", flaky_get_file)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    data, content_type = await client.download_file("F1")

    assert data == b"bytes"
    assert content_type == "image/jpeg"
    assert calls["n"] == 3  # две неудачи + успех третьей попытки


@pytest.mark.asyncio
async def test_persistent_failure_raises_after_three_attempts(client, monkeypatch):
    calls = {"n": 0}

    async def always_down(file_id):
        calls["n"] += 1
        raise httpx.ConnectError("down")

    monkeypatch.setattr(client, "get_file", always_down)

    # E1 (аудит 2026-08-18): наружу летит САНИТИЗИРОВАННОЕ исключение —
    # исходное несло бы URL с токеном в traceback/debug-ответ.
    with pytest.raises(TelegramDownloadError) as excinfo:
        await client.download_file("F2")
    assert calls["n"] == 3
    assert "ConnectError" in str(excinfo.value)
    assert excinfo.value.__suppress_context__  # from None: цепочка подавлена


@pytest.mark.asyncio
async def test_client_4xx_not_retried(client, monkeypatch):
    calls = {"n": 0}

    async def ok_get_file(file_id):
        calls["n"] += 1
        return SimpleNamespace(file_path="photos/1.jpg")

    class _NotFoundClient(_FakeAsyncClient):
        async def get(self, url):
            return _FakeResponse(status_code=404)

    monkeypatch.setattr(client, "get_file", ok_get_file)
    monkeypatch.setattr(httpx, "AsyncClient", _NotFoundClient)

    with pytest.raises(TelegramDownloadError) as excinfo:
        await client.download_file("F3")
    assert calls["n"] == 1  # 4xx повторами не лечится — одна попытка
    assert "HTTP 404" in str(excinfo.value)  # диагностика сохранена, URL — нет
