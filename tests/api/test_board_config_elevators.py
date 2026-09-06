"""Модуль витрины «elevators» (T16): гейт по ``settings.ELEVATORS_ENABLED``.

Клон tests/api/test_board_config_work_reports.py под 7-й модуль layout: модуль
вырезан из HTTP-ответа при выключенном флаге, присутствует при включённом,
хранится в строке всегда, а старый PUT без него не «воскрешает» дефолт
(visible=False) поверх включённого менеджером состояния.
"""
import copy

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.board_config.defaults import (
    ALL_MODULE_IDS,
    DEFAULT_BOARD_CONFIG,
    MODULE_DEFAULTS,
    enabled_module_ids,
)
from uk_management_bot.api.board_config.schemas import StoredBoardConfigData
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.board_config import BoardConfig


def _old_client_body() -> dict:
    """Layout без «elevators» и без блока `elevators` — клиент до T16."""
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data.pop("work_reports", None)
    data.pop("elevators", None)
    return data


def _body_with_elevators(visible: bool = False) -> dict:
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    item = dict(MODULE_DEFAULTS["elevators"])
    item["visible"] = visible
    data["layout"].append(item)
    return data


@pytest_asyncio.fixture
async def seed_config(db_session: AsyncSession, manager_user):
    async def _seed(data: dict):
        db_session.add(BoardConfig(id=1, data=data, updated_by=manager_user.id))
        await db_session.commit()

    return _seed


async def _row_data(db_session: AsyncSession) -> dict:
    result = await db_session.execute(select(BoardConfig).where(BoardConfig.id == 1))
    return result.scalar_one().data


def test_module_registered_with_invisible_default():
    assert "elevators" in ALL_MODULE_IDS
    assert MODULE_DEFAULTS["elevators"] == {"id": "elevators", "visible": False, "width": "full"}
    assert DEFAULT_BOARD_CONFIG["elevators"]["title"] == {"ru": "Лифты", "uz": "Liftlar"}


def test_enabled_module_ids_cuts_elevators_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    assert "elevators" not in enabled_module_ids()
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)
    assert "elevators" in enabled_module_ids()


@pytest.mark.asyncio
async def test_get_hides_elevators_when_flag_off(client, seed_config, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    await seed_config(_body_with_elevators(visible=True))
    resp = await client.get("/api/v2/public/board-config")
    assert resp.status_code == 200
    assert "elevators" not in [i["id"] for i in resp.json()["layout"]]


@pytest.mark.asyncio
async def test_put_response_hides_elevators_when_flag_off(client, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    resp = await client.put("/api/v2/board-config", json=_body_with_elevators(visible=True))
    assert resp.status_code == 200
    assert "elevators" not in [i["id"] for i in resp.json()["layout"]]


@pytest.mark.asyncio
async def test_stored_row_retains_elevators_when_flag_off(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    resp = await client.put("/api/v2/board-config", json=_old_client_body())
    assert resp.status_code == 200
    data = await _row_data(db_session)
    assert "elevators" in [i["id"] for i in data["layout"]]
    assert "title" in data["elevators"]


@pytest.mark.asyncio
async def test_flag_on_reveals_stored_module_and_title(client, seed_config, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)
    await seed_config(_body_with_elevators(visible=True))
    resp = await client.get("/api/v2/public/board-config")
    assert resp.status_code == 200
    body = resp.json()
    layout_by_id = {i["id"]: i for i in body["layout"]}
    assert layout_by_id["elevators"]["visible"] is True
    assert body["elevators"]["title"] == {"ru": "Лифты", "uz": "Liftlar"}


@pytest.mark.asyncio
async def test_old_put_does_not_reset_enabled_elevators(client, seed_config, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)
    await seed_config(_body_with_elevators(visible=True))
    resp = await client.put("/api/v2/board-config", json=_old_client_body())
    assert resp.status_code == 200
    layout_by_id = {i["id"]: i for i in resp.json()["layout"]}
    assert layout_by_id["elevators"]["visible"] is True


@pytest.mark.asyncio
async def test_put_omitting_elevators_block_keeps_stored_title(client, seed_config, db_session):
    seeded = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    seeded["elevators"]["title"] = {"ru": "Наши лифты", "uz": "Liftlarimiz"}
    await seed_config(seeded)
    resp = await client.put("/api/v2/board-config", json=_old_client_body())
    assert resp.status_code == 200
    data = await _row_data(db_session)
    assert data["elevators"]["title"] == {"ru": "Наши лифты", "uz": "Liftlarimiz"}


@pytest.mark.asyncio
async def test_put_elevators_title_is_strict(client):
    body = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    body["elevators"] = {"title": {"ru": "Лифты", "uz": "Liftlar"}, "limit": 3}
    assert (await client.put("/api/v2/board-config", json=body)).status_code == 422


def test_normalization_appends_elevators_after_workreports():
    data = _old_client_body()
    cfg = StoredBoardConfigData.model_validate(data)
    assert [i.id for i in cfg.layout][5:] == ["workreports", "elevators"]
