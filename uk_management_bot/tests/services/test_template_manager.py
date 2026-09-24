"""Unit tests for TemplateManager."""
from unittest.mock import MagicMock, patch

from uk_management_bot.services.template_manager import TemplateManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_template(template_id=1, name="Тест", is_active=True, auto_create=True):
    t = MagicMock()
    t.id = template_id
    t.name = name
    t.is_active = is_active
    t.auto_create = auto_create
    # Production code drives generation via is_date_included(date).
    t.is_date_included = MagicMock(return_value=True)
    return t


def _make_service():
    db = MagicMock()
    service = TemplateManager(db)
    return service, db


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

class TestConstructor:
    def test_db_stored(self):
        service, db = _make_service()
        assert service.db is db


# ---------------------------------------------------------------------------
# create_template
# ---------------------------------------------------------------------------

class TestCreateTemplate:
    def test_invalid_name_empty_returns_none(self):
        service, db = _make_service()
        # _validate_template_params will be called; stub it to return False
        service._validate_template_params = MagicMock(return_value=False)
        result = service.create_template("", 9, 8)
        assert result is None

    def test_duplicate_name_returns_none(self):
        service, db = _make_service()
        service._validate_template_params = MagicMock(return_value=True)
        existing = _make_template(name="Дубль")
        q = MagicMock()
        q.filter.return_value.first.return_value = existing
        db.query.return_value = q
        result = service.create_template("Дубль", 9, 8)
        assert result is None

    def test_success_returns_template(self):
        service, db = _make_service()
        service._validate_template_params = MagicMock(return_value=True)
        # No existing template with same name
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q
        created = _make_template(name="Новый")
        db.refresh = MagicMock(side_effect=lambda t: None)
        # db.add stores the object; after commit/refresh we return it
        added_objects = []
        db.add.side_effect = lambda obj: added_objects.append(obj)
        db.commit = MagicMock()
        # Patch ShiftTemplate constructor to return our mock
        with patch("uk_management_bot.services.template_manager.ShiftTemplate", return_value=created):
            result = service.create_template("Новый", 9, 8)
        assert result is created
        db.commit.assert_called_once()

    def test_exception_rollback_returns_none(self):
        service, db = _make_service()
        service._validate_template_params = MagicMock(return_value=True)
        db.query.side_effect = Exception("db error")
        result = service.create_template("Тест", 9, 8)
        assert result is None
        db.rollback.assert_called()


# ---------------------------------------------------------------------------
# delete_template
# ---------------------------------------------------------------------------

class TestDeleteTemplate:
    def test_not_found_returns_false(self):
        service, db = _make_service()
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q
        assert service.delete_template(999) is False

    def test_has_related_shifts_no_force_returns_false(self):
        service, db = _make_service()
        template = _make_template()

        call_count = [0]

        def _query(model):
            q = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                q.filter.return_value.first.return_value = template
            else:
                q.filter.return_value.count.return_value = 3
            return q

        db.query.side_effect = _query
        assert service.delete_template(1, force=False) is False

    def test_has_related_shifts_with_force_succeeds(self):
        service, db = _make_service()
        template = _make_template()

        q = MagicMock()
        q.filter.return_value.first.return_value = template
        db.query.return_value = q

        assert service.delete_template(1, force=True) is True
        db.delete.assert_called_with(template)
        db.commit.assert_called()

    def test_no_related_shifts_deletes(self):
        service, db = _make_service()
        template = _make_template()

        call_count = [0]

        def _query(model):
            q = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                q.filter.return_value.first.return_value = template
            else:
                q.filter.return_value.count.return_value = 0
            return q

        db.query.side_effect = _query
        assert service.delete_template(1) is True
        db.delete.assert_called_with(template)

    def test_exception_rollback_returns_false(self):
        service, db = _make_service()
        db.query.side_effect = Exception("fail")
        assert service.delete_template(1) is False
        db.rollback.assert_called()
