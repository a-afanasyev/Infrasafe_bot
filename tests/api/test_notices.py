"""Раздел «Новости и уведомления»: API ``/api/v2/board-config/notices`` и витрина из таблицы.

Жители получают прежние списки ``announcements`` / ``planned_works``, но
собранные из ``notices`` (services/notices/board.py), а не из JSON витрины.
"""
import copy
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.database.models.board_config import BoardConfig
from uk_management_bot.database.models.notice import Notice
from uk_management_bot.services.board_config.defaults import DEFAULT_BOARD_CONFIG
from uk_management_bot.services.notices import board
from uk_management_bot.utils.business_time import BUSINESS_TZ

BASE = "/api/v2/board-config/notices"
NOW = datetime.now(timezone.utc)


def _iso(delta: timedelta) -> str:
    return (NOW + delta).isoformat()


def _news(**over) -> dict:
    return {"kind": "news", "title_ru": "Собрание жильцов", "title_uz": "Yig'ilish",
            "text_ru": "В 19:00 во дворе", "text_uz": "Soat 19:00 da", **over}


async def _board(client) -> dict:
    resp = await client.get("/api/v2/public/board-config")
    assert resp.status_code == 200, resp.text
    return resp.json()


# ───────────── жизненный цикл и видимость на витрине ─────────────


@pytest.mark.asyncio
async def test_draft_is_hidden_until_published(client):
    created = await client.post(BASE, json=_news())
    assert created.status_code == 201, created.text
    notice = created.json()
    assert (notice["status"], notice["state"], notice["source"]) == ("draft", "draft", "manual")
    assert (await _board(client))["announcements"] == []

    published = await client.post(f"{BASE}/{notice['id']}/publish")
    assert published.status_code == 200 and published.json()["state"] == "active"
    [ann] = (await _board(client))["announcements"]
    assert ann["id"] == f"notice-{notice['id']}"
    assert ann["title"] == {"ru": "Собрание жильцов", "uz": "Yig'ilish"}
    assert ann["text"] == {"ru": "В 19:00 во дворе", "uz": "Soat 19:00 da"}

    # главная TWA читает тот же список
    twa = (await client.get("/api/v2/announcements")).json()["announcements"]
    assert [a["title"] for a in twa if a["type"] == "info"] == ["Собрание жильцов"]


@pytest.mark.asyncio
async def test_scheduled_expired_and_closed_are_not_on_board(client):
    scheduled = (await client.post(BASE, json=_news(title_ru="Позже", publish=True, publish_at=_iso(timedelta(days=2))))).json()
    expired = (await client.post(BASE, json=_news(title_ru="Истекла", publish=True, expires_at=_iso(timedelta(hours=-1))))).json()
    live = (await client.post(BASE, json=_news(title_ru="Идёт", publish=True))).json()
    closed = (await client.post(BASE, json=_news(title_ru="Снята", publish=True))).json()
    assert (await client.post(f"{BASE}/{closed['id']}/close")).json()["state"] == "closed"

    assert (scheduled["state"], expired["state"], live["state"]) == ("scheduled", "expired", "active")
    titles = [a["title"]["ru"] for a in (await _board(client))["announcements"]]
    assert titles == ["Идёт"]


@pytest.mark.asyncio
async def test_planned_outage_goes_to_planned_works_not_news(client):
    day = (NOW + timedelta(days=3)).astimezone(BUSINESS_TZ).replace(hour=10, minute=0, second=0, microsecond=0)
    body = {"kind": "outage", "resource": "power", "title_ru": "Отключение электричества",
            "place_ru": "Двор Северный", "starts_at": day.isoformat(),
            "ends_at": (day + timedelta(hours=4)).isoformat(), "publish": True}
    created = await client.post(BASE, json=body)
    assert created.status_code == 201, created.text

    data = await _board(client)
    assert data["announcements"] == []
    [work] = data["planned_works"]
    assert (work["date"], work["time_from"], work["time_to"]) == (day.date().isoformat(), "10:00", "14:00")
    assert work["title"]["ru"] == "Отключение электричества" and work["place"]["ru"] == "Двор Северный"


