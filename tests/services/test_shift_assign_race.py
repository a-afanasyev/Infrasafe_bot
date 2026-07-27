"""П6-хвост / AUD5-ARCH-7 — гонка автоназначения против ручного.

Пункт был заведён с пометкой «требует подтверждения». Подтверждено: API-путь
держит строку смены под `FOR UPDATE`
(`api/shifts/service.get_shift_for_update`), а планировщик выбирал смены по
`user_id IS NULL` без блокировки и писал результат подбора безусловно. Между
выборкой и записью проходит подбор кандидатов (скоринг + проверка конфликтов),
и ручное назначение менеджера в этом окне затиралось системным — молча, без
записи в аудите.

Гонка воспроизводится не таймингами, а её сутью: строку меняет ДРУГОЕ
соединение, пока сервис держит свою версию объекта в памяти.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService

AUTO_EXECUTOR_ID = 10
MANUAL_EXECUTOR_ID = 20
START = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)


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
    """Две сессии на одной БД — планировщик и «менеджер из API»."""
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    scheduler, manager = factory(), factory()
    yield scheduler, manager
    scheduler.close()
    manager.close()


@pytest.fixture()
def unassigned_shift(sessions):
    scheduler, _ = sessions
    for uid, name in ((AUTO_EXECUTOR_ID, "Auto"), (MANUAL_EXECUTOR_ID, "Manual")):
        scheduler.add(User(
            id=uid, telegram_id=uid, first_name=name, roles='["executor"]',
            active_role="executor", status="approved", language="ru",
        ))
    shift = Shift(user_id=None, status="planned", start_time=START,
                  end_time=START + timedelta(hours=8))
    scheduler.add(shift)
    scheduler.commit()
    return shift


def _service_picking(session, executor_id: int) -> ShiftAssignmentService:
    """Сервис, чей подбор всегда выбирает `executor_id` и не видит конфликтов.

    Подменяются скоринг и детектор конфликтов — то есть уровень НИЖЕ предмета
    пункта. Сам `_assign_single_shift` (в нём и живёт защита) настоящий.
    """
    service = ShiftAssignmentService(session)
    score = MagicMock()
    score.executor_id = executor_id
    score.executor_name = f"Executor {executor_id}"
    score.total_score = 0.9
    score.reasons = []
    service.scoring_engine._evaluate_executors_for_shift = MagicMock(return_value=[score])
    service.conflict_detector._check_assignment_conflicts = MagicMock(return_value=[])
    return service


class TestManualAssignmentIsNotOverwritten:
    def test_assignment_made_during_scoring_wins(self, sessions, unassigned_shift):
        """Пока планировщик подбирал кандидата, менеджер назначил своего."""
        scheduler, manager = sessions
        service = _service_picking(scheduler, AUTO_EXECUTOR_ID)

        # Планировщик уже прочитал смену как свободную (объект в памяти).
        assert unassigned_shift.user_id is None

        # ... и в этот момент менеджер назначает исполнителя другим соединением.
        manager.query(Shift).filter(Shift.id == unassigned_shift.id).update(
            {"user_id": MANUAL_EXECUTOR_ID}, synchronize_session=False
        )
        manager.commit()

        result = service._assign_single_shift(unassigned_shift, [])

        assert result["success"] is False, "системное назначение затёрло ручное"
        assert result["error"] == "shift_changed_meanwhile"

        manager.expire_all()
        stored = manager.query(Shift).filter(Shift.id == unassigned_shift.id).first()
        assert stored.user_id == MANUAL_EXECUTOR_ID, (
            f"в БД оказался исполнитель {stored.user_id} — планировщик перезаписал "
            "решение менеджера"
        )

    def test_untouched_shift_is_still_assigned(self, sessions, unassigned_shift):
        """Защита не должна мешать обычному случаю: строка не менялась."""
        scheduler, manager = sessions
        service = _service_picking(scheduler, AUTO_EXECUTOR_ID)

        result = service._assign_single_shift(unassigned_shift, [])

        assert result["success"] is True
        assert result["executor_id"] == AUTO_EXECUTOR_ID

        manager.expire_all()
        stored = manager.query(Shift).filter(Shift.id == unassigned_shift.id).first()
        assert stored.user_id == AUTO_EXECUTOR_ID

    def test_reassign_guards_against_the_value_it_saw(self, sessions, unassigned_shift):
        """Переназначение сверяется с ТЕМ исполнителем, которого видело.

        `force_reassign`/`reassign_on_absence` осознанно перезаписывают уже
        назначенную смену — но только ту же самую, а не ту, что менеджер уже
        успел передать третьему.
        """
        scheduler, manager = sessions
        scheduler.query(Shift).filter(Shift.id == unassigned_shift.id).update(
            {"user_id": MANUAL_EXECUTOR_ID}, synchronize_session=False
        )
        scheduler.commit()
        scheduler.expire_all()
        shift = scheduler.query(Shift).filter(Shift.id == unassigned_shift.id).first()
        assert shift.user_id == MANUAL_EXECUTOR_ID  # это состояние сервис и видит

        manager.query(Shift).filter(Shift.id == shift.id).update(
            {"user_id": 999}, synchronize_session=False
        )
        manager.commit()

        service = _service_picking(scheduler, AUTO_EXECUTOR_ID)
        result = service._assign_single_shift(shift, [])

        assert result["success"] is False
        assert result["error"] == "shift_changed_meanwhile"
