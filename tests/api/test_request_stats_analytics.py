"""Аналитика заявок: обзор периода, исполнители, CSV (фазы 1–2 плана аналитики).

Харнес — sqlite (naive-UTC в колонках, канон трактует naive как UTC); граница
бизнес-суток Ташкента (+05) — 19:00 UTC.
"""
import csv
import io
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from uk_management_bot.api.dependencies import get_current_user, get_db
from uk_management_bot.api.main import app
from uk_management_bot.database.models.material import Material, MaterialIssue
from uk_management_bot.database.models.rating import Rating
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User

STATS = "/api/v2/requests/stats"


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def people(db_session):
    def mk(tid, roles, first, last):
        return User(telegram_id=tid, roles=json.dumps(roles), active_role=roles[0],
                    status="approved", language="ru", first_name=first, last_name=last)

    applicant = mk(810001, ["applicant"], "Житель", "Один")
    alice = mk(810002, ["executor"], "Алиса", "Сантехник")
    bob = mk(810003, ["executor"], "Борис", "Электрик")
    db_session.add_all([applicant, alice, bob])
    await db_session.commit()
    return {"applicant": applicant, "alice": alice, "bob": bob}


async def add_request(db, people, number, *, status="Принято", executor=None, created,
                      assigned=None, executed=None, completed=None, urgency="medium",
                      category="plumbing", returned_at=None, manager_return_reason=None,
                      is_returned=False, report=None, rating=None, review=None,
                      media=None, source="bot"):
    db.add(Request(
        request_number=number, user_id=people["applicant"].id, category=category,
        status=status, description="d", urgency=urgency, address="ул. Тестовая, 1",
        is_returned=is_returned, manager_confirmed=False, source=source,
        executor_id=people[executor].id if executor else None,
        created_at=created, assigned_at=assigned, executed_at=executed,
        completed_at=completed, returned_at=returned_at,
        manager_return_reason=manager_return_reason, completion_report=report,
        completion_media=media or [],
    ))
    if rating is not None:
        await db.flush()
        db.add(Rating(request_number=number, user_id=people["applicant"].id,
                      rating=rating, review=review))
    await db.commit()


@pytest_asyncio.fixture
async def seeded(db_session, people):
    """Октябрь 2026: Алиса — 2 принятых (одна с возвратом жителя, одна просрочена),
    Борис — 1 принятая (возврат менеджером), 1 сдана, но не принята; сентябрь — база."""
    db = db_session
    # Алиса: создана 01.10 10:00 Ташкента, сдана через 3 ч — в нормативе medium 72 ч
    await add_request(db, people, "261001-001", executor="alice",
                      created=utc(2026, 10, 1, 5), assigned=utc(2026, 10, 1, 6),
                      executed=utc(2026, 10, 1, 9), completed=utc(2026, 10, 2, 5),
                      rating=5, review="=HYPERLINK(\"x\")", report="=cmd|' /C calc'!A0",
                      media=[{"media_id": 1}], returned_at=utc(2026, 10, 1, 12),
                      is_returned=False)
    # Алиса: high (24 ч), сдана через 30 ч — просрочка; принята 31.10 в 20:00 UTC
    # = 01:00 01.11 по Ташкенту → в октябрь НЕ входит
    await add_request(db, people, "261002-001", executor="alice", urgency="high",
                      created=utc(2026, 10, 2, 5), assigned=utc(2026, 10, 2, 5),
                      executed=utc(2026, 10, 3, 11), completed=utc(2026, 10, 31, 20),
                      rating=3)
    await add_request(db, people, "261003-001", executor="alice", urgency="high",
                      created=utc(2026, 10, 3, 5), assigned=utc(2026, 10, 3, 5),
                      executed=utc(2026, 10, 4, 11), completed=utc(2026, 10, 30, 10))
    # Борис: возврат менеджером, принята
    await add_request(db, people, "261005-001", executor="bob", category="Электрика",
                      created=utc(2026, 10, 5, 5), assigned=utc(2026, 10, 5, 6),
                      executed=utc(2026, 10, 5, 8), completed=utc(2026, 10, 6, 5),
                      manager_return_reason="грязно")
    # Борис: сдана в октябре, ждёт приёмки → «выполнено», не «принято»
    await add_request(db, people, "261010-001", status="Выполнена", executor="bob",
                      created=utc(2026, 10, 10, 5), assigned=utc(2026, 10, 10, 6),
                      executed=utc(2026, 10, 10, 8))
    # Борис: сейчас в работе
    await add_request(db, people, "261011-001", status="В работе", executor="bob",
                      created=utc(2026, 10, 11, 5), assigned=utc(2026, 10, 11, 6))
    # Отменённая и новая — не «принято»
    await add_request(db, people, "261012-001", status="Отменена",
                      created=utc(2026, 10, 12, 5))
    await add_request(db, people, "261012-002", status="Новая",
                      created=utc(2026, 10, 12, 20))  # 01:00 13.10 Ташкента
    # Сентябрь: база сравнения
    await add_request(db, people, "260915-001", executor="alice",
                      created=utc(2026, 9, 15, 5), assigned=utc(2026, 9, 15, 6),
                      executed=utc(2026, 9, 15, 8), completed=utc(2026, 9, 16, 5))
    # Материалы по заявке Бориса: 150 сум
    material = Material(name="Кабель", unit="m")
    db.add(material)
    await db.flush()
    db.add(MaterialIssue(material_id=material.id, doc_type="request", qty=Decimal("3"),
                         total_cost=Decimal("150.00"), request_number="261005-001",
                         material_name="Кабель", unit="m", created_by=people["bob"].id))
    await db.commit()
    return people