@pytest.mark.asyncio
async def test_finished_outage_leaves_planned_works(client, db_session):
    db_session.add(Notice(kind="outage", resource="water", source="manual", title_ru="Было", status="published",
                          publish_at=NOW - timedelta(days=5), starts_at=NOW - timedelta(days=3),
                          ends_at=NOW - timedelta(days=2)))
    await db_session.commit()
    assert (await _board(client))["planned_works"] == []


@pytest.mark.asyncio
async def test_channel_outage_is_shown_in_news_as_important(client, db_session):
    """Отключение из канала/от сотрудника срочное — видно и в новостях."""
    db_session.add(Notice(kind="outage", resource="water", source="news_watch", title_ru="Отключение воды",
                          text_ru="нет воды", status="published", publish_at=NOW - timedelta(minutes=5)))
    await db_session.commit()
    [ann] = (await _board(client))["announcements"]
    assert ann["important"] is True and ann["icon"] == board.RESOURCE_ICONS["water"]


# ───────────── редактор витрины больше не пишет новости в JSON ─────────────


@pytest.mark.asyncio
async def test_board_editor_put_does_not_store_news_or_works(client, db_session):
    await client.post(BASE, json=_news(publish=True))
    body = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    body["announcements"] = [{"id": "stale", "icon": "", "important": False, "published_at": "",
                              "title": {"ru": "Из старой вкладки", "uz": ""}, "text": {"ru": "x", "uz": ""}}]
    body["planned_works"] = [{"id": "pw", "date": "2099-01-01", "title": {"ru": "Старое", "uz": ""}}]
    resp = await client.put("/api/v2/board-config", json=body)
    assert resp.status_code == 200, resp.text
    # ответ и витрина — из notices, тело старого клиента проигнорировано
    assert [a["title"]["ru"] for a in resp.json()["announcements"]] == ["Собрание жильцов"]
    assert resp.json()["planned_works"] == []

    stored = (await db_session.execute(select(BoardConfig))).scalar_one().data
    assert "Из старой вкладки" not in str(stored) and "Старое" not in str(stored)


# ───────────── правка, удаление, лента ─────────────


@pytest.mark.asyncio
async def test_patch_updates_and_clears_fields(client):
    notice = (await client.post(BASE, json=_news(publish=True, expires_at=_iso(timedelta(days=1))))).json()
    patched = await client.patch(f"{BASE}/{notice['id']}", json={"title_ru": "Перенос собрания", "expires_at": None})
    assert patched.status_code == 200, patched.text
    assert patched.json()["title_ru"] == "Перенос собрания" and patched.json()["expires_at"] is None
    assert patched.json()["title_uz"] == "Yig'ilish"  # не присланное поле не тронуто

    assert (await client.patch(f"{BASE}/{notice['id']}", json={"title_ru": None})).status_code == 422
    assert (await client.patch(f"{BASE}/999", json={"title_ru": "x"})).status_code == 404

    await client.post(f"{BASE}/{notice['id']}/close")
    assert (await client.patch(f"{BASE}/{notice['id']}", json={"title_ru": "x"})).status_code == 409


@pytest.mark.asyncio
async def test_only_draft_can_be_deleted(client):
    draft = (await client.post(BASE, json=_news())).json()
    live = (await client.post(BASE, json=_news(publish=True))).json()
    assert (await client.delete(f"{BASE}/{live['id']}")).status_code == 409
    assert (await client.delete(f"{BASE}/{draft['id']}")).status_code == 204
    listed = (await client.get(BASE)).json()
    assert listed["total"] == 1 and [n["id"] for n in listed["items"]] == [live["id"]]


