"""Unit tests for AddressService read methods (mock-based, no DB required).

ARCH-014: the write methods (create/update/delete/bulk/moderation) are now thin
async adapters over services/addresses/core and open their own AsyncSession.
Their behaviour is covered by the Postgres suites
uk_management_bot/tests/test_address_core.py and test_address_e2e_parity.py.
The mock-based write-method tests that used to live here asserted sync-Session
side effects (session.commit/add/rollback, queue_webhook_sync) that no longer
apply, so they were retired. Only the read-method tests remain — read methods
still operate on the caller's sync Session and are unchanged.
"""
import json
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import DetachedInstanceError


class _FakeYard:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.name = kwargs.get("name", "Двор А")
        self.description = kwargs.get("description", "Тестовый")
        self.gps_latitude = kwargs.get("gps_latitude", None)
        self.gps_longitude = kwargs.get("gps_longitude", None)
        self.is_active = kwargs.get("is_active", True)
        self.created_by = kwargs.get("created_by", 1)
        self.buildings = kwargs.get("buildings", [])


class _FakeBuilding:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.address = kwargs.get("address", "ул. Тестовая, 1")
        self.yard_id = kwargs.get("yard_id", 1)
        self.is_active = kwargs.get("is_active", True)
        self.gps_latitude = kwargs.get("gps_latitude", None)
        self.gps_longitude = kwargs.get("gps_longitude", None)
        self.entrance_count = kwargs.get("entrance_count", 1)
        self.floor_count = kwargs.get("floor_count", 1)
        self.description = kwargs.get("description", None)
        self.created_by = kwargs.get("created_by", 1)


class _FakeApartment:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.building_id = kwargs.get("building_id", 1)
        self.apartment_number = kwargs.get("apartment_number", "10")
        self.is_active = kwargs.get("is_active", True)
        self.entrance = kwargs.get("entrance", None)
        self.floor = kwargs.get("floor", None)
        self.rooms_count = kwargs.get("rooms_count", None)
        self.area = kwargs.get("area", None)
        self.description = kwargs.get("description", None)
        self.created_by = kwargs.get("created_by", 1)


def _mock_execute(session, scalar_result=None, scalars_all=None):
    """Helper to mock session.execute().scalar_one_or_none() and .scalars().all()"""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scalar_result
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = scalars_all or []
    mock_result.scalars.return_value = mock_scalars
    mock_result.unique.return_value = mock_result
    mock_result.scalar.return_value = 0
    session.execute.return_value = mock_result
    return mock_result


# ===== get_yard_by_id =====

class TestGetYardById:
    @pytest.mark.asyncio
    async def test_returns_yard(self):
        session = MagicMock()
        yard = _FakeYard()
        _mock_execute(session, scalar_result=yard)
        from uk_management_bot.services.address_service import AddressService

        result = AddressService.get_yard_by_id(session, 1)
        assert result == yard

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        session = MagicMock()
        _mock_execute(session, scalar_result=None)
        from uk_management_bot.services.address_service import AddressService

        result = AddressService.get_yard_by_id(session, 999)
        assert result is None


# ===== get_all_yards =====

class TestGetAllYards:
    @pytest.mark.asyncio
    async def test_returns_active_yards(self):
        session = MagicMock()
        yards = [_FakeYard(id=1), _FakeYard(id=2)]
        _mock_execute(session, scalars_all=yards)
        from uk_management_bot.services.address_service import AddressService

        result = AddressService.get_all_yards(session)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_all_yards_including_inactive(self):
        session = MagicMock()
        yards = [_FakeYard(is_active=False)]
        _mock_execute(session, scalars_all=yards)
        from uk_management_bot.services.address_service import AddressService

        result = AddressService.get_all_yards(session, only_active=False)
        assert len(result) == 1


# ===== get_buildings_by_yard =====

