"""Unit tests for RequestNumberService.

PR5: генератор переведён на атомарный счётчик дня (request_number_counters,
UPSERT…RETURNING) — тесты генерации идут против реальной SQLite-схемы
(create_all), а не моков: важна семантика (self-seed, монотонность,
отсутствие переиспользования после удаления), а не форма SQL.
"""
import pytest
from datetime import date
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.services.request_number_service import (
    BUSINESS_TZ,
    RequestNumberService,
    business_today,
)


# ---------------------------------------------------------------------------
# validate_request_number_format
# ---------------------------------------------------------------------------

class TestValidateRequestNumberFormat:
    def test_valid_format(self):
        assert RequestNumberService.validate_request_number_format("260402-001") is True

    def test_valid_format_double_digit_sequence(self):
        assert RequestNumberService.validate_request_number_format("260402-010") is True

    def test_valid_format_triple_digit_sequence(self):
        assert RequestNumberService.validate_request_number_format("260402-100") is True

    def test_valid_format_large_sequence(self):
        # Supports >999 requests per day (3+ digits)
        assert RequestNumberService.validate_request_number_format("260402-1000") is True

    def test_invalid_format_missing_dash(self):
        assert RequestNumberService.validate_request_number_format("260402001") is False

    def test_invalid_format_too_short_sequence(self):
        # 2 digits — must be 3+
        assert RequestNumberService.validate_request_number_format("260402-01") is False

    def test_invalid_format_not_string(self):
        assert RequestNumberService.validate_request_number_format(260402001) is False

    def test_invalid_format_empty_string(self):
        assert RequestNumberService.validate_request_number_format("") is False

    def test_invalid_date_month_13(self):
        # Month 13 is invalid
        assert RequestNumberService.validate_request_number_format("261302-001") is False

    def test_invalid_date_day_00(self):
        assert RequestNumberService.validate_request_number_format("260400-001") is False

    def test_invalid_date_day_32(self):
        assert RequestNumberService.validate_request_number_format("260432-001") is False

    def test_invalid_format_with_letters(self):
        assert RequestNumberService.validate_request_number_format("26040A-001") is False


# ---------------------------------------------------------------------------
# next_number / generate_next_number (counter-backed, PR5)
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    from uk_management_bot.database.session import Base
    # Модели регистрируются в Base.metadata при импорте пакета моделей
    import uk_management_bot.database.models  # noqa: F401
    from uk_management_bot.database.models.user import User

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1, telegram_id=1, first_name="U",
                     roles='["applicant"]', active_role="applicant",
                     status="approved", language="ru"))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _insert_request(db, number):
    from uk_management_bot.database.models.request import Request
    db.add(Request(request_number=number, user_id=1, category="c",
                   description="d", urgency="low", status="Новая"))
    db.commit()


TARGET = date(2026, 4, 2)


