"""Тест client.media_client.MediaServiceClient.upload_access_photo.

HTTP-слой (httpx) МОКается — проверяем, что клиент формирует правильный запрос
к POST /media/upload-access и нормализует ответ в dict(media_id, telegram_file_id,
file_url). Используется access_control-сервисом.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# client/ — не пакет в составе app; добавим путь для импорта media_client.
sys.path.insert(0, str(Path(__file__).parent / "client"))

from media_client import MediaServiceClient  # noqa: E402


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_upload_access_photo_builds_request(monkeypatch):
    captured = {}

    async def fake_post(url, files=None, data=None, **kwargs):
        captured["url"] = url
        captured["files"] = files
        captured["data"] = data
        return _FakeResponse(
            {
                "media_file": {"id": 321, "telegram_file_id": "TGFILEXYZ"},
                "file_url": "/api/v1/media/321/file",
            }
        )

    client = MediaServiceClient(base_url="http://media:8000", api_key="testkey")
    monkeypatch.setattr(client.client, "post", fake_post)

    result = await client.upload_access_photo(
        kind="plate",
        ref="GATE1|evt-99",
        file_data=b"\x89PNG\r\n\x1a\n",
        filename="plate.png",
        content_type="image/png",
        uploaded_by=7,
    )

    # правильный маршрут
    assert captured["url"] == "/media/upload-access"
    # форм-поля
    assert captured["data"]["kind"] == "plate"
    assert captured["data"]["ref"] == "GATE1|evt-99"
    assert captured["data"]["uploaded_by"] == "7"
    # файл передан как multipart
    assert captured["files"][0][0] == "file"
    # ответ нормализован
    assert result == {
        "media_id": 321,
        "telegram_file_id": "TGFILEXYZ",
        "file_url": "/api/v1/media/321/file",
    }
    await client.close()


@pytest.mark.asyncio
async def test_client_sends_api_key_header():
    """api_key, если передан, уходит в заголовок X-API-Key (SEC-022)."""
    client = MediaServiceClient(base_url="http://media:8000", api_key="secret123")
    assert client.client.headers.get("X-API-Key") == "secret123"
    await client.close()
