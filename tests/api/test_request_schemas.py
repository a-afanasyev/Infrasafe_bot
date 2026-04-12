"""Tests for request Pydantic schemas (uk_management_bot/api/requests/schemas.py)."""
import pytest
from datetime import datetime
from pydantic import ValidationError

from uk_management_bot.api.requests.schemas import (
    VALID_STATUSES,
    VALID_URGENCIES,
    RequestCard,
    KanbanColumn,
    KanbanResponse,
    CreateRequestBody,
    UpdateRequestBody,
    CommentBody,
    CommentOut,
)


# ═══════════════════════ Constants ═══════════════════════


class TestConstants:

    def test_valid_statuses_contains_expected(self):
        assert "Новая" in VALID_STATUSES
        assert "В работе" in VALID_STATUSES
        assert "Выполнена" in VALID_STATUSES
        assert "Отменена" in VALID_STATUSES
        assert "Исполнено" in VALID_STATUSES
        assert "Принято" in VALID_STATUSES

    def test_valid_urgencies_contains_expected(self):
        assert "Обычная" in VALID_URGENCIES
        assert "Средняя" in VALID_URGENCIES
        assert "Срочная" in VALID_URGENCIES
        assert "Критическая" in VALID_URGENCIES


# ═══════════════════════ RequestCard ═══════════════════════


class TestRequestCard:

    def test_minimal(self):
        card = RequestCard(request_number="260101-001", status="Новая", category="Электрика")
        assert card.request_number == "260101-001"
        assert card.status == "Новая"
        assert card.category == "Электрика"
        assert card.urgency is None
        assert card.executor_id is None
        assert card.manager_confirmed is False

    def test_full(self):
        now = datetime.now()
        card = RequestCard(
            request_number="260101-002",
            status="В работе",
            category="Сантехника",
            urgency="Срочная",
            source="web",
            description="Течёт кран",
            address="ул. Пушкина 10",
            apartment_id=5,
            executor_id=42,
            executor_name="Иван Петров",
            created_at=now,
            updated_at=now,
            manager_confirmed=True,
            completion_report="Готово",
            notes="Заметки",
            requested_materials="Кран",
            return_reason=None,
        )
        assert card.executor_id == 42
        assert card.manager_confirmed is True

    def test_from_attributes_config(self):
        assert RequestCard.model_config["from_attributes"] is True


# ═══════════════════════ KanbanColumn / KanbanResponse ═══════════════════════


class TestKanbanModels:

    def test_kanban_column(self):
        card = RequestCard(request_number="260101-001", status="Новая", category="Тест")
        column = KanbanColumn(status="Новая", count=1, requests=[card])
        assert column.status == "Новая"
        assert column.count == 1
        assert len(column.requests) == 1

    def test_kanban_response(self):
        col = KanbanColumn(status="Новая", count=0, requests=[])
        resp = KanbanResponse(columns=[col])
        assert len(resp.columns) == 1

    def test_kanban_column_empty(self):
        column = KanbanColumn(status="В работе", count=0, requests=[])
        assert column.requests == []


# ═══════════════════════ CreateRequestBody ═══════════════════════


class TestCreateRequestBody:

    def test_valid_minimal(self):
        body = CreateRequestBody(
            category="Электрика", urgency="Обычная", description="Не горит свет"
        )
        assert body.category == "Электрика"
        assert body.source == "web"
        assert body.apartment_id is None
        assert body.media_files is None

    def test_valid_full(self):
        body = CreateRequestBody(
            category="Сантехника",
            urgency="Срочная",
            description="Прорвало трубу",
            apartment_id=10,
            address="ул. Мира 5",
            source="twa",
            media_files=["photo1.jpg", "photo2.jpg"],
        )
        assert body.source == "twa"
        assert body.media_files == ["photo1.jpg", "photo2.jpg"]

    @pytest.mark.parametrize("urgency", VALID_URGENCIES)
    def test_all_valid_urgencies(self, urgency: str):
        body = CreateRequestBody(
            category="Тест", urgency=urgency, description="Описание"
        )
        assert body.urgency == urgency

    def test_invalid_urgency_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateRequestBody(
                category="Тест", urgency="НеверныйУровень", description="Описание"
            )
        assert "urgency" in str(exc_info.value)

    def test_missing_category_raises(self):
        with pytest.raises(ValidationError):
            CreateRequestBody(urgency="Обычная", description="Описание")

    def test_missing_description_raises(self):
        with pytest.raises(ValidationError):
            CreateRequestBody(category="Тест", urgency="Обычная")


# ═══════════════════════ UpdateRequestBody ═══════════════════════


class TestUpdateRequestBody:

    def test_all_none_is_valid(self):
        body = UpdateRequestBody()
        assert body.status is None
        assert body.executor_id is None
        assert body.notes is None

    @pytest.mark.parametrize("status", VALID_STATUSES)
    def test_all_valid_statuses(self, status: str):
        body = UpdateRequestBody(status=status)
        assert body.status == status

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            UpdateRequestBody(status="НесуществующийСтатус")
        assert "status" in str(exc_info.value)

    def test_none_status_is_valid(self):
        body = UpdateRequestBody(status=None)
        assert body.status is None

    def test_partial_update(self):
        body = UpdateRequestBody(
            notes="Заметка", completion_report="Готово", manager_confirmed=True
        )
        assert body.notes == "Заметка"
        assert body.completion_report == "Готово"
        assert body.manager_confirmed is True

    def test_return_reason_and_materials(self):
        body = UpdateRequestBody(
            return_reason="Неверная категория",
            requested_materials="Болты, гайки",
        )
        assert body.return_reason == "Неверная категория"
        assert body.requested_materials == "Болты, гайки"


# ═══════════════════════ CommentBody / CommentOut ═══════════════════════


class TestCommentModels:

    def test_comment_body_minimal(self):
        body = CommentBody(text="Готово")
        assert body.text == "Готово"
        assert body.is_internal is False
        assert body.media_files is None

    def test_comment_body_internal(self):
        body = CommentBody(text="Заметка для менеджера", is_internal=True)
        assert body.is_internal is True

    def test_comment_body_with_media(self):
        body = CommentBody(text="Фото", media_files=["img1.jpg"])
        assert body.media_files == ["img1.jpg"]

    def test_comment_body_missing_text_raises(self):
        with pytest.raises(ValidationError):
            CommentBody()

    def test_comment_out(self):
        now = datetime.now()
        out = CommentOut(
            id=1, user_id=42, comment_type="text",
            comment_text="Комментарий", is_internal=False, created_at=now,
        )
        assert out.id == 1
        assert out.user_id == 42
        assert out.comment_type == "text"

    def test_comment_out_defaults(self):
        out = CommentOut(id=1, user_id=2, comment_type="text", comment_text="Текст")
        assert out.is_internal is False
        assert out.created_at is None

    def test_comment_out_from_attributes(self):
        assert CommentOut.model_config["from_attributes"] is True
