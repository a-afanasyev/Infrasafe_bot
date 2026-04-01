"""
Unit tests for uk_management_bot/api/profile/router.py

Tests cover:
- switch_role()  — valid role switch, invalid role raises 422
- get_my_apartments() — returns mapped apartment data
- get_profile() — returns ProfileOut
- ProfileOut.from_user() — pure instantiation
- update_profile() — language and email validation
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


# ── Helpers ─────────────────────────────────────────────────────────


def _make_user(
    *,
    id: int = 1,
    telegram_id: int = 100,
    roles: str = '["applicant"]',
    role: str = "applicant",
    active_role: str | None = "applicant",
    status: str = "approved",
    language: str = "ru",
    email: str | None = None,
    first_name: str = "Ivan",
    last_name: str = "Petrov",
    phone: str | None = None,
    verification_status: str = "pending",
):
    user = MagicMock()
    user.id = id
    user.telegram_id = telegram_id
    user.roles = roles
    user.role = role
    user.active_role = active_role
    user.status = status
    user.language = language
    user.email = email
    user.first_name = first_name
    user.last_name = last_name
    user.phone = phone
    user.verification_status = verification_status
    return user


# ── switch_role ──────────────────────────────────────────────────────


class TestSwitchRole:
    @pytest.mark.asyncio
    async def test_valid_role_switch_returns_updated_role(self):
        from uk_management_bot.api.profile.router import switch_role, RoleSwitchBody

        user = _make_user(roles='["applicant", "executor"]')
        db_user = MagicMock()
        db_user.active_role = "applicant"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = db_user
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        body = RoleSwitchBody(active_role="executor")
        result = await switch_role(body=body, user=user, db=mock_db)

        assert result.active_role == "executor"
        assert "executor" in result.roles
        assert db_user.active_role == "executor"
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_role_raises_422(self):
        from fastapi import HTTPException
        from uk_management_bot.api.profile.router import switch_role, RoleSwitchBody

        user = _make_user(roles='["applicant"]', role="applicant")
        mock_db = AsyncMock()

        body = RoleSwitchBody(active_role="manager")

        with pytest.raises(HTTPException) as exc_info:
            await switch_role(body=body, user=user, db=mock_db)

        assert exc_info.value.status_code == 422
        assert "manager" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_switch_to_same_role_succeeds(self):
        from uk_management_bot.api.profile.router import switch_role, RoleSwitchBody

        user = _make_user(roles='["applicant"]', active_role="applicant")
        db_user = MagicMock()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = db_user
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        body = RoleSwitchBody(active_role="applicant")
        result = await switch_role(body=body, user=user, db=mock_db)

        assert result.active_role == "applicant"

    @pytest.mark.asyncio
    async def test_manager_role_switch_updates_db_user(self):
        from uk_management_bot.api.profile.router import switch_role, RoleSwitchBody

        user = _make_user(
            roles='["executor", "manager"]',
            active_role="executor",
        )
        db_user = MagicMock()
        db_user.active_role = "executor"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = db_user
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        body = RoleSwitchBody(active_role="manager")
        await switch_role(body=body, user=user, db=mock_db)

        assert db_user.active_role == "manager"

    @pytest.mark.asyncio
    async def test_empty_role_raises_422(self):
        from fastapi import HTTPException
        from uk_management_bot.api.profile.router import switch_role, RoleSwitchBody

        user = _make_user(roles='["applicant"]', role="applicant")
        mock_db = AsyncMock()

        body = RoleSwitchBody(active_role="")

        with pytest.raises(HTTPException) as exc_info:
            await switch_role(body=body, user=user, db=mock_db)

        assert exc_info.value.status_code == 422


# ── get_my_apartments ────────────────────────────────────────────────


class TestGetMyApartments:
    @pytest.mark.asyncio
    async def test_returns_mapped_apartment_list(self):
        from uk_management_bot.api.profile.router import get_my_apartments

        user = _make_user(id=7)

        # Simulate (Apartment, Building.address, Yard.name) rows
        apt = MagicMock()
        apt.id = 10
        apt.apartment_number = "42"

        rows = [(apt, "ул. Ленина 1", "Двор А")]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = rows
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_my_apartments(user=user, db=mock_db)

        assert len(result) == 1
        item = result[0]
        assert item["apartment_id"] == 10
        assert item["apartment_number"] == "42"
        assert item["building_address"] == "ул. Ленина 1"
        assert item["yard_name"] == "Двор А"
        assert "42" in item["full_address"]

    @pytest.mark.asyncio
    async def test_empty_apartments_returns_empty_list(self):
        from uk_management_bot.api.profile.router import get_my_apartments

        user = _make_user(id=7)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_my_apartments(user=user, db=mock_db)

        assert result == []

    @pytest.mark.asyncio
    async def test_multiple_apartments_all_returned(self):
        from uk_management_bot.api.profile.router import get_my_apartments

        user = _make_user(id=3)

        rows = []
        for i in range(3):
            apt = MagicMock()
            apt.id = i + 1
            apt.apartment_number = str(i + 10)
            rows.append((apt, f"ул. Тест {i}", "Двор Б"))

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = rows
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_my_apartments(user=user, db=mock_db)

        assert len(result) == 3
        ids = [r["apartment_id"] for r in result]
        assert ids == [1, 2, 3]


# ── get_profile ──────────────────────────────────────────────────────


class TestGetProfile:
    @pytest.mark.asyncio
    async def test_returns_profile_out(self):
        from uk_management_bot.api.profile.router import get_profile, ProfileOut

        user = _make_user(
            id=5,
            telegram_id=12345,
            roles='["manager"]',
            role="manager",
            active_role="manager",
            status="approved",
        )

        result = await get_profile(user=user)

        assert isinstance(result, ProfileOut)
        assert result.id == 5
        assert result.telegram_id == 12345
        assert "manager" in result.roles
        assert result.active_role == "manager"
        assert result.status == "approved"

    @pytest.mark.asyncio
    async def test_profile_out_from_user_classmethod(self):
        from uk_management_bot.api.profile.router import ProfileOut

        user = _make_user(
            id=2,
            telegram_id=9999,
            roles='["applicant", "executor"]',
            role="applicant",
            active_role="executor",
            status="approved",
            first_name="Алексей",
            last_name="Иванов",
            language="uz",
        )

        profile = ProfileOut.from_user(user)

        assert profile.id == 2
        assert profile.first_name == "Алексей"
        assert profile.language == "uz"
        assert profile.roles == ["applicant", "executor"]
        assert profile.active_role == "executor"


# ── update_profile ───────────────────────────────────────────────────


class TestUpdateProfile:
    @pytest.mark.asyncio
    async def test_invalid_language_raises_400(self):
        from fastapi import HTTPException
        from uk_management_bot.api.profile.router import update_profile, UpdateProfileBody

        user = _make_user()
        mock_db = AsyncMock()
        db_user = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = db_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        body = UpdateProfileBody(language="fr")  # not in {"ru", "uz"}

        with pytest.raises(HTTPException) as exc_info:
            await update_profile(body=body, db=mock_db, user=user)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_email_raises_400(self):
        from fastapi import HTTPException
        from uk_management_bot.api.profile.router import update_profile, UpdateProfileBody

        user = _make_user()
        mock_db = AsyncMock()
        db_user = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = db_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        body = UpdateProfileBody(email="notanemail")

        with pytest.raises(HTTPException) as exc_info:
            await update_profile(body=body, db=mock_db, user=user)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_valid_language_updates_db_user(self):
        from uk_management_bot.api.profile.router import update_profile, UpdateProfileBody

        user = _make_user()
        mock_db = AsyncMock()
        db_user = MagicMock()
        db_user.language = "ru"
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = db_user
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        body = UpdateProfileBody(language="uz")
        result = await update_profile(body=body, db=mock_db, user=user)

        assert result == {"ok": True}
        assert db_user.language == "uz"

    @pytest.mark.asyncio
    async def test_valid_email_updates_db_user(self):
        from uk_management_bot.api.profile.router import update_profile, UpdateProfileBody

        user = _make_user()
        mock_db = AsyncMock()
        db_user = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = db_user
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        body = UpdateProfileBody(email="new@example.com")
        result = await update_profile(body=body, db=mock_db, user=user)

        assert result == {"ok": True}
        assert db_user.email == "new@example.com"
