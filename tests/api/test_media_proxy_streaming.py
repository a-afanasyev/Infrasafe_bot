"""П9a / AUD5-APIFE-15 — медиа-прокси отдаёт байты потоком, а не через память.

Раньше файл (до 50 МБ) целиком поднимался в память API-процесса на каждый
`<img>`: при нескольких параллельных просмотрах это прямой путь к OOM.

Проверяется не «используется ли StreamingResponse», а наблюдаемые следствия:
сколько кусков успел отдать апстрим к моменту, когда клиент получил первый;
закрывается ли соединение при обрыве клиента и на ошибке; где проходит
граница ретрая. Форма ответа сама по себе ничего не гарантирует — можно
обернуть в `StreamingResponse` уже прочитанные байты.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException

from uk_management_bot.api.routes import media_proxy

MEDIA_ID = 7
REQUEST_NUMBER = "260601-001"
CHUNKS = [b"aaaa", b"bbbb", b"cccc", b"dddd"]


class RecordingStream(httpx.AsyncByteStream):
    """Апстрим-поток, который помнит, сколько кусков отдал и закрыли ли его."""

    def __init__(self, chunks: list[bytes], fail_after: int | None = None):
        self._chunks = chunks
        self._fail_after = fail_after
        self.yielded = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self._chunks:
            if self._fail_after is not None and self.yielded >= self._fail_after:
                raise httpx.ReadError("апстрим оборвался посреди тела")
            self.yielded += 1
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def upstream():
    """Состояние поддельного media-service: поток, счётчик попыток, сценарий."""
    return {
        "stream": RecordingStream(list(CHUNKS)),
        "attempts": 0,
        "file_status": 200,
        "content_type": "image/jpeg",
        "transport_errors": 0,
    }


@pytest.fixture
def wired(monkeypatch, upstream):
    """Прокси, подключённый к поддельному media-service через MockTransport."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(f"/media/{MEDIA_ID}"):
            return httpx.Response(200, json={"request_number": REQUEST_NUMBER})
        upstream["attempts"] += 1
        if upstream["transport_errors"] >= upstream["attempts"]:
            raise httpx.ConnectError("media-service недоступен")
        if upstream["file_status"] != 200:
            return httpx.Response(upstream["file_status"], content=b"nope")
        return httpx.Response(
            200,
            stream=upstream["stream"],
            headers={"content-type": upstream["content_type"]},
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def _factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(media_proxy.httpx, "AsyncClient", _factory)
    monkeypatch.setattr(media_proxy, "check_request_access", AsyncMock())
    monkeypatch.setattr(
        type(media_proxy.settings), "MEDIA_SERVICE_URL",
        property(lambda self: "http://media.test"), raising=False,
    )
    # Ретраи без ожидания: предмет проверки — граница ретрая, а не backoff.
    monkeypatch.setattr(media_proxy.stream_with_retries.__globals__["asyncio"],
                        "sleep", AsyncMock())
    return upstream


async def _call():
    return await media_proxy.proxy_media_file(
        media_id=MEDIA_ID, user=MagicMock(), db=MagicMock()
    )


pytestmark = pytest.mark.asyncio


class TestBytesAreStreamed:
    async def test_first_chunk_reaches_client_before_upstream_is_drained(self, wired):
        """Суть пункта: тело НЕ читается целиком до ответа клиенту."""
        response = await _call()
        body = response.body_iterator

        first = await body.__anext__()

        assert first == CHUNKS[0]
        assert wired["stream"].yielded == 1, (
            f"апстрим отдал {wired['stream'].yielded} кусков к моменту первого "
            "куска у клиента — тело буферизуется целиком"
        )
        await body.aclose()

    async def test_whole_body_arrives_intact(self, wired):
        response = await _call()
        received = b"".join([chunk async for chunk in response.body_iterator])
        assert received == b"".join(CHUNKS)

    async def test_content_type_and_cache_headers_are_preserved(self, wired):
        wired["content_type"] = "video/mp4"
        response = await _call()
        try:
            assert response.media_type == "video/mp4"
            assert response.headers["cache-control"] == "private, max-age=300"
        finally:
            await response.body_iterator.aclose()


class TestUpstreamIsAlwaysClosed:
    async def test_closed_when_the_client_disconnects_mid_stream(self, wired):
        """Обрыв клиента: Starlette закрывает генератор — соединение не течёт."""
        response = await _call()
        body = response.body_iterator
        await body.__anext__()

        await body.aclose()  # ровно это делает Starlette при disconnect

        assert wired["stream"].closed, "апстрим остался открытым после обрыва клиента"

    async def test_closed_after_a_complete_read(self, wired):
        response = await _call()
        async for _ in response.body_iterator:
            pass
        assert wired["stream"].closed

    async def test_closed_when_upstream_answers_with_an_error(self, wired):
        wired["file_status"] = 404
        with pytest.raises(HTTPException) as exc:
            await _call()
        assert exc.value.status_code == 404

    async def test_transport_failure_degrades_to_503(self, wired):
        wired["transport_errors"] = 99  # падают все попытки
        with pytest.raises(HTTPException) as exc:
            await _call()
        assert exc.value.status_code == 503


class TestRetryBoundary:
    async def test_retries_while_only_headers_are_at_stake(self, wired):
        """До первого байта тела повтор безопасен — и он происходит."""
        wired["transport_errors"] = 1  # первая попытка падает, вторая живёт

        response = await _call()
        received = b"".join([chunk async for chunk in response.body_iterator])

        assert wired["attempts"] == 2
        assert received == b"".join(CHUNKS)

    async def test_does_not_retry_once_bytes_are_on_the_wire(self, wired):
        """Ретрай в середине тела склеил бы файл из двух попыток.

        Обрыв апстрима после второго куска обязан оборвать выдачу, а не
        начать её заново: клиент уже получил байты, «переиграть» их нельзя.
        """
        wired["stream"] = RecordingStream(list(CHUNKS), fail_after=2)

        response = await _call()
        received = b""
        with pytest.raises(httpx.ReadError):
            async for chunk in response.body_iterator:
                received += chunk

        assert wired["attempts"] == 1, "тело пытались перезапросить после отдачи байтов"
        assert received == b"".join(CHUNKS[:2])


class TestSizeLimit:
    async def test_stream_is_cut_when_it_outgrows_the_declared_limit(
        self, wired, monkeypatch
    ):
        """Лимит апстрима — обещание, а не гарантия; режем по факту."""
        monkeypatch.setattr(media_proxy, "_MEDIA_MAX_BYTES", 6)

        response = await _call()
        received = b"".join([chunk async for chunk in response.body_iterator])

        # Кусок, который перевалил бы за лимит, клиенту НЕ уходит: предел —
        # это потолок отданного, а не «примерно столько». Та же семантика, что
        # у эталона в api/work_reports/public_router.py.
        assert len(received) == 4, (
            f"за лимит 6 байт ушло {len(received)} — предел не соблюдён"
        )
        assert wired["stream"].closed
