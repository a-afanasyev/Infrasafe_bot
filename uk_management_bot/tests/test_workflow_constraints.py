"""Constraints-фаза SSOT (миграция 018): DB-гарантии идемпотентности.

Модельные constraints (create_all-паритет с миграцией):
  - ratings: UNIQUE(request_number);
  - request_assignments: partial-unique WHERE status='active'
    (история cancelled/completed сохраняется).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.rating import Rating
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.user import User


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    s.add(User(id=1, telegram_id=1, first_name="U", role="applicant",
               status="approved", language="ru"))
    s.add(Request(request_number="260610-001", user_id=1, category="c",
                  description="d", urgency="low", status="Исполнено"))
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


class TestRatingUnique:
    def test_second_rating_for_same_request_rejected(self, db):
        db.add(Rating(request_number="260610-001", user_id=1, rating=5))
        db.commit()
        db.add(Rating(request_number="260610-001", user_id=1, rating=3))
        with pytest.raises(IntegrityError):
            db.commit()


class TestActiveAssignmentPartialUnique:
    def _assignment(self, status):
        return RequestAssignment(
            request_number="260610-001", assignment_type="individual",
            executor_id=1, status=status, created_by=1,
        )

    def test_second_active_rejected(self, db):
        db.add(self._assignment("active"))
        db.commit()
        db.add(self._assignment("active"))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_history_preserved(self, db):
        """cancelled/completed не конфликтуют — partial, не unique-по-заявке."""
        db.add(self._assignment("cancelled"))
        db.add(self._assignment("completed"))
        db.add(self._assignment("active"))
        db.commit()
        assert db.query(RequestAssignment).count() == 3

    def test_cancel_then_new_active_ok(self, db):
        a1 = self._assignment("active")
        db.add(a1)
        db.commit()
        a1.status = "cancelled"
        db.add(self._assignment("active"))
        db.commit()
        assert db.query(RequestAssignment).filter_by(status="active").count() == 1
