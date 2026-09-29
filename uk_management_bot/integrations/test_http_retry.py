"""Unit tests for ARCH-03 idempotent-GET retry helper (`get_with_retries`).

Покрывает: успех без ретрая, ретрай транзиентных transport-ошибок, ретрай
502/503/504, исчерпание попыток (raise на transport, return последнего ответа
на 5xx), отсутствие ретрая на 404, валидацию retries, расчёт backoff.
asyncio.sleep замокан — тесты не спят.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from uk_management_bot.integrations.http_retry import get_with_retries


def _resp(status: int) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    return r


@pytest.fixture(autouse=True)
def _no_sleep():
    """Не спим реально: backoff делает asyncio.sleep — заменяем на no-op."""
    with patch(
        "uk_management_bot.integrations.http_retry.asyncio.sleep",
        new=AsyncMock(return_value=None),
    ) as sleep_mock:
        yield sleep_mock


class TestSuccessPath:
    @pytest.mark.asyncio
    async def test_returns_first_2xx_without_retry(self, _no_sleep):
        client = MagicMock()
        client.get = AsyncMock(return_value=_resp(200))

        resp = await get_with_retries(client, "/x")

        assert resp.status_code == 200
        client.get.assert_called_once()
        _no_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_retry_4xx(self, _no_sleep):
        client = MagicMock()
        client.get = AsyncMock(return_value=_resp(404))

        resp = await get_with_retries(client, "/x")

        assert resp.status_code == 404
        client.get.assert_called_once()  # 404 не транзиентна — не ретраим
        _no_sleep.assert_not_called()


class TestTransportRetry:
    @pytest.mark.asyncio
    async def test_retries_transport_error_then_succeeds(self, _no_sleep):
        client = MagicMock()
        client.get = AsyncMock(
            side_effect=[httpx.ConnectError("boom"), _resp(200)]
        )

        resp = await get_with_retries(client, "/x", retries=3)

        assert resp.status_code == 200
        assert client.get.call_count == 2
        assert _no_sleep.call_count == 1

    @pytest.mark.asyncio
    async def test_exhausts_retries_raises_last_transport_error(self, _no_sleep):
        client = MagicMock()
        client.get = AsyncMock(side_effect=httpx.ReadTimeout("slow"))

        with pytest.raises(httpx.ReadTimeout):
            await get_with_retries(client, "/x", retries=3)

        assert client.get.call_count == 3
        assert _no_sleep.call_count == 2  # спим между попытками, не после последней


class TestStatusRetry:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [502, 503, 504])
    async def test_retries_gateway_5xx_then_succeeds(self, status, _no_sleep):
        client = MagicMock()
        client.get = AsyncMock(side_effect=[_resp(status), _resp(200)])

        resp = await get_with_retries(client, "/x", retries=3)

        assert resp.status_code == 200
        assert client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_last_5xx_when_exhausted(self, _no_sleep):
        client = MagicMock()
        client.get = AsyncMock(return_value=_resp(503))

        resp = await get_with_retries(client, "/x", retries=3)

        # Исчерпали попытки → возвращаем последний ответ (не raise) — вызывающий
        # сам решает деградацию.
        assert resp.status_code == 503
        assert client.get.call_count == 3

    @pytest.mark.asyncio
    async def test_does_not_retry_500(self, _no_sleep):
        client = MagicMock()
        client.get = AsyncMock(return_value=_resp(500))

        resp = await get_with_retries(client, "/x", retries=3)

        assert resp.status_code == 500
        client.get.assert_called_once()  # 500 чаще детерминированная — не ретраим


class TestBackoffAndValidation:
    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self, _no_sleep):
        client = MagicMock()
        client.get = AsyncMock(side_effect=httpx.ConnectError("x"))

        with pytest.raises(httpx.ConnectError):
            await get_with_retries(client, "/x", retries=3, backoff_base=0.5)

        # backoff_base * 2**attempt: 0.5, 1.0
        delays = [c.args[0] for c in _no_sleep.call_args_list]
        assert delays == [0.5, 1.0]

    @pytest.mark.asyncio
    async def test_retries_below_one_raises(self):
        client = MagicMock()
        client.get = AsyncMock(return_value=_resp(200))

        with pytest.raises(ValueError, match="retries must be >= 1"):
            await get_with_retries(client, "/x", retries=0)

    @pytest.mark.asyncio
    async def test_single_attempt_no_retry(self, _no_sleep):
        client = MagicMock()
        client.get = AsyncMock(side_effect=httpx.ConnectError("x"))

        with pytest.raises(httpx.ConnectError):
            await get_with_retries(client, "/x", retries=1)

        client.get.assert_called_once()
        _no_sleep.assert_not_called()


class TestRetryStatuses:
    """FILE_RETRY_STATUSES (ревью 2026-09-28): 502 от /file не повторяем —
    media-service уже ретраил скачивание у Telegram в своём бюджете."""

    @pytest.mark.asyncio
    async def test_file_statuses_do_not_retry_502(self, _no_sleep):
        from uk_management_bot.integrations.http_retry import FILE_RETRY_STATUSES

        client = MagicMock()
        client.get = AsyncMock(return_value=_resp(502))

        resp = await get_with_retries(client, "/x", retry_statuses=FILE_RETRY_STATUSES)

        assert resp.status_code == 502
        client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_file_statuses_still_retry_503(self, _no_sleep):
        from uk_management_bot.integrations.http_retry import FILE_RETRY_STATUSES

        client = MagicMock()
        client.get = AsyncMock(side_effect=[_resp(503), _resp(200)])

        resp = await get_with_retries(client, "/x", retry_statuses=FILE_RETRY_STATUSES)

        assert resp.status_code == 200
        assert client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_bot_download_media_file_does_not_retry_502(self, _no_sleep):
        from uk_management_bot.integrations.media_client import MediaServiceClient

        media = MediaServiceClient("http://media.test")
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(502, request=request)

        media.client = httpx.AsyncClient(
            base_url="http://media.test", transport=httpx.MockTransport(handler)
        )
        try:
            assert await media.download_media_file(5) is None
        finally:
            await media.client.aclose()
        assert calls["n"] == 1
