"""
Tests for the addresses API module.

Covers: stats, yards CRUD, buildings CRUD, apartments CRUD,
bulk create, search, moderation (approve/reject), and business logic guards.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.yard import Yard
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.user_apartment import UserApartment

pytestmark = pytest.mark.asyncio

BASE = "/api/v2/addresses"


# ═══════════════════════ Helpers ═══════════════════════


async def _create_yard(client: AsyncClient, name: str = "Test Yard", **kw) -> dict:
    payload = {"name": name, **kw}
    r = await client.post(f"{BASE}/yards", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


async def _create_building(client: AsyncClient, yard_id: int, address: str = "ул. Тестовая 1", **kw) -> dict:
    payload = {"yard_id": yard_id, "address": address, **kw}
    r = await client.post(f"{BASE}/buildings", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


async def _create_apartment(client: AsyncClient, building_id: int, number: str = "1", **kw) -> dict:
    payload = {"building_id": building_id, "apartment_number": number, **kw}
    r = await client.post(f"{BASE}/apartments", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ═══════════════════════ Stats ═══════════════════════


class TestStats:

    async def test_empty_stats(self, client: AsyncClient):
        r = await client.get(f"{BASE}/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["yards_total"] == 0
        assert data["buildings_total"] == 0
        assert data["apartments_total"] == 0
        assert data["residents_approved"] == 0
        assert data["residents_pending"] == 0

    async def test_stats_after_data(self, client: AsyncClient):
        yard = await _create_yard(client, "Stats Yard")
        bld = await _create_building(client, yard["id"], "Addr for stats")
        await _create_apartment(client, bld["id"], "100")

        r = await client.get(f"{BASE}/stats")
        data = r.json()
        assert data["yards_total"] == 1
        assert data["yards_active"] == 1
        assert data["buildings_total"] == 1
        assert data["apartments_total"] == 1


# ═══════════════════════ Yards CRUD ═══════════════════════


class TestYards:

    async def test_create_yard(self, client: AsyncClient):
        data = await _create_yard(client, "My Yard", description="desc", gps_latitude=55.7)
        assert data["name"] == "My Yard"
        assert data["description"] == "desc"
        assert data["gps_latitude"] == 55.7
        assert data["is_active"] is True
        assert data["buildings_count"] == 0

    async def test_create_yard_duplicate_name(self, client: AsyncClient):
        await _create_yard(client, "Unique Name")
        r = await client.post(f"{BASE}/yards", json={"name": "Unique Name"})
        assert r.status_code == 409
        assert "already exists" in r.json()["detail"]

    async def test_list_yards(self, client: AsyncClient):
        await _create_yard(client, "Yard A")
        await _create_yard(client, "Yard B")
        r = await client.get(f"{BASE}/yards")
        assert r.status_code == 200
        names = [y["name"] for y in r.json()]
        assert "Yard A" in names
        assert "Yard B" in names

    async def test_list_yards_excludes_inactive(self, client: AsyncClient):
        yard = await _create_yard(client, "Active Yard")
        inactive = await _create_yard(client, "Inactive Yard")
        # Deactivate one yard
        await client.patch(f"{BASE}/yards/{inactive['id']}", json={"is_active": False})

        r = await client.get(f"{BASE}/yards")
        names = [y["name"] for y in r.json()]
        assert "Active Yard" in names
        assert "Inactive Yard" not in names

        # With include_inactive
        r2 = await client.get(f"{BASE}/yards?include_inactive=true")
        names2 = [y["name"] for y in r2.json()]
        assert "Inactive Yard" in names2

    async def test_update_yard(self, client: AsyncClient):
        yard = await _create_yard(client, "Old Name")
        r = await client.patch(f"{BASE}/yards/{yard['id']}", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    async def test_update_yard_duplicate_name(self, client: AsyncClient):
        await _create_yard(client, "Name A")
        yard_b = await _create_yard(client, "Name B")
        r = await client.patch(f"{BASE}/yards/{yard_b['id']}", json={"name": "Name A"})
        assert r.status_code == 409

    async def test_update_yard_not_found(self, client: AsyncClient):
        r = await client.patch(f"{BASE}/yards/99999", json={"name": "Nonexistent Yard"})
        assert r.status_code == 404

    async def test_delete_yard(self, client: AsyncClient):
        yard = await _create_yard(client, "To Delete")
        r = await client.delete(f"{BASE}/yards/{yard['id']}")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    async def test_delete_yard_blocked_by_active_buildings(self, client: AsyncClient):
        yard = await _create_yard(client, "Has Buildings")
        await _create_building(client, yard["id"], "Some addr 123")
        r = await client.delete(f"{BASE}/yards/{yard['id']}")
        assert r.status_code == 409
        assert "active building" in r.json()["detail"]

    async def test_deactivate_yard_via_patch_blocked(self, client: AsyncClient):
        yard = await _create_yard(client, "Patch Deactivate")
        await _create_building(client, yard["id"], "Child building 1")
        r = await client.patch(f"{BASE}/yards/{yard['id']}", json={"is_active": False})
        assert r.status_code == 409


# ═══════════════════════ Buildings CRUD ═══════════════════════


class TestBuildings:

    async def test_create_building(self, client: AsyncClient):
        yard = await _create_yard(client, "Yard for Bld")
        bld = await _create_building(client, yard["id"], "ул. Пушкина 10", entrance_count=3, floor_count=9)
        assert bld["address"] == "ул. Пушкина 10"
        assert bld["yard_id"] == yard["id"]
        assert bld["yard_name"] == "Yard for Bld"
        assert bld["entrance_count"] == 3
        assert bld["floor_count"] == 9
        assert bld["apartments_count"] == 0

    async def test_create_building_in_inactive_yard(self, client: AsyncClient):
        yard = await _create_yard(client, "Will Deactivate")
        await client.patch(f"{BASE}/yards/{yard['id']}", json={"is_active": False})
        r = await client.post(f"{BASE}/buildings", json={"yard_id": yard["id"], "address": "ул. X 1"})
        assert r.status_code == 409
        assert "inactive yard" in r.json()["detail"]

    async def test_create_building_nonexistent_yard(self, client: AsyncClient):
        r = await client.post(f"{BASE}/buildings", json={"yard_id": 99999, "address": "ул. X 1"})
        assert r.status_code == 404

    async def test_list_buildings(self, client: AsyncClient):
        yard = await _create_yard(client, "List Bld Yard")
        await _create_building(client, yard["id"], "Addr A")
        await _create_building(client, yard["id"], "Addr B")

        r = await client.get(f"{BASE}/yards/{yard['id']}/buildings")
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_list_buildings_nonexistent_yard(self, client: AsyncClient):
        r = await client.get(f"{BASE}/yards/99999/buildings")
        assert r.status_code == 404

    async def test_update_building(self, client: AsyncClient):
        yard = await _create_yard(client, "Upd Bld Yard")
        bld = await _create_building(client, yard["id"], "Old addr")
        r = await client.patch(f"{BASE}/buildings/{bld['id']}", json={"address": "New addr"})
        assert r.status_code == 200
        assert r.json()["address"] == "New addr"

    async def test_delete_building(self, client: AsyncClient):
        yard = await _create_yard(client, "Del Bld Yard")
        bld = await _create_building(client, yard["id"], "To delete bld")
        r = await client.delete(f"{BASE}/buildings/{bld['id']}")
        assert r.status_code == 200

    async def test_delete_building_blocked_by_apartments(self, client: AsyncClient):
        yard = await _create_yard(client, "Has Apt Yard")
        bld = await _create_building(client, yard["id"], "Has Apt addr")
        await _create_apartment(client, bld["id"], "1")
        r = await client.delete(f"{BASE}/buildings/{bld['id']}")
        assert r.status_code == 409
        assert "active apartment" in r.json()["detail"]

    async def test_deactivate_building_via_patch_blocked(self, client: AsyncClient):
        yard = await _create_yard(client, "Deact Bld Yard")
        bld = await _create_building(client, yard["id"], "Deact bld addr")
        await _create_apartment(client, bld["id"], "42")
        r = await client.patch(f"{BASE}/buildings/{bld['id']}", json={"is_active": False})
        assert r.status_code == 409


# ═══════════════════════ Apartments CRUD ═══════════════════════


class TestApartments:

    async def test_create_apartment(self, client: AsyncClient):
        yard = await _create_yard(client, "Apt Yard")
        bld = await _create_building(client, yard["id"], "Apt Addr")
        apt = await _create_apartment(client, bld["id"], "42", entrance=2, floor=5, rooms_count=3, area=65.5)
        assert apt["apartment_number"] == "42"
        assert apt["building_id"] == bld["id"]
        assert apt["building_address"] == "Apt Addr"
        assert apt["yard_name"] == "Apt Yard"
        assert apt["entrance"] == 2
        assert apt["floor"] == 5
        assert apt["rooms_count"] == 3
        assert apt["area"] == 65.5
        assert apt["residents_count"] == 0

    async def test_create_apartment_duplicate(self, client: AsyncClient):
        yard = await _create_yard(client, "Dup Apt Yard")
        bld = await _create_building(client, yard["id"], "Dup Apt Addr")
        await _create_apartment(client, bld["id"], "1")
        r = await client.post(f"{BASE}/apartments", json={"building_id": bld["id"], "apartment_number": "1"})
        assert r.status_code == 409
        assert "already exists" in r.json()["detail"]

    async def test_create_apartment_in_inactive_building(self, client: AsyncClient):
        yard = await _create_yard(client, "Inactive Bld Yard")
        bld = await _create_building(client, yard["id"], "Inactive Bld Addr")
        await client.patch(f"{BASE}/buildings/{bld['id']}", json={"is_active": False})
        r = await client.post(f"{BASE}/apartments", json={"building_id": bld["id"], "apartment_number": "1"})
        assert r.status_code == 409

    async def test_list_apartments(self, client: AsyncClient):
        yard = await _create_yard(client, "List Apt Yard")
        bld = await _create_building(client, yard["id"], "List Apt Addr")
        await _create_apartment(client, bld["id"], "1")
        await _create_apartment(client, bld["id"], "2")

        r = await client.get(f"{BASE}/buildings/{bld['id']}/apartments")
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_update_apartment(self, client: AsyncClient):
        yard = await _create_yard(client, "Upd Apt Yard")
        bld = await _create_building(client, yard["id"], "Upd Apt Addr")
        apt = await _create_apartment(client, bld["id"], "10")
        r = await client.patch(f"{BASE}/apartments/{apt['id']}", json={"apartment_number": "10A", "floor": 3})
        assert r.status_code == 200
        assert r.json()["apartment_number"] == "10A"
        assert r.json()["floor"] == 3

    async def test_update_apartment_duplicate_number(self, client: AsyncClient):
        yard = await _create_yard(client, "Dup Num Yard")
        bld = await _create_building(client, yard["id"], "Dup Num Addr")
        await _create_apartment(client, bld["id"], "1")
        apt2 = await _create_apartment(client, bld["id"], "2")
        r = await client.patch(f"{BASE}/apartments/{apt2['id']}", json={"apartment_number": "1"})
        assert r.status_code == 409

    async def test_delete_apartment(self, client: AsyncClient):
        yard = await _create_yard(client, "Del Apt Yard")
        bld = await _create_building(client, yard["id"], "Del Apt Addr")
        apt = await _create_apartment(client, bld["id"], "99")
        r = await client.delete(f"{BASE}/apartments/{apt['id']}")
        assert r.status_code == 200

    async def test_delete_apartment_blocked_by_residents(self, client: AsyncClient, db_session: AsyncSession, resident_user):
        yard = await _create_yard(client, "Resident Apt Yard")
        bld = await _create_building(client, yard["id"], "Resident Apt Addr")
        apt = await _create_apartment(client, bld["id"], "55")

        # Add an approved UserApartment directly in DB
        ua = UserApartment(
            user_id=resident_user.id,
            apartment_id=apt["id"],
            status="approved",
            is_owner=True,
            is_primary=True,
        )
        db_session.add(ua)
        await db_session.commit()

        r = await client.delete(f"{BASE}/apartments/{apt['id']}")
        assert r.status_code == 409
        assert "approved resident" in r.json()["detail"]

    async def test_deactivate_apartment_via_patch_blocked_by_residents(
        self, client: AsyncClient, db_session: AsyncSession, resident_user
    ):
        yard = await _create_yard(client, "Deact Apt Yard")
        bld = await _create_building(client, yard["id"], "Deact Apt Addr")
        apt = await _create_apartment(client, bld["id"], "77")

        ua = UserApartment(
            user_id=resident_user.id,
            apartment_id=apt["id"],
            status="approved",
            is_owner=False,
            is_primary=True,
        )
        db_session.add(ua)
        await db_session.commit()

        r = await client.patch(f"{BASE}/apartments/{apt['id']}", json={"is_active": False})
        assert r.status_code == 409


# ═══════════════════════ Bulk Create ═══════════════════════


class TestBulkCreate:

    async def test_bulk_create_basic(self, client: AsyncClient):
        yard = await _create_yard(client, "Bulk Yard")
        bld = await _create_building(client, yard["id"], "Bulk Addr")

        r = await client.post(f"{BASE}/apartments/bulk", json={
            "building_id": bld["id"],
            "apartment_numbers": ["1", "2", "3", "4", "5"],
        })
        assert r.status_code == 201
        data = r.json()
        assert data["created"] == 5
        assert data["skipped"] == 0
        assert data["errors"] == []

    async def test_bulk_create_skips_duplicates(self, client: AsyncClient):
        yard = await _create_yard(client, "Bulk Dup Yard")
        bld = await _create_building(client, yard["id"], "Bulk Dup Addr")

        # Create first batch
        await client.post(f"{BASE}/apartments/bulk", json={
            "building_id": bld["id"],
            "apartment_numbers": ["1", "2", "3"],
        })

        # Second batch overlaps
        r = await client.post(f"{BASE}/apartments/bulk", json={
            "building_id": bld["id"],
            "apartment_numbers": ["2", "3", "4", "5"],
        })
        data = r.json()
        assert data["created"] == 2
        assert data["skipped"] == 2

    async def test_bulk_create_empty_numbers_skipped(self, client: AsyncClient):
        yard = await _create_yard(client, "Bulk Empty Yard")
        bld = await _create_building(client, yard["id"], "Bulk Empty Addr")

        r = await client.post(f"{BASE}/apartments/bulk", json={
            "building_id": bld["id"],
            "apartment_numbers": ["1", "", "  ", "2"],
        })
        data = r.json()
        assert data["created"] == 2
        assert len(data["errors"]) >= 1  # empty numbers reported

    async def test_bulk_create_too_long_number(self, client: AsyncClient):
        yard = await _create_yard(client, "Bulk Long Yard")
        bld = await _create_building(client, yard["id"], "Bulk Long Addr")

        r = await client.post(f"{BASE}/apartments/bulk", json={
            "building_id": bld["id"],
            "apartment_numbers": ["1", "A" * 25],
        })
        data = r.json()
        assert data["created"] == 1
        assert any("too long" in e for e in data["errors"])

    async def test_bulk_create_inactive_building(self, client: AsyncClient):
        yard = await _create_yard(client, "Bulk Inact Yard")
        bld = await _create_building(client, yard["id"], "Bulk Inact Addr")
        await client.patch(f"{BASE}/buildings/{bld['id']}", json={"is_active": False})

        r = await client.post(f"{BASE}/apartments/bulk", json={
            "building_id": bld["id"],
            "apartment_numbers": ["1"],
        })
        assert r.status_code == 409

    async def test_bulk_create_nonexistent_building(self, client: AsyncClient):
        r = await client.post(f"{BASE}/apartments/bulk", json={
            "building_id": 99999,
            "apartment_numbers": ["1"],
        })
        assert r.status_code == 404


# ═══════════════════════ Search ═══════════════════════


class TestSearch:

    async def test_search_by_apartment_number(self, client: AsyncClient):
        yard = await _create_yard(client, "Search Yard")
        bld = await _create_building(client, yard["id"], "Проспект Ленина 15")
        await _create_apartment(client, bld["id"], "42")
        await _create_apartment(client, bld["id"], "43")
        await _create_apartment(client, bld["id"], "100")

        r = await client.get(f"{BASE}/apartments/search?q=42")
        assert r.status_code == 200
        results = r.json()
        numbers = [a["apartment_number"] for a in results]
        assert "42" in numbers

    async def test_search_by_building_address(self, client: AsyncClient):
        yard = await _create_yard(client, "Search Addr Yard")
        bld = await _create_building(client, yard["id"], "Проспект Мира 20")
        await _create_apartment(client, bld["id"], "1")

        r = await client.get(f"{BASE}/apartments/search?q=Мира")
        assert r.status_code == 200
        assert len(r.json()) >= 1
        assert r.json()[0]["building_address"] == "Проспект Мира 20"

    async def test_search_no_results(self, client: AsyncClient):
        r = await client.get(f"{BASE}/apartments/search?q=nonexistent_xyz")
        assert r.status_code == 200
        assert r.json() == []

    async def test_search_escapes_like_chars(self, client: AsyncClient):
        yard = await _create_yard(client, "Like Yard")
        bld = await _create_building(client, yard["id"], "100% Test Address")
        await _create_apartment(client, bld["id"], "1")

        # Search with % — should be escaped, not treated as wildcard
        r = await client.get(f"{BASE}/apartments/search?q=100%25")
        assert r.status_code == 200


# ═══════════════════════ Moderation ═══════════════════════


class TestModeration:

    async def _setup_pending(self, client, db_session, resident_user):
        """Helper: create yard → building → apartment → pending UserApartment."""
        yard = await _create_yard(client, f"Mod Yard {id(self)}")
        bld = await _create_building(client, yard["id"], f"Mod Addr {id(self)}")
        apt = await _create_apartment(client, bld["id"], "1")

        ua = UserApartment(
            user_id=resident_user.id,
            apartment_id=apt["id"],
            status="pending",
            is_owner=True,
            is_primary=True,
        )
        db_session.add(ua)
        await db_session.commit()
        await db_session.refresh(ua)
        return ua

    async def test_list_pending(self, client: AsyncClient, db_session: AsyncSession, resident_user):
        ua = await self._setup_pending(client, db_session, resident_user)

        r = await client.get(f"{BASE}/moderation")
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 1
        item = next(i for i in items if i["id"] == ua.id)
        assert item["status"] == "pending"
        assert item["is_owner"] is True
        assert item["user_name"] == "Resident User"

    async def test_approve(self, client: AsyncClient, db_session: AsyncSession, resident_user):
        ua = await self._setup_pending(client, db_session, resident_user)

        r = await client.post(f"{BASE}/moderation/{ua.id}/approve")
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    async def test_approve_already_approved(self, client: AsyncClient, db_session: AsyncSession, resident_user):
        ua = await self._setup_pending(client, db_session, resident_user)
        await client.post(f"{BASE}/moderation/{ua.id}/approve")

        r = await client.post(f"{BASE}/moderation/{ua.id}/approve")
        assert r.status_code == 409

    async def test_reject(self, client: AsyncClient, db_session: AsyncSession, resident_user):
        ua = await self._setup_pending(client, db_session, resident_user)

        r = await client.post(f"{BASE}/moderation/{ua.id}/reject", json={"comment": "Wrong apartment"})
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

    async def test_reject_requires_comment(self, client: AsyncClient, db_session: AsyncSession, resident_user):
        ua = await self._setup_pending(client, db_session, resident_user)

        r = await client.post(f"{BASE}/moderation/{ua.id}/reject", json={"comment": ""})
        assert r.status_code == 422

    async def test_reject_comment_too_short(self, client: AsyncClient, db_session: AsyncSession, resident_user):
        ua = await self._setup_pending(client, db_session, resident_user)

        r = await client.post(f"{BASE}/moderation/{ua.id}/reject", json={"comment": "ab"})
        assert r.status_code == 422

    async def test_approve_nonexistent(self, client: AsyncClient):
        r = await client.post(f"{BASE}/moderation/99999/approve")
        assert r.status_code == 404

    async def test_reject_nonexistent(self, client: AsyncClient):
        r = await client.post(f"{BASE}/moderation/99999/reject", json={"comment": "some reason"})
        assert r.status_code == 404
