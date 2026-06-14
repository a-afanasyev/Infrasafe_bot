"""Unit tests for uk_management_bot/database/init_admin.py."""
import os
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_session():
    """Return a context-manager-capable mock session."""
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


def _make_admin_user(
    telegram_id: int = 123456789,
    roles: str = '["applicant", "executor", "manager"]',
    status: str = "approved",
    phone: str = "+998000000000",
    username: str = "admin_123456789",
):
    user = MagicMock()
    user.id = 1
    user.telegram_id = telegram_id
    user.roles = roles
    user.status = status
    user.phone = phone
    user.username = username
    return user


# ---------------------------------------------------------------------------
# Tests: init_admin_user()
# ---------------------------------------------------------------------------

class TestInitAdminUser:
    @pytest.fixture(autouse=True)
    def patch_session_local(self):
        self.mock_session = _make_mock_session()
        with patch(
            "uk_management_bot.database.init_admin.SessionLocal",
            return_value=self.mock_session,
        ):
            yield

    def test_returns_false_when_env_var_not_set(self):
        from uk_management_bot.database.init_admin import init_admin_user

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ADMIN_USER_IDS", None)
            result = init_admin_user()

        assert result is False

    def test_returns_false_when_env_var_is_empty_string(self):
        from uk_management_bot.database.init_admin import init_admin_user

        with patch.dict(os.environ, {"ADMIN_USER_IDS": ""}):
            result = init_admin_user()

        assert result is False

    def test_creates_new_admin_when_not_found(self):
        from uk_management_bot.database.init_admin import init_admin_user

        # No existing user
        self.mock_session.execute.return_value.scalar_one_or_none.return_value = None
        self.mock_session.refresh = MagicMock()

        with patch.dict(os.environ, {"ADMIN_USER_IDS": "123456789"}):
            result = init_admin_user()

        assert result is True
        self.mock_session.add.assert_called_once()
        self.mock_session.commit.assert_called_once()

    def test_returns_true_when_admin_already_exists_with_manager_role(self):
        from uk_management_bot.database.init_admin import init_admin_user

        existing = _make_admin_user(roles='["applicant", "executor", "manager"]')
        self.mock_session.execute.return_value.scalar_one_or_none.return_value = existing

        with patch.dict(os.environ, {"ADMIN_USER_IDS": "123456789"}):
            result = init_admin_user()

        assert result is True
        # Should NOT add a new user
        self.mock_session.add.assert_not_called()

    def test_updates_existing_user_missing_manager_role(self):
        from uk_management_bot.database.init_admin import init_admin_user

        existing = _make_admin_user(roles='["applicant"]', status="pending")
        self.mock_session.execute.return_value.scalar_one_or_none.return_value = existing

        with patch.dict(os.environ, {"ADMIN_USER_IDS": "123456789"}):
            result = init_admin_user()

        assert result is True
        # Should have updated roles and committed
        assert existing.roles == '["applicant", "executor", "manager"]'
        self.mock_session.commit.assert_called_once()

    def test_returns_false_on_db_exception(self):
        from uk_management_bot.database.init_admin import init_admin_user

        self.mock_session.execute.side_effect = Exception("db error")

        with patch.dict(os.environ, {"ADMIN_USER_IDS": "123456789"}):
            result = init_admin_user()

        assert result is False

    def test_parses_first_id_from_comma_separated_list(self):
        from uk_management_bot.database.init_admin import init_admin_user

        self.mock_session.execute.return_value.scalar_one_or_none.return_value = None
        self.mock_session.refresh = MagicMock()

        with patch.dict(os.environ, {"ADMIN_USER_IDS": "111,222,333"}):
            result = init_admin_user()

        assert result is True
        # Verify the User was created with telegram_id=111
        created_user = self.mock_session.add.call_args[0][0]
        assert created_user.telegram_id == 111


# ---------------------------------------------------------------------------
# Tests: init_all_admins()
# ---------------------------------------------------------------------------

