"""Unit tests for AuthService."""
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from uk_management_bot.services.auth_service import AuthService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(
    user_id=1,
    telegram_id=100,
    status="pending",
    role="applicant",
    roles='["applicant"]',
    active_role="applicant",
    language="ru",
):
    user = MagicMock()
    user.id = user_id
    user.telegram_id = telegram_id
    user.status = status
    user.role = role
    user.roles = roles
    user.active_role = active_role
    user.language = language
    user.created_at = None
    user.username = "testuser"
    user.first_name = "Test"
    user.last_name = "User"
    user.specialization = None
    return user


def _make_db(user=None):
    """Build a minimal Session mock with chained query pattern."""
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value.first.return_value = user
    q.filter.return_value.all.return_value = [user] if user else []
    q.all.return_value = [user] if user else []
    db.query.return_value = q
    return db


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:
    def test_stores_db_reference(self):
        db = MagicMock()
        service = AuthService(db)
        assert service.db is db


# ---------------------------------------------------------------------------
# get_or_create_user  (async)
# ---------------------------------------------------------------------------

class TestGetOrCreateUser:
    @pytest.mark.asyncio
    async def test_returns_existing_user(self):
        user = _make_user()
        db = _make_db(user=user)

        service = AuthService(db)
        result = await service.get_or_create_user(100, "user", "First", "Last")

        assert result is user
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_new_user_when_not_found(self):
        db = _make_db(user=None)

        service = AuthService(db)
        await service.get_or_create_user(200, "newuser", "New", "User")

        db.add.assert_called_once()
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_new_user_has_correct_defaults(self):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q

        created = []
        db.add.side_effect = lambda obj: created.append(obj)

        service = AuthService(db)
        await service.get_or_create_user(300, "u", "F", "L")

        assert len(created) == 1
        obj = created[0]
        assert obj.telegram_id == 300
        # PR-31/DB-060: legacy .role dropped — new users get roles JSON + active_role.
        assert obj.active_role == "applicant"
        assert obj.roles == '["applicant"]'
        assert obj.status == "pending"


# ---------------------------------------------------------------------------
# update_user_language  (async)
# ---------------------------------------------------------------------------

class TestUpdateUserLanguage:
    @pytest.mark.asyncio
    async def test_updates_language_for_supported_lang(self):
        user = _make_user()
        db = _make_db(user=user)

        with patch(
            "uk_management_bot.services.auth_service.settings"
        ) as mock_settings:
            mock_settings.SUPPORTED_LANGUAGES = ["ru", "uz"]
            service = AuthService(db)
            result = await service.update_user_language(100, "uz")

        assert result is True
        assert user.language == "uz"
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_returns_false_for_unsupported_lang(self):
        user = _make_user()
        db = _make_db(user=user)

        with patch(
            "uk_management_bot.services.auth_service.settings"
        ) as mock_settings:
            mock_settings.SUPPORTED_LANGUAGES = ["ru", "uz"]
            service = AuthService(db)
            result = await service.update_user_language(100, "en")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_user_not_found(self):
        db = _make_db(user=None)

        with patch(
            "uk_management_bot.services.auth_service.settings"
        ) as mock_settings:
            mock_settings.SUPPORTED_LANGUAGES = ["ru", "uz"]
            service = AuthService(db)
            result = await service.update_user_language(999, "ru")

        assert result is False


# ---------------------------------------------------------------------------
# auto_approve_user  (async)
# ---------------------------------------------------------------------------

class TestAutoApproveUser:
    @pytest.mark.asyncio
    async def test_approves_user_with_valid_role(self):
        user = _make_user(status="pending")
        db = _make_db(user=user)

        with patch(
            "uk_management_bot.services.auth_service.settings"
        ) as mock_settings:
            mock_settings.USER_ROLES = ["applicant", "executor", "manager"]
            service = AuthService(db)
            result = await service.auto_approve_user(100, "executor")

        assert result is True
        assert user.status == "approved"
        # PR-31/DB-060: legacy .role dropped — approval adds the role to roles JSON.
        assert "executor" in json.loads(user.roles)

    @pytest.mark.asyncio
    async def test_returns_false_for_invalid_role(self):
        db = _make_db()

        with patch(
            "uk_management_bot.services.auth_service.settings"
        ) as mock_settings:
            mock_settings.USER_ROLES = ["applicant", "executor", "manager"]
            service = AuthService(db)
            result = await service.auto_approve_user(100, "superadmin")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_user_not_found(self):
        db = _make_db(user=None)

        with patch(
            "uk_management_bot.services.auth_service.settings"
        ) as mock_settings:
            mock_settings.USER_ROLES = ["applicant", "executor", "manager"]
            service = AuthService(db)
            result = await service.auto_approve_user(999, "applicant")

        assert result is False


