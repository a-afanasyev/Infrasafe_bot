"""Tests for GET /api/v2/announcements — TWA home fed by board_config (путь Б).

The endpoint is unauthenticated and reads the editable board_config singleton,
localizing to ?lang=ru|uz. These tests pin: default fallback, saved config,
UZ localization + RU fallback, news filtering/order, contacts assembly, and the
format_working_hours grouping helper.
"""
import copy

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.board_config.defaults import DEFAULT_BOARD_CONFIG
from uk_management_bot.api.board_config.schemas import WorkingHourCfg
from uk_management_bot.api.board_config.service import format_working_hours
from uk_management_bot.database.models.board_config import BoardConfig


def _wh(day, open_="", close="", closed=False):
    return WorkingHourCfg(day=day, open=open_, close=close, closed=closed)


@pytest_asyncio.fixture
async def seed_config(db_session: AsyncSession, manager_user):
    """Insert a BoardConfig row (id=1); return the mutable data dict."""

    async def _seed(data: dict):
        db_session.add(BoardConfig(id=1, data=data, updated_by=manager_user.id))
        await db_session.commit()

    return _seed


# ── Default fallback (no row) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_default_fallback_shape(client):
    resp = await client.get("/api/v2/announcements")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"announcements", "working_hours", "emergency_phones"}
    # Default phone flows through to emergency_phones.
    assert body["emergency_phones"] == ["+998 71 123-45-67"]
    # Default working hours grouped mon-fri / sat / sun.
    assert body["working_hours"] == "Пн–Пт: 08:00–20:00\nСб: 09:00–17:00\nВс: 10:00–16:00"


@pytest.mark.asyncio
async def test_broken_row_falls_back_to_default_not_500(client, seed_config):
    # Строка есть, но data не проходит схему → 200 с дефолтом, не 500.
    await seed_config({"broken": True})
    resp = await client.get("/api/v2/announcements")
    assert resp.status_code == 200
    assert resp.json()["working_hours"] == "Пн–Пт: 08:00–20:00\nСб: 09:00–17:00\nВс: 10:00–16:00"


@pytest.mark.asyncio
async def test_default_contacts_card(client):
    body = (await client.get("/api/v2/announcements")).json()
    contact = [a for a in body["announcements"] if a["type"] == "contact"]
    assert len(contact) == 1
    assert contact[0]["title"] == "Контакты"
    assert contact[0]["body"] == "Диспетчерская: +998 71 123-45-67\nАварийная служба: круглосуточно"


@pytest.mark.asyncio
async def test_default_news_filters_empty_text(client):
    # DEFAULT has 2 announcements: planned-works (has text) and default-announcement
    # (empty text) → only the first survives; contact card is separate.
    body = (await client.get("/api/v2/announcements")).json()
    news = [a for a in body["announcements"] if a["type"] == "info"]
    assert len(news) == 1
    assert news[0]["title"] == "Плановые работы"


# ── Saved config ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_saved_config_used(client, seed_config):
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data["contacts"]["dispatch_phone"] = "+998783331971"
    data["contacts"]["dispatch_label"] = {"ru": "Диспетчерская (круглосуточно)", "uz": "Dispetcherlik"}
    await seed_config(data)

    body = (await client.get("/api/v2/announcements")).json()
    assert body["emergency_phones"] == ["+998783331971"]
    contact = [a for a in body["announcements"] if a["type"] == "contact"][0]
    assert contact["body"].startswith("Диспетчерская (круглосуточно): +998783331971")


@pytest.mark.asyncio
async def test_news_order_important_then_recent(client, seed_config):
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data["announcements"] = [
        {"id": "old", "icon": "", "important": False, "title": {"ru": "Старое", "uz": ""},
         "text": {"ru": "t", "uz": ""}, "published_at": "2026-01-01T00:00:00"},
        {"id": "new", "icon": "", "important": False, "title": {"ru": "Новое", "uz": ""},
         "text": {"ru": "t", "uz": ""}, "published_at": "2026-05-01T00:00:00"},
        {"id": "imp", "icon": "", "important": True, "title": {"ru": "Важное", "uz": ""},
         "text": {"ru": "t", "uz": ""}, "published_at": "2020-01-01T00:00:00"},
    ]
    await seed_config(data)

    news = [a for a in (await client.get("/api/v2/announcements")).json()["announcements"]
            if a["type"] == "info"]
    assert [n["title"] for n in news] == ["Важное", "Новое", "Старое"]


