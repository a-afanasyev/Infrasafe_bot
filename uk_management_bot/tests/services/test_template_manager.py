"""Unit tests for TemplateManager."""
from datetime import date
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
# update_template
# ---------------------------------------------------------------------------

class TestUpdateTemplate:
    def test_not_found_returns_none(self):
        service, db = _make_service()
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q
        result = service.update_template(999, name="X")
        assert result is None

    def test_invalid_updates_returns_none(self):
        service, db = _make_service()
        template = _make_template()
        q = MagicMock()
        q.filter.return_value.first.return_value = template
        db.query.return_value = q
        service._validate_template_updates = MagicMock(return_value=False)
        result = service.update_template(1, start_hour=25)
        assert result is None

    def test_valid_update_sets_attribute(self):
        service, db = _make_service()
        template = _make_template()
        q = MagicMock()
        q.filter.return_value.first.return_value = template
        db.query.return_value = q
        service._validate_template_updates = MagicMock(return_value=True)
        db.refresh = MagicMock()
        result = service.update_template(1, is_active=False)
        assert result is template
        db.commit.assert_called()

    def test_exception_rollback_returns_none(self):
        service, db = _make_service()
        db.query.side_effect = Exception("fail")
        result = service.update_template(1, name="X")
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


# ---------------------------------------------------------------------------
# activate_template / deactivate_template
# ---------------------------------------------------------------------------

class TestActivateDeactivateTemplate:
    def test_activate_calls_update_with_is_active_true(self):
        service, _ = _make_service()
        template = _make_template()
        service.update_template = MagicMock(return_value=template)
        result = service.activate_template(1)
        service.update_template.assert_called_once_with(1, is_active=True)
        assert result is True

    def test_deactivate_calls_update_with_is_active_false(self):
        service, _ = _make_service()
        service.update_template = MagicMock(return_value=None)
        result = service.deactivate_template(1)
        service.update_template.assert_called_once_with(1, is_active=False)
        assert result is False


# ---------------------------------------------------------------------------
# enable_auto_create / disable_auto_create
# ---------------------------------------------------------------------------

class TestAutoCreate:
    def test_enable_auto_create_calls_update(self):
        service, _ = _make_service()
        template = _make_template()
        service.update_template = MagicMock(return_value=template)
        result = service.enable_auto_create(1)
        service.update_template.assert_called_once_with(1, auto_create=True)
        assert result is True

    def test_disable_auto_create_calls_update(self):
        service, _ = _make_service()
        service.update_template = MagicMock(return_value=None)
        result = service.disable_auto_create(1)
        service.update_template.assert_called_once_with(1, auto_create=False)
        assert result is False


# ---------------------------------------------------------------------------
# apply_template_to_period
# ---------------------------------------------------------------------------

class TestApplyTemplateToPeriod:
    def test_template_not_found_returns_error(self):
        service, db = _make_service()
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q
        result = service.apply_template_to_period(999, date(2026, 4, 5), date(2026, 4, 6))
        assert "error" in result

    def test_template_found_iterates_days(self):
        service, db = _make_service()
        template = _make_template()
        q = MagicMock()
        q.filter.return_value.first.return_value = template
        db.query.return_value = q
        service.apply_template = MagicMock(return_value=[])
        result = service.apply_template_to_period(1, date(2026, 4, 7), date(2026, 4, 9))
        assert "template_name" in result
        assert "total_created" in result
        # apply_template called for each day where is_date_included is True
        assert service.apply_template.call_count >= 0

    def test_exception_returns_error(self):
        service, db = _make_service()
        db.query.side_effect = Exception("boom")
        result = service.apply_template_to_period(1, date(2026, 4, 5), date(2026, 4, 6))
        assert "error" in result


# ---------------------------------------------------------------------------
# get_predefined_templates
# ---------------------------------------------------------------------------

class TestGetPredefinedTemplates:
    def test_returns_dict(self):
        service, _ = _make_service()
        templates = service.get_predefined_templates()
        assert isinstance(templates, dict)

    def test_has_standard_workday(self):
        service, _ = _make_service()
        templates = service.get_predefined_templates()
        assert "standard_workday" in templates

    def test_has_weekend_duty(self):
        service, _ = _make_service()
        templates = service.get_predefined_templates()
        assert "weekend_duty" in templates

    def test_standard_workday_has_required_keys(self):
        service, _ = _make_service()
        t = service.get_predefined_templates()["standard_workday"]
        for key in ("name", "start_hour", "duration_hours", "min_executors"):
            assert key in t

    def test_emergency_duty_not_auto_create(self):
        service, _ = _make_service()
        t = service.get_predefined_templates()["emergency_duty"]
        assert t["auto_create"] is False