# ---------------------------------------------------------------------------
# block_user_by_telegram_id  (async)
# ---------------------------------------------------------------------------

class TestBlockUserByTelegramId:
    @pytest.mark.asyncio
    async def test_blocks_user(self):
        user = _make_user(status="approved")
        db = _make_db(user=user)

        service = AuthService(db)
        result = await service.block_user_by_telegram_id(100)

        assert result is True
        assert user.status == "blocked"

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self):
        db = _make_db(user=None)

        service = AuthService(db)
        result = await service.block_user_by_telegram_id(999)

        assert result is False


# ---------------------------------------------------------------------------
# approve_user  (sync)
# ---------------------------------------------------------------------------

class TestApproveUser:
    def _db_for_approve(self, target_user, approver_user=None):
        """DB mock where first query returns target_user, second returns approver_user."""
        db = MagicMock()
        calls = [0]

        def query_side_effect(model):
            q = MagicMock()
            calls[0] += 1
            if calls[0] == 1:
                # user by id lookup
                q.filter.return_value.first.return_value = target_user
            elif calls[0] == 2:
                # approver lookup
                q.filter.return_value.first.return_value = approver_user or MagicMock()
            else:
                # additional lookups (target_user again for audit)
                q.filter.return_value.first.return_value = target_user
            return q

        db.query.side_effect = query_side_effect
        db.execute.return_value.scalar.return_value = "2026-01-01"
        return db

    def test_approves_pending_user(self):
        user = _make_user(status="pending")
        db = self._db_for_approve(user)

        service = AuthService(db)
        result = service.approve_user(1, approved_by=2)

        assert result is True
        assert user.status == "approved"
        db.commit.assert_called()

    def test_returns_true_if_already_approved(self):
        user = _make_user(status="approved")
        db = _make_db(user=user)

        service = AuthService(db)
        result = service.approve_user(1, approved_by=2)

        assert result is True

    def test_returns_false_when_user_not_found(self):
        db = _make_db(user=None)

        service = AuthService(db)
        result = service.approve_user(999, approved_by=2)

        assert result is False

    def test_returns_false_on_db_exception(self):
        db = MagicMock()
        db.query.side_effect = Exception("DB error")

        service = AuthService(db)
        result = service.approve_user(1, approved_by=2)

        assert result is False
        db.rollback.assert_called()


# ---------------------------------------------------------------------------
# block_user  (sync)
# ---------------------------------------------------------------------------

class TestBlockUser:
    def _db_for_block(self, target_user):
        db = MagicMock()
        calls = [0]

        def query_side_effect(model):
            q = MagicMock()
            calls[0] += 1
            q.filter.return_value.first.return_value = target_user
            return q

        db.query.side_effect = query_side_effect
        db.execute.return_value.scalar.return_value = "2026-01-01"
        return db

    def test_blocks_approved_user(self):
        user = _make_user(status="approved")
        db = self._db_for_block(user)

        service = AuthService(db)
        result = service.block_user(1, blocked_by=2, reason="violation")

        assert result is True
        assert user.status == "blocked"

    def test_returns_true_if_already_blocked(self):
        user = _make_user(status="blocked")
        db = _make_db(user=user)

        service = AuthService(db)
        result = service.block_user(1, blocked_by=2)

        assert result is True

    def test_returns_false_when_user_not_found(self):
        db = _make_db(user=None)

        service = AuthService(db)
        result = service.block_user(999, blocked_by=2)

        assert result is False

    def test_rolls_back_on_exception(self):
        db = MagicMock()
        db.query.side_effect = Exception("DB error")

        service = AuthService(db)
        result = service.block_user(1, blocked_by=2)

        assert result is False
        db.rollback.assert_called()


# ---------------------------------------------------------------------------
# unblock_user  (sync)
# ---------------------------------------------------------------------------