class TestGetBuildingsByYard:
    @pytest.mark.asyncio
    async def test_returns_buildings(self):
        session = MagicMock()
        buildings = [_FakeBuilding(id=1), _FakeBuilding(id=2)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = buildings
        session.execute.return_value = mock_result

        from uk_management_bot.services.address_service import AddressService

        result = AddressService.get_buildings_by_yard(session, 1)
        assert len(result) == 2


# ===== get_apartments_by_building =====

class TestGetApartmentsByBuilding:
    @pytest.mark.asyncio
    async def test_returns_sorted_apartments(self):
        session = MagicMock()
        apt1 = _FakeApartment(apartment_number="2")
        apt2 = _FakeApartment(apartment_number="1")
        apt3 = _FakeApartment(apartment_number="A")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [apt1, apt2, apt3]
        session.execute.return_value = mock_result

        from uk_management_bot.services.address_service import AddressService

        result = AddressService.get_apartments_by_building(session, 1)
        # Numeric "1" before "2" before non-numeric "A"
        assert result[0].apartment_number == "1"
        assert result[1].apartment_number == "2"
        assert result[2].apartment_number == "A"


# ===== get_apartment_by_id =====

class TestGetApartmentById:
    @pytest.mark.asyncio
    async def test_returns_apartment(self):
        session = MagicMock()
        apt = _FakeApartment()
        _mock_execute(session, scalar_result=apt)
        from uk_management_bot.services.address_service import AddressService

        result = AddressService.get_apartment_by_id(session, 1)
        assert result == apt

    @pytest.mark.asyncio
    async def test_returns_none(self):
        session = MagicMock()
        _mock_execute(session, scalar_result=None)
        from uk_management_bot.services.address_service import AddressService

        result = AddressService.get_apartment_by_id(session, 999)
        assert result is None


# ===========================================================================
# BUG-028 — exception hardening (no schema leak to UI)
# ===========================================================================

# Recognizable internal text that must NEVER reach the user-facing message.
_LEAK_MARKER = 'duplicate key value violates unique constraint "apartment_uk"'


def _integrity_error() -> IntegrityError:
    return IntegrityError("INSERT INTO apartments ...", {}, Exception(_LEAK_MARKER))


def _operational_error() -> OperationalError:
    return OperationalError("SELECT ...", {}, Exception("server closed the connection"))


class _FakeAsyncCM:
    """Minimal async context manager so `async with _async_session() as adb:` works."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _patch_core(method: str, exc: Exception):
    """Patch a core coroutine to raise `exc`, and stub _async_session."""
    return (
        patch(
            f"uk_management_bot.services.address_service._core.{method}",
            new=AsyncMock(side_effect=exc),
        ),
        patch(
            "uk_management_bot.services.address_service._async_session",
            new=lambda: _FakeAsyncCM(MagicMock()),
        ),
    )


class TestWriteMethodsDoNotLeakOnDbError:
    """Group A/B/C write-adapters: DB error -> contract shape + opaque message."""

    @pytest.mark.asyncio
    async def test_create_yard_db_error_returns_opaque(self):
        from uk_management_bot.services.address_service import AddressService

        p_core, p_sess = _patch_core("create_yard", _integrity_error())
        with p_core, p_sess:
            yard, error = await AddressService.create_yard(MagicMock(), "Двор", 1)

        assert yard is None
        assert error is not None
        assert _LEAK_MARKER not in error
        assert "INSERT" not in error

    @pytest.mark.asyncio
    async def test_delete_building_db_error_returns_opaque(self):
        from uk_management_bot.services.address_service import AddressService

        p_core, p_sess = _patch_core("delete_building", _integrity_error())
        with p_core, p_sess:
            ok, error = await AddressService.delete_building(MagicMock(), 1)

        assert ok is False
        assert error is not None
        assert _LEAK_MARKER not in error

    @pytest.mark.asyncio
    async def test_bulk_create_apartments_db_error_returns_opaque(self):
        from uk_management_bot.services.address_service import AddressService

        p_core, p_sess = _patch_core("bulk_create_apartments", _integrity_error())
        with p_core, p_sess:
            created, skipped, errors = await AddressService.bulk_create_apartments(
                MagicMock(), 1, ["1", "2"], 1
            )

        assert (created, skipped) == (0, 0)
        assert len(errors) == 1
        assert _LEAK_MARKER not in errors[0]

    @pytest.mark.asyncio
    async def test_non_db_exception_propagates(self):
        """Не-DB исключение больше не глотается (раньше уходило строкой юзеру)."""
        from uk_management_bot.services.address_service import AddressService

        p_core, p_sess = _patch_core("create_yard", ValueError("boom"))
        with p_core, p_sess, pytest.raises(ValueError):
            await AddressService.create_yard(MagicMock(), "Двор", 1)


class TestReadMethodsPropagateDbError:
    """Read methods must NOT swallow a DB error into []/{} (poisoned session)."""

    @pytest.mark.asyncio
    async def test_get_statistics_reraises(self):
        from uk_management_bot.services.address_service import AddressService

        session = MagicMock()
        session.execute.side_effect = _operational_error()

        with pytest.raises(OperationalError):
            AddressService.get_statistics(session)

    def test_get_user_available_yards_reraises(self):
        from uk_management_bot.services.address_service import AddressService

        session = MagicMock()
        session.execute.side_effect = _operational_error()

        with pytest.raises(OperationalError):
            AddressService.get_user_available_yards(session, 12345)


class TestFormatApartmentAddressDetached:
    def test_detached_building_falls_back_without_reaccess(self):
        from uk_management_bot.services.address_service import AddressService

        class _DetachedApartment:
            apartment_number = "42"

            @property
            def building(self):
                raise DetachedInstanceError("detached")

        result = AddressService.format_apartment_address(_DetachedApartment())
        # COD-05: канонический формат «дом первым» → fallback без здания = «кв. N».
        assert result == "кв. 42"

    def test_detached_number_falls_back_to_placeholder(self):
        from uk_management_bot.services.address_service import AddressService

        class _FullyDetached:
            @property
            def apartment_number(self):
                raise DetachedInstanceError("detached")

            @property
            def building(self):
                raise DetachedInstanceError("detached")

        result = AddressService.format_apartment_address(_FullyDetached())
        assert result == "кв. ?"


class TestSanitizedLocaleKeysHaveNoErrorPlaceholder:
    """Regression guard: exception-path keys must not interpolate {error}."""

    _LOCALES = Path(__file__).resolve().parents[2] / "uk_management_bot" / "config" / "locales"
    _KEYS = [
        "address_apartments.handlers.creation_exception",
        "address_apartments.handlers.area_update_exception",
        "address_moderation.handlers.approve_exception",
        "address_moderation.handlers.reject_exception",
        "address_yards.handlers.operation_failed",
        "address_buildings.handlers.operation_failed",
    ]

    @staticmethod
    def _resolve(data: dict, dotted: str) -> str:
        node = data
        for part in dotted.split("."):
            node = node[part]
        return node

    @pytest.mark.parametrize("lang", ["ru", "uz"])
    def test_no_error_placeholder(self, lang):
        data = json.loads((self._LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
        for key in self._KEYS:
            value = self._resolve(data, key)
            assert "{error}" not in value, f"{lang}:{key} still leaks {{error}}"