# ── Localization ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_uz_localization(client, seed_config):
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    await seed_config(data)
    body = (await client.get("/api/v2/announcements", params={"lang": "uz"})).json()
    news = [a for a in body["announcements"] if a["type"] == "info"][0]
    assert news["title"] == "Rejalashtirilgan ishlar"
    assert body["working_hours"].startswith("Du–Ju:")
    contact = [a for a in body["announcements"] if a["type"] == "contact"][0]
    assert contact["title"] == "Aloqa"


@pytest.mark.asyncio
async def test_uz_falls_back_to_ru_when_empty(client, seed_config):
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data["announcements"] = [
        {"id": "x", "icon": "", "important": False, "title": {"ru": "Только RU", "uz": ""},
         "text": {"ru": "Текст RU", "uz": "   "}, "published_at": "2026-05-01T00:00:00"},
    ]
    await seed_config(data)
    news = [a for a in (await client.get("/api/v2/announcements", params={"lang": "uz"})).json()["announcements"]
            if a["type"] == "info"]
    assert len(news) == 1
    assert news[0]["title"] == "Только RU"
    assert news[0]["body"] == "Текст RU"


# ── Contacts edge cases ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_dispatch_label_falls_back(client, seed_config):
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data["contacts"]["dispatch_label"] = {"ru": "", "uz": ""}
    await seed_config(data)
    contact = [a for a in (await client.get("/api/v2/announcements")).json()["announcements"]
               if a["type"] == "contact"][0]
    assert contact["body"].startswith("Диспетчерская: +998 71 123-45-67")


@pytest.mark.asyncio
async def test_no_phone_no_emergency_drops_contact_card(client, seed_config):
    data = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    data["contacts"] = {"dispatch_phone": "", "dispatch_label": {"ru": "Д", "uz": ""},
                        "emergency": {"ru": "  ", "uz": ""}}
    await seed_config(data)
    body = (await client.get("/api/v2/announcements")).json()
    assert not [a for a in body["announcements"] if a["type"] == "contact"]
    assert body["emergency_phones"] == []


# ── format_working_hours unit ───────────────────────────────────────

def test_format_working_hours_arbitrary_order_and_grouping():
    hours = [
        _wh("sun", closed=True),
        _wh("mon", "08:00", "20:00"),
        _wh("wed", "08:00", "20:00"),
        _wh("tue", "08:00", "20:00"),
        _wh("fri", "08:00", "20:00"),
        _wh("thu", "08:00", "20:00"),
        _wh("sat", "09:00", "17:00"),
    ]
    assert format_working_hours(hours, "ru") == (
        "Пн–Пт: 08:00–20:00\nСб: 09:00–17:00\nВс: Выходной"
    )


def test_format_working_hours_incomplete_is_dash_not_closed():
    hours = [_wh(d, "08:00", "20:00") for d in ("mon", "tue", "wed", "thu", "fri")]
    hours.append(_wh("sat", open_="09:00", close=""))  # incomplete (close пустой) → «—»
    hours.append(_wh("sun", closed=True))               # closed → «Выходной»
    out = format_working_hours(hours, "ru")
    assert "Сб: —" in out
    assert "Вс: Выходной" in out


def test_format_working_hours_open_empty_close_set_is_dash():
    # Симметричный неполный случай: open пустой, close заполнен → «—».
    hours = [_wh(d, "08:00", "20:00") for d in ("mon", "tue", "wed", "thu", "fri", "sun")]
    hours.append(_wh("sat", open_="", close="18:00"))
    assert "Сб: —" in format_working_hours(hours, "ru")


def test_format_working_hours_closed_wins_over_filled_time():
    # closed=True перекрывает заполненное время → «Выходной», не «HH:MM–HH:MM».
    hours = [_wh(d, "08:00", "20:00") for d in ("mon", "tue", "wed", "thu", "fri", "sat")]
    hours.append(_wh("sun", open_="10:00", close="14:00", closed=True))
    out = format_working_hours(hours, "ru")
    assert "Вс: Выходной" in out
    assert "10:00" not in out


def test_format_working_hours_uz_labels():
    hours = [_wh(d, "08:00", "20:00") for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")]
    assert format_working_hours(hours, "uz") == "Du–Ya: 08:00–20:00"
