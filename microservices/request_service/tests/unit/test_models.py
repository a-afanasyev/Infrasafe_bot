"""
Unit tests for Request Service models
"""

import pytest
from datetime import datetime
from decimal import Decimal

from app.models import (
    Request, RequestComment, RequestRating, RequestAssignment, RequestMaterial,
    RequestStatus, RequestPriority, RequestCategory
)


@pytest.mark.unit
class TestRequestModel:
    """Test Request model functionality"""

    def test_request_creation(self):
        """Test basic request creation"""
        request = Request(
            request_number="250927-001",
            title="Test Request",
            description="Test Description",
            category=RequestCategory.PLUMBING,
            priority=RequestPriority.NORMAL,
            status=RequestStatus.NEW,
            address="Test Address, 1",
            applicant_user_id="user_123"
        )

        assert request.request_number == "250927-001"
        assert request.title == "Test Request"
        assert request.category == RequestCategory.PLUMBING
        assert request.priority == RequestPriority.NORMAL
        assert request.status == RequestStatus.NEW
        assert request.applicant_user_id == "user_123"
        assert request.materials_requested == False
        assert request.is_deleted == False

    def test_request_with_optional_fields(self):
        """Test request creation with optional fields"""
        request = Request(
            request_number="250927-002",
            title="Test Request with Options",
            description="Test Description",
            category=RequestCategory.ELECTRICAL,
            priority=RequestPriority.HIGH,
            status=RequestStatus.IN_PROGRESS,
            address="Test Address, 2",
            apartment_number="42",
            building_id="building_001",
            applicant_user_id="user_456",
            executor_user_id="executor_789",
            materials_requested=True,
            materials_cost=Decimal("1500.50"),
            latitude=55.7558,
            longitude=37.6176,
            work_duration_minutes=120,
            completion_notes="Test completion"
        )

        assert request.apartment_number == "42"
        assert request.building_id == "building_001"
        assert request.executor_user_id == "executor_789"
        assert request.materials_requested == True
        assert request.materials_cost == Decimal("1500.50")
        assert request.latitude == 55.7558
        assert request.longitude == 37.6176
        assert request.work_duration_minutes == 120
        assert request.completion_notes == "Test completion"

    def test_request_repr(self):
        """Test request string representation"""
        request = Request(
            request_number="250927-003",
            title="Test Repr",
            description="Test",
            category=RequestCategory.CLEANING,
            status=RequestStatus.NEW,
            address="Test",
            applicant_user_id="user_123"
        )

        repr_str = repr(request)
        assert "250927-003" in repr_str
        assert "новая" in repr_str

    def test_request_media_files(self):
        """Test request with media files"""
        request = Request(
            request_number="250927-004",
            title="Test Media",
            description="Test",
            category=RequestCategory.REPAIR,
            status=RequestStatus.NEW,
            address="Test",
            applicant_user_id="user_123",
            media_file_ids=["file_1", "file_2", "file_3"]
        )

        assert request.media_file_ids == ["file_1", "file_2", "file_3"]
        assert len(request.media_file_ids) == 3

    def test_request_materials_list(self):
        """Test request with materials list"""
        materials_list = {
            "items": [
                {"name": "Труба", "quantity": 5, "unit": "м", "price": 100},
                {"name": "Фитинг", "quantity": 10, "unit": "шт", "price": 50}
            ],
            "total_cost": 1000
        }

        request = Request(
            request_number="250927-005",
            title="Test Materials",
            description="Test",
            category=RequestCategory.PLUMBING,
            status=RequestStatus.NEW,
            address="Test",
            applicant_user_id="user_123",
            materials_requested=True,
            materials_list=materials_list,
            materials_cost=Decimal("1000.00")
        )

        assert request.materials_list == materials_list
        assert request.materials_list["total_cost"] == 1000
        assert len(request.materials_list["items"]) == 2