def october(**extra):
    return {"date_from": "2026-10-01", "date_to": "2026-10-31", **extra}


@pytest.mark.asyncio
async def test_overview_series_kpi_and_previous(client, seeded):
    resp = await client.get(STATS, params=october())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["granularity"] == "day"
    series = {p["bucket"]: p for p in body["series"]}
    assert len(series) == 31, "пустые дни — на оси с нулями"
    assert series["2026-10-13"]["created"] == 1, "20:00 UTC 12.10 = 13.10 по Ташкенту"
    assert series["2026-10-12"]["created"] == 1
    assert series["2026-10-02"]["accepted"] == 1
    assert sum(p["accepted"] for p in body["series"]) == 3, \
        "приёмка 31.10 20:00 UTC — это уже 01.11 по Ташкенту"
    kpi = body["kpi"]
    assert kpi["created"] == 8 and kpi["accepted"] == 3
    assert kpi["avg_satisfaction"] == 5.0
    assert kpi["returned"] == 2
    assert kpi["avg_work_hours"] == round((3 + 30 + 2) / 3, 1)
    assert body["previous"]["accepted"] == 1 and body["previous"]["created"] == 1
    assert body["by_category"] == {"plumbing": 7, "electricity": 1}, "legacy RU → канон"
    assert body["open_by_status"] == {"В работе": 1, "Новая": 1}


@pytest.mark.asyncio
async def test_overview_month_and_year_granularity(client, seeded):
    body = (await client.get(STATS, params={
        "date_from": "2026-01-01", "date_to": "2026-12-31"})).json()
    assert body["granularity"] == "month"
    months = {p["bucket"]: p["accepted"] for p in body["series"]}
    assert len(months) == 12 and months["2026-10"] == 3 and months["2026-11"] == 1
    body = (await client.get(STATS, params={
        "date_from": "2026-01-01", "date_to": "2026-12-31", "granularity": "year"})).json()
    assert body["series"] == [{"bucket": "2026", "created": 9, "accepted": 5}]


