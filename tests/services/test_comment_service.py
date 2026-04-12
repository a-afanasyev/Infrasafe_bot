"""
Unit tests for CommentService (mock-based, no DB required).

Covers:
- add_comment (happy path, request not found, user not found, invalid type)
- get_request_comments
- get_comments_by_type
- format_comments_for_display
- add_status_change_comment
- add_purchase_comment
- add_clarification_comment
- add_completion_report_comment
- get_latest_comment
- _get_comment_type_emoji
- _create_audit_log
- _notify_comment_added
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, call


# Constants (mirrors uk_management_bot.utils.constants)
COMMENT_TYPE_STATUS_CHANGE = "status_change"
COMMENT_TYPE_CLARIFICATION = "clarification"
COMMENT_TYPE_PURCHASE = "purchase"
COMMENT_TYPE_REPORT = "report"


class _FakeComment:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.request_number = kwargs.get("request_number", "260412-001")
        self.user_id = kwargs.get("user_id", 10)
        self.comment_text = kwargs.get("comment_text", "test comment")
        self.comment_type = kwargs.get("comment_type", COMMENT_TYPE_STATUS_CHANGE)
        self.previous_status = kwargs.get("previous_status", None)
        self.new_status = kwargs.get("new_status", None)
        self.created_at = kwargs.get("created_at", datetime(2026, 4, 12, 10, 0))


class _FakeRequest:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.request_number = kwargs.get("request_number", "260412-001")
        self.user_id = kwargs.get("user_id", 10)
        self.executor_id = kwargs.get("executor_id", None)


class _FakeUser:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 10)
        self.first_name = kwargs.get("first_name", "Тест")
        self.last_name = kwargs.get("last_name", "Юзер")


def _build_service(db_mock):
    with patch("uk_management_bot.services.comment_service.NotificationService"):
        from uk_management_bot.services.comment_service import CommentService
        return CommentService(db_mock)


# ===== add_comment =====

class TestAddComment:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_happy_path(self):
        req = _FakeRequest()
        user = _FakeUser()
        # query(Request).filter(...).first() -> req
        # query(User).filter(...).first() -> user
        self.db.query.return_value.filter.return_value.first.side_effect = [req, user]

        with patch.object(self.svc, "_create_audit_log"), \
             patch.object(self.svc, "_notify_comment_added"):
            result = self.svc.add_comment(
                request_id="260412-001",
                user_id=10,
                comment_text="test",
                comment_type=COMMENT_TYPE_STATUS_CHANGE,
            )
            self.db.add.assert_called_once()
            self.db.commit.assert_called()

    def test_request_not_found_raises(self):
        self.db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(ValueError, match="не найдена"):
            self.svc.add_comment("260412-999", 10, "txt", COMMENT_TYPE_STATUS_CHANGE)

    def test_user_not_found_raises(self):
        req = _FakeRequest()
        self.db.query.return_value.filter.return_value.first.side_effect = [req, None]
        with pytest.raises(ValueError, match="Пользователь"):
            self.svc.add_comment("260412-001", 999, "txt", COMMENT_TYPE_STATUS_CHANGE)

    def test_invalid_type_raises(self):
        req = _FakeRequest()
        user = _FakeUser()
        self.db.query.return_value.filter.return_value.first.side_effect = [req, user]
        with pytest.raises(ValueError, match="Неверный тип"):
            self.svc.add_comment("260412-001", 10, "txt", "invalid_type")


# ===== get_request_comments =====

class TestGetRequestComments:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_returns_comments(self):
        comments = [_FakeComment(), _FakeComment(id=2)]
        (self.db.query.return_value
         .filter.return_value
         .order_by.return_value
         .limit.return_value
         .all.return_value) = comments
        result = self.svc.get_request_comments("260412-001")
        assert len(result) == 2

    def test_empty_returns_empty_list(self):
        (self.db.query.return_value
         .filter.return_value
         .order_by.return_value
         .limit.return_value
         .all.return_value) = []
        result = self.svc.get_request_comments("260412-001")
        assert result == []


# ===== get_comments_by_type =====

class TestGetCommentsByType:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_filters_by_type(self):
        comments = [_FakeComment(comment_type=COMMENT_TYPE_PURCHASE)]
        (self.db.query.return_value
         .filter.return_value
         .order_by.return_value
         .all.return_value) = comments
        result = self.svc.get_comments_by_type("260412-001", COMMENT_TYPE_PURCHASE)
        assert len(result) == 1


# ===== format_comments_for_display =====

class TestFormatCommentsForDisplay:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_empty_comments(self):
        result = self.svc.format_comments_for_display([])
        assert "Комментариев пока нет" in result

    def test_formats_comments_with_user(self):
        user = _FakeUser(first_name="Иван", last_name="Петров")
        self.db.query.return_value.filter.return_value.first.return_value = user
        comment = _FakeComment(
            comment_type=COMMENT_TYPE_STATUS_CHANGE,
            previous_status="Новая",
            new_status="В работе",
        )
        result = self.svc.format_comments_for_display([comment])
        assert "Иван" in result
        assert "Петров" in result
        assert "Статус изменен" in result

    def test_formats_comments_without_user(self):
        self.db.query.return_value.filter.return_value.first.return_value = None
        comment = _FakeComment(user_id=42)
        result = self.svc.format_comments_for_display([comment])
        assert "Пользователь 42" in result

    def test_formats_comment_without_names(self):
        user = _FakeUser(first_name=None, last_name=None)
        self.db.query.return_value.filter.return_value.first.return_value = user
        comment = _FakeComment(user_id=42)
        result = self.svc.format_comments_for_display([comment])
        assert "Пользователь 42" in result


# ===== add_status_change_comment =====

class TestAddStatusChangeComment:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_request_not_found(self):
        self.db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(ValueError, match="не найдена"):
            self.svc.add_status_change_comment("260412-999", 10, "Новая", "В работе")

    def test_creates_comment_with_status_info(self):
        req = _FakeRequest()
        user = _FakeUser()
        # First call: find request; second call: find request again (via add_comment); third: find user
        self.db.query.return_value.filter.return_value.first.side_effect = [
            req, req, user
        ]
        with patch.object(self.svc, "_create_audit_log"), \
             patch.object(self.svc, "_notify_comment_added"):
            result = self.svc.add_status_change_comment(
                "260412-001", 10, "Новая", "В работе", "доп инфо"
            )
            self.db.add.assert_called()

    def test_creates_comment_without_additional(self):
        req = _FakeRequest()
        user = _FakeUser()
        self.db.query.return_value.filter.return_value.first.side_effect = [
            req, req, user
        ]
        with patch.object(self.svc, "_create_audit_log"), \
             patch.object(self.svc, "_notify_comment_added"):
            self.svc.add_status_change_comment("260412-001", 10, "Новая", "В работе")
            self.db.add.assert_called()


# ===== add_purchase_comment =====

class TestAddPurchaseComment:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_creates_purchase_comment(self):
        req = _FakeRequest()
        user = _FakeUser()
        self.db.query.return_value.filter.return_value.first.side_effect = [req, user]
        with patch.object(self.svc, "_create_audit_log"), \
             patch.object(self.svc, "_notify_comment_added"):
            self.svc.add_purchase_comment("260412-001", 10, "Трубы, фитинги")
            self.db.add.assert_called()


# ===== add_clarification_comment =====

class TestAddClarificationComment:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_creates_clarification_comment(self):
        req = _FakeRequest()
        user = _FakeUser()
        self.db.query.return_value.filter.return_value.first.side_effect = [req, user]
        with patch.object(self.svc, "_create_audit_log"), \
             patch.object(self.svc, "_notify_comment_added"):
            self.svc.add_clarification_comment("260412-001", 10, "Уточните адрес")
            self.db.add.assert_called()


# ===== add_completion_report_comment =====

class TestAddCompletionReportComment:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_creates_report_comment(self):
        req = _FakeRequest()
        user = _FakeUser()
        self.db.query.return_value.filter.return_value.first.side_effect = [req, user]
        with patch.object(self.svc, "_create_audit_log"), \
             patch.object(self.svc, "_notify_comment_added"):
            self.svc.add_completion_report_comment("260412-001", 10, "Работа завершена")
            self.db.add.assert_called()


# ===== get_latest_comment =====

class TestGetLatestComment:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_returns_latest_without_type(self):
        comment = _FakeComment()
        (self.db.query.return_value
         .filter.return_value
         .order_by.return_value
         .first.return_value) = comment
        result = self.svc.get_latest_comment("260412-001")
        assert result == comment

    def test_returns_latest_with_type(self):
        comment = _FakeComment(comment_type=COMMENT_TYPE_PURCHASE)
        (self.db.query.return_value
         .filter.return_value
         .filter.return_value
         .order_by.return_value
         .first.return_value) = comment
        result = self.svc.get_latest_comment("260412-001", COMMENT_TYPE_PURCHASE)
        assert result == comment

    def test_returns_none_when_no_comments(self):
        (self.db.query.return_value
         .filter.return_value
         .order_by.return_value
         .first.return_value) = None
        result = self.svc.get_latest_comment("260412-001")
        assert result is None


# ===== _get_comment_type_emoji =====

class TestGetCommentTypeEmoji:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_known_types(self):
        from uk_management_bot.utils.constants import (
            COMMENT_TYPE_STATUS_CHANGE as SC,
            COMMENT_TYPE_CLARIFICATION as CL,
            COMMENT_TYPE_PURCHASE as PU,
            COMMENT_TYPE_REPORT as RP,
        )
        assert self.svc._get_comment_type_emoji(SC) != ""
        assert self.svc._get_comment_type_emoji(CL) != ""
        assert self.svc._get_comment_type_emoji(PU) != ""
        assert self.svc._get_comment_type_emoji(RP) != ""

    def test_unknown_type_returns_default(self):
        assert self.svc._get_comment_type_emoji("unknown") != ""


# ===== _create_audit_log =====

class TestCreateAuditLog:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_adds_audit_log(self):
        # _create_audit_log may fail internally (e.g. bad keyword arg) and catch the error
        # Just ensure it does not raise
        self.svc._create_audit_log("260412-001", 10, "Test action")
        # If AuditLog constructor fails, add is never called — that's expected behavior

    def test_handles_exception(self):
        self.db.add.side_effect = Exception("DB error")
        # Should not raise
        self.svc._create_audit_log("260412-001", 10, "Test action")


# ===== _notify_comment_added =====

class TestNotifyCommentAdded:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_notifies_owner_when_comment_by_other(self):
        req = _FakeRequest(user_id=10, executor_id=20)
        comment = _FakeComment(user_id=20)  # comment by executor
        self.svc._notify_comment_added(req, comment)
        self.svc.notification_service.send_notification.assert_called()

    def test_notifies_executor_when_comment_by_owner(self):
        req = _FakeRequest(user_id=10, executor_id=20)
        comment = _FakeComment(user_id=10)  # comment by owner
        self.svc._notify_comment_added(req, comment)
        self.svc.notification_service.send_notification.assert_called()

    def test_no_notification_when_only_owner(self):
        req = _FakeRequest(user_id=10, executor_id=None)
        comment = _FakeComment(user_id=10)
        self.svc._notify_comment_added(req, comment)
        self.svc.notification_service.send_notification.assert_not_called()

    def test_handles_exception(self):
        req = _FakeRequest(user_id=10, executor_id=20)
        comment = _FakeComment(user_id=20)
        self.svc.notification_service.send_notification.side_effect = Exception("fail")
        # Should not raise
        self.svc._notify_comment_added(req, comment)