@pytest.mark.unit
class TestRequestCommentModel:
    """Test RequestComment model functionality"""

    def test_comment_creation(self):
        """Test basic comment creation"""
        comment = RequestComment(
            request_number="250927-001",
            comment_text="Test comment",
            author_user_id="user_123"
        )

        assert comment.request_number == "250927-001"
        assert comment.comment_text == "Test comment"
        assert comment.author_user_id == "user_123"
        assert comment.is_internal == False
        assert comment.is_status_change == False
        assert comment.is_deleted == False

    def test_status_change_comment(self):
        """Test status change comment"""
        comment = RequestComment(
            request_number="250927-001",
            comment_text="Status changed from новая to в работе",
            author_user_id="user_123",
            old_status=RequestStatus.NEW,
            new_status=RequestStatus.IN_PROGRESS,
            is_status_change=True,
            is_internal=True
        )

        assert comment.is_status_change == True
        assert comment.is_internal == True
        assert comment.old_status == RequestStatus.NEW
        assert comment.new_status == RequestStatus.IN_PROGRESS

    def test_comment_with_media(self):
        """Test comment with media files"""
        comment = RequestComment(
            request_number="250927-001",
            comment_text="Comment with media",
            author_user_id="user_123",
            media_file_ids=["media_1", "media_2"]
        )

        assert comment.media_file_ids == ["media_1", "media_2"]

    def test_comment_repr(self):
        """Test comment string representation"""
        comment = RequestComment(
            request_number="250927-001",
            comment_text="Test comment",
            author_user_id="user_123"
        )

        repr_str = repr(comment)
        assert "250927-001" in repr_str


@pytest.mark.unit
class TestRequestRatingModel:
    """Test RequestRating model functionality"""

    def test_rating_creation(self):
        """Test basic rating creation"""
        rating = RequestRating(
            request_number="250927-001",
            rating=5,
            feedback="Excellent work!",
            author_user_id="user_123"
        )

        assert rating.request_number == "250927-001"
        assert rating.rating == 5
        assert rating.feedback == "Excellent work!"
        assert rating.author_user_id == "user_123"

    def test_rating_without_feedback(self):
        """Test rating without feedback"""
        rating = RequestRating(
            request_number="250927-001",
            rating=4,
            author_user_id="user_123"
        )

        assert rating.rating == 4
        assert rating.feedback is None

    def test_rating_bounds(self):
        """Test rating value bounds"""
        # Test minimum rating
        rating_min = RequestRating(
            request_number="250927-001",
            rating=1,
            author_user_id="user_123"
        )
        assert rating_min.rating == 1

        # Test maximum rating
        rating_max = RequestRating(
            request_number="250927-001",
            rating=5,
            author_user_id="user_123"
        )
        assert rating_max.rating == 5

    def test_rating_repr(self):
        """Test rating string representation"""
        rating = RequestRating(
            request_number="250927-001",
            rating=5,
            author_user_id="user_123"
        )

        repr_str = repr(rating)
        assert "250927-001" in repr_str
        assert "5" in repr_str


@pytest.mark.unit
class TestRequestAssignmentModel:
    """Test RequestAssignment model functionality"""

    def test_assignment_creation(self):
        """Test basic assignment creation"""
        assignment = RequestAssignment(
            request_number="250927-001",
            assigned_user_id="executor_123",
            assigned_by_user_id="manager_456",
            assignment_type="manual",
            specialization_required="сантехника"
        )

        assert assignment.request_number == "250927-001"
        assert assignment.assigned_user_id == "executor_123"
        assert assignment.assigned_by_user_id == "manager_456"
        assert assignment.assignment_type == "manual"
        assert assignment.specialization_required == "сантехника"
        assert assignment.is_active == True

    def test_assignment_with_reason(self):
        """Test assignment with reason"""
        assignment = RequestAssignment(
            request_number="250927-001",
            assigned_user_id="executor_123",
            assigned_by_user_id="manager_456",
            assignment_type="ai_auto",
            assignment_reason="AI recommendation based on skills and location"
        )

        assert assignment.assignment_type == "ai_auto"
        assert assignment.assignment_reason == "AI recommendation based on skills and location"

    def test_assignment_acceptance(self):
        """Test assignment acceptance"""
        assignment = RequestAssignment(
            request_number="250927-001",
            assigned_user_id="executor_123",
            assigned_by_user_id="manager_456",
            assignment_type="manual"
        )

        # Simulate acceptance
        assignment.accepted_at = datetime.utcnow()

        assert assignment.accepted_at is not None
        assert assignment.rejected_at is None

    def test_assignment_rejection(self):
        """Test assignment rejection"""
        assignment = RequestAssignment(
            request_number="250927-001",
            assigned_user_id="executor_123",
            assigned_by_user_id="manager_456",
            assignment_type="manual"
        )

        # Simulate rejection
        assignment.rejected_at = datetime.utcnow()
        assignment.rejection_reason = "Not available at this time"
        assignment.is_active = False

        assert assignment.rejected_at is not None
        assert assignment.rejection_reason == "Not available at this time"
        assert assignment.is_active == False

    def test_assignment_repr(self):
        """Test assignment string representation"""
        assignment = RequestAssignment(
            request_number="250927-001",
            assigned_user_id="executor_123",
            assigned_by_user_id="manager_456"
        )

        repr_str = repr(assignment)
        assert "250927-001" in repr_str
        assert "executor_123" in repr_str


