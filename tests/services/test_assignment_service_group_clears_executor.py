"""Регрессия: `AssignmentService.assign_to_group` должен обнулять
`Request.executor_id` при переходе в группу.

Найдено ревью auto-manager'а: заявка, ранее назначенная индивидуально, затем
переназначенная группе через `assign_to_group` (a НЕ через workflow-движок),
сохраняла устаревший `executor_id`. `assign_to_executor` симметрично СТАВИТ
`executor_id` — до этого фикса `assign_to_group` его не чистил, что ломало
любой денормализованный фильтр вида "executor_id IS NULL = непривязанная
группа" (напр. `services/auto_manager/orchestrator.py`'s main-очередь).

Паттерн sqlite-фикстуры — как в test_auto_manager_orchestrator.py.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.assignment_service import AssignmentService

APPLICANT_ID = 1
OLD_EXECUTOR_ID = 2
MANAGER_ID = 3


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    session.add_all([
        User(id=APPLICANT_ID, telegram_id=APPLICANT_ID, roles='["applicant"]', status="approved"),
        User(id=OLD_EXECUTOR_ID, telegram_id=OLD_EXECUTOR_ID, roles='["executor"]', status="approved"),
        User(id=MANAGER_ID, telegram_id=MANAGER_ID, roles='["manager"]', status="approved"),
    ])
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _request_with_individual_assignment(db) -> Request:
    req = Request(
        request_number="260723-001",
        user_id=APPLICANT_ID,
        category="plumbing",
        description="test",
        status="В работе",
        executor_id=OLD_EXECUTOR_ID,
        assignment_type="individual",
        assigned_at=datetime.now(timezone.utc),
        assigned_by=MANAGER_ID,
    )
    db.add(req)
    db.add(RequestAssignment(
        request_number=req.request_number,
        assignment_type="individual",
        executor_id=OLD_EXECUTOR_ID,
        status="active",
        created_by=MANAGER_ID,
    ))
    db.commit()
    return req


def test_assign_to_group_clears_stale_individual_executor_id(db):
    _request_with_individual_assignment(db)

    AssignmentService(db).assign_to_group("260723-001", "plumber", MANAGER_ID)

    req = db.query(Request).filter(Request.request_number == "260723-001").one()
    assert req.assignment_type == "group"
    assert req.assigned_group == "plumber"
    assert req.executor_id is None, (
        "assign_to_group must clear executor_id — a group-type request must "
        "never carry a stale individual executor_id from a prior assignment"
    )


def test_assign_to_group_cancels_previous_individual_assignment_row(db):
    _request_with_individual_assignment(db)

    AssignmentService(db).assign_to_group("260723-001", "plumber", MANAGER_ID)

    rows = db.query(RequestAssignment).filter(
        RequestAssignment.request_number == "260723-001").all()
    by_type = {r.assignment_type: r for r in rows if r.status == "active"}
    assert "individual" not in by_type
    assert by_type["group"].group_specialization == "plumber"
    assert by_type["group"].executor_id is None


def test_assign_to_executor_still_sets_executor_id(db):
    # Symmetry sanity check — assign_to_executor's own behavior unchanged.
    req = Request(
        request_number="260723-002",
        user_id=APPLICANT_ID,
        category="plumbing",
        description="test",
        status="Новая",
    )
    db.add(req)
    db.commit()

    AssignmentService(db).assign_to_executor("260723-002", OLD_EXECUTOR_ID, MANAGER_ID)

    req = db.query(Request).filter(Request.request_number == "260723-002").one()
    assert req.executor_id == OLD_EXECUTOR_ID
    assert req.assignment_type == "individual"
