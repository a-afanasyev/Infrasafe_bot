"""Плановые работы витрины (`planned_works`) — блок «Ближайшие работы» на
странице жителей. Список хранится в board_config, правится в редакторе витрины.
"""
import copy

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.board_config import BoardConfig
from uk_management_bot.services.board_config.defaults import DEFAULT_BOARD_CONFIG
from uk_management_bot.services.board_config.schemas import MAX_PLANNED_WORKS

WORK = {
    "id": "pw-1",
    "date": "2026-10-15",
    "time_from": "10:00",
    "time_to": "12:00",
    "title": {"ru": "Уборка территории", "uz": "Hududni tozalash"},
    "place": {"ru": "Двор и дорожки", "uz": "Hovli va yo'laklar"},
    "text": {"ru": "", "uz": ""},
}


def _body(**overrides) -> dict:
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data.update(overrides)
    return data


@pytest_asyncio.fixture
async def seed_config(db_session: AsyncSession, manager_user):
    async def _seed(data: dict):
        db_session.add(BoardConfig(id=1, data=data, updated_by=manager_user.id))
        await db_session.commit()

    return _seed


def test_default_has_no_planned_works():
    assert DEFAULT_BOARD_CONFIG["planned_works"] == []


@pytest.mark.asyncio
async def test_put_saves_and_get_returns_planned_works(client):
    resp = await client.put("/api/v2/board-config", json=_body(planned_works=[WORK]))
    assert resp.status_code == 200
    assert resp.json()["planned_works"] == [WORK]

    public = await client.get("/api/v2/public/board-config")
    assert public.json()["planned_works"] == [WORK]


@pytest.mark.asyncio
async def test_old_row_without_field_reads_as_empty_list(client, seed_config):
    legacy = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    legacy.pop("planned_works")
    await seed_config(legacy)
    resp = await client.get("/api/v2/public/board-config")
    assert resp.status_code == 200
    assert resp.json()["planned_works"] == []
    # Остальная витрина не сброшена в дефолт из-за отсутствующего поля.
    assert resp.json()["org"] == legacy["org"]


@pytest.mark.asyncio
async def test_put_without_field_keeps_stored_works(client, seed_config):
    await seed_config(_body(planned_works=[WORK]))
    old_client = _body()
    old_client.pop("planned_works")
    resp = await client.put("/api/v2/board-config", json=old_client)
    assert resp.status_code == 200
    assert resp.json()["planned_works"] == [WORK]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "patch",
    [
        {"date": "15.10.2026"},
        {"date": "2026-02-30"},
        {"time_from": "25:00"},
        {"time_to": "10-00"},
        {"unexpected": "x"},
    ],
)
async def test_put_rejects_malformed_work(client, patch):
    work = {**WORK, **patch}
    resp = await client.put("/api/v2/board-config", json=_body(planned_works=[work]))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_empty_times_allowed(client):
    work = {**WORK, "time_from": "", "time_to": ""}
    resp = await client.put("/api/v2/board-config", json=_body(planned_works=[work]))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_put_rejects_too_many_works(client):
    works = [{**WORK, "id": f"pw-{i}"} for i in range(MAX_PLANNED_WORKS + 1)]
    resp = await client.put("/api/v2/board-config", json=_body(planned_works=works))
    assert resp.status_code == 422