@pytest.mark.unit
class TestRequestMaterialModel:
    """Test RequestMaterial model functionality"""

    def test_material_creation(self):
        """Test basic material creation"""
        material = RequestMaterial(
            request_number="250927-001",
            material_name="PVC Pipe",
            description="32mm PVC pipe for water supply",
            category="plumbing",
            quantity=Decimal("5.0"),
            unit="m",
            unit_price=Decimal("150.00"),
            total_cost=Decimal("750.00"),
            supplier="TechnoStroy"
        )

        assert material.request_number == "250927-001"
        assert material.material_name == "PVC Pipe"
        assert material.description == "32mm PVC pipe for water supply"
        assert material.category == "plumbing"
        assert material.quantity == Decimal("5.0")
        assert material.unit == "m"
        assert material.unit_price == Decimal("150.00")
        assert material.total_cost == Decimal("750.00")
        assert material.supplier == "TechnoStroy"
        assert material.status == "requested"

    def test_material_without_pricing(self):
        """Test material without pricing information"""
        material = RequestMaterial(
            request_number="250927-001",
            material_name="Generic Material",
            quantity=Decimal("1.0"),
            unit="шт"
        )

        assert material.unit_price is None
        assert material.total_cost is None
        assert material.supplier is None

    def test_material_status_transitions(self):
        """Test material status changes"""
        material = RequestMaterial(
            request_number="250927-001",
            material_name="Test Material",
            quantity=Decimal("1.0"),
            unit="шт",
            status="requested"
        )

        assert material.status == "requested"

        # Simulate ordering
        material.status = "ordered"
        material.ordered_at = datetime.utcnow()

        assert material.status == "ordered"
        assert material.ordered_at is not None

        # Simulate delivery
        material.status = "delivered"
        material.delivered_at = datetime.utcnow()

        assert material.status == "delivered"
        assert material.delivered_at is not None

    def test_material_repr(self):
        """Test material string representation"""
        material = RequestMaterial(
            request_number="250927-001",
            material_name="Test Material",
            quantity=Decimal("1.0"),
            unit="шт"
        )

        repr_str = repr(material)
        assert "250927-001" in repr_str
        assert "Test Material" in repr_str


@pytest.mark.unit
class TestModelEnums:
    """Test model enumerations"""

    def test_request_status_enum(self):
        """Test RequestStatus enum values"""
        assert RequestStatus.NEW == "новая"
        assert RequestStatus.IN_PROGRESS == "в работе"
        assert RequestStatus.MATERIALS_REQUESTED == "заказаны материалы"
        assert RequestStatus.MATERIALS_DELIVERED == "материалы доставлены"
        assert RequestStatus.WAITING_PAYMENT == "ожидает оплаты"
        assert RequestStatus.COMPLETED == "выполнена"
        assert RequestStatus.CANCELLED == "отменена"
        assert RequestStatus.REJECTED == "отклонена"

    def test_request_priority_enum(self):
        """Test RequestPriority enum values"""
        assert RequestPriority.LOW == "низкий"
        assert RequestPriority.NORMAL == "обычный"
        assert RequestPriority.HIGH == "высокий"
        assert RequestPriority.URGENT == "срочный"
        assert RequestPriority.EMERGENCY == "аварийный"

    def test_request_category_enum(self):
        """Test RequestCategory enum values"""
        assert RequestCategory.PLUMBING == "сантехника"
        assert RequestCategory.ELECTRICAL == "электрика"
        assert RequestCategory.HVAC == "вентиляция"
        assert RequestCategory.CLEANING == "уборка"
        assert RequestCategory.MAINTENANCE == "обслуживание"
        assert RequestCategory.REPAIR == "ремонт"
        assert RequestCategory.INSTALLATION == "установка"
        assert RequestCategory.INSPECTION == "осмотр"
        assert RequestCategory.OTHER == "прочее"

    def test_enum_membership(self):
        """Test enum membership checks"""
        assert "новая" in [status.value for status in RequestStatus]
        assert "аварийный" in [priority.value for priority in RequestPriority]
        assert "сантехника" in [category.value for category in RequestCategory]

        # Test invalid values
        assert "invalid_status" not in [status.value for status in RequestStatus]
        assert "invalid_priority" not in [priority.value for priority in RequestPriority]
        assert "invalid_category" not in [category.value for category in RequestCategory]