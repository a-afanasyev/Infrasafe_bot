"""Tests for callcenter Pydantic schemas (uk_management_bot/api/callcenter/schemas.py)."""
import pytest
from pydantic import ValidationError

from uk_management_bot.api.callcenter.schemas import (
    ResidentSearchResult,
    CallCenterCreateRequest,
)


# ═══════════════════════ ResidentSearchResult ═══════════════════════


class TestResidentSearchResult:

    def test_valid_full(self):
        result = ResidentSearchResult(
            id=1, telegram_id=123456,
            full_name="Ivan Petrov",
            phone="+998901234567",
            address="ул. Пушкина 10, кв. 42",
            requests_count=3,
        )
        assert result.id == 1
        assert result.full_name == "Ivan Petrov"
        assert result.requests_count == 3

    def test_valid_minimal(self):
        result = ResidentSearchResult(id=1, telegram_id=123456)
        assert result.full_name is None
        assert result.phone is None
        assert result.address is None
        assert result.requests_count == 0

    def test_missing_id_raises(self):
        with pytest.raises(ValidationError):
            ResidentSearchResult(telegram_id=123456)

    def test_missing_telegram_id_raises(self):
        with pytest.raises(ValidationError):
            ResidentSearchResult(id=1)

    def test_from_attributes_config(self):
        assert ResidentSearchResult.model_config["from_attributes"] is True


# ═══════════════════════ CallCenterCreateRequest ═══════════════════════


class TestCallCenterCreateRequest:

    def test_valid_minimal(self):
        body = CallCenterCreateRequest(
            category="Электрика", urgency="Обычная", description="Не горит свет"
        )
        # FS-04: валидатор нормализует legacy RU-лейбл к канон-EN-ключу.
        assert body.category == "electricity"
        assert body.user_id is None
        assert body.apartment_id is None
        assert body.caller_name is None
        assert body.caller_phone is None
        assert body.address is None

    def test_valid_full(self):
        body = CallCenterCreateRequest(
            category="Сантехника",
            urgency="Срочная",
            description="Прорвало трубу",
            user_id=42,
            apartment_id=10,
            caller_name="Иван Петров",
            caller_phone="+998901234567",
            address="ул. Мира 5",
        )
        assert body.user_id == 42
        assert body.caller_name == "Иван Петров"

    def test_missing_category_raises(self):
        with pytest.raises(ValidationError):
            CallCenterCreateRequest(urgency="Обычная", description="Описание")

    def test_missing_urgency_raises(self):
        with pytest.raises(ValidationError):
            CallCenterCreateRequest(category="Тест", description="Описание")

    def test_missing_description_raises(self):
        with pytest.raises(ValidationError):
            CallCenterCreateRequest(category="Тест", urgency="Обычная")

    def test_urgency_normalized_to_key(self):
        # TASK 17: канон-ключ; толерантно принимает ключ и legacy-рус.
        assert CallCenterCreateRequest(category="Электрика", urgency="high", description="x").urgency == "high"
        assert CallCenterCreateRequest(category="Электрика", urgency="Срочная", description="x").urgency == "high"

    def test_unknown_urgency_raises(self):
        with pytest.raises(ValidationError):
            CallCenterCreateRequest(category="Электрика", urgency="nope", description="x")
