"""Tests for the board_config work-reports backward-compat layer (T2).

`"workreports"` is a 6th layout module id wired into the schema/normalization
machinery now, gated behind `settings.WORK_REPORTS_ENABLED` (off everywhere).
The bug this whole layer exists to prevent: a single shared Pydantic model
used for both storage AND `response_model` would let a normalizer silently
re-add a module that the service layer just filtered out for being disabled —
defeating the gate at the FastAPI response boundary. These tests prove the
three-model split (`StoredBoardConfigData` / `BoardConfigResponse` /
`BoardConfigUpdateIn`) actually holds, by checking raw HTTP response JSON, not
service-layer return values.
"""
import copy

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.board_config.defaults import DEFAULT_BOARD_CONFIG, MODULE_DEFAULTS
from uk_management_bot.api.board_config.schemas import StoredBoardConfigData
from uk_management_bot.api.board_config.service import merge_and_save_board_config
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.board_config import BoardConfig


def _old_client_body() -> dict:
    """5-item layout, no `work_reports` key — what a pre-T2 client would send."""
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data.pop("work_reports", None)
    return data


def _full_body_with_workreports(visible: bool = False) -> dict:
    """6-item layout including "workreports" — what a post-T2 client would send."""
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    wr_item = dict(MODULE_DEFAULTS["workreports"])
    wr_item["visible"] = visible
    data["layout"].append(wr_item)
    return data


@pytest_asyncio.fixture
async def seed_config(db_session: AsyncSession, manager_user):
    """Insert a BoardConfig row (id=1) with raw data (bypasses the API)."""

    async def _seed(data: dict):
        db_session.add(BoardConfig(id=1, data=data, updated_by=manager_user.id))
        await db_session.commit()

    return _seed


async def _row_data(db_session: AsyncSession) -> dict:
    result = await db_session.execute(select(BoardConfig).where(BoardConfig.id == 1))
    return result.scalar_one().data


# ── Flag OFF: "workreports" hidden in HTTP responses, retained in storage ──


@pytest.mark.asyncio
async def test_get_hides_workreports_when_flag_off(client, seed_config):
    await seed_config(_full_body_with_workreports(visible=True))
    resp = await client.get("/api/v2/public/board-config")
    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()["layout"]]
    assert "workreports" not in ids


@pytest.mark.asyncio
async def test_put_response_hides_workreports_when_flag_off(client):
    body = _full_body_with_workreports(visible=True)
    resp = await client.put("/api/v2/board-config", json=body)
    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()["layout"]]
    assert "workreports" not in ids


@pytest.mark.asyncio
async def test_stored_row_retains_workreports_when_flag_off(client, db_session):
    # A PUT that never mentions "workreports" still gets it backfilled into
    # the STORED row by the normalizer — the flag only hides it at the HTTP
    # response boundary, it never deletes data.
    resp = await client.put("/api/v2/board-config", json=_old_client_body())
    assert resp.status_code == 200

    data = await _row_data(db_session)
    ids = [i["id"] for i in data["layout"]]
    assert "workreports" in ids


@pytest.mark.asyncio
async def test_flag_on_reveals_previously_hidden_stored_module(client, seed_config, monkeypatch):
    await seed_config(_full_body_with_workreports(visible=True))
    monkeypatch.setattr(settings, "WORK_REPORTS_ENABLED", True)

    resp = await client.get("/api/v2/public/board-config")
    assert resp.status_code == 200
    layout_by_id = {i["id"]: i for i in resp.json()["layout"]}
    assert "workreports" in layout_by_id
    assert layout_by_id["workreports"]["visible"] is True


# ── Old-client compatibility ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_old_five_item_put_body_returns_200(client):
    resp = await client.put("/api/v2/board-config", json=_old_client_body())
    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()["layout"]]
    assert set(ids) == {"stats", "requests", "announcements", "rating", "hours"}


@pytest.mark.asyncio
async def test_key_regression_old_put_does_not_reset_enabled_workreports(client, seed_config, monkeypatch):
    """Flag ON, DB has workreports.visible=True (manager enabled it earlier).
    An old 5-item client PUT (doesn't mention "workreports" at all) must not
    silently reset it back to the MODULE_DEFAULTS default of visible=False."""
    await seed_config(_full_body_with_workreports(visible=True))
    monkeypatch.setattr(settings, "WORK_REPORTS_ENABLED", True)

    resp = await client.put("/api/v2/board-config", json=_old_client_body())
    assert resp.status_code == 200
    layout_by_id = {i["id"]: i for i in resp.json()["layout"]}
    assert layout_by_id["workreports"]["visible"] is True


# ── Layout normalization: unknown ids, duplicates, idempotence ─────────


@pytest.mark.asyncio
async def test_unknown_layout_id_silently_dropped_others_kept(client):
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data.pop("work_reports", None)
    data["layout"].insert(2, {"id": "legacy_widget", "visible": True, "width": "full"})
    # Give one known module a distinguishing value to prove it survives untouched.
    for item in data["layout"]:
        if item["id"] == "hours":
            item["width"] = "half"

    resp = await client.put("/api/v2/board-config", json=data)
    assert resp.status_code == 200
    layout = resp.json()["layout"]
    ids = [i["id"] for i in layout]
    assert "legacy_widget" not in ids
    assert set(ids) == {"stats", "requests", "announcements", "rating", "hours"}
    by_id = {i["id"]: i for i in layout}
    assert by_id["hours"]["width"] == "half"


