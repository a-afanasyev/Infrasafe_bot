"""Unit tests for AsyncRequestService."""
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from uk_management_bot.services.async_request_service import AsyncRequestService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(
    user_id=1,
    telegram_id=100,
    role="applicant",
    roles='["applicant"]',
    active_role="applicant",
    status="approved",
):
    u = MagicMock()
    u.id = user_id
    u.telegram_id = telegram_id
    u.role = role
    u.roles = roles
    u.active_role = active_role
    u.status = status
    u.notes = None
    return u


def _make_request(
    request_number="260401-001",
    user_id=1,
    status="Новая",
    executor_id=None,
    notes=None,
):
    r = MagicMock()
    r.request_number = request_number
    r.user_id = user_id
    r.status = status
    r.executor_id = executor_id
    r.notes = notes
    r.updated_at = None
    r.created_at = MagicMock()
    r.completed_at = None
    r.user = _make_user()
    r.media_files = []
    return r


def _make_async_db():
    """Build minimal AsyncSession mock."""
    db = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:
    def test_stores_db_reference(self):
        db = AsyncMock()
        service = AsyncRequestService(db)
        assert service.db is db


# ---------------------------------------------------------------------------
# is_transition_allowed  (pure sync method)
# ---------------------------------------------------------------------------

class TestIsTransitionAllowed:
    def setup_method(self):
        self.service = AsyncRequestService(AsyncMock())

    def test_new_to_in_work_allowed(self):
        assert self.service.is_transition_allowed("Новая", "В работе") is True

    def test_new_to_cancelled_allowed(self):
        assert self.service.is_transition_allowed("Новая", "Отменена") is True

    def test_completed_to_accepted_allowed(self):
        assert self.service.is_transition_allowed("Выполнена", "Принято") is True

    def test_completed_to_clarification_not_allowed(self):
        assert self.service.is_transition_allowed("Выполнена", "Уточнение") is False

    def test_accepted_has_no_allowed_transitions(self):
        assert self.service.is_transition_allowed("Принято", "В работе") is False
        assert self.service.is_transition_allowed("Принято", "Отменена") is False

    def test_cancelled_has_no_allowed_transitions(self):
        assert self.service.is_transition_allowed("Отменена", "Новая") is False

    def test_unknown_status_returns_false(self):
        assert self.service.is_transition_allowed("Unknown", "Новая") is False

    def test_in_work_to_completed_allowed(self):
        assert self.service.is_transition_allowed("В работе", "Выполнена") is True

    def test_in_work_to_purchase_allowed(self):
        assert self.service.is_transition_allowed("В работе", "Закуп") is True

    def test_completed_to_executed_allowed(self):
        # return flow for applicant
        assert self.service.is_transition_allowed("Выполнена", "Исполнено") is True

    def test_executed_to_completed_allowed(self):
        # re-confirm by manager
        assert self.service.is_transition_allowed("Исполнено", "Выполнена") is True


# ---------------------------------------------------------------------------
# is_role_allowed_for_transition  (pure sync method)
# ---------------------------------------------------------------------------

class TestIsRoleAllowedForTransition:
    def setup_method(self):
        self.service = AsyncRequestService(AsyncMock())

    def _actor(self, role, active_role=None, roles=None, user_id=1):
        actor = MagicMock()
        actor.id = user_id
        actor.role = role
        actor.active_role = active_role or role
        actor.roles = roles or json.dumps([role])
        return actor

    def _request(self, user_id=1, status="Новая"):
        r = MagicMock()
        r.user_id = user_id
        r.status = status
        return r

    def test_applicant_can_cancel_own_new_request(self):
        actor = self._actor("applicant", user_id=1)
        req = self._request(user_id=1, status="Новая")
        assert self.service.is_role_allowed_for_transition(actor, req, "Отменена") is True

    def test_applicant_cannot_cancel_others_request(self):
        actor = self._actor("applicant", user_id=1)
        req = self._request(user_id=2, status="Новая")
        assert self.service.is_role_allowed_for_transition(actor, req, "Отменена") is False

    def test_applicant_can_accept_own_completed_request(self):
        actor = self._actor("applicant", user_id=1)
        req = self._request(user_id=1, status="Выполнена")
        assert self.service.is_role_allowed_for_transition(actor, req, "Принято") is True

    def test_applicant_cannot_set_in_work(self):
        actor = self._actor("applicant", user_id=1)
        req = self._request(user_id=1, status="Новая")
        assert self.service.is_role_allowed_for_transition(actor, req, "В работе") is False

    def test_executor_can_set_in_work(self):
        actor = self._actor("executor")
        req = self._request(user_id=2, status="Новая")
        assert self.service.is_role_allowed_for_transition(actor, req, "В работе") is True

    def test_executor_can_set_completed(self):
        actor = self._actor("executor")
        req = self._request(user_id=2, status="В работе")
        assert self.service.is_role_allowed_for_transition(actor, req, "Выполнена") is True

    def test_executor_cannot_accept(self):
        actor = self._actor("executor")
        req = self._request(user_id=2, status="Выполнена")
        assert self.service.is_role_allowed_for_transition(actor, req, "Принято") is False

    def test_manager_can_do_anything(self):
        actor = self._actor("manager", active_role="manager", roles='["manager"]')
        req = self._request(user_id=2, status="Новая")
        for status in ["В работе", "Выполнена", "Принято", "Отменена"]:
            assert self.service.is_role_allowed_for_transition(actor, req, status) is True

    def test_unknown_role_cannot_transition(self):
        actor = self._actor("guest", active_role="guest", roles='["guest"]')
        req = self._request(user_id=2, status="Новая")
        assert self.service.is_role_allowed_for_transition(actor, req, "В работе") is False


