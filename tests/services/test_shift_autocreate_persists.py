"""Фантомное автосоздание смен: джоба рапортует «создано N», в БД — ноль строк.

Прод-инцидент 2026-08-31 (profk: уведомление «Создано 26 новых смен», при этом
`shifts_id_seq` не сдвинулся ни на единицу — не было даже откаченных INSERT).
Механизм: `create_shift_from_template` добавлял смены в сессию БЕЗ commit и
сразу звал автоназначение; его CAS-guard перечитывает строку по `Shift.id`
(у pending-объекта id ещё None) — «строка исчезла» → `db.rollback()`, и все
pending-вставки молча выброшены из сессии. Счётчик же считал питоновские
объекты из списка, поэтому уведомление уходило ежедневно.

Моками это не ловится принципиально: MagicMock-сессия «переживает» rollback.
Здесь настоящий sqlite и настоящие ShiftPlanningService/ShiftAssignmentService;
подменяется только уровень НИЖЕ предмета — скоринг, детектор конфликтов и
телеграм-уведомления (паттерн test_shift_assign_race.py).
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.shift_planning_service import ShiftPlanningService
from uk_management_bot.utils.business_time import business_today

EXECUTOR_ID = 10


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def sessions(engine):
    """Две сессии на одной БД: сервис и «проверяющий» (независимое чтение)."""
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    svc, probe = factory(), factory()
    yield svc, probe
    svc.close()
    probe.close()


@pytest.fixture()
def template(sessions):
    svc, _ = sessions
    svc.add(User(
        id=EXECUTOR_ID, telegram_id=EXECUTOR_ID, first_name="Auto",
        roles='["executor"]', active_role="executor", status="approved",
        language="ru",
    ))
    tpl = ShiftTemplate(
        name="Дежурный", start_hour=9, start_minute=0, duration_hours=8,
        min_executors=2, max_executors=3, is_active=True, auto_create=True,
        days_of_week=[1, 2, 3, 4, 5, 6, 7], advance_days=7,
    )
    svc.add(tpl)
    svc.commit()
    return tpl


def _service(session) -> ShiftPlanningService:
    """Настоящий планировщик; подменён только слой ниже предмета."""
    service = ShiftPlanningService(session)
    assignment = service.assignment_service

    score = MagicMock()
    score.executor_id = EXECUTOR_ID
    score.executor_name = f"Executor {EXECUTOR_ID}"
    score.total_score = 0.9
    score.reasons = []
    assignment.scoring_engine._evaluate_executors_for_shift = MagicMock(
        return_value=[score]
    )
    assignment.conflict_detector._check_assignment_conflicts = MagicMock(
        return_value=[]
    )
    assignment.notification_service = MagicMock()
    return service


class TestCreatedShiftsActuallyPersist:
    def test_created_shifts_are_rows_not_python_objects(self, sessions, template):
        """Главный сценарий инцидента: «создано N» обязано означать N строк."""
        svc, probe = sessions
        target = business_today() + timedelta(days=1)

        created = _service(svc).create_shift_from_template(template.id, target)

        rows = probe.query(Shift).all()
        assert len(created) == template.min_executors  # отчёт джобы
        assert len(rows) == len(created), (
            "смены посчитаны, но в БД не сохранены — фантомное автосоздание"
        )

    def test_assignment_survives_and_lands_in_db(self, sessions, template):
        """CAS-guard автоназначения обязан видеть строку (id уже есть) и
        назначение обязано доехать до БД, а не остаться на выброшенном объекте."""
        svc, probe = sessions
        target = business_today() + timedelta(days=1)

        _service(svc).create_shift_from_template(template.id, target)

        assigned = probe.query(Shift).filter(Shift.user_id == EXECUTOR_ID).count()
        assert assigned > 0, "автоназначение не сохранилось в БД"

    def test_auto_create_counter_matches_db(self, sessions, template):
        """Счётчик total_created (он же текст уведомления) равен числу строк."""
        svc, probe = sessions

        result = _service(svc).auto_create_shifts(days_ahead=2)

        rows = probe.query(Shift).count()
        assert result["total_created"] == rows
        assert rows > 0

    def test_assignment_failure_does_not_destroy_shifts(self, sessions, template):
        """Сбой подбора — не повод уничтожать смены: неназначенная planned-смена
        валидна, её доназначит менеджер или следующая балансировка."""
        svc, probe = sessions
        target = business_today() + timedelta(days=1)

        service = _service(svc)
        service.assignment_service.auto_assign_executors_to_shifts = MagicMock(
            side_effect=RuntimeError("подбор упал")
        )
        # fallback тоже пуст — исполнителей «нет»
        service._get_available_executors_for_template = MagicMock(return_value=[])

        created = service.create_shift_from_template(template.id, target)

        rows = probe.query(Shift).filter(Shift.status == "planned").all()
        assert len(rows) == len(created) == template.min_executors
        assert all(r.user_id is None for r in rows)
