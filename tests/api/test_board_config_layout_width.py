"""LayoutItem.width — блоки табло могут быть 'full' или 'half' (две плитки в ряд).

Ключевое: backend ОБЯЗАН знать поле, иначе pydantic выкинет его на PUT/GET и
ширина не сохранится. Тесты пинят дефолт, валидацию и round-trip через PUT→GET.
"""
import copy

import pytest
from pydantic import ValidationError

from uk_management_bot.api.board_config.defaults import DEFAULT_BOARD_CONFIG
from uk_management_bot.api.board_config.schemas import BoardConfigData, LayoutItem


def test_width_defaults_to_full():
    item = LayoutItem(id="stats", visible=True)
    assert item.width == "full"


def test_width_accepts_half():
    assert LayoutItem(id="hours", visible=True, width="half").width == "half"


def test_width_rejects_unknown():
    with pytest.raises(ValidationError):
        LayoutItem(id="hours", visible=True, width="quarter")


def test_config_without_width_validates_and_defaults():
    # Легаси-строка без width должна валидироваться и получить 'full'.
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    for item in data["layout"]:
        item.pop("width", None)
    cfg = BoardConfigData.model_validate(data)
    assert all(i.width == "full" for i in cfg.layout)


@pytest.mark.asyncio
async def test_put_get_roundtrip_preserves_width(client):
    # PUT конфига с 'half' → GET возвращает ту же ширину (не выкинута схемой).
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    for item in data["layout"]:
        item["width"] = "half" if item["id"] in ("rating", "hours") else "full"

    put = await client.put("/api/v2/board-config", json=data)
    assert put.status_code == 200

    got = await client.get("/api/v2/public/board-config")
    assert got.status_code == 200
    widths = {i["id"]: i["width"] for i in got.json()["layout"]}
    assert widths["rating"] == "half" and widths["hours"] == "half"
    assert widths["stats"] == "full"
