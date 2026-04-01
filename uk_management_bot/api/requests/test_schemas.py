"""
Unit tests for api/requests/schemas.py

Tests Pydantic validation for RequestCard, CreateRequestBody, UpdateRequestBody,
CommentBody, CommentOut, KanbanColumn, KanbanResponse.
"""
import pytest
from datetime import datetime

from uk_management_bot.api.requests.schemas import (
    RequestCard,
    CreateRequestBody,
    UpdateRequestBody,
    CommentBody,
    CommentOut,
    KanbanColumn,
    KanbanResponse,
    VALID_STATUSES,
    VALID_URGENCIES,
)


# ---------------------------------------------------------------------------
# RequestCard
# ---------------------------------------------------------------------------

class TestRequestCard:
    def test_minimal_valid(self):
        card = RequestCard(
            request_number="260101-001",
            status="Новая",
            category="electricity",
        )
        assert card.request_number == "260101-001"
        assert card.status == "Новая"
        assert card.category == "electricity"

    def test_all_optional_fields_default_none(self):
        card = RequestCard(
            request_number="260101-001",
            status="Новая",
            category="plumbing",
        )
        assert card.urgency is None
        assert card.description is None
        assert card.address is None
        assert card.apartment_id is None
        assert card.executor_id is None
        assert card.executor_name is None
        assert card.created_at is None
        assert card.updated_at is None
        assert card.completion_report is None
        assert card.notes is None
        assert card.requested_materials is None
        assert card.return_reason is None

    def test_manager_confirmed_default_false(self):
        card = RequestCard(
            request_number="260101-001",
            status="Новая",
            category="heating",
        )
        assert card.manager_confirmed is False

    def test_full_payload(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        card = RequestCard(
            request_number="260101-042",
            status="В работе",
            category="plumbing",
            urgency="Срочная",
            description="Течёт кран",
            address="ул. Ленина 1",
            apartment_id=7,
            executor_id=3,
            executor_name="Иванов И.",
            created_at=now,
            updated_at=now,
            manager_confirmed=True,
            completion_report="Устранено",
            notes="Примечание",
            requested_materials="Труба",
            return_reason=None,
        )
        assert card.apartment_id == 7
        assert card.manager_confirmed is True

    def test_missing_required_fields_raises(self):
        with pytest.raises(Exception):
            RequestCard(status="Новая")  # category and request_number missing


# ---------------------------------------------------------------------------
# KanbanColumn / KanbanResponse
# ---------------------------------------------------------------------------

class TestKanbanColumn:
    def test_valid(self):
        col = KanbanColumn(status="Новая", count=2, requests=[])
        assert col.count == 2
        assert col.requests == []

    def test_with_cards(self):
        card = RequestCard(request_number="260101-001", status="Новая", category="X")
        col = KanbanColumn(status="Новая", count=1, requests=[card])
        assert len(col.requests) == 1


class TestKanbanResponse:
    def test_valid(self):
        col = KanbanColumn(status="Новая", count=0, requests=[])
        resp = KanbanResponse(columns=[col])
        assert len(resp.columns) == 1


# ---------------------------------------------------------------------------
# CreateRequestBody
# ---------------------------------------------------------------------------

class TestCreateRequestBody:
    def test_valid_minimal(self):
        body = CreateRequestBody(
            category="electricity",
            urgency="Обычная",
            description="Нет света",
        )
        assert body.source == "web"
        assert body.media_files is None
        assert body.apartment_id is None

    def test_valid_with_all_fields(self):
        body = CreateRequestBody(
            category="plumbing",
            urgency="Срочная",
            description="Потоп",
            apartment_id=5,
            address="ул. Ленина 1",
            source="bot",
            media_files=["file1.jpg"],
        )
        assert body.apartment_id == 5
        assert body.source == "bot"
        assert len(body.media_files) == 1

    def test_invalid_urgency_raises(self):
        with pytest.raises(Exception):
            CreateRequestBody(
                category="electricity",
                urgency="INVALID",
                description="test",
            )

    @pytest.mark.parametrize("urgency", VALID_URGENCIES)
    def test_all_valid_urgencies_accepted(self, urgency: str):
        body = CreateRequestBody(
            category="electricity",
            urgency=urgency,
            description="test",
        )
        assert body.urgency == urgency

    def test_missing_required_category_raises(self):
        with pytest.raises(Exception):
            CreateRequestBody(urgency="Обычная", description="test")

    def test_missing_required_description_raises(self):
        with pytest.raises(Exception):
            CreateRequestBody(category="electricity", urgency="Обычная")


# ---------------------------------------------------------------------------
# UpdateRequestBody
# ---------------------------------------------------------------------------

class TestUpdateRequestBody:
    def test_all_optional_defaults_none(self):
        body = UpdateRequestBody()
        assert body.status is None
        assert body.executor_id is None
        assert body.notes is None
        assert body.completion_report is None
        assert body.manager_confirmed is None
        assert body.manager_confirmation_notes is None
        assert body.requested_materials is None
        assert body.return_reason is None

    def test_valid_status(self):
        body = UpdateRequestBody(status="В работе")
        assert body.status == "В работе"

    def test_invalid_status_raises(self):
        with pytest.raises(Exception):
            UpdateRequestBody(status="BOGUS")

    def test_none_status_passes_validator(self):
        body = UpdateRequestBody(status=None)
        assert body.status is None

    @pytest.mark.parametrize("status", VALID_STATUSES)
    def test_all_valid_statuses_accepted(self, status: str):
        body = UpdateRequestBody(status=status)
        assert body.status == status

    def test_partial_update(self):
        body = UpdateRequestBody(executor_id=7, notes="Назначен исполнитель")
        assert body.executor_id == 7
        assert body.notes == "Назначен исполнитель"
        assert body.status is None

    def test_manager_confirmed_bool(self):
        body = UpdateRequestBody(manager_confirmed=True)
        assert body.manager_confirmed is True


# ---------------------------------------------------------------------------
# CommentBody
# ---------------------------------------------------------------------------

class TestCommentBody:
    def test_minimal_valid(self):
        c = CommentBody(text="Привет")
        assert c.text == "Привет"
        assert c.is_internal is False
        assert c.media_files is None

    def test_internal_comment(self):
        c = CommentBody(text="Внутреннее", is_internal=True)
        assert c.is_internal is True

    def test_with_media(self):
        c = CommentBody(text="Фото", media_files=["a.jpg", "b.jpg"])
        assert len(c.media_files) == 2


# ---------------------------------------------------------------------------
# CommentOut
# ---------------------------------------------------------------------------

class TestCommentOut:
    def test_valid(self):
        out = CommentOut(
            id=1,
            user_id=2,
            comment_type="text",
            comment_text="Хорошо",
        )
        assert out.is_internal is False
        assert out.created_at is None

    def test_full_payload(self):
        now = datetime(2026, 1, 1, 10, 0, 0)
        out = CommentOut(
            id=5,
            user_id=3,
            comment_type="internal",
            comment_text="Для менеджера",
            is_internal=True,
            created_at=now,
        )
        assert out.is_internal is True
        assert out.created_at == now
