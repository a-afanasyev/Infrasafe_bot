"""E4 (аудит 2026-08-18): лимит тела device-эндпоинтов — матрица плана.

`authenticate_edge` читает тело целиком до эндпоинта (HMAC), поэтому лимит
живёт на чтении СЫРОГО потока, а не после request.form(). До фикса лимитов
в access_control не было вообще.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from access_control.services.device_auth import MAX_EDGE_BODY_BYTES, _read_body_capped


def _request(chunks: list[bytes], content_length=None) -> Request:
    headers = []
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))
    scope = {"type": "http", "method": "POST", "path": "/edge/x",
             "headers": headers, "query_string": b""}
    sent = {"i": 0}

    async def receive():
        i = sent["i"]
        if i < len(chunks):
            sent["i"] += 1
            return {"type": "http.request", "body": chunks[i],
                    "more_body": sent["i"] < len(chunks)}
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_oversized_content_length_rejected_before_reading():
    req = _request([b"x"], content_length=MAX_EDGE_BODY_BYTES + 1)
    with pytest.raises(HTTPException) as e:
        await _read_body_capped(req)
    assert e.value.status_code == 413
    # ранний отказ: Content-Length проверяется ДО stream(), тело не читалось
    assert getattr(req, "_body", None) is None


@pytest.mark.asyncio
async def test_oversized_chunked_body_aborted_on_stream():
    """Без Content-Length (chunked): обрыв на capped-потоке."""
    big = b"a" * 1024
    req = _request([big] * 8, content_length=None)
    with pytest.raises(HTTPException) as e:
        await _read_body_capped(req, limit=4096)
    assert e.value.status_code == 413


@pytest.mark.asyncio
async def test_fake_smaller_content_length_rejected_not_truncated():
    body = b"a" * 100
    req = _request([body], content_length=10)
    with pytest.raises(HTTPException) as e:
        await _read_body_capped(req, limit=4096)
    assert e.value.status_code == 400  # mismatch, не тихое усечение


@pytest.mark.asyncio
async def test_body_exactly_at_limit_passes():
    body = b"a" * 4096
    req = _request([body], content_length=4096)
    assert await _read_body_capped(req, limit=4096) == body


@pytest.mark.asyncio
async def test_body_preserved_for_downstream_readers():
    """HMAC получил байты, а последующий request.body()/form() эндпоинта
    обязан читать из кэша, не из уже выпитого потока."""
    body = b"payload=1"
    req = _request([body], content_length=len(body))
    first = await _read_body_capped(req, limit=4096)
    assert first == body
    assert await req.body() == body  # Starlette-кэш _body


@pytest.mark.asyncio
async def test_invalid_content_length_rejected():
    req = _request([b"x"], content_length="abc")
    with pytest.raises(HTTPException) as e:
        await _read_body_capped(req, limit=4096)
    assert e.value.status_code == 400
