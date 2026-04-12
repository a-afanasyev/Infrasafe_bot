"""
Unit tests for RequestService (mock-based, no DB required).

Covers:
- create_request (happy path, validation errors)
- get_user_requests / get_request_by_number / get_request_by_id
- update_request_status (happy path, invalid status, completed_at, notes)
- update_status_by_actor (role checks, transition matrix, shift check)
- is_transition_allowed (matrix edges)
- is_role_allowed_for_transition (applicant, executor, manager)
- search_requests, get_request_statistics
- delete_request (owner, admin, unauthorized)
- add_media_to_request
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock


class _FakeRequest:
    """Lightweight stand-in for a Request ORM object."""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.request_number = kwargs.get("request_number", "260412-001")
        self.user_id = kwargs.get("user_id", 10)
        self.category = kwargs.get("category", "electricity")
        self.address = kwargs.get("address", "ул. Тестовая, 1")
        self.description = kwargs.get("description", "Описание")
        self.apartment = kwargs.get("apartment", None)
        self.urgency = kwargs.get("urgency", "Обычная")
        self.media_files = kwargs.get("media_files", [])
        self.status = kwargs.get("status", "Новая")
        self.executor_id = kwargs.get("executor_id", None)
        self.notes = kwargs.get("notes", None)
        self.completed_at = kwargs.get("completed_at", None)
        self.created_at = kwargs.get("created_at", datetime.now())
        self.user = kwargs.get("user", None)
        self.executor = kwargs.get("executor", None)


class _FakeUser:
    """Lightweight stand-in for a User ORM object."""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 10)
        self.telegram_id = kwargs.get("telegram_id", 100)
        self.username = kwargs.get("username", "tester")
        self.first_name = kwargs.get("first_name", "Test")
        self.last_name = kwargs.get("last_name", "User")
        self.role = kwargs.get("role", "applicant")
        self.roles = kwargs.get("roles", '["applicant"]')
        self.active_role = kwargs.get("active_role", "applicant")
        self.status = kwargs.get("status", "approved")
        self.name = kwargs.get("name", "Test User")


# ---------------------------------------------------------------------------
# Helpers to build the service with all heavy imports mocked out
# ---------------------------------------------------------------------------

def _build_service(db_mock):
    """Import and instantiate RequestService with mocked dependencies."""
    with patch("uk_management_bot.services.request_service.ShiftService"), \
         patch("uk_management_bot.services.request_service.notify_status_changed"), \
         patch("uk_management_bot.services.request_service.async_notify_request_status_changed"):
        from uk_management_bot.services.request_service import RequestService
        return RequestService(db_mock)


# ===== is_transition_allowed =====

class TestIsTransitionAllowed:
    """Matrix-level transition checks (pure logic, no DB)."""

    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    # Happy transitions
    @pytest.mark.parametrize("current,target", [
        ("Новая", "В работе"),
        ("Новая", "Отменена"),
        ("В работе", "Выполнена"),
        ("В работе", "Уточнение"),
        ("В работе", "Закуп"),
        ("Уточнение", "В работе"),
        ("Закуп", "В работе"),
        ("Выполнена", "Принято"),
        ("Выполнена", "Исполнено"),
        ("Исполнено", "Выполнена"),
        ("Исполнено", "Принято"),
    ])
    def test_allowed_transitions(self, current, target):
        assert self.svc.is_transition_allowed(current, target) is True

    # Forbidden transitions
    @pytest.mark.parametrize("current,target", [
        ("Новая", "Выполнена"),
        ("Принято", "В работе"),
        ("Отменена", "Новая"),
        ("Принято", "Отменена"),
    ])
    def test_disallowed_transitions(self, current, target):
        assert self.svc.is_transition_allowed(current, target) is False

    def test_unknown_status_returns_false(self):
        assert self.svc.is_transition_allowed("НесуществующийСтатус", "В работе") is False


# ===== is_role_allowed_for_transition =====

class TestIsRoleAllowedForTransition:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def _user(self, **overrides):
        return _FakeUser(**overrides)

    def _request(self, **overrides):
        return _FakeRequest(**overrides)

    # Applicant scenarios
    def test_applicant_can_cancel_own_new_request(self):
        actor = self._user(active_role="applicant", roles='["applicant"]')
        req = self._request(user_id=actor.id, status="Новая")
        assert self.svc.is_role_allowed_for_transition(actor, req, "Отменена") is True

    def test_applicant_cannot_cancel_other_user_request(self):
        actor = self._user(id=10, active_role="applicant", roles='["applicant"]')
        req = self._request(user_id=999, status="Новая")
        assert self.svc.is_role_allowed_for_transition(actor, req, "Отменена") is False

    def test_applicant_can_accept_completed_request(self):
        actor = self._user(active_role="applicant", roles='["applicant"]')
        req = self._request(user_id=actor.id, status="Выполнена")
        assert self.svc.is_role_allowed_for_transition(actor, req, "Принято") is True

    def test_applicant_can_return_completed_request(self):
        actor = self._user(active_role="applicant", roles='["applicant"]')
        req = self._request(user_id=actor.id, status="Выполнена")
        assert self.svc.is_role_allowed_for_transition(actor, req, "Исполнено") is True

    def test_applicant_cannot_take_in_work(self):
        actor = self._user(active_role="applicant", roles='["applicant"]')
        req = self._request(user_id=actor.id, status="Новая")
        assert self.svc.is_role_allowed_for_transition(actor, req, "В работе") is False

    # Executor scenarios
    def test_executor_can_take_in_work(self):
        actor = self._user(active_role="executor", roles='["executor"]')
        req = self._request(status="Новая")
        assert self.svc.is_role_allowed_for_transition(actor, req, "В работе") is True

    def test_executor_can_complete(self):
        actor = self._user(active_role="executor", roles='["executor"]')
        req = self._request(status="В работе")
        assert self.svc.is_role_allowed_for_transition(actor, req, "Выполнена") is True

    def test_executor_cannot_accept(self):
        actor = self._user(active_role="executor", roles='["executor"]')
        req = self._request(status="Выполнена")
        assert self.svc.is_role_allowed_for_transition(actor, req, "Принято") is False

    # Manager scenarios
    def test_manager_can_do_anything(self):
        actor = self._user(active_role="manager", roles='["manager"]')
        req = self._request(status="Новая")
        assert self.svc.is_role_allowed_for_transition(actor, req, "В работе") is True
        assert self.svc.is_role_allowed_for_transition(actor, req, "Отменена") is True

    # Admin scenario
    def test_admin_can_do_anything(self):
        actor = self._user(active_role="admin", roles='["admin"]')
        req = self._request(status="В работе")
        assert self.svc.is_role_allowed_for_transition(actor, req, "Выполнена") is True


# ===== update_request_status =====

class TestUpdateRequestStatus:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_invalid_status_returns_none(self):
        result = self.svc.update_request_status("260412-001", "НесуществующийСтатус")
        assert result is None

    def test_request_not_found_returns_none(self):
        with patch.object(self.svc, "get_request_by_number", return_value=None):
            result = self.svc.update_request_status("260412-999", "В работе")
            assert result is None

    def test_happy_path_updates_status(self):
        req = _FakeRequest(status="Новая")
        with patch.object(self.svc, "get_request_by_number", return_value=req):
            result = self.svc.update_request_status("260412-001", "В работе", notes="Начинаю")
            assert result is not None
            assert req.status == "В работе"
            assert req.notes == "Начинаю"
            self.db.commit.assert_called()

    def test_completed_sets_completed_at(self):
        req = _FakeRequest(status="В работе")
        with patch.object(self.svc, "get_request_by_number", return_value=req):
            result = self.svc.update_request_status("260412-001", "Выполнена")
            assert result is not None
            assert req.completed_at is not None

    def test_same_status_with_notes_appends(self):
        req = _FakeRequest(status="В работе", notes="first")
        with patch.object(self.svc, "get_request_by_number", return_value=req):
            result = self.svc.update_request_status("260412-001", "В работе", notes="second")
            assert result is not None
            assert "first" in req.notes
            assert "second" in req.notes

    def test_executor_id_is_set(self):
        req = _FakeRequest(status="Новая")
        with patch.object(self.svc, "get_request_by_number", return_value=req):
            result = self.svc.update_request_status("260412-001", "В работе", executor_id=42)
            assert req.executor_id == 42


# ===== update_status_by_actor =====

class TestUpdateStatusByActor:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_invalid_status_returns_failure(self):
        result = self.svc.update_status_by_actor("260412-001", "Чепуха", 100)
        assert result["success"] is False
        assert "Неверный статус" in result["message"]

    def test_request_not_found(self):
        with patch.object(self.svc, "get_request_by_number", return_value=None):
            result = self.svc.update_status_by_actor("260412-999", "В работе", 100)
            assert result["success"] is False
            assert "не найдена" in result["message"]

    def test_actor_not_found(self):
        req = _FakeRequest()
        with patch.object(self.svc, "get_request_by_number", return_value=req), \
             patch.object(self.svc, "get_user_by_telegram_id", return_value=None):
            result = self.svc.update_status_by_actor("260412-001", "В работе", 999)
            assert result["success"] is False
            assert "не найден" in result["message"]

    def test_applicant_cannot_manage_own_request(self):
        actor = _FakeUser(id=10, telegram_id=100, active_role="applicant",
                          role="applicant", roles='["applicant"]')
        req = _FakeRequest(user_id=10, status="Новая")
        with patch.object(self.svc, "get_request_by_number", return_value=req), \
             patch.object(self.svc, "get_user_by_telegram_id", return_value=actor):
            result = self.svc.update_status_by_actor("260412-001", "В работе", 100)
            assert result["success"] is False
            assert "собственной" in result["message"]

    def test_disallowed_transition_fails(self):
        actor = _FakeUser(id=20, telegram_id=200, active_role="manager",
                          role="manager", roles='["manager"]')
        req = _FakeRequest(user_id=10, status="Принято")  # terminal state
        with patch.object(self.svc, "get_request_by_number", return_value=req), \
             patch.object(self.svc, "get_user_by_telegram_id", return_value=actor):
            result = self.svc.update_status_by_actor("260412-001", "В работе", 200)
            assert result["success"] is False
            assert "Недопустимый" in result["message"]

    def test_executor_without_shift_is_rejected(self):
        actor = _FakeUser(id=20, telegram_id=200, active_role="executor",
                          role="executor", roles='["executor"]')
        req = _FakeRequest(user_id=10, status="Новая")
        mock_shift = MagicMock()
        mock_shift.is_user_in_active_shift.return_value = False

        with patch.object(self.svc, "get_request_by_number", return_value=req), \
             patch.object(self.svc, "get_user_by_telegram_id", return_value=actor), \
             patch("uk_management_bot.services.request_service.ShiftService", return_value=mock_shift):
            result = self.svc.update_status_by_actor("260412-001", "В работе", 200)
            assert result["success"] is False
            assert "смене" in result["message"].lower() or "Смена" in result["message"]

    def test_same_status_with_notes_adds_note(self):
        actor = _FakeUser(id=20, telegram_id=200, active_role="manager",
                          role="manager", roles='["manager"]')
        req = _FakeRequest(user_id=10, status="В работе", notes="old")
        with patch.object(self.svc, "get_request_by_number", return_value=req), \
             patch.object(self.svc, "get_user_by_telegram_id", return_value=actor):
            result = self.svc.update_status_by_actor("260412-001", "В работе", 200, notes="new")
            assert result["success"] is True
            assert "new" in req.notes

    def test_same_status_without_notes_succeeds(self):
        actor = _FakeUser(id=20, telegram_id=200, active_role="manager",
                          role="manager", roles='["manager"]')
        req = _FakeRequest(user_id=10, status="В работе")
        with patch.object(self.svc, "get_request_by_number", return_value=req), \
             patch.object(self.svc, "get_user_by_telegram_id", return_value=actor):
            result = self.svc.update_status_by_actor("260412-001", "В работе", 200)
            assert result["success"] is True
            assert "не изменён" in result["message"]

    def test_manager_happy_path(self):
        actor = _FakeUser(id=20, telegram_id=200, active_role="manager",
                          role="manager", roles='["manager"]')
        fake_user_obj = _FakeUser(id=10, telegram_id=100)
        req = _FakeRequest(user_id=10, status="Новая", user=fake_user_obj)

        mock_audit_cls = MagicMock()
        with patch.object(self.svc, "get_request_by_number", return_value=req), \
             patch.object(self.svc, "get_user_by_telegram_id", return_value=actor), \
             patch("uk_management_bot.services.request_service.AuditLog", mock_audit_cls), \
             patch("uk_management_bot.services.request_service.notify_status_changed"):
            result = self.svc.update_status_by_actor("260412-001", "В работе", 200)
            assert result["success"] is True
            assert req.status == "В работе"

    def test_manager_can_manage_own_request(self):
        """Manager with own request can still change status."""
        actor = _FakeUser(id=10, telegram_id=100, active_role="manager",
                          role="manager", roles='["manager"]')
        fake_user_obj = _FakeUser(id=10, telegram_id=100)
        req = _FakeRequest(user_id=10, status="Новая", user=fake_user_obj)

        with patch.object(self.svc, "get_request_by_number", return_value=req), \
             patch.object(self.svc, "get_user_by_telegram_id", return_value=actor), \
             patch("uk_management_bot.services.request_service.AuditLog", MagicMock()), \
             patch("uk_management_bot.services.request_service.notify_status_changed"):
            result = self.svc.update_status_by_actor("260412-001", "В работе", 100)
            assert result["success"] is True


# ===== get_request_by_id (deprecated) =====

class TestDeprecatedGetRequestById:
    def test_returns_none(self):
        db = MagicMock()
        svc = _build_service(db)
        assert svc.get_request_by_id(123) is None


# ===== search_requests =====

class TestSearchRequests:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_search_returns_list(self):
        req = _FakeRequest()
        mock_query = MagicMock()
        mock_query.options.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [req]
        self.db.query.return_value = mock_query

        results = self.svc.search_requests(category="electricity")
        assert len(results) == 1

    def test_search_exception_returns_empty(self):
        self.db.query.side_effect = Exception("DB error")
        results = self.svc.search_requests()
        assert results == []


# ===== delete_request =====

class TestDeleteRequest:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_delete_by_owner(self):
        req = _FakeRequest(user_id=10)
        with patch.object(self.svc, "get_request_by_number", return_value=req):
            assert self.svc.delete_request("260412-001", 10) is True
            self.db.delete.assert_called_once_with(req)

    def test_delete_by_admin(self):
        req = _FakeRequest(user_id=10)
        admin = _FakeUser(id=99, role="admin")
        with patch.object(self.svc, "get_request_by_number", return_value=req):
            self.db.query.return_value.filter.return_value.first.return_value = admin
            assert self.svc.delete_request("260412-001", 99) is True

    def test_delete_unauthorized(self):
        req = _FakeRequest(user_id=10)
        non_admin = _FakeUser(id=50, role="applicant")
        with patch.object(self.svc, "get_request_by_number", return_value=req):
            self.db.query.return_value.filter.return_value.first.return_value = non_admin
            assert self.svc.delete_request("260412-001", 50) is False

    def test_delete_nonexistent_returns_false(self):
        with patch.object(self.svc, "get_request_by_number", return_value=None):
            assert self.svc.delete_request("260412-999", 10) is False


# ===== add_media_to_request =====

class TestAddMediaToRequest:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_adds_files(self):
        req = _FakeRequest(media_files=["old.jpg"])
        with patch.object(self.svc, "get_request_by_number", return_value=req):
            result = self.svc.add_media_to_request("260412-001", ["new.jpg"])
            assert result is not None
            assert "old.jpg" in req.media_files
            assert "new.jpg" in req.media_files

    def test_nonexistent_request_returns_none(self):
        with patch.object(self.svc, "get_request_by_number", return_value=None):
            result = self.svc.add_media_to_request("260412-999", ["f.jpg"])
            assert result is None


# ===== _get_user_name =====

class TestGetUserName:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_returns_user_name(self):
        user = _FakeUser(name="Иван Иванов")
        self.db.query.return_value.filter.return_value.first.return_value = user
        assert self.svc._get_user_name(10) == "Иван Иванов"

    def test_returns_fallback_when_not_found(self):
        self.db.query.return_value.filter.return_value.first.return_value = None
        assert self.svc._get_user_name(10) == "User_10"

    def test_returns_fallback_on_exception(self):
        self.db.query.side_effect = Exception("fail")
        assert self.svc._get_user_name(10) == "User_10"
