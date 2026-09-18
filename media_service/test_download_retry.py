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


# BUG-189 (2026-09-09): edge-nginx отдаёт браузеру 504 через 30 с, а одно
# повисшее соединение с Telegram ждалось 60 с — ретрай приходил в пустоту.
# Худший случай трёх попыток с backoff обязан укладываться в этот бюджет.
EDGE_BUDGET_SECONDS = 30.0


@pytest.mark.asyncio
async def test_download_timeouts_fit_edge_budget(client, monkeypatch):
    seen = {}

    class _RecordingClient(_FakeAsyncClient):
        def __init__(self, *args, **kwargs):
            seen["timeout"] = kwargs.get("timeout")

    async def ok_get_file(file_id):
        return SimpleNamespace(file_path="photos/1.jpg")

    monkeypatch.setattr(client, "get_file", ok_get_file)
    monkeypatch.setattr(httpx, "AsyncClient", _RecordingClient)

    await client.download_file("F4")

    timeout = seen["timeout"]
    assert isinstance(timeout, httpx.Timeout), (
        f"одно число {timeout!r} на connect/read: повисший connect ждётся как чтение"
    )
    assert timeout.connect is not None and timeout.connect <= 5.0
    assert timeout.read is not None and timeout.read <= 20.0
    from app.services.telegram_client import DOWNLOAD_BACKOFF_SECONDS

    worst_case = len(DOWNLOAD_BACKOFF_SECONDS) * timeout.connect + sum(DOWNLOAD_BACKOFF_SECONDS)
    assert worst_case < EDGE_BUDGET_SECONDS


def test_bot_api_timeout_is_bounded(monkeypatch):
    """`get_file` идёт через aiogram-сессию с дефолтом 60 с — тот же бюджет."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "telegram_bot_token", "123456:ci-dummy-token")
    svc = TelegramClientService()
    assert svc.bot.session.timeout <= 15.0


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


# AUD7-ARCH-03 (остаток BUG-189): connect-таймауты уложены в бюджет, но общий
# цикл — нет: каждая попытка заново зовёт get_file (до 15 с) и читает файл
# (до 20 с), плюс ожидание семафора — по коду допустимы 47–62 с при бюджете
# edge 30 с. Один общий deadline на очередь + get_file + чтение + ретраи.


@pytest.fixture
def virtual_clock(monkeypatch):
    """Виртуальные часы клиента: тест сам «проматывает» время попыток."""
    from app.services import telegram_client as tc

    state = {"now": 1000.0}
    monkeypatch.setattr(tc, "_monotonic", lambda: state["now"])
    return state


@pytest.mark.asyncio
async def test_worst_case_three_read_timeouts_stay_within_budget(client, monkeypatch, virtual_clock):
    """Три read-timeout подряд: цикл обязан оборваться до 30 с, а не дочитать
    все попытки по 15 + 20 с каждая."""
    from app.core.config import settings

    attempts = []

    class _SlowReadClient(_FakeAsyncClient):
        def __init__(self, *args, **kwargs):
            self.read_timeout = kwargs["timeout"].read

        async def get(self, url):
            attempts.append(virtual_clock["now"])
            # Чтение виснет до read-таймаута, который передал клиент.
            virtual_clock["now"] += self.read_timeout
            raise httpx.ReadTimeout("read timed out", request=httpx.Request("GET", url))

    async def slow_get_file(file_id):
        virtual_clock["now"] += settings.telegram_api_timeout_seconds  # 15 с Bot API
        return SimpleNamespace(file_path="photos/1.jpg")

    monkeypatch.setattr(client, "get_file", slow_get_file)
    monkeypatch.setattr(httpx, "AsyncClient", _SlowReadClient)
    started = virtual_clock["now"]

    with pytest.raises(TelegramDownloadError):
        await client.download_file("F-slow")

    elapsed = virtual_clock["now"] - started
    assert elapsed < EDGE_BUDGET_SECONDS, f"цикл занял {elapsed} с виртуального времени"
    assert len(attempts) < 3, "поздние попытки обязаны отсекаться общим deadline"


@pytest.mark.asyncio
async def test_hung_read_is_cancelled_by_total_budget(client, monkeypatch):
    """Реальный таймер: повисшее чтение обрывается общим бюджетом, а не read-таймаутом."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "telegram_download_total_budget_seconds", 0.3)

    class _HangingClient(_FakeAsyncClient):
        async def get(self, url):
            await asyncio.Event().wait()  # никогда

    async def ok_get_file(file_id):
        return SimpleNamespace(file_path="photos/1.jpg")

    monkeypatch.setattr(client, "get_file", ok_get_file)
    monkeypatch.setattr(httpx, "AsyncClient", _HangingClient)
    loop = asyncio.get_running_loop()
    t0 = loop.time()

    with pytest.raises(TelegramDownloadError):
        await client.download_file("F-hang")

    assert loop.time() - t0 < 2.0


@pytest.mark.asyncio
async def test_semaphore_wait_counts_toward_budget(client, monkeypatch):
    """Очередь семафора входит в бюджет: занятый семафор → отказ по deadline,
    get_file даже не вызывается."""
    from app.core.config import settings
    from app.services import preview_cache

    monkeypatch.setattr(settings, "telegram_download_total_budget_seconds", 0.3)
    sem = asyncio.Semaphore(1)
    await sem.acquire()  # держим единственный слот
    monkeypatch.setattr(preview_cache, "download_semaphore", lambda: sem)
    calls = []

    async def counting_get_file(file_id):
        calls.append(file_id)
        return SimpleNamespace(file_path="photos/1.jpg")

    monkeypatch.setattr(client, "get_file", counting_get_file)

    with pytest.raises(TelegramDownloadError):
        await client.download_file("F-queued")

    assert calls == []
    sem.release()