class TestUnblockUser:
    def _db_for_unblock(self, target_user):
        db = MagicMock()

        def query_side_effect(model):
            q = MagicMock()
            q.filter.return_value.first.return_value = target_user
            return q

        db.query.side_effect = query_side_effect
        db.execute.return_value.scalar.return_value = "2026-01-01"
        return db

    def test_unblocks_blocked_user(self):
        user = _make_user(status="blocked")
        db = self._db_for_unblock(user)

        service = AuthService(db)
        result = service.unblock_user(1, unblocked_by=2)

        assert result is True
        assert user.status == "approved"

    def test_returns_false_when_not_blocked(self):
        user = _make_user(status="approved")
        db = _make_db(user=user)

        service = AuthService(db)
        result = service.unblock_user(1, unblocked_by=2)

        assert result is False

    def test_returns_false_when_user_not_found(self):
        db = _make_db(user=None)

        service = AuthService(db)
        result = service.unblock_user(999, unblocked_by=2)

        assert result is False


# ---------------------------------------------------------------------------
# assign_role  (sync)
# ---------------------------------------------------------------------------

class TestAssignRole:
    def _db_with_user_roles(self, user, roles_json):
        user.roles = roles_json
        db = MagicMock()

        def query_side_effect(model):
            q = MagicMock()
            q.filter.return_value.first.return_value = user
            return q

        db.query.side_effect = query_side_effect
        db.execute.return_value.scalar.return_value = "2026-01-01"
        return db

    def test_adds_new_role(self):
        user = _make_user(roles='["applicant"]', active_role="applicant")
        db = self._db_with_user_roles(user, '["applicant"]')

        service = AuthService(db)
        result = service.assign_role(1, "executor", assigned_by=2)

        assert result is True
        roles = json.loads(user.roles)
        assert "executor" in roles

    def test_returns_true_if_role_already_exists(self):
        user = _make_user(roles='["applicant", "executor"]', active_role="executor")
        db = self._db_with_user_roles(user, '["applicant", "executor"]')

        service = AuthService(db)
        result = service.assign_role(1, "executor", assigned_by=2)

        assert result is True

    def test_returns_false_for_invalid_role(self):
        user = _make_user()
        db = self._db_with_user_roles(user, '["applicant"]')

        service = AuthService(db)
        result = service.assign_role(1, "superadmin", assigned_by=2)

        assert result is False

    def test_returns_false_when_user_not_found(self):
        db = _make_db(user=None)

        service = AuthService(db)
        result = service.assign_role(999, "executor", assigned_by=2)

        assert result is False


# ---------------------------------------------------------------------------
# remove_role  (sync)
# ---------------------------------------------------------------------------

class TestRemoveRole:
    def _db_with_user_roles(self, user):
        db = MagicMock()

        def query_side_effect(model):
            q = MagicMock()
            q.filter.return_value.first.return_value = user
            return q

        db.query.side_effect = query_side_effect
        db.execute.return_value.scalar.return_value = "2026-01-01"
        return db

    def test_removes_role_from_multi_role_user(self):
        user = _make_user(roles='["applicant", "executor"]', active_role="applicant")
        db = self._db_with_user_roles(user)

        service = AuthService(db)
        result = service.remove_role(1, "executor", removed_by=2)

        assert result is True
        roles = json.loads(user.roles)
        assert "executor" not in roles

    def test_returns_false_when_removing_last_role(self):
        user = _make_user(roles='["applicant"]', active_role="applicant")
        db = self._db_with_user_roles(user)

        service = AuthService(db)
        result = service.remove_role(1, "applicant", removed_by=2)

        assert result is False

    def test_returns_true_when_role_not_present(self):
        user = _make_user(roles='["applicant"]', active_role="applicant")
        db = self._db_with_user_roles(user)

        service = AuthService(db)
        result = service.remove_role(1, "executor", removed_by=2)

        assert result is True

    def test_switches_active_role_when_active_removed(self):
        user = _make_user(roles='["executor", "manager"]', active_role="executor")
        db = self._db_with_user_roles(user)

        service = AuthService(db)
        service.remove_role(1, "executor", removed_by=2)

        assert user.active_role != "executor"


# ---------------------------------------------------------------------------
# get_user_roles  (sync)
# ---------------------------------------------------------------------------

