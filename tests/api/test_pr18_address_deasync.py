"""PR-18 — FIX-008 de-async + BUG-126/127 + PERF-093 + NICE-076/081.

FIX-008: 12 read-методов AddressService больше НЕ `async` (sync Session, нет
await); write-методы остаются async. PERF-093: get_statistics — conditional
aggregates, исполняется на sqlite (FILTER). BUG-126: limit. BUG-127: _UNSET
sentinel для GPS update_yard. NICE-076/081: purge — with_for_update + audit.
"""
import inspect
import typing

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database.session import Base
from uk_management_bot.services.address_service import AddressService, _UNSET
from uk_management_bot.api.addresses import router as addr_router


DEASYNC = [
    "get_yard_by_id", "get_all_yards", "get_building_by_id",
    "get_buildings_by_yard", "get_apartment_by_id", "get_apartments_by_building",
    "search_apartments", "get_pending_requests", "get_user_apartments",
    "get_apartment_residents", "get_statistics", "get_user_approved_apartments",
]
STILL_ASYNC = ["create_yard", "update_yard", "delete_yard", "create_building", "update_building"]


# ---------------------------------------------------------------------------
# FIX-008 — read-методы de-async, write-методы остаются async
# ---------------------------------------------------------------------------

class TestFix008Deasync:
    @pytest.mark.parametrize("name", DEASYNC)
    def test_read_methods_not_coroutine(self, name):
        fn = getattr(AddressService, name)
        assert not inspect.iscoroutinefunction(fn), f"{name} всё ещё async"

    @pytest.mark.parametrize("name", STILL_ASYNC)
    def test_write_methods_stay_async(self, name):
        fn = getattr(AddressService, name)
        assert inspect.iscoroutinefunction(fn), f"{name} должен остаться async"


# ---------------------------------------------------------------------------
# PERF-093 — get_statistics conditional aggregates, исполняется на sqlite
# ---------------------------------------------------------------------------

@pytest.fixture()
def sync_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    yield s
    s.close()
    engine.dispose()


class TestPerf093Statistics:
    def test_get_statistics_shape_on_empty_db(self, sync_session):
        # Главный риск PERF-093: count(...) FILTER(...) должен исполниться на
        # sqlite. Пустая БД → все нули, но SQL отработал.
        stats = AddressService.get_statistics(sync_session)
        for key in ("yards", "buildings", "apartments", "residents"):
            assert key in stats
        assert stats["yards"] == {"total": 0, "active": 0}
        assert stats["residents"] == {"total": 0, "approved": 0, "pending": 0, "rejected": 0}

    def test_get_statistics_counts(self, sync_session):
        from uk_management_bot.database.models import Yard
        sync_session.add_all([
            Yard(name="A", is_active=True, created_by=1),
            Yard(name="B", is_active=False, created_by=1),
        ])
        sync_session.commit()
        stats = AddressService.get_statistics(sync_session)
        assert stats["yards"] == {"total": 2, "active": 1}


# ---------------------------------------------------------------------------
# BUG-126 / BUG-127 — limit + GPS sentinel
# ---------------------------------------------------------------------------

class TestBug126Bug127:
    def test_apartments_by_building_query_bounded(self):
        src = inspect.getsource(AddressService.get_apartments_by_building)
        assert ".limit(" in src, "get_apartments_by_building без LIMIT (BUG-126)"

    def test_update_yard_gps_uses_unset_sentinel(self):
        sig = inspect.signature(AddressService.update_yard)
        assert sig.parameters["gps_latitude"].default is _UNSET
        assert sig.parameters["gps_longitude"].default is _UNSET


# ---------------------------------------------------------------------------
# NICE-076 / NICE-081 — purge: row-lock + audit
# ---------------------------------------------------------------------------

class TestNice076Nice081Purge:
    def test_purge_endpoints_lock_and_audit(self):
        for name in ("purge_yard", "purge_building", "purge_apartment"):
            src = inspect.getsource(getattr(addr_router, name))
            assert "with_for_update()" in src, f"{name} без FOR UPDATE (NICE-076)"
            assert "AuditLog(" in src, f"{name} без audit (NICE-081)"
            # audit идёт ДО физического удаления
            assert src.index("AuditLog(") < src.index("db.delete("), \
                f"{name}: audit должен предшествовать delete"
