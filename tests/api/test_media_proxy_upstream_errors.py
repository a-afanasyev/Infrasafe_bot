"""Ревью медиасервиса 2026-09-28, PR 2: как прокси переводит ответы media-service.

- 401/403 media-service = рассинхрон MEDIA_API_KEY между сервисами, а не
  «пользователь не авторизован». Проброшенный браузеру 401 запускал refresh
  сессии на каждый <img>; наружу — 502 и error-лог.
- 502 от `/file` media-service значит «сам уже ретраил скачивание у Telegram
  в своём бюджете 25 с». Повторять его прокси не должен: 3 × 25 с гарантированно
  упираются в 504 edge (30 с) и удваивают нагрузку на Telegram.
- Список вложений при ошибке media-service раньше молча отдавал `[]` — сбой
  выглядел как «фото нет». Теперь ошибка; и limit=200 вместо дефолтных 50.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException

from uk_management_bot.api.routes import media_proxy

MEDIA_ID = 7
REQUEST_NUMBER = "260601-001"

pytestmark = pytest.mark.asyncio


@pytest.fixture
def upstream():
    return {"meta_status": 200, "file_status": 200, "list_status": 200,
            "file_attempts": 0, "list_requests": [], "timeouts": [],
            "list_transport_error": False}


@pytest.fixture
def wired(monkeypatch, upstream):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith(f"/media/{MEDIA_ID}"):
            return httpx.Response(upstream["meta_status"], json={"request_number": REQUEST_NUMBER})
        if path.endswith(f"/media/{MEDIA_ID}/file"):
            upstream["file_attempts"] += 1
            if upstream["file_status"] != 200:
                return httpx.Response(upstream["file_status"], content=b"nope")
            return httpx.Response(200, content=b"img", headers={"content-type": "image/jpeg"})
        if "/media/request/" in path:
            upstream["list_requests"].append(request)
            if upstream["list_transport_error"]:
                raise httpx.ConnectError("media-service недоступен")
            return httpx.Response(upstream["list_status"], json=[{"id": 1}])
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def _factory(*args, **kwargs):
        upstream["timeouts"].append(kwargs.get("timeout"))
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(media_proxy.httpx, "AsyncClient", _factory)
    monkeypatch.setattr(media_proxy, "check_request_access", AsyncMock())
    monkeypatch.setattr(
        type(media_proxy.settings), "MEDIA_SERVICE_URL",
        property(lambda self: "http://media.test"), raising=False,
    )
    monkeypatch.setattr(media_proxy.stream_with_retries.__globals__["asyncio"],
                        "sleep", AsyncMock())
    return upstream


async def _file():
    return await media_proxy.proxy_media_file(media_id=MEDIA_ID, user=MagicMock(), db=MagicMock())


async def _list():
    return await media_proxy.proxy_media_list(request_number=REQUEST_NUMBER, user=MagicMock(), db=MagicMock())


class TestFileStream:
    async def test_upstream_502_is_not_retried(self, wired):
        wired["file_status"] = 502
        with pytest.raises(HTTPException) as exc:
            await _file()
        assert exc.value.status_code == 502
        assert wired["file_attempts"] == 1

    async def test_upstream_503_is_still_retried(self, wired):
        # Рестарт media-service — транзиентно, повтор имеет смысл.
        wired["file_status"] = 503
        with pytest.raises(HTTPException) as exc:
            await _file()
        assert exc.value.status_code == 503
        assert wired["file_attempts"] == 3

    @pytest.mark.parametrize("status", [401, 403])
    async def test_upstream_auth_failure_becomes_502(self, wired, status):
        wired["file_status"] = status
        with pytest.raises(HTTPException) as exc:
            await _file()
        assert exc.value.status_code == 502

    async def test_upstream_404_stays_404(self, wired):
        wired["file_status"] = 404
        with pytest.raises(HTTPException) as exc:
            await _file()
        assert exc.value.status_code == 404

    @pytest.mark.parametrize("status,expected", [(401, 502), (403, 502), (500, 502), (404, 404)])
    async def test_meta_status_mapping(self, wired, status, expected):
        wired["meta_status"] = status
        with pytest.raises(HTTPException) as exc:
            await _file()
        assert exc.value.status_code == expected


class TestList:
    async def test_ok_passes_limit_200_and_meta_timeout(self, wired):
        assert await _list() == [{"id": 1}]
        assert wired["list_requests"][0].url.params.get("limit") == "200"
        assert wired["timeouts"][0] is media_proxy._MEDIA_META_TIMEOUT

    @pytest.mark.parametrize("status", [401, 500, 502])
    async def test_upstream_error_is_not_masked_as_empty(self, wired, status):
        wired["list_status"] = status
        with pytest.raises(HTTPException) as exc:
            await _list()
        assert exc.value.status_code == 502

    async def test_transport_error_is_503(self, wired):
        wired["list_transport_error"] = True
        with pytest.raises(HTTPException) as exc:
            await _list()
        assert exc.value.status_code == 503


class TestFeedbackMediaFile:
    """Вложения обратной связи (менеджер): те же правила перевода статусов."""

    @pytest.fixture
    def feedback_wired(self, monkeypatch):
        from uk_management_bot.api.feedback import router as fb_router

        state = {"status": 200, "calls": 0, "timeouts": []}

        def handler(request: httpx.Request) -> httpx.Response:
            state["calls"] += 1
            if state["status"] != 200:
                return httpx.Response(state["status"])
            return httpx.Response(200, content=b"img", headers={"content-type": "image/jpeg"})

        real_client = httpx.AsyncClient

        def _factory(*args, **kwargs):
            state["timeouts"].append(kwargs.get("timeout"))
            kwargs["transport"] = httpx.MockTransport(handler)
            return real_client(*args, **kwargs)

        monkeypatch.setattr(fb_router.httpx, "AsyncClient", _factory)
        monkeypatch.setattr(fb_router, "_get_feedback_or_404",
                            AsyncMock(return_value=MagicMock(media_files=[MEDIA_ID])))
        monkeypatch.setattr(fb_router, "_media_base", lambda: "http://media.test")
        return fb_router, state

    async def _get(self, fb_router):
        return await fb_router.feedback_media_file(fid=1, media_id=MEDIA_ID, user=MagicMock(), db=MagicMock())

    async def test_ok_within_edge_budget(self, feedback_wired):
        fb_router, state = feedback_wired
        resp = await self._get(fb_router)
        assert resp.body == b"img"
        assert state["timeouts"] == [media_proxy._MEDIA_STREAM_TIMEOUT]

    @pytest.mark.parametrize("status,expected", [(401, 502), (502, 502), (503, 503), (404, 404)])
    async def test_status_mapping(self, feedback_wired, status, expected):
        fb_router, state = feedback_wired
        state["status"] = status
        with pytest.raises(HTTPException) as exc:
            await self._get(fb_router)
        assert exc.value.status_code == expected
        assert state["calls"] == 1