class TestNextNumber:
    def test_first_of_day_is_001(self, db):
        assert RequestNumberService.next_number(db, TARGET) == "260402-001"

    def test_sequential_increments(self, db):
        assert RequestNumberService.next_number(db, TARGET) == "260402-001"
        assert RequestNumberService.next_number(db, TARGET) == "260402-002"
        assert RequestNumberService.next_number(db, TARGET) == "260402-003"

    def test_self_seed_from_existing_requests(self, db):
        """Нет строки счётчика, но заявки дня существуют (созданы старым
        кодом) → стартуем с числового MAX(suffix)+1, не с 001."""
        _insert_request(db, "260402-007")
        assert RequestNumberService.next_number(db, TARGET) == "260402-008"

    def test_self_seed_numeric_not_lexicographic(self, db):
        """MAX должен быть ЧИСЛОВЫМ: '260402-1000' > '260402-999' (лексикографически наоборот)."""
        _insert_request(db, "260402-999")
        _insert_request(db, "260402-1000")
        assert RequestNumberService.next_number(db, TARGET) == "260402-1001"

    def test_rollover_999_to_1000(self, db):
        _insert_request(db, "260402-999")
        assert RequestNumberService.next_number(db, TARGET) == "260402-1000"

    def test_no_reuse_after_deleting_max_row(self, db):
        """Gap-safe: удаление заявки с MAX-суффиксом не приводит к повторной
        выдаче того же номера (COUNT(*)+1 и MAX+1 здесь ломались)."""
        from uk_management_bot.database.models.request import Request

        n1 = RequestNumberService.next_number(db, TARGET)
        _insert_request(db, n1)
        n2 = RequestNumberService.next_number(db, TARGET)
        _insert_request(db, n2)
        db.query(Request).filter(Request.request_number == n2).delete()
        db.commit()

        n3 = RequestNumberService.next_number(db, TARGET)
        assert n3 == "260402-003", f"deleted {n2} must NOT be reissued, got {n3}"

    def test_independent_days(self, db):
        assert RequestNumberService.next_number(db, date(2026, 4, 2)) == "260402-001"
        assert RequestNumberService.next_number(db, date(2026, 4, 3)) == "260403-001"
        assert RequestNumberService.next_number(db, date(2026, 4, 2)) == "260402-002"

    def test_padding_three_digits(self, db):
        n = RequestNumberService.next_number(db, TARGET)
        assert len(n.split("-")[1]) == 3

    def test_no_db_raises(self):
        """Ветка db=None удалена: раньше возвращала константный '-001' (коллизии)."""
        with pytest.raises(ValueError):
            RequestNumberService.next_number(None, TARGET)
        with pytest.raises(ValueError):
            RequestNumberService.generate_next_number(creation_date=TARGET, db=None)

    def test_deprecated_alias_delegates(self, db):
        assert RequestNumberService.generate_next_number(
            creation_date=TARGET, db=db
        ) == "260402-001"

    def test_default_date_is_business_today(self, db):
        """Без creation_date — бизнес-дата Asia/Tashkent (не серверная tz)."""
        result = RequestNumberService.next_number(db)
        assert result.startswith(business_today().strftime("%y%m%d"))
        assert str(BUSINESS_TZ) == "Asia/Tashkent"

    def test_counter_rolls_back_with_transaction(self, db):
        """Счётчик инкрементится в транзакции вызывающего: rollback отменяет
        и инкремент (retry в _persist_request получает чистое состояние)."""
        n1 = RequestNumberService.next_number(db, TARGET)
        assert n1 == "260402-001"
        db.rollback()
        assert RequestNumberService.next_number(db, TARGET) == "260402-001"


# ---------------------------------------------------------------------------
# parse_request_number
# ---------------------------------------------------------------------------

class TestParseRequestNumber:
    def test_valid_number_returns_components(self):
        parsed = RequestNumberService.parse_request_number("260402-007")
        assert parsed["valid"] is True
        assert parsed["year"] == 2026
        assert parsed["month"] == 4
        assert parsed["day"] == 2
        assert parsed["sequence"] == 7
        assert parsed["date_prefix"] == "260402"
        assert parsed["sequence_str"] == "007"

    def test_valid_date_object(self):
        parsed = RequestNumberService.parse_request_number("260402-007")
        assert parsed["date"] == date(2026, 4, 2)

    def test_invalid_format_returns_invalid(self):
        parsed = RequestNumberService.parse_request_number("bad-format")
        assert parsed["valid"] is False
        assert "error" in parsed

    def test_empty_string_returns_invalid(self):
        parsed = RequestNumberService.parse_request_number("")
        assert parsed["valid"] is False

    def test_large_sequence(self):
        parsed = RequestNumberService.parse_request_number("260402-1234")
        assert parsed["valid"] is True
        assert parsed["sequence"] == 1234


# ---------------------------------------------------------------------------
# format_for_display
# ---------------------------------------------------------------------------

class TestFormatForDisplay:
    def test_valid_number_includes_date_in_parentheses(self):
        result = RequestNumberService.format_for_display("260402-001")
        assert "260402-001" in result
        assert "02.04.2026" in result
        assert result.startswith("№")

    def test_invalid_number_returned_as_is(self):
        invalid = "not-a-number"
        result = RequestNumberService.format_for_display(invalid)
        assert result == invalid


# ---------------------------------------------------------------------------
# check_number_availability
# ---------------------------------------------------------------------------

class TestCheckNumberAvailability:
    def test_available_when_not_in_db(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None

        svc = RequestNumberService(db)
        assert svc.check_number_availability("260402-001") is True

    def test_not_available_when_in_db(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (1,)

        svc = RequestNumberService(db)
        assert svc.check_number_availability("260402-001") is False

    def test_invalid_format_returns_false(self):
        db = MagicMock()
        svc = RequestNumberService(db)
        assert svc.check_number_availability("bad") is False

    def test_db_exception_returns_false(self):
        db = MagicMock()
        db.execute.side_effect = Exception("DB error")

        svc = RequestNumberService(db)
        assert svc.check_number_availability("260402-001") is False