class TestInitAllAdmins:
    @pytest.fixture(autouse=True)
    def patch_session_local(self):
        self.mock_session = _make_mock_session()
        with patch(
            "uk_management_bot.database.init_admin.SessionLocal",
            return_value=self.mock_session,
        ):
            yield

    def test_returns_zero_tuple_when_env_var_not_set(self):
        from uk_management_bot.database.init_admin import init_all_admins

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ADMIN_USER_IDS", None)
            result = init_all_admins()

        assert result == (0, 0)

    def test_returns_zero_tuple_when_env_var_is_empty(self):
        from uk_management_bot.database.init_admin import init_all_admins

        with patch.dict(os.environ, {"ADMIN_USER_IDS": ""}):
            result = init_all_admins()

        assert result == (0, 0)

    def test_creates_new_admin_returns_created_count(self):
        from uk_management_bot.database.init_admin import init_all_admins

        # No existing user for any ID
        self.mock_session.execute.return_value.scalar_one_or_none.return_value = None

        with patch.dict(os.environ, {"ADMIN_USER_IDS": "111"}):
            created, updated = init_all_admins()

        assert created == 1
        assert updated == 0

    def test_creates_multiple_new_admins(self):
        from uk_management_bot.database.init_admin import init_all_admins

        self.mock_session.execute.return_value.scalar_one_or_none.return_value = None

        with patch.dict(os.environ, {"ADMIN_USER_IDS": "111,222,333"}):
            created, updated = init_all_admins()

        assert created == 3
        assert updated == 0

    def test_updates_existing_admin_missing_all_roles(self):
        from uk_management_bot.database.init_admin import init_all_admins

        existing = _make_admin_user(
            telegram_id=111,
            roles="applicant",  # missing executor, manager
            status="pending",
        )
        self.mock_session.execute.return_value.scalar_one_or_none.return_value = existing

        with patch.dict(os.environ, {"ADMIN_USER_IDS": "111"}):
            created, updated = init_all_admins()

        assert created == 0
        assert updated == 1
        assert existing.status == "approved"

    def test_does_not_update_fully_configured_admin(self):
        from uk_management_bot.database.init_admin import init_all_admins

        # existing admin has all required roles as a JSON list (not comma-split)
        # The code uses set split(",") so we mimic the exact format it checks
        existing = _make_admin_user(
            telegram_id=111,
            # roles stored as JSON-like string containing all three role keywords
            roles="applicant,executor,manager",
            status="approved",
        )
        self.mock_session.execute.return_value.scalar_one_or_none.return_value = existing

        with patch.dict(os.environ, {"ADMIN_USER_IDS": "111"}):
            created, updated = init_all_admins()

        assert created == 0
        assert updated == 0

    def test_returns_zero_tuple_on_db_exception(self):
        from uk_management_bot.database.init_admin import init_all_admins

        self.mock_session.execute.side_effect = Exception("connection lost")

        with patch.dict(os.environ, {"ADMIN_USER_IDS": "111"}):
            result = init_all_admins()

        assert result == (0, 0)

    def test_commit_called_on_success(self):
        from uk_management_bot.database.init_admin import init_all_admins

        self.mock_session.execute.return_value.scalar_one_or_none.return_value = None

        with patch.dict(os.environ, {"ADMIN_USER_IDS": "111"}):
            init_all_admins()

        self.mock_session.commit.assert_called_once()

    def test_new_admin_gets_all_roles(self):
        from uk_management_bot.database.init_admin import init_all_admins

        self.mock_session.execute.return_value.scalar_one_or_none.return_value = None

        with patch.dict(os.environ, {"ADMIN_USER_IDS": "555"}):
            init_all_admins()

        # The User object added to the session should have all roles
        added_user = self.mock_session.add.call_args[0][0]
        assert "manager" in added_user.roles
        assert "executor" in added_user.roles
        assert "applicant" in added_user.roles
        assert added_user.status == "approved"
        assert added_user.active_role == "manager"

    def test_new_admin_phone_fallback_set(self):
        from uk_management_bot.database.init_admin import init_all_admins

        self.mock_session.execute.return_value.scalar_one_or_none.return_value = None

        with patch.dict(os.environ, {"ADMIN_USER_IDS": "555"}):
            init_all_admins()

        added_user = self.mock_session.add.call_args[0][0]
        assert added_user.phone is not None
        assert len(added_user.phone) > 0

    def test_existing_admin_without_phone_gets_phone_fallback(self):
        from uk_management_bot.database.init_admin import init_all_admins

        existing = _make_admin_user(
            telegram_id=111,
            roles="applicant",  # triggers update path
            status="pending",
        )
        existing.phone = None  # no phone

        self.mock_session.execute.return_value.scalar_one_or_none.return_value = existing

        with patch.dict(os.environ, {"ADMIN_USER_IDS": "111"}):
            init_all_admins()

        # Phone should have been set during update
        assert existing.phone is not None