@pytest.mark.asyncio
async def test_list_filters_by_kind_status_and_calendar_window(client):
    await client.post(BASE, json=_news(title_ru="Черновик"))
    await client.post(BASE, json=_news(title_ru="Сегодня", publish=True))
    start = NOW + timedelta(days=20)
    await client.post(BASE, json={"kind": "outage", "resource": "water", "title_ru": "Через 20 дней",
                                  "starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=2)).isoformat(),
                                  "publish": True})

    assert (await client.get(BASE, params={"kind": "outage"})).json()["total"] == 1
    assert (await client.get(BASE, params={"status": "draft"})).json()["total"] == 1
    window = {"from": (NOW + timedelta(days=15)).isoformat(), "to": (NOW + timedelta(days=25)).isoformat()}
    in_window = (await client.get(BASE, params=window)).json()["items"]
    assert [n["title_ru"] for n in in_window] == ["Через 20 дней"]
    assert (await client.get(BASE, params={"kind": "nope"})).status_code == 422


# ───────────── валидация и права ─────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"kind": "news"},  # без заголовка
    {"kind": "outage", "title_ru": "x", "starts_at": "2099-01-01T10:00:00+05:00"},  # без ресурса
    {"kind": "outage", "title_ru": "x", "resource": "water"},  # без окна
    {"kind": "outage", "title_ru": "x", "resource": "steam", "starts_at": "2099-01-01T10:00:00+05:00"},
    {"kind": "news", "title_ru": "x", "publish_at": "2099-01-01T10:00:00"},  # время без зоны
    {"kind": "news", "title_ru": "x", "starts_at": "2099-01-02T10:00:00+05:00", "ends_at": "2099-01-01T10:00:00+05:00"},
    {"kind": "news", "title_ru": "x", "status": "published"},  # служебное поле
    {"kind": "news", "title_ru": "x" * 201},
])
async def test_create_rejects_invalid_body(client, body):
    assert (await client.post(BASE, json=body)).status_code == 422


@pytest.mark.asyncio
async def test_resident_cannot_manage_notices(client, resident_user):
    app.dependency_overrides[get_current_user] = lambda: resident_user
    assert (await client.get(BASE)).status_code == 403
    assert (await client.post(BASE, json=_news())).status_code == 403


# ───────────── замечания ревью 2026-11-15 ─────────────


def _outage(**over) -> dict:
    start = NOW + timedelta(hours=-1)
    return {"kind": "outage", "resource": "water", "title_ru": "Нет воды", "publish": True,
            "starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=2)).isoformat(), **over}


@pytest.mark.asyncio
async def test_extending_outage_extends_its_show_window(client, db_session):
    """Без своего срока показа запись живёт до конца окна — и продлевается вместе с ним."""
    db_session.add(Notice(kind="outage", resource="water", source="news_watch", title_ru="Нет воды", status="published",
                          publish_at=NOW - timedelta(hours=3), starts_at=NOW - timedelta(hours=3),
                          ends_at=NOW - timedelta(minutes=5)))
    await db_session.commit()
    notice = (await client.get(BASE)).json()["items"][0]
    assert notice["state"] == "expired" and (await _board(client))["announcements"] == []

    patched = await client.patch(f"{BASE}/{notice['id']}", json={"ends_at": _iso(timedelta(hours=2))})
    assert patched.status_code == 200 and patched.json()["state"] == "active"
    assert [a["title"]["ru"] for a in (await _board(client))["announcements"]] == ["Нет воды"]


@pytest.mark.asyncio
async def test_patch_is_validated_against_stored_values(client):
    notice = (await client.post(BASE, json=_outage())).json()
    nid = notice["id"]
    # окончание раньше сохранённого начала
    assert (await client.patch(f"{BASE}/{nid}", json={"ends_at": _iso(timedelta(days=-2))})).status_code == 422
    # отключение без начала / без ресурса
    assert (await client.patch(f"{BASE}/{nid}", json={"starts_at": None})).status_code == 422
    assert (await client.patch(f"{BASE}/{nid}", json={"resource": None})).status_code == 422
    # опубликованная запись без заголовка
    assert (await client.patch(f"{BASE}/{nid}", json={"title_ru": "  "})).status_code == 422
    # отклонённая правка ничего не изменила
    assert (await client.get(BASE)).json()["items"][0] == notice

    news = (await client.post(BASE, json=_news(publish=True))).json()
    assert (await client.patch(f"{BASE}/{news['id']}", json={"kind": "outage"})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("title_ru", "Собрание\x00"), ("title_ru", "Собрание\nв 19:00"), ("text_ru", "x\x07"),
    ("icon", "‮"), ("place_ru", "двор​"),
])
async def test_control_and_invisible_characters_are_rejected(client, field, value):
    assert (await client.post(BASE, json=_news(**{field: value}))).status_code == 422


