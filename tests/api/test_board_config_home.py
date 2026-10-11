"""Настройки страницы жителей (`board_config.home`): название комплекса,
заголовки и блоки страницы (видимость + свой заголовок). Правятся в редакторе
витрины; блоки «Лифты» и «Отчёты о работах» гейтуются теми же флагами, что и
модули табло.
"""
import copy
from typing import get_args

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.board_config import BoardConfig
from uk_management_bot.services.board_config.defaults import DEFAULT_BOARD_CONFIG, HOME_BLOCK_IDS
from uk_management_bot.services.board_config.schemas import HomeBlockId

EMPTY = {"ru": "", "uz": ""}


def _body(**overrides) -> dict:
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data.update(overrides)
    return data


def _home(**overrides) -> dict:
    home = copy.deepcopy(DEFAULT_BOARD_CONFIG["home"])
    home.update(overrides)
    return home


@pytest_asyncio.fixture
async def seed_config(db_session: AsyncSession, manager_user):
    async def _seed(data: dict):
        db_session.add(BoardConfig(id=1, data=data, updated_by=manager_user.id))
        await db_session.commit()

    return _seed


@pytest.fixture
def modules_on(monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)
    monkeypatch.setattr(settings, "WORK_REPORTS_ENABLED", True)


def test_strict_block_id_type_matches_canonical_list():
    assert get_args(HomeBlockId) == HOME_BLOCK_IDS


def test_default_home_has_every_block_visible_with_empty_texts():
    home = DEFAULT_BOARD_CONFIG["home"]
    assert [b["id"] for b in home["blocks"]] == list(HOME_BLOCK_IDS)
    assert all(b["visible"] and b["title"] == EMPTY for b in home["blocks"])
    assert home["complex_name"] == EMPTY and home["title"] == EMPTY


@pytest.mark.asyncio
async def test_old_row_without_home_reads_as_default(client, seed_config, modules_on):
    legacy = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    legacy.pop("home")
    await seed_config(legacy)
    body = (await client.get("/api/v2/public/board-config")).json()
    assert [b["id"] for b in body["home"]["blocks"]] == list(HOME_BLOCK_IDS)
    assert body["org"] == legacy["org"]


@pytest.mark.asyncio
async def test_put_saves_texts_and_blocks(client, modules_on):
    blocks = [{"id": "requests", "visible": False, "title": {"ru": "Заявки ЖК", "uz": ""}}]
    home = _home(complex_name={"ru": "ЖК Olmazor", "uz": "Olmazor TJM"}, blocks=blocks)
    resp = await client.put("/api/v2/board-config", json=_body(home=home))
    assert resp.status_code == 200
    saved = resp.json()["home"]
    assert saved["complex_name"] == {"ru": "ЖК Olmazor", "uz": "Olmazor TJM"}
    # Неполный список блоков дополняется, порядок — канонический.
    assert [b["id"] for b in saved["blocks"]] == list(HOME_BLOCK_IDS)
    requests = next(b for b in saved["blocks"] if b["id"] == "requests")
    assert requests == {"id": "requests", "visible": False, "title": {"ru": "Заявки ЖК", "uz": ""}}


@pytest.mark.asyncio
async def test_duplicate_block_ids_keep_first(client, modules_on):
    blocks = [
        {"id": "works", "visible": False, "title": EMPTY},
        {"id": "works", "visible": True, "title": EMPTY},
    ]
    resp = await client.put("/api/v2/board-config", json=_body(home=_home(blocks=blocks)))
    works = [b for b in resp.json()["home"]["blocks"] if b["id"] == "works"]
    assert works == [{"id": "works", "visible": False, "title": EMPTY}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "home_patch",
    [
        {"blocks": [{"id": "weather", "visible": True, "title": EMPTY}]},
        {"unexpected": 1},
        {"blocks": [{"id": "works", "visible": True, "title": EMPTY, "width": "half"}]},
    ],
)
async def test_put_rejects_malformed_home(client, home_patch):
    resp = await client.put("/api/v2/board-config", json=_body(home=_home(**home_patch)))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_without_home_keeps_stored(client, seed_config):
    await seed_config(_body(home=_home(complex_name={"ru": "ЖК Olmazor", "uz": ""})))
    old_client = _body()
    old_client.pop("home")
    resp = await client.put("/api/v2/board-config", json=old_client)
    assert resp.status_code == 200
    assert resp.json()["home"]["complex_name"]["ru"] == "ЖК Olmazor"


@pytest.mark.asyncio
async def test_disabled_modules_cut_from_home_blocks(client, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    monkeypatch.setattr(settings, "WORK_REPORTS_ENABLED", False)
    ids = [b["id"] for b in (await client.get("/api/v2/public/board-config")).json()["home"]["blocks"]]
    assert "elevators" not in ids and "workreports" not in ids
    assert ids == ["announcements", "contacts", "requests", "works"]


@pytest.mark.asyncio
async def test_stored_row_keeps_disabled_blocks(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    resp = await client.put("/api/v2/board-config", json=_body())
    assert resp.status_code == 200
    row = (await db_session.execute(select(BoardConfig).where(BoardConfig.id == 1))).scalar_one()
    assert "elevators" in [b["id"] for b in row.data["home"]["blocks"]]


@pytest.mark.asyncio
async def test_put_from_editor_with_module_off_keeps_hidden_block(client, seed_config, monkeypatch):
    """Флаг лифтов выключен → редактор блока не видит и не присылает; сохранённые
    «скрыт» и заголовок не должны сброситься в дефолт."""
    hidden = {"id": "elevators", "visible": False, "title": {"ru": "Наши лифты", "uz": ""}}
    blocks = [b if b["id"] != "elevators" else hidden for b in _home()["blocks"]]
    await seed_config(_body(home=_home(blocks=blocks)))
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    seen = (await client.get("/api/v2/public/board-config")).json()["home"]
    resp = await client.put("/api/v2/board-config", json=_body(home=seen))
    assert resp.status_code == 200
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)
    body = (await client.get("/api/v2/public/board-config")).json()
    assert next(b for b in body["home"]["blocks"] if b["id"] == "elevators") == hidden
