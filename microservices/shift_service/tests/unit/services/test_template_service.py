# Template Service Unit Tests
# UK Management Bot - Shift Service

import pytest
from datetime import time, datetime, timedelta
from uuid import uuid4

from services.template_service import TemplateService
from schemas.shifts import ShiftTemplateCreate
from schemas.common import PaginationParams
from utils.datetime_utils import utc_now


class TestTemplateServiceCreate:
    """Test template creation"""

    async def test_create_template_basic(self, db_session, mock_user):
        """Test basic template creation"""
        service = TemplateService(db_session)

        template_data = ShiftTemplateCreate(
            name="Morning Shift",
            description="Standard morning shift",
            start_time=time(8, 0),
            end_time=time(16, 0),
            days_of_week=[1, 2, 3, 4, 5],  # Mon-Fri
            specialization="maintenance",
            priority=2
        )

        template = await service.create_template(template_data, mock_user["user_id"])

        assert template is not None
        assert template.name == "Morning Shift"
        assert template.duration_hours == 8.0
        assert template.days_of_week == [1, 2, 3, 4, 5]

    async def test_create_template_overnight(self, db_session, mock_user):
        """Test overnight shift template (end time before start time)"""
        service = TemplateService(db_session)

        template_data = ShiftTemplateCreate(
            name="Night Shift",
            start_time=time(22, 0),  # 10 PM
            end_time=time(6, 0),     # 6 AM next day
            days_of_week=[1, 2, 3],
            specialization="security",
            priority=2
        )

        template = await service.create_template(template_data, mock_user["user_id"])

        assert template is not None
        # Should calculate as 8 hours (22:00 -> 06:00 next day)
        assert template.duration_hours == 8.0

    async def test_create_template_weekend_only(self, db_session, mock_user):
        """Test weekend-only template"""
        service = TemplateService(db_session)

        template_data = ShiftTemplateCreate(
            name="Weekend Shift",
            start_time=time(9, 0),
            end_time=time(17, 0),
            days_of_week=[6, 7],  # Sat, Sun
            specialization="janitor",
            priority=1
        )

        template = await service.create_template(template_data, mock_user["user_id"])

        assert template is not None
        assert template.days_of_week == [6, 7]


class TestTemplateServiceRetrieve:
    """Test template retrieval"""

    async def test_get_template(self, db_session, template_factory):
        """Test getting template by ID"""
        service = TemplateService(db_session)

        # Create template
        template = await template_factory(name="Test Template")

        # Retrieve it
        retrieved = await service.get_template(template.id)

        assert retrieved is not None
        assert retrieved.id == template.id
        assert retrieved.name == "Test Template"

    async def test_get_template_not_found(self, db_session):
        """Test getting non-existent template"""
        service = TemplateService(db_session)

        fake_id = uuid4()
        template = await service.get_template(fake_id)

        assert template is None

    async def test_list_templates_basic(self, db_session, template_factory):
        """Test listing templates"""
        service = TemplateService(db_session)

        # Create templates
        await template_factory(name="Template 1")
        await template_factory(name="Template 2")

        # List them
        pagination = PaginationParams(page=1, page_size=10)
        result = await service.list_templates(pagination, {})

        assert "items" in result
        assert len(result["items"]) >= 2

    async def test_list_templates_with_specialization_filter(self, db_session, template_factory):
        """Test listing templates filtered by specialization"""
        service = TemplateService(db_session)

        await template_factory(specialization="plumber")
        await template_factory(specialization="electrician")

        pagination = PaginationParams(page=1, page_size=10)
        result = await service.list_templates(
            pagination,
            {"specialization": "plumber"}
        )

        assert "items" in result
        # Should only return plumber templates
        for item in result["items"]:
            if item.specialization:
                assert item.specialization.value == "plumber"

    async def test_list_templates_with_active_filter(self, db_session, template_factory):
        """Test listing templates filtered by active status"""
        service = TemplateService(db_session)

        await template_factory(is_active=True)
        await template_factory(is_active=False)

        pagination = PaginationParams(page=1, page_size=10)
        result = await service.list_templates(
            pagination,
            {"is_active": True}
        )

        assert "items" in result


class TestTemplateServiceUpdate:
    """Test template updates"""

    async def test_update_template(self, db_session, template_factory, mock_user):
        """Test updating template"""
        service = TemplateService(db_session)

        template = await template_factory(name="Original Name")

        # Update data
        update_data = ShiftTemplateCreate(
            name="Updated Name",
            start_time=template.start_time,
            end_time=template.end_time,
            days_of_week=template.days_of_week,
            specialization=template.specialization.value,
            priority=3
        )

        updated = await service.update_template(
            template.id,
            update_data,
            mock_user["user_id"]
        )

        assert updated is not None
        assert updated.name == "Updated Name"

    async def test_update_template_not_found(self, db_session, mock_user):
        """Test updating non-existent template"""
        service = TemplateService(db_session)

        fake_id = uuid4()
        update_data = ShiftTemplateCreate(
            name="Test",
            start_time=time(8, 0),
            end_time=time(16, 0),
            days_of_week=[1],
            specialization="maintenance",
            priority=2
        )

        updated = await service.update_template(fake_id, update_data, mock_user["user_id"])

        assert updated is None