def test_duplicate_layout_id_collapses_to_first_occurrence():
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data.pop("work_reports", None)
    dup = dict(data["layout"][0])  # id="stats"
    dup["width"] = "half"  # different from the original ("full") so we can tell which survived
    data["layout"] = [data["layout"][0], dup] + data["layout"][1:]

    cfg = StoredBoardConfigData.model_validate(data)
    stats_items = [i for i in cfg.layout if i.id == "stats"]
    assert len(stats_items) == 1
    assert stats_items[0].width == "full"  # first occurrence wins, not the duplicate


def test_normalization_is_idempotent():
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data.pop("work_reports", None)
    once = StoredBoardConfigData.model_validate(data)
    twice = StoredBoardConfigData.model_validate(once.model_dump(mode="json"))
    assert once.model_dump(mode="json") == twice.model_dump(mode="json")


def test_normalization_preserves_survivor_order_appends_new_at_end():
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data.pop("work_reports", None)
    # Manager-chosen order: reverse the 5 known modules.
    data["layout"] = list(reversed(data["layout"]))
    cfg = StoredBoardConfigData.model_validate(data)
    ids = [i.id for i in cfg.layout]
    assert ids[:5] == ["hours", "rating", "announcements", "requests", "stats"]
    assert ids[5:] == ["workreports"]  # new module appended at the end


# ── work_reports settings: PUT that omits the key must not reset it ────


@pytest.mark.asyncio
async def test_put_omitting_work_reports_does_not_reset_it(client, seed_config, db_session):
    seeded = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    seeded["work_reports"]["limit"] = 12
    await seed_config(seeded)

    resp = await client.put("/api/v2/board-config", json=_old_client_body())
    assert resp.status_code == 200
    assert resp.json()["work_reports"]["limit"] == 12

    data = await _row_data(db_session)
    assert data["work_reports"]["limit"] == 12


# ── autopost_since stamping (server-computed, client value ignored) ────


@pytest.mark.asyncio
async def test_autopost_false_to_true_stamps_autopost_since(db_session, manager_user):
    updates = {"work_reports": {"autopost": True, "autopost_since": "2000-01-01T00:00:00+00:00",
                                 "limit": 6, "title": {"ru": "", "uz": ""}}}
    result = await merge_and_save_board_config(db_session, updates, manager_user.id)
    assert result.work_reports.autopost is True
    # Server-stamped "now", not the client-sent 2000 value.
    assert result.work_reports.autopost_since is not None
    assert result.work_reports.autopost_since.year > 2000


@pytest.mark.asyncio
async def test_autopost_staying_true_keeps_stored_since(db_session, manager_user):
    first = await merge_and_save_board_config(
        db_session,
        {"work_reports": {"autopost": True, "autopost_since": None, "limit": 6,
                           "title": {"ru": "", "uz": ""}}},
        manager_user.id,
    )
    stamped_since = first.work_reports.autopost_since
    assert stamped_since is not None

    second = await merge_and_save_board_config(
        db_session,
        {"work_reports": {"autopost": True, "autopost_since": "1999-01-01T00:00:00+00:00",
                           "limit": 9, "title": {"ru": "", "uz": ""}}},
        manager_user.id,
    )
    assert second.work_reports.autopost is True
    assert second.work_reports.autopost_since == stamped_since
    assert second.work_reports.limit == 9  # other fields in the block still update


@pytest.mark.asyncio
async def test_autopost_false_clears_since(db_session, manager_user):
    await merge_and_save_board_config(
        db_session,
        {"work_reports": {"autopost": True, "autopost_since": None, "limit": 6,
                           "title": {"ru": "", "uz": ""}}},
        manager_user.id,
    )
    result = await merge_and_save_board_config(
        db_session,
        {"work_reports": {"autopost": False, "autopost_since": "1999-01-01T00:00:00+00:00",
                           "limit": 6, "title": {"ru": "", "uz": ""}}},
        manager_user.id,
    )
    assert result.work_reports.autopost is False
    assert result.work_reports.autopost_since is None


# ── Sequential merge calls read current state, don't clobber each other ──


@pytest.mark.asyncio
async def test_sequential_merge_calls_read_current_stored_state(db_session, manager_user):
    org_update = copy.deepcopy(DEFAULT_BOARD_CONFIG["org"])
    org_update["name"] = {"ru": "Новое имя УК", "uz": "Yangi nom"}
    first = await merge_and_save_board_config(db_session, {"org": org_update}, manager_user.id)
    assert first.org.name.ru == "Новое имя УК"

    reordered = list(reversed(copy.deepcopy(DEFAULT_BOARD_CONFIG["layout"])))
    second = await merge_and_save_board_config(db_session, {"layout": reordered}, manager_user.id)

    # Layout change from call 2 applied...
    assert [i.id for i in second.layout][:5] == ["hours", "rating", "announcements", "requests", "stats"]
    # ...and the org change from call 1 was NOT clobbered (proves call 2 read
    # the current stored state, not some stale/cached copy).
    assert second.org.name.ru == "Новое имя УК"