@pytest.mark.asyncio
async def test_multiline_text_and_compound_emoji_are_accepted(client):
    resp = await client.post(BASE, json=_news(text_ru="Первая строка\nВторая строка", icon="👨‍🔧"))
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_overnight_outage_is_clamped_to_the_shown_day(client, db_session):
    """Началось вчера, закончится завтра — на сегодняшней строке весь день, а не одинокое время."""
    db_session.add(Notice(kind="outage", resource="heating", source="manual", title_ru="Отопление", status="published",
                          publish_at=NOW - timedelta(days=2), starts_at=NOW - timedelta(days=1),
                          ends_at=NOW + timedelta(days=1)))
    await db_session.commit()
    [work] = (await _board(client))["planned_works"]
    assert (work["time_from"], work["time_to"]) == ("00:00", "23:59")


@pytest.mark.asyncio
async def test_public_feed_is_capped(client, db_session):
    for i in range(board.MAX_ANNOUNCEMENTS + 5):
        db_session.add(Notice(kind="news", source="manual", title_ru=f"Новость {i}", text_ru="t", status="published",
                              publish_at=NOW - timedelta(minutes=i)))
    await db_session.commit()
    announcements = (await _board(client))["announcements"]
    assert len(announcements) == board.MAX_ANNOUNCEMENTS
    assert announcements[0]["title"]["ru"] == "Новость 0"  # свежие остаются


# ───────────── этап 2: рассылка и адресаты ─────────────


@pytest.mark.asyncio
async def test_broadcast_flag_and_audience_endpoints(client, db_session):
    from uk_management_bot.database.models.building import Building
    from uk_management_bot.database.models.yard import Yard

    db_session.add(Yard(id=1, name="Северный"))
    db_session.add(Building(id=12, address="Садовая, 14", yard_id=1))
    await db_session.commit()

    created = await client.post(BASE, json=_news(publish=True, broadcast=True, scope="buildings", scope_ids=[12]))
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["broadcast_status"], body["scope"], body["scope_ids"]) == ("pending", "buildings", [12])

    # отмена ещё не начатой рассылки; повторять нечего
    off = await client.patch(f"{BASE}/{body['id']}", json={"broadcast": False})
    assert off.json()["broadcast_status"] == "none"
    assert (await client.post(f"{BASE}/{body['id']}/retry-broadcast")).status_code == 409

    # адресаты: неизвестный дом и пустой выбор отклоняются
    assert (await client.post(BASE, json=_news(scope="buildings", scope_ids=[999]))).status_code == 422
    assert (await client.post(BASE, json=_news(scope="yards"))).status_code == 422

    count = await client.get(f"{BASE}/audience", params={"scope": "buildings", "ids": [12]})
    assert count.status_code == 200 and count.json() == {"count": 0}
    assert (await client.get(f"{BASE}/audience", params={"scope": "buildings", "ids": [999]})).status_code == 422
    assert (await client.get(f"{BASE}/audience")).json() == {"count": 0}