class TestGetUserRoles:
    def test_returns_roles_list(self):
        user = _make_user(roles='["applicant", "executor"]')
        db = _make_db(user=user)

        service = AuthService(db)
        roles = service.get_user_roles(1)

        assert roles == ["applicant", "executor"]

    def test_returns_empty_when_user_not_found(self):
        db = _make_db(user=None)

        service = AuthService(db)
        roles = service.get_user_roles(999)

        assert roles == []

    def test_non_json_string_parsed_as_csv(self):
        # COD-01: get_user_roles delegates to the canonical parse_roles_safe,
        # which treats a non-JSON string as CSV. A single garbage token yields a
        # single-element list (harmless — it matches no real role downstream).
        # Previously the inline json.loads raised and returned [].
        user = _make_user(roles="not-json")
        db = _make_db(user=user)

        service = AuthService(db)
        roles = service.get_user_roles(1)

        assert roles == ["not-json"]

    def test_csv_roles_parsed(self):
        # COD-01: legacy CSV roles column now parses correctly (was [] before).
        user = _make_user(roles="executor,manager")
        db = _make_db(user=user)

        service = AuthService(db)
        assert service.get_user_roles(1) == ["executor", "manager"]

    def test_returns_empty_when_roles_is_none(self):
        user = _make_user(roles=None)
        db = _make_db(user=user)

        service = AuthService(db)
        roles = service.get_user_roles(1)

        assert roles == []


# ---------------------------------------------------------------------------
# is_user_approved / is_user_manager / is_user_executor  (async)
# ---------------------------------------------------------------------------

class TestStatusChecks:
    @pytest.mark.asyncio
    async def test_is_user_approved_true(self):
        user = _make_user(status="approved")
        db = _make_db(user=user)

        service = AuthService(db)
        assert await service.is_user_approved(100) is True

    @pytest.mark.asyncio
    async def test_is_user_approved_false_for_pending(self):
        user = _make_user(status="pending")
        db = _make_db(user=user)

        service = AuthService(db)
        assert await service.is_user_approved(100) is False

    @pytest.mark.asyncio
    async def test_is_user_approved_false_when_not_found(self):
        db = _make_db(user=None)

        service = AuthService(db)
        # Returns None (falsy) when user not found — not strictly False
        assert not await service.is_user_approved(999)

    @pytest.mark.asyncio
    async def test_is_user_manager_true(self):
        user = _make_user(
            status="approved",
            role="manager",
            roles='["manager"]',
            active_role="manager",
        )
        db = _make_db(user=user)

        service = AuthService(db)
        assert await service.is_user_manager(100) is True

    @pytest.mark.asyncio
    async def test_is_user_manager_false_for_applicant(self):
        user = _make_user(status="approved", role="applicant", roles='["applicant"]')
        db = _make_db(user=user)

        service = AuthService(db)
        assert await service.is_user_manager(100) is False

    @pytest.mark.asyncio
    async def test_is_user_executor_true_via_active_role(self):
        user = _make_user(status="approved", active_role="executor")
        db = _make_db(user=user)

        service = AuthService(db)
        assert await service.is_user_executor(100) is True

    @pytest.mark.asyncio
    async def test_is_user_executor_false_when_not_approved(self):
        user = _make_user(status="pending", active_role="executor")
        db = _make_db(user=user)

        service = AuthService(db)
        assert await service.is_user_executor(100) is False

    @pytest.mark.asyncio
    async def test_is_user_manager_unusable_roles_falls_back_to_active_role(self):
        """COD-01: неразбираемая строка ролей → роль не найдена среди распарсенных
        (canonical parse_roles_safe трактует её как CSV-мусор, "manager" там нет),
        поэтому падаем в legacy_primary_role() → active_role="manager" → True.
        Прежний ARCH-04 warning убран: под каноническим парсером «битого JSON»
        как ошибки больше нет (строка — валидный CSV).
        """
        user = _make_user(status="approved", roles="{broken json", active_role="manager")
        db = _make_db(user=user)

        service = AuthService(db)
        assert await service.is_user_manager(100) is True

    @pytest.mark.asyncio
    async def test_is_user_executor_unusable_roles_falls_back(self):
        """COD-01: та же семантика для is_user_executor. active_role="applicant"
        (не executor), в распарсенных ролях executor'а нет → False, без warning.
        """
        user = _make_user(status="approved", roles="{broken json", active_role="applicant")
        db = _make_db(user=user)

        service = AuthService(db)
        assert await service.is_user_executor(100) is False

    @pytest.mark.asyncio
    async def test_is_user_manager_csv_roles(self):
        """COD-01: legacy CSV-роли теперь распознаются (раньше давали False)."""
        user = _make_user(status="approved", roles="applicant,manager", active_role="manager")
        db = _make_db(user=user)

        service = AuthService(db)
        assert await service.is_user_manager(100) is True


# ---------------------------------------------------------------------------
# get_all_users / get_users_by_role  (async)
# ---------------------------------------------------------------------------

