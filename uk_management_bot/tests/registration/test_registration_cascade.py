"""Каскад двор → дом → квартира и статус контакта под тикетом регистрации
(спека 2026-09-03 §4.1, §4.3)."""
import pytest

from uk_management_bot.api.registration.tickets import create_registration_ticket


def _bearer(tid: int):
    return {"Authorization": f"Bearer {create_registration_ticket(tid)}"}


# ─── /contact-status ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_contact_status_requires_ticket(api_client):
    r = await api_client.get("/api/v2/registration/contact-status")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_contact_status_null_without_user(api_client):
    r = await api_client.get("/api/v2/registration/contact-status", headers=_bearer(99801))
    assert r.status_code == 200 and r.json() == {"phone": None}


@pytest.mark.asyncio
async def test_contact_status_returns_saved_phone(api_client, seed_user):
    await seed_user(telegram_id=99802, phone="+998901234567")
    r = await api_client.get("/api/v2/registration/contact-status", headers=_bearer(99802))
    assert r.status_code == 200 and r.json() == {"phone": "+998901234567"}


# ─── каскад ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cascade_requires_ticket(api_client):
    for path in ("/yards", "/yards/1/buildings", "/buildings/1/apartments"):
        r = await api_client.get(f"/api/v2/registration{path}")
        assert r.status_code == 401, path


@pytest.mark.asyncio
async def test_yards_lists_active_only(api_client, seed_apartment):
    active = await seed_apartment(yard_name="Активный")
    await seed_apartment(yard_name="Неактивный", yard_active=False)
    r = await api_client.get("/api/v2/registration/yards", headers=_bearer(99803))
    assert r.status_code == 200
    names = [y["name"] for y in r.json()]
    assert any(n.startswith("Активный") for n in names)
    assert not any(n.startswith("Неактивный") for n in names)
    assert {"id", "name"} <= set(r.json()[0].keys())
    assert active.building_id  # seed sanity


@pytest.mark.asyncio
async def test_buildings_of_yard(api_client, async_db, seed_apartment):
    from uk_management_bot.database.models.building import Building
    apt = await seed_apartment(address="ул. Ленина 1")
    yard_id = (await async_db.get(Building, apt.building_id)).yard_id
    async_db.add(Building(address="ул. Тёмная 2", yard_id=yard_id, is_active=False))
    await async_db.flush()

    r = await api_client.get(f"/api/v2/registration/yards/{yard_id}/buildings", headers=_bearer(99804))
    assert r.status_code == 200
    assert [b["address"] for b in r.json()] == ["ул. Ленина 1"]
    assert {"id", "address"} <= set(r.json()[0].keys())


@pytest.mark.asyncio
async def test_buildings_of_inactive_or_missing_yard_404(api_client, async_db, seed_apartment):
    from uk_management_bot.database.models.building import Building
    apt = await seed_apartment(yard_active=False)
    yard_id = (await async_db.get(Building, apt.building_id)).yard_id
    r = await api_client.get(f"/api/v2/registration/yards/{yard_id}/buildings", headers=_bearer(99805))
    assert r.status_code == 404
    r = await api_client.get("/api/v2/registration/yards/999999/buildings", headers=_bearer(99805))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_apartments_of_building_sorted_numerically(api_client, async_db, seed_apartment):
    from uk_management_bot.database.models.apartment import Apartment
    apt = await seed_apartment(number="10")
    for n, active in (("2", True), ("10а", True), ("3", False)):
        async_db.add(Apartment(apartment_number=n, building_id=apt.building_id, is_active=active))
    await async_db.flush()

    r = await api_client.get(f"/api/v2/registration/buildings/{apt.building_id}/apartments", headers=_bearer(99806))
    assert r.status_code == 200
    assert [a["apartment_number"] for a in r.json()] == ["2", "10", "10а"]
    assert {"id", "apartment_number", "floor", "entrance"} <= set(r.json()[0].keys())


@pytest.mark.asyncio
async def test_apartments_of_inactive_building_or_yard_404(api_client, seed_apartment):
    a = await seed_apartment(building_active=False)
    r = await api_client.get(f"/api/v2/registration/buildings/{a.building_id}/apartments", headers=_bearer(99807))
    assert r.status_code == 404
    b = await seed_apartment(yard_active=False)
    r = await api_client.get(f"/api/v2/registration/buildings/{b.building_id}/apartments", headers=_bearer(99807))
    assert r.status_code == 404
    r = await api_client.get("/api/v2/registration/buildings/999999/apartments", headers=_bearer(99807))
    assert r.status_code == 404