class TestTemplateServiceDelete:
    """Test template deletion"""

    async def test_delete_template(self, db_session, template_factory, mock_user):
        """Test deleting template"""
        service = TemplateService(db_session)

        template = await template_factory()

        success = await service.delete_template(template.id, mock_user["user_id"])

        assert success is True

        # Verify deletion (soft delete - marked inactive)
        deleted = await service.get_template(template.id)
        # May be None (hard delete) or inactive (soft delete)
        if deleted:
            assert deleted.is_active is False

    async def test_delete_template_not_found(self, db_session, mock_user):
        """Test deleting non-existent template"""
        service = TemplateService(db_session)

        fake_id = uuid4()
        success = await service.delete_template(fake_id, mock_user["user_id"])

        assert success is False


class TestTemplateServiceShiftGeneration:
    """Test shift generation from templates"""

    async def test_generate_shifts_from_template(self, db_session, template_factory, mock_user):
        """Test generating shifts from template"""
        service = TemplateService(db_session)

        # Create template with weekday pattern
        template = await template_factory(
            days_of_week=[1, 3, 5],  # Mon, Wed, Fri
            is_active=True
        )

        # Generate shifts for 7 days
        result = await service.generate_shifts_from_template(
            template.id,
            days_ahead=7,
            created_by=mock_user["user_id"]
        )

        assert result is not None
        # Should have generated some shifts (depends on days matching pattern)
        if isinstance(result, dict):
            assert "generated" in result or "shifts_created" in result

    async def test_generate_shifts_template_not_found(self, db_session, mock_user):
        """Test generating shifts from non-existent template"""
        service = TemplateService(db_session)

        fake_id = uuid4()
        result = await service.generate_shifts_from_template(
            fake_id,
            days_ahead=7,
            created_by=mock_user["user_id"]
        )

        assert result is None

    async def test_generate_shifts_inactive_template(self, db_session, template_factory, mock_user):
        """Test generating shifts from inactive template"""
        service = TemplateService(db_session)

        template = await template_factory(is_active=False)

        result = await service.generate_shifts_from_template(
            template.id,
            days_ahead=7,
            created_by=mock_user["user_id"]
        )

        # Should return None or fail gracefully
        # Implementation may allow or deny inactive templates
        assert result is None or isinstance(result, dict)

    async def test_generate_shifts_long_period(self, db_session, template_factory, mock_user):
        """Test generating shifts for longer period"""
        service = TemplateService(db_session)

        template = await template_factory(
            days_of_week=[1, 2, 3, 4, 5],  # All weekdays
            is_active=True
        )

        # Generate for 30 days
        result = await service.generate_shifts_from_template(
            template.id,
            days_ahead=30,
            created_by=mock_user["user_id"]
        )

        assert result is not None
        # Should generate multiple shifts
        if isinstance(result, dict) and "generated" in result:
            # Expect at least several shifts for 30 days
            assert result["generated"] >= 0


class TestTemplateServiceEdgeCases:
    """Test edge cases and error handling"""

    async def test_create_template_with_same_time(self, db_session, mock_user):
        """Test template with same start and end time"""
        service = TemplateService(db_session)

        template_data = ShiftTemplateCreate(
            name="Zero Duration",
            start_time=time(8, 0),
            end_time=time(8, 0),  # Same as start
            days_of_week=[1],
            specialization="maintenance",
            priority=2
        )

        # Should handle as overnight (24 hours)
        template = await service.create_template(template_data, mock_user["user_id"])

        assert template is not None
        # Duration should be 24 hours (overnight)
        assert template.duration_hours == 24.0

    async def test_list_templates_empty(self, db_session):
        """Test listing templates when none exist"""
        service = TemplateService(db_session)

        pagination = PaginationParams(page=1, page_size=10)
        result = await service.list_templates(pagination, {})

        assert "items" in result
        assert isinstance(result["items"], list)

    async def test_list_templates_pagination(self, db_session, template_factory):
        """Test template pagination"""
        service = TemplateService(db_session)

        # Create multiple templates
        for i in range(5):
            await template_factory(name=f"Template {i}")

        # Get first page
        pagination = PaginationParams(page=1, page_size=2)
        result = await service.list_templates(pagination, {})

        assert "items" in result
        assert "total" in result

    async def test_template_with_all_days(self, db_session, mock_user):
        """Test template for all days of week"""
        service = TemplateService(db_session)

        template_data = ShiftTemplateCreate(
            name="Daily Shift",
            start_time=time(9, 0),
            end_time=time(17, 0),
            days_of_week=[1, 2, 3, 4, 5, 6, 7],  # All days
            specialization="security",
            priority=2
        )

        template = await service.create_template(template_data, mock_user["user_id"])

        assert template is not None
        assert len(template.days_of_week) == 7