# ---------------------------------------------------------------------------
# get_user_requests  (async)
# ---------------------------------------------------------------------------

class TestGetUserRequests:
    @pytest.mark.asyncio
    async def test_returns_empty_list_on_exception(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("DB error"))

        service = AsyncRequestService(db)
        result = await service.get_user_requests(1)

        assert result == []

    @pytest.mark.asyncio
    async def test_calls_execute_with_query(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        service = AsyncRequestService(db)
        result = await service.get_user_requests(1)

        db.execute.assert_called_once()
        assert result == []


# ---------------------------------------------------------------------------
# get_request_by_number  (async)
# ---------------------------------------------------------------------------

class TestGetRequestByNumber:
    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("DB error"))

        service = AsyncRequestService(db)
        result = await service.get_request_by_number("260401-001")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_request_when_found(self):
        req = _make_request()
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = req
        db.execute = AsyncMock(return_value=mock_result)

        service = AsyncRequestService(db)
        result = await service.get_request_by_number("260401-001")

        assert result is req


# ---------------------------------------------------------------------------
# update_request_status  (async)
# ---------------------------------------------------------------------------

class TestUpdateRequestStatus:
    @pytest.mark.asyncio
    async def test_returns_none_for_invalid_status(self):
        db = AsyncMock()
        service = AsyncRequestService(db)
        result = await service.update_request_status("260401-001", "InvalidStatus")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_request_not_found(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        service = AsyncRequestService(db)
        result = await service.update_request_status("260401-001", "В работе")
        assert result is None

    @pytest.mark.asyncio
    async def test_updates_status_successfully(self):
        req = _make_request(status="Новая")
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = req
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        service = AsyncRequestService(db)
        result = await service.update_request_status("260401-001", "В работе")

        assert req.status == "В работе"

    @pytest.mark.asyncio
    async def test_no_op_update_with_notes_appends_note(self):
        req = _make_request(status="Новая", notes=None)
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = req
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        service = AsyncRequestService(db)
        await service.update_request_status("260401-001", "Новая", notes="Extra info")

        assert "Extra info" in req.notes

    @pytest.mark.asyncio
    async def test_sets_completed_at_when_completed(self):
        req = _make_request(status="В работе")
        req.completed_at = None
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = req
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        service = AsyncRequestService(db)
        await service.update_request_status("260401-001", "Выполнена")

        assert req.completed_at is not None


# ---------------------------------------------------------------------------
# delete_request  (async)
# ---------------------------------------------------------------------------

class TestDeleteRequest:
    @pytest.mark.asyncio
    async def test_returns_false_when_request_not_found(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        service = AsyncRequestService(db)
        result = await service.delete_request("260401-001", user_id=1)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("DB error"))

        service = AsyncRequestService(db)
        result = await service.delete_request("260401-001", user_id=1)

        assert result is False

    @pytest.mark.asyncio
    async def test_deletes_own_request(self):
        req = _make_request(user_id=1)
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = req
        db.execute = AsyncMock(return_value=mock_result)
        db.delete = AsyncMock()
        db.flush = AsyncMock()

        service = AsyncRequestService(db)
        result = await service.delete_request("260401-001", user_id=1)

        assert result is True
        db.delete.assert_called_once_with(req)


# ---------------------------------------------------------------------------
# get_user_by_telegram_id  (async)
# ---------------------------------------------------------------------------

class TestGetUserByTelegramId:
    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("DB error"))

        service = AsyncRequestService(db)
        result = await service.get_user_by_telegram_id(100)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_user_when_found(self):
        user = _make_user()
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(return_value=mock_result)

        service = AsyncRequestService(db)
        result = await service.get_user_by_telegram_id(100)

        assert result is user


# ---------------------------------------------------------------------------
# add_media_to_request  (async)
# ---------------------------------------------------------------------------

class TestAddMediaToRequest:
    @pytest.mark.asyncio
    async def test_returns_none_when_request_not_found(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        service = AsyncRequestService(db)
        result = await service.add_media_to_request("260401-001", ["file1"])

        assert result is None

    @pytest.mark.asyncio
    async def test_appends_files_to_existing(self):
        req = _make_request()
        req.media_files = ["existing.jpg"]

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = req
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        service = AsyncRequestService(db)
        await service.add_media_to_request("260401-001", ["new.jpg"])

        assert "existing.jpg" in req.media_files
        assert "new.jpg" in req.media_files


# ---------------------------------------------------------------------------
# get_request_statistics  (async) — error path
# ---------------------------------------------------------------------------

class TestGetRequestStatistics:
    @pytest.mark.asyncio
    async def test_returns_default_on_exception(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("DB error"))

        service = AsyncRequestService(db)
        result = await service.get_request_statistics()

        assert result["total_requests"] == 0
        assert result["status_statistics"] == {}
        assert result["category_statistics"] == {}
        assert result["urgency_statistics"] == {}
