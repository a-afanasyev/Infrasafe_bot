"""Публичный виджет статусов лифтов (T16, Р16): GET /api/v2/public/elevators.

Анонимный эндпоинт — впервые данные лифтов покидают авторизованный периметр,
поэтому проверяется буквально: обе «тихие» калитки (флаг и ``module_public``)
дают 200 с пустым ответом, а в JSON нет ни одного запрещённого ключа
(``public_code``, паспорт, договор, заявки, люди).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import uk_management_bot.api.elevators.public_router as public_router
from uk_management_bot.api.board_config.defaults import DEFAULT_BOARD_CONFIG
from uk_management_bot.api.dependencies import get_db
from uk_management_bot.api.main import app
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.board_config import BoardConfig
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.elevator import (
    Elevator,
    ElevatorMaintenanceOccurrence,
    ElevatorStatusEvent,
)
from uk_management_bot.database.models.elevators_config import ElevatorsConfig
from uk_management_bot.database.models.yard import Yard

URL = "/api/v2/public/elevators"
NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
D = timedelta(days=1)

# Ключи, которых не должно быть НИГДЕ в публичном JSON.
FORBIDDEN_ANYWHERE = {
    "public_code", "passport_number", "serial_number", "factory_number",
    "contract_number", "contract_until", "cert_number", "cert_act_url",
    "request_number", "open_requests_count", "requests", "executor_id",
    "user_id", "actor_user_id", "created_by_user_id", "done_by_user_id",
    "first_name", "last_name", "telegram_id", "flags", "no_contract",
    "description", "reason", "comment", "archived_reason", "version",
}
# Полный набор ключей одного лифта — «id» отсутствует намеренно.
ELEVATOR_KEYS = {
    "entrance_number", "elevator_number", "label", "status", "status_since",
    "availability_30d", "last_maintenance_on", "cert_valid_until", "cert_expired",
    "service_org_name", "service_org_phone", "manufacturer", "model",
    "production_year", "capacity_kg", "downtime_reason", "spare_part_expected_on",
}


def _elevator(id: int, building_id: int, entrance: int, number: int, **extra) -> Elevator:
    fields = dict(
        id=id, building_id=building_id, entrance_number=entrance, elevator_number=number,
        passport_number=f"P-{id}", manufacturer="OTIS", serial_number=f"S-{id}",
        factory_number=f"F-{id}", model="Gen2", production_year=2015, capacity_kg=630,
        public_code=f"code-{id}-xxxxxxxxxxxx", is_public=True, is_commissioned=True,
        commissioned_at=date(2026, 1, 1), current_status="working", status_since=NOW - 3 * D,
        contract_number=f"C-{id}", contract_until=date(2099, 1, 1),
        cert_number=f"CERT-{id}", cert_valid_until=date(2099, 1, 1),
        cert_act_url="https://example.org/act.pdf",
        service_org_name="ЛифтСервис", service_org_phone="+998 71 000-00-00",
    )
    fields.update(extra)
    return Elevator(**fields)


@pytest.fixture(autouse=True)
def _reset_public_elevators_cache():
    public_router._public_elevators_cache.clear()
    yield
    public_router._public_elevators_cache.clear()


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)


@pytest_asyncio.fixture
async def anon_client(db_session_factory):
    """Честно анонимный клиент: подменён только get_db, НЕ get_current_user."""

    async def override_get_db():
        async with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    """Два двора, три дома; лифты: публичные 1,2 (дом 1), 3 (дом 2, простой с деталями),
    4 (двор 2, простой без деталей); 5 не публичный, 6 архивный, 7 не введён."""
    db_session.add_all([
        Yard(id=1, name="Бета", is_active=True),
        Yard(id=2, name="Альфа", is_active=True),
        Building(id=1, yard_id=1, address="ул. Мира, д. 5", entrance_count=4, floor_count=9, is_active=True),
        Building(id=2, yard_id=1, address="ул. Мира, д. 3", entrance_count=2, floor_count=9, is_active=True),
        Building(id=3, yard_id=2, address="ул. Садовая, д. 1", entrance_count=2, floor_count=9, is_active=True),
        ElevatorsConfig(id=1, data={"module_public": True}),
    ])
    await db_session.flush()
    db_session.add_all([
        _elevator(1, 1, entrance=2, number=1),
        _elevator(2, 1, entrance=1, number=1, cert_valid_until=date(2020, 1, 1)),
        _elevator(3, 2, entrance=1, number=1, current_status="under_repair",
                  status_since=NOW - 2 * D, downtime_reason="Ждём лебёдку",
                  spare_part_expected_on=date(2026, 9, 20), publish_downtime_details=True),
        _elevator(4, 3, entrance=1, number=1, current_status="not_working",
                  downtime_reason="Секрет", spare_part_expected_on=date(2026, 9, 20),
                  publish_downtime_details=False),
        _elevator(5, 1, entrance=3, number=1, is_public=False),
        _elevator(6, 1, entrance=4, number=1, archived_at=NOW),
        _elevator(7, 2, entrance=2, number=1, is_commissioned=False, current_status=None,
                  status_since=None, commissioned_at=None),
    ])
    db_session.add_all([
        # Просроченное ТО: due 01.08, закрыто 20.08 — наружу идёт дата закрытия.
        ElevatorMaintenanceOccurrence(elevator_id=1, kind="maintenance", due_on=date(2026, 8, 1),
                                      state="done",
                                      done_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)),
        ElevatorMaintenanceOccurrence(elevator_id=1, kind="maintenance", due_on=date(2026, 7, 1),
                                      state="done", done_at=None),
        ElevatorMaintenanceOccurrence(elevator_id=1, kind="maintenance", due_on=date(2026, 10, 1),
                                      state="planned"),
        ElevatorMaintenanceOccurrence(elevator_id=1, kind="certification", due_on=date(2026, 8, 15),
                                      state="done", done_at=NOW - 20 * D),
        ElevatorStatusEvent(elevator_id=1, event_kind="status_changed", old_status=None,
                            new_status="working", occurred_at=NOW - 40 * D, source="manual"),
    ])
    await db_session.commit()


def _walk_keys(node) -> set[str]:
    keys: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(key)
            keys |= _walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            keys |= _walk_keys(item)
    return keys


def _all_elevators(body: dict) -> list[dict]:
    return [e for yard in body["yards"] for b in yard["buildings"] for e in b["elevators"]]


# ── Калитки ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_flag_off_gives_empty_200_not_404(anon_client, seeded, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    resp = await anon_client.get(URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["yards"] == []
    assert body["dispatch_phone"] is None
    assert body["generated_at"]


@pytest.mark.asyncio
async def test_module_public_off_gives_empty_200(anon_client, seeded, enabled, db_session):
    row = await db_session.get(ElevatorsConfig, 1)
    row.data = {"module_public": False}
    await db_session.commit()
    resp = await anon_client.get(URL)
    assert resp.status_code == 200
    assert resp.json()["yards"] == []


@pytest.mark.asyncio
async def test_no_config_row_means_module_not_public(anon_client, enabled, db_session):
    db_session.add_all([
        Yard(id=1, name="Двор", is_active=True),
        Building(id=1, yard_id=1, address="д. 1", entrance_count=1, floor_count=9, is_active=True),
    ])
    await db_session.flush()
    db_session.add(_elevator(1, 1, entrance=1, number=1))
    await db_session.commit()
    assert (await anon_client.get(URL)).json()["yards"] == []


# ── Состав ответа ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_anonymous_gets_only_public_commissioned_active_grouped_and_sorted(
    anon_client, seeded, enabled
):
    resp = await anon_client.get(URL)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Дворы по имени, дома по адресу, лифты по подъезду → номеру.
    assert [y["name"] for y in body["yards"]] == ["Альфа", "Бета"]
    beta = body["yards"][1]
    assert [b["address"] for b in beta["buildings"]] == ["ул. Мира, д. 3", "ул. Мира, д. 5"]
    house5 = beta["buildings"][1]["elevators"]
    assert [(e["entrance_number"], e["elevator_number"]) for e in house5] == [(1, 1), (2, 1)]
    # 5 (не публичный), 6 (архив), 7 (не введён) — отсутствуют
    assert len(_all_elevators(body)) == 4
    # Строки board_config нет → null (канон бота get_dispatch_phone), не плейсхолдер дефолта.
    assert body["dispatch_phone"] is None


@pytest.mark.asyncio
async def test_response_never_contains_forbidden_keys(anon_client, seeded, enabled):
    body = (await anon_client.get(URL)).json()
    assert _walk_keys(body) & FORBIDDEN_ANYWHERE == set()
    for elevator in _all_elevators(body):
        assert set(elevator.keys()) == ELEVATOR_KEYS
    text = (await anon_client.get(URL)).text
    assert "code-" not in text and "P-1" not in text and "CERT-" not in text


@pytest.mark.asyncio
async def test_elevator_fields(anon_client, seeded, enabled):
    body = (await anon_client.get(URL)).json()
    by_label = {e["label"]: e for e in _all_elevators(body)}
    e1 = by_label["ул. Мира, д. 5, подъезд 2, лифт 1"]
    assert e1["status"] == "working"
    assert e1["status_since"].startswith("2026-09-03T12:00:00")
    # Дата закрытия последнего done-ТО (не due_on, не planned, не освидетельствование).
    assert e1["last_maintenance_on"] == "2026-08-20"
    assert e1["cert_valid_until"] == "2099-01-01" and e1["cert_expired"] is False
    assert e1["service_org_name"] == "ЛифтСервис"
    assert e1["service_org_phone"] == "+998 71 000-00-00"
    assert (e1["manufacturer"], e1["model"], e1["production_year"], e1["capacity_kg"]) == (
        "OTIS", "Gen2", 2015, 630)
    assert e1["availability_30d"] == 1.0
    assert e1["downtime_reason"] is None and e1["spare_part_expected_on"] is None

    e2 = by_label["ул. Мира, д. 5, подъезд 1, лифт 1"]
    assert e2["cert_expired"] is True and e2["last_maintenance_on"] is None


@pytest.mark.asyncio
async def test_downtime_details_only_when_published(anon_client, seeded, enabled):
    body = (await anon_client.get(URL)).json()
    by_label = {e["label"]: e for e in _all_elevators(body)}
    shown = by_label["ул. Мира, д. 3, подъезд 1, лифт 1"]
    assert shown["status"] == "under_repair"
    assert shown["downtime_reason"] == "Ждём лебёдку"
    assert shown["spare_part_expected_on"] == "2026-09-20"
    hidden = by_label["ул. Садовая, д. 1, подъезд 1, лифт 1"]
    assert hidden["status"] == "not_working"
    assert hidden["downtime_reason"] is None and hidden["spare_part_expected_on"] is None
    assert "Секрет" not in (await anon_client.get(URL)).text


@pytest.mark.asyncio
async def test_lang_uz_localizes_label(anon_client, seeded, enabled):
    body = (await anon_client.get(URL, params={"lang": "uz"})).json()
    labels = {e["label"] for e in _all_elevators(body)}
    assert any("kirish" in label and "lift" in label for label in labels)
    assert (await anon_client.get(URL, params={"lang": "xx"})).status_code == 422


@pytest.mark.asyncio
async def test_dispatch_phone_from_board_config(anon_client, seeded, enabled, db_session):
    data = {**DEFAULT_BOARD_CONFIG, "contacts": {**DEFAULT_BOARD_CONFIG["contacts"],
                                                  "dispatch_phone": " +998 90 111-22-33 "}}
    db_session.add(BoardConfig(id=1, data=data, updated_by=None))
    await db_session.commit()
    assert (await anon_client.get(URL)).json()["dispatch_phone"] == "+998 90 111-22-33"


# ── Кэш ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cached_per_lang_for_ttl(anon_client, seeded, enabled, db_session):
    first = (await anon_client.get(URL)).json()
    assert len(_all_elevators(first)) == 4
    row = await db_session.get(Elevator, 1)
    row.is_public = False
    await db_session.commit()
    # В пределах TTL — прежний ответ (кэш), другой язык — отдельный слот.
    assert len(_all_elevators((await anon_client.get(URL)).json())) == 4
    assert len(_all_elevators((await anon_client.get(URL, params={"lang": "uz"})).json())) == 3
    public_router._public_elevators_cache.clear()
    assert len(_all_elevators((await anon_client.get(URL)).json())) == 3


@pytest.mark.asyncio
async def test_module_public_off_bypasses_warm_cache(anon_client, seeded, enabled, db_session):
    """Калитка module_public проверяется ДО кэша: выключение видно сразу, не через TTL."""
    assert len(_all_elevators((await anon_client.get(URL)).json())) == 4
    row = await db_session.get(ElevatorsConfig, 1)
    row.data = {"module_public": False}
    await db_session.commit()
    assert (await anon_client.get(URL)).json()["yards"] == []
    # Обратное включение — снова полный ответ (кэш переживает выключение, но не обходит калитку).
    row.data = {"module_public": True}
    await db_session.commit()
    assert len(_all_elevators((await anon_client.get(URL)).json())) == 4