class TestGetUsers:
    @pytest.mark.asyncio
    async def test_get_all_users_returns_list(self):
        users = [_make_user(user_id=i, telegram_id=100 + i) for i in range(3)]
        db = MagicMock()
        db.query.return_value.all.return_value = users

        service = AuthService(db)
        result = await service.get_all_users()

        assert result == users

    @pytest.mark.asyncio
    async def test_get_users_by_role_calls_filter(self):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.all.return_value = []
        db.query.return_value = q

        service = AuthService(db)
        await service.get_users_by_role("executor")

        db.query.assert_called()


# ---------------------------------------------------------------------------
# set_active_role  (async)
# ---------------------------------------------------------------------------

class TestSetActiveRole:
    @pytest.mark.asyncio
    async def test_sets_role_when_in_list(self):
        user = _make_user(roles='["applicant", "executor"]')
        db = _make_db(user=user)

        service = AuthService(db)
        result = await service.set_active_role(100, "executor")

        assert result is True
        assert user.active_role == "executor"

    @pytest.mark.asyncio
    async def test_returns_false_when_role_not_in_list(self):
        user = _make_user(roles='["applicant"]')
        db = _make_db(user=user)

        service = AuthService(db)
        result = await service.set_active_role(100, "manager")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_user_not_found(self):
        db = _make_db(user=None)

        service = AuthService(db)
        result = await service.set_active_role(999, "executor")

        assert result is False


# ---------------------------------------------------------------------------
# Trust invariant: manager/admin ⇒ verification_status = "verified"
# ---------------------------------------------------------------------------

class TestTrustVerificationInvariant:
    """Менеджер/админ — корень доверия: при выдаче роли сразу verified,
    чтобы они не зависали в очереди одобрения (кнопка защищена guard'ом)."""

    def _db_with_user(self, user):
        db = MagicMock()

        def query_side_effect(model):
            q = MagicMock()
            q.filter.return_value.first.return_value = user
            return q

        db.query.side_effect = query_side_effect
        db.execute.return_value.scalar.return_value = "2026-01-01"
        return db

    def test_assign_manager_role_marks_verified(self):
        user = _make_user(roles='["applicant"]', active_role="applicant")
        user.verification_status = "pending"
        db = self._db_with_user(user)

        service = AuthService(db)
        result = service.assign_role(1, "manager", assigned_by=2)

        assert result is True
        assert user.verification_status == "verified"

    def test_assign_executor_role_does_not_verify(self):
        user = _make_user(roles='["applicant"]', active_role="applicant")
        user.verification_status = "pending"
        db = self._db_with_user(user)

        service = AuthService(db)
        result = service.assign_role(1, "executor", assigned_by=2)

        assert result is True
        assert user.verification_status == "pending"

    @pytest.mark.asyncio
    async def test_invite_join_as_manager_marks_verified(self):
        user = _make_user(roles=None, active_role=None)
        user.verification_status = "pending"
        service = AuthService(MagicMock())
        service.get_or_create_user = AsyncMock(return_value=user)

        result = await service.process_invite_join(100, {"role": "manager"})

        assert result is user
        assert user.verification_status == "verified"

    @pytest.mark.asyncio
    async def test_invite_join_as_executor_stays_pending(self):
        user = _make_user(roles=None, active_role=None)
        user.verification_status = "pending"
        service = AuthService(MagicMock())
        service.get_or_create_user = AsyncMock(return_value=user)

        result = await service.process_invite_join(100, {"role": "executor"})

        assert result is user
        assert user.verification_status == "pending"

    @pytest.mark.asyncio
    async def test_make_admin_by_password_marks_verified(self):
        user = _make_user(roles='["applicant"]', active_role="applicant")
        user.verification_status = "pending"
        db = self._db_with_user(user)
        service = AuthService(db)

        with patch("uk_management_bot.config.settings.settings") as mock_settings:
            mock_settings.ADMIN_PASSWORD = "secret"
            result = await service.make_admin_by_password(100, "secret")

        assert result is True
        assert user.verification_status == "verified"

    @pytest.mark.asyncio
    async def test_make_admin_by_password_grants_only_manager(self):
        """SEC-06 (least privilege): /admin выдаёт только ["manager"],
        а не весь набор ролей скопом."""
        user = _make_user(roles='["applicant"]', active_role="applicant")
        user.verification_status = "pending"
        db = self._db_with_user(user)
        service = AuthService(db)

        with patch("uk_management_bot.config.settings.settings") as mock_settings:
            mock_settings.ADMIN_PASSWORD = "secret"
            result = await service.make_admin_by_password(100, "secret")

        assert result is True
        assert user.roles == '["manager"]'
        assert user.active_role == "manager"
