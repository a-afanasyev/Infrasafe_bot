"""Unit tests for check_request_access() in uk_management_bot/api/dependencies_access.py.

Extends the existing tests in uk_management_bot/tests/test_api_access.py which cover
is_assigned_executor(). This file focuses on the async check_request_access() function.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies_access import check_request_access


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(request_obj=None, assignment_obj=None, resident_obj=None):
    """Return an AsyncSession mock whose execute() returns appropriate results."""
    db = AsyncMock(spec=AsyncSession)

    async def fake_execute(stmt, *args, **kwargs):
        # We inspect the statement text to figure out which query is being run.
        # A simpler approach: return different mocks per call order via side_effect.
        result = MagicMock()
        return result

    # Build a side_effect list so queries resolve in order:
    # 1st call  → fetch Request
    # 2nd call  → fetch RequestAssignment (only reached for executor path)
    # 3rd call  → fetch UserApartment (only reached for resident path)
    def _scalar_mock(value):
        r = MagicMock()
        r.scalar_one_or_none.return_value = value
        return r

    db.execute = AsyncMock(side_effect=[
        _scalar_mock(request_obj),    # 1st: Request lookup
        _scalar_mock(assignment_obj), # 2nd: RequestAssignment lookup
        _scalar_mock(resident_obj),   # 3rd: UserApartment lookup
    ])
    return db


def _make_user(user_id: int, roles: list[str]) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    import json as _json
    user.roles = _json.dumps(roles)
    user.role = roles[0] if roles else None
    return user


def _make_request(
    request_number: str = "260401-001",
    user_id: int = 10,
    status: str = "Новая",
    apartment_id: int | None = None,
    executor_id: int | None = None,
) -> MagicMock:
    req = MagicMock()
    req.request_number = request_number
    req.user_id = user_id
    req.status = status
    req.apartment_id = apartment_id
    req.executor_id = executor_id
    return req


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCheckRequestAccess:

    async def test_manager_always_has_access(self):
        """A manager gets the request back regardless of ownership."""
        request = _make_request(user_id=999)
        db = _make_db(request_obj=request)
        user = _make_user(user_id=1, roles=["manager"])

        result = await check_request_access("260401-001", db, user)
        assert result is request

    async def test_owner_has_access(self):
        """The request owner (request.user_id == user.id) always has access."""
        request = _make_request(user_id=42, status="В работе")
        db = _make_db(request_obj=request)
        user = _make_user(user_id=42, roles=["applicant"])

        result = await check_request_access("260401-001", db, user)
        assert result is request

    async def test_non_owner_non_manager_gets_403(self):
        """A regular applicant who does not own the request is denied."""
        request = _make_request(user_id=10, status="В работе", apartment_id=None)
        db = _make_db(request_obj=request)
        user = _make_user(user_id=99, roles=["applicant"])

        with pytest.raises(HTTPException) as exc_info:
            await check_request_access("260401-001", db, user)
        assert exc_info.value.status_code == 403

    async def test_request_not_found_raises_404(self):
        """Missing request raises 404."""
        db = _make_db(request_obj=None)
        user = _make_user(user_id=1, roles=["manager"])

        with pytest.raises(HTTPException) as exc_info:
            await check_request_access("260401-999", db, user)
        assert exc_info.value.status_code == 404

    async def test_apartment_resident_access_when_status_ispolneno(self):
        """Apartment resident gets access when status == 'Исполнено'."""
        apt_id = 5
        request = _make_request(
            user_id=10, status="Исполнено", apartment_id=apt_id
        )
        resident_record = MagicMock()  # truthy — resident found

        # DB call order: Request → (no assignment needed) → UserApartment
        # The executor path is skipped (user has no executor role), so we
        # need: 1st=request, 2nd=resident.
        db = AsyncMock(spec=AsyncSession)

        def _scalar_mock(value):
            r = MagicMock()
            r.scalar_one_or_none.return_value = value
            return r

        db.execute = AsyncMock(side_effect=[
            _scalar_mock(request),          # 1st: Request
            _scalar_mock(resident_record),  # 2nd: UserApartment
        ])

        user = _make_user(user_id=99, roles=["applicant"])

        result = await check_request_access("260401-001", db, user)
        assert result is request

    async def test_apartment_resident_gets_403_when_not_ispolneno(self):
        """Apartment resident is denied when status != 'Исполнено'."""
        apt_id = 5
        request = _make_request(
            user_id=10, status="В работе", apartment_id=apt_id
        )

        db = AsyncMock(spec=AsyncSession)

        def _scalar_mock(value):
            r = MagicMock()
            r.scalar_one_or_none.return_value = value
            return r

        # Only the Request query fires; resident check is never reached because
        # status != 'Исполнено'.
        db.execute = AsyncMock(side_effect=[
            _scalar_mock(request),  # 1st: Request
        ])

        user = _make_user(user_id=99, roles=["applicant"])

        with pytest.raises(HTTPException) as exc_info:
            await check_request_access("260401-001", db, user)
        assert exc_info.value.status_code == 403

    async def test_apartment_resident_no_approved_record_gets_403(self):
        """Apartment resident record not found in UserApartment → 403."""
        apt_id = 5
        request = _make_request(
            user_id=10, status="Исполнено", apartment_id=apt_id
        )

        db = AsyncMock(spec=AsyncSession)

        def _scalar_mock(value):
            r = MagicMock()
            r.scalar_one_or_none.return_value = value
            return r

        db.execute = AsyncMock(side_effect=[
            _scalar_mock(request),  # 1st: Request
            _scalar_mock(None),     # 2nd: UserApartment — not found
        ])

        user = _make_user(user_id=99, roles=["applicant"])

        with pytest.raises(HTTPException) as exc_info:
            await check_request_access("260401-001", db, user)
        assert exc_info.value.status_code == 403

    async def test_executor_with_executor_id_has_access(self):
        """Executor matched by request.executor_id gets access."""
        request = _make_request(user_id=10, status="В работе", executor_id=55)
        db = _make_db(request_obj=request)
        user = _make_user(user_id=55, roles=["executor"])

        result = await check_request_access("260401-001", db, user)
        assert result is request

    async def test_executor_via_assignment_has_access(self):
        """Executor matched by active RequestAssignment gets access."""
        request = _make_request(user_id=10, status="В работе", executor_id=None)
        assignment = MagicMock()  # truthy — assignment found

        db = AsyncMock(spec=AsyncSession)

        def _scalar_mock(value):
            r = MagicMock()
            r.scalar_one_or_none.return_value = value
            return r

        db.execute = AsyncMock(side_effect=[
            _scalar_mock(request),     # 1st: Request
            _scalar_mock(assignment),  # 2nd: RequestAssignment
        ])

        user = _make_user(user_id=55, roles=["executor"])

        result = await check_request_access("260401-001", db, user)
        assert result is request