@pytest.mark.parametrize("params", [
    {"date_from": "2026-10-31", "date_to": "2026-10-01"},
    {"date_from": "2019-01-01", "date_to": "2026-10-01"},
    {"date_from": "01.10.2026", "date_to": "2026-10-31"},
    {"date_to": "2026-10-31"},
])
@pytest.mark.asyncio
async def test_bad_period_is_422(client, params):
    assert (await client.get(STATS, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_executor_rows_count_executed_accepted_returns_overdue(client, seeded):
    resp = await client.get(f"{STATS}/executors", params=october())
    assert resp.status_code == 200, resp.text
    rows = {r["name"]: r for r in resp.json()}
    alice, bob = rows["Алиса Сантехник"], rows["Борис Электрик"]
    assert (alice["executed"], alice["accepted"]) == (3, 2)
    assert alice["returned"] == 1, "возврат жителя — по returned_at, не is_returned"
    assert alice["overdue"] == 1, "high: 30 ч > 24 ч"
    assert alice["avg_rating"] == 5.0 and alice["ratings_count"] == 1
    assert (bob["executed"], bob["accepted"], bob["returned"]) == (2, 1, 1)
    assert bob["in_work_now"] == 1
    assert bob["materials_cost"] == 150.0


def _parse_csv(resp) -> list[list[str]]:
    assert resp.headers["content-type"].startswith("text/csv")
    text = resp.content.decode("utf-8")
    assert text.startswith("﻿"), "BOM для Excel"
    return list(csv.reader(io.StringIO(text[1:]), delimiter=";"))


@pytest.mark.asyncio
async def test_export_only_accepted_and_escaped(client, seeded):
    resp = await client.get(f"{STATS}/export", params=october())
    assert resp.status_code == 200, resp.text
    assert "completed_requests_2026-10-01_2026-10-31.csv" in resp.headers["content-disposition"]
    header, *rows = _parse_csv(resp)
    assert [r[0] for r in rows] == ["261001-001", "261003-001", "261005-001"], \
        "только «Принято» в окне; порядок — исполнитель, затем приёмка"
    first = dict(zip(header, rows[0]))
    assert first["Исполнитель"] == "Алиса Сантехник"
    assert first["Отчёт исполнителя"].startswith("'="), "formula injection экранирована"
    assert first["Отзыв"].startswith("'=")
    assert first["Возвращали"] == "да" and first["Кто вернул"] == "Житель"
    assert first["Фото работ"] == "да"
    assert first["Часы работы"] == "3,0"
    assert first["Создана"] == "01.10.2026 10:00", "бизнес-зона Ташкента"
    bob = dict(zip(header, rows[2]))
    assert bob["Кто вернул"] == "Менеджер" and bob["Причина возврата"] == "грязно"
    alice_late = dict(zip(header, rows[1]))
    assert alice_late["Возвращали"] == "нет" and alice_late["Причина возврата"] == ""
    assert bob["Материалы, сум"] == "150,00"
    assert bob["Категория"] == "Электрика"


@pytest.mark.asyncio
async def test_export_single_executor(client, seeded):
    bob_id = seeded["bob"].id
    resp = await client.get(f"{STATS}/export", params=october(executor_id=bob_id))
    _, *rows = _parse_csv(resp)
    assert [r[0] for r in rows] == ["261005-001"]
    assert f"executor{bob_id}" in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_export_executors_summary(client, seeded):
    resp = await client.get(f"{STATS}/export/executors", params=october())
    header, *rows = _parse_csv(resp)
    assert header[0] == "Исполнитель" and len(rows) == 2
    alice = dict(zip(header, rows[0]))
    assert (alice["Выполнено"], alice["Принято"], alice["С просрочкой"]) == ("3", "2", "1")


@pytest_asyncio.fixture
async def executor_client(db_session_factory, people):
    async def override_get_db():
        async with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: people["alice"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.parametrize("path", ["", "/executors", "/export", "/export/executors"])
@pytest.mark.asyncio
async def test_non_manager_forbidden(executor_client, path):
    assert (await executor_client.get(STATS + path, params=october())).status_code == 403


# ═══ Фаза 3: сроки и качество ═══


@pytest.mark.asyncio
async def test_quality_by_urgency_returns_ratings_reviews(client, seeded):
    resp = await client.get(f"{STATS}/quality", params=october())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sla_hours"] == {"critical": 4, "high": 24, "medium": 72, "low": 168}, \
        "без строки конфига — дефолтные нормативы"
    urg = {u["urgency"]: u for u in body["by_urgency"]}
    assert (urg["medium"]["accepted"], urg["medium"]["overdue"]) == (2, 0)
    assert urg["medium"]["median_hours"] == 3.5, "4 ч и 3 ч от создания до сдачи"
    assert (urg["high"]["accepted"], urg["high"]["overdue"], urg["high"]["p90_hours"]) == (1, 1, 30.0)
    assert urg["critical"]["median_hours"] is None
    assert body["returns_by_category"] == [
        {"category": "plumbing", "accepted": 2, "returned": 1},
        {"category": "electricity", "accepted": 1, "returned": 1},
    ]
    assert body["ratings"] == {"1": 0, "2": 0, "3": 0, "4": 0, "5": 1}
    assert [r["request_number"] for r in body["recent_reviews"]] == ["261001-001"]


def test_percentile_nearest_rank():
    from uk_management_bot.services.request_analytics.quality import percentile

    assert percentile([], 0.9) is None
    assert percentile([5.0], 0.9) == 5.0
    assert percentile([float(i) for i in range(1, 11)], 0.9) == 9.0
    assert percentile([float(i) for i in range(1, 12)], 0.9) == 10.0


# ═══ Фаза 4: хвост и адреса ═══


@pytest.mark.asyncio
async def test_backlog_ages_queues_oldest(db_session, seeded):
    from uk_management_bot.services.request_analytics.operations import backlog

    data = await backlog(db_session, now=utc(2026, 10, 13, 0))
    assert data.total == 2
    assert data.by_age == {"lt1": 1, "d1_3": 1, "d3_7": 0, "d7_30": 0, "gt30": 0}
    assert [q.name for q in data.queues] in (
        ["Борис Электрик", None], [None, "Борис Электрик"])
    assert data.oldest[0].request_number == "261011-001"


@pytest.mark.asyncio
async def test_backlog_endpoint(client, seeded):
    resp = await client.get(f"{STATS}/backlog")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 2


@pytest_asyncio.fixture
async def addressed(db_session, people):
    from uk_management_bot.database.models.apartment import Apartment
    from uk_management_bot.database.models.building import Building
    from uk_management_bot.database.models.yard import Yard

    db = db_session
    yard = Yard(name="Двор А")
    db.add(yard)
    await db.flush()
    house = Building(address="ул. Садовая, 5", yard_id=yard.id)
    db.add(house)
    await db.flush()
    flat = Apartment(building_id=house.id, apartment_number="12")
    db.add(flat)
    await db.flush()

    def req(number, *, created, status="Новая", completed=None, category="plumbing",
            apartment=True, source="bot"):
        return Request(
            request_number=number, user_id=people["applicant"].id, category=category,
            status=status, description="d", urgency="low", is_returned=False,
            manager_confirmed=False, source=source, created_at=created,
            completed_at=completed, address="ул. Садовая, 5, кв. 12",
            address_type="apartment" if apartment else "building",
            apartment_id=flat.id if apartment else None,
            building_id=None if apartment else house.id,
        )

    db.add_all([
        req("261002-101", created=utc(2026, 10, 1, 5), status="Принято",
            completed=utc(2026, 10, 2, 5)),
        # повтор: та же квартира и категория через 18 дней после приёмки
        req("261020-101", created=utc(2026, 10, 20, 5), source="twa"),
        # другая категория — не повтор
        req("261021-101", created=utc(2026, 10, 21, 5), category="electricity"),
        # на дом целиком
        req("261022-101", created=utc(2026, 10, 22, 5), apartment=False),
        # через 40 дней после приёмки — не повтор
        req("261111-101", created=utc(2026, 11, 11, 5)),
    ])
    await db.commit()
    return {"yard": yard, "house": house}


@pytest.mark.asyncio
async def test_addresses_top_and_repeats(client, addressed):
    resp = await client.get(f"{STATS}/addresses", params=october())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["buildings"] == [
        {"id": addressed["house"].id, "name": "ул. Садовая, 5", "count": 4}]
    assert body["yards"] == [{"id": addressed["yard"].id, "name": "Двор А", "count": 4}]
    assert [(r["request_number"], r["previous_number"], r["days_after"])
            for r in body["repeats"]] == [("261020-101", "261002-101", 18.0)]
    november = await client.get(f"{STATS}/addresses",
                                params={"date_from": "2026-11-01", "date_to": "2026-11-30"})
    assert november.json()["repeats"] == [], "40 дней после приёмки — уже не повтор"


# ═══ Фаза 5: каналы и затраты ═══


@pytest.mark.asyncio
async def test_channels_totals_and_series(client, addressed):
    resp = await client.get(f"{STATS}/channels", params=october())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["totals"] == {"bot": 3, "twa": 1}
    point = {p["bucket"]: p["counts"] for p in body["series"]}
    assert point["2026-10-20"] == {"twa": 1} and point["2026-10-05"] == {}
    assert len(body["series"]) == 31


@pytest.mark.asyncio
async def test_costs_by_category(client, seeded):
    resp = await client.get(f"{STATS}/costs", params=october())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 150.0 and body["requests_with_materials"] == 1
    assert body["accepted"] == 3
    assert body["by_category"] == {"electricity": 150.0}


@pytest.mark.parametrize("path", ["/quality", "/backlog", "/addresses", "/channels", "/costs"])
@pytest.mark.asyncio
async def test_non_manager_forbidden_new_sections(executor_client, path):
    assert (await executor_client.get(STATS + path, params=october())).status_code == 403


def test_returned_by_both_resident_and_manager():
    from uk_management_bot.services.request_analytics.csv_export import completed_row
    from uk_management_bot.services.request_analytics.executors import AcceptedRequest

    row = AcceptedRequest(
        request_number="261001-009", executor_id=1, executor_name="Ф", category="plumbing",
        urgency="low", source="bot", address="a", created_at=utc(2026, 10, 1, 5),
        assigned_at=None, executed_at=None, completed_at=utc(2026, 10, 2, 5),
        returned_at=utc(2026, 10, 1, 9), manager_return_reason="доделать",
        return_reason="течёт", completion_report=None, has_photos=False, rating=None,
        review=None, apartment_id=None, building_id=None, yard_id=None,
    )
    cells = completed_row(row, {"low": 168}, None)
    assert "Житель и менеджер" in cells and "течёт / доделать" in cells
