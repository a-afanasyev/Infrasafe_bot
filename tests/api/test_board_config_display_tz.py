"""ARCH-137 B5: зона показа отдаётся полем `display_tz` публичного board-config.

Почему здесь, а не новым эндпоинтом: на InfraSafe `/uk/api/*` идёт по
prefix-allowlist edge (SEC-22) — новый путь вернул бы 404 до правки edge
владельцем; board-config уже разрешён и публичен.

Контракт трёхсторонний, и каждая сторона проверяется по сырому HTTP:
  * GET и PUT отдают `display_tz` == settings.DISPLAY_TZ (поле заполняет
    `to_public_response`, общий для обоих путей — заполнение в GET-хендлере
    уронило бы PUT);
  * PUT, echo-ящий `display_tz` обратно (клиент, посеявший draft из ответа
    целиком), получает 422 — вход строгий (`_StrictIn`), и фронт обязан
    снимать поле (`toEditableBoardConfig`);
  * хранимая строка BoardConfig поле НЕ содержит — зона принадлежит
    развёртыванию, а не сохранённому конфигу.
"""
import copy

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.board_config.defaults import DEFAULT_BOARD_CONFIG
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.board_config import BoardConfig


def _client_body() -> dict:
    return copy.deepcopy(DEFAULT_BOARD_CONFIG)


@pytest.mark.asyncio
async def test_get_public_board_config_carries_display_tz(client):
    resp = await client.get("/api/v2/public/board-config")
    assert resp.status_code == 200
    assert resp.json()["display_tz"] == settings.DISPLAY_TZ


@pytest.mark.asyncio
async def test_put_response_carries_display_tz(client):
    resp = await client.put("/api/v2/board-config", json=_client_body())
    assert resp.status_code == 200
    assert resp.json()["display_tz"] == settings.DISPLAY_TZ


@pytest.mark.asyncio
async def test_put_echoing_display_tz_is_422(client):
    """Ровно та граба, от которой фронт держит `toEditableBoardConfig`."""
    body = _client_body()
    body["display_tz"] = settings.DISPLAY_TZ
    resp = await client.put("/api/v2/board-config", json=body)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_stored_row_has_no_display_tz(client, db_session: AsyncSession):
    resp = await client.put("/api/v2/board-config", json=_client_body())
    assert resp.status_code == 200
    row = (await db_session.execute(select(BoardConfig).where(BoardConfig.id == 1))).scalar_one()
    assert "display_tz" not in row.data
