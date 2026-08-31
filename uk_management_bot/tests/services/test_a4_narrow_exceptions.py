"""A4 (AUD3-27 / AUD5-ARCH-5 / AUD5-CODE-13) — DB-ошибки в money-paths
не маскируются «безопасными» значениями.

Семейство broad-except маскировало SQLAlchemyError безопасными дефолтами:
скоринг возвращал 0.5, проверка занятости — «занят», подбор лучшего
исполнителя — None, чтение/поиск заявок — пустые списки. Инфраструктурная
ошибка при этом тихо превращалась в бизнес-ответ («нет кандидатов»,
«нет заявок»), и планировщик/менеджер получали ложную картину.

Инвариант волны: sqlalchemy.exc.SQLAlchemyError пропагируется к вызывающему
(с logger.exception на месте), ожидаемые данные-ошибки обрабатываются
по-прежнему локально.
"""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from uk_management_bot.services.assignment_service import AssignmentService
from uk_management_bot.services.request_service import RequestService
from uk_management_bot.services.shift_assignment_service import (
    ShiftAssignmentService,
)
from uk_management_bot.services.shift_planning_service import ShiftPlanningService


def _db_err() -> SQLAlchemyError:
    """Реалистичная инфраструктурная ошибка (подкласс SQLAlchemyError)."""
    return OperationalError("SELECT 1", {}, RuntimeError("db down"))


# ---------------------------------------------------------------------------
# Хелперы конструирования сервисов (в стиле существующих сьютов)
# ---------------------------------------------------------------------------

def _make_assignment_shift_service():
    db = MagicMock()
    with (
        patch("uk_management_bot.services.shift_assignment_service.service.AssignmentService"),
        patch("uk_management_bot.services.shift_assignment_service.service.NotificationService"),
    ):
        service = ShiftAssignmentService(db)
    service.db = db
    return service, db


def _make_planning_service():
    db = MagicMock()
    with (
        patch("uk_management_bot.services.shift_planning_service.ShiftAnalytics"),
        patch("uk_management_bot.services.shift_planning_service.MetricsManager"),
        patch("uk_management_bot.services.shift_planning_service.RecommendationEngine"),
        patch("uk_management_bot.services.shift_planning_service.ShiftAssignmentService"),
    ):
        service = ShiftPlanningService(db)
    service.db = db
    return service, db


def _make_template():
    t = MagicMock()
    t.id = 1
    t.name = "T"
    t.start_hour = 9
    t.start_minute = 0
    t.duration_hours = 8
    t.required_specializations = []
    t.is_date_included = MagicMock(return_value=True)
    return t


def _make_shift():
    from datetime import datetime, timezone

    s = MagicMock()
    s.id = 1
    s.user_id = None
    s.specialization_focus = None
    s.planned_start_time = datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)
    s.planned_end_time = datetime(2026, 8, 14, 18, 0, tzinfo=timezone.utc)
    return s


def _make_executor(user_id=10):
    u = MagicMock()
    u.id = user_id
    u.first_name = "Ivan"
    u.last_name = "Petrov"
    u.specialization = None
    u.rating = None
    return u


# ---------------------------------------------------------------------------
# БЛОК 1 (AUD3-27): скоринг и занятость — DB-ошибка не превращается в 0.5/busy
# ---------------------------------------------------------------------------

class TestScoringDbErrorsPropagate:
    def test_workload_score_db_error_propagates_not_neutral(self):
        """scoring._calculate_workload_score: раньше except Exception → 0.5."""
        service, db = _make_assignment_shift_service()
        db.query.side_effect = _db_err()

        with pytest.raises(SQLAlchemyError):
            service.scoring_engine._calculate_workload_score(
                _make_shift(), _make_executor()
            )

    def test_availability_score_db_error_propagates_not_neutral(self):
        """scoring._calculate_availability_score: раньше except Exception → 0.5."""
        service, db = _make_assignment_shift_service()
        db.query.side_effect = _db_err()

        with pytest.raises(SQLAlchemyError):
            service.scoring_engine._calculate_availability_score(
                _make_shift(), _make_executor()
            )

    def test_evaluate_loop_db_error_propagates_not_silent_drop(self):
        """Цикл оценки кандидатов: DB-ошибка не «выкидывает исполнителя молча».

        Раньше except Exception → logger.error → continue: при лежащей БД
        список кандидатов молча пустел и назначение «честно» не находило
        исполнителей.
        """
        service, db = _make_assignment_shift_service()
        service.scoring_engine._calculate_executor_score = MagicMock(
            side_effect=_db_err()
        )

        with pytest.raises(SQLAlchemyError):
            service.scoring_engine._evaluate_executors_for_shift(
                _make_shift(), [_make_executor()]
            )

    def test_evaluate_loop_data_error_still_skips_executor(self):
        """Регресс-инвариант: НЕ-DB ошибка данных одного кандидата по-прежнему
        не роняет пачку — кандидат пропускается."""
        service, db = _make_assignment_shift_service()
        good_score = MagicMock()
        good_score.total_score = 0.7
        service.scoring_engine._calculate_executor_score = MagicMock(
            side_effect=[ValueError("битые данные кандидата"), good_score]
        )

        result = service.scoring_engine._evaluate_executors_for_shift(
            _make_shift(), [_make_executor(1), _make_executor(2)]
        )
        assert len(result) == 1


class TestGetBestExecutorDbError:
    def test_db_error_propagates_not_none(self):
        """service.get_best_executor_for_shift: раньше except Exception → None
        («лучший исполнитель не найден» при любой ошибке)."""
        service, db = _make_assignment_shift_service()
        db.query.side_effect = _db_err()

        with pytest.raises(SQLAlchemyError):
            service.get_best_executor_for_shift(_make_shift())


class TestPlanningBusyDbError:
    def test_is_executor_busy_db_error_propagates_not_busy(self):
        """planning._is_executor_busy: раньше except Exception → True
        («считаем занятым») — DB-ошибка тихо резала все назначения."""
        service, db = _make_planning_service()
        db.query.side_effect = _db_err()

        with pytest.raises(SQLAlchemyError):
            service._is_executor_busy(10, date(2026, 8, 14), _make_template())

    def test_available_executors_propagate_busy_db_error(self):
        """_get_available_executors_for_template не гасит DB-ошибку из
        _is_executor_busy возвратом [] («никто не доступен»)."""
        service, db = _make_planning_service()
        executor = _make_executor()
        db.query.return_value.filter.return_value.all.return_value = [executor]

        with (
            patch.object(service, "_can_executor_work_template", return_value=True),
            patch.object(service, "_is_executor_busy", side_effect=_db_err()),
        ):
            with pytest.raises(SQLAlchemyError):
                service._get_available_executors_for_template(
                    _make_template(), date(2026, 8, 14)
                )

    def test_create_shift_from_template_db_error_propagates_with_rollback(self):
        """create_shift_from_template: DB-ошибка пропагируется (после rollback),
        а не гасится в [] — выше по цепочке plan_weekly_schedule /
        auto_create_shifts кладут её в честный errors-отчёт."""
        service, db = _make_planning_service()
        db.query.side_effect = _db_err()

        with pytest.raises(SQLAlchemyError):
            service.create_shift_from_template(1, date(2026, 8, 14))
        db.rollback.assert_called()

    def test_plan_weekly_schedule_records_db_error_honestly(self):
        """Честный failed-путь планировщика: DB-ошибка создания смен по шаблону
        попадает в results['errors'], а не растворяется в «0 смен создано»."""
        service, db = _make_planning_service()
        template = _make_template()
        q = MagicMock()
        q.filter.return_value.all.return_value = [template]
        db.query.return_value = q
        service._update_shift_schedule = MagicMock()

        with patch.object(
            service, "create_shift_from_template", side_effect=_db_err()
        ):
            results = service.plan_weekly_schedule(date(2026, 8, 10))

        assert results["errors"], "DB-ошибка обязана попасть в errors-отчёт"
        assert results["statistics"]["total_shifts"] == 0


# ---------------------------------------------------------------------------
# БЛОК 3 (AUD5-CODE-13): request_service / assignment_service
# ---------------------------------------------------------------------------

class TestRequestServiceDbErrorsPropagate:
    def _svc(self):
        db = MagicMock()
        return RequestService(db), db

    def test_get_user_requests_db_error_propagates_not_empty(self):
        svc, db = self._svc()
        db.query.side_effect = _db_err()
        with pytest.raises(SQLAlchemyError):
            svc.get_user_requests(user_id=1)

    def test_get_request_by_number_db_error_propagates_not_none(self):
        """DB-ошибка не должна выглядеть как «заявка не найдена»."""
        svc, db = self._svc()
        db.query.side_effect = _db_err()
        with pytest.raises(SQLAlchemyError):
            svc.get_request_by_number("260814-001")

    def test_get_user_by_telegram_id_db_error_propagates_not_none(self):
        """DB-ошибка не должна выглядеть как «пользователь не найден»."""
        svc, db = self._svc()
        db.query.side_effect = _db_err()
        with pytest.raises(SQLAlchemyError):
            svc.get_user_by_telegram_id(12345)

    def test_search_requests_db_error_propagates_not_empty(self):
        svc, db = self._svc()
        db.query.side_effect = _db_err()
        with pytest.raises(SQLAlchemyError):
            svc.search_requests(category="electric")

    def test_get_request_statistics_db_error_propagates_not_zeros(self):
        """DB-ошибка не должна рисовать менеджеру нулевую статистику."""
        svc, db = self._svc()
        db.query.side_effect = _db_err()
        with pytest.raises(SQLAlchemyError):
            svc.get_request_statistics()

    def test_delete_request_db_error_propagates_with_rollback(self):
        """DB-ошибка не должна выглядеть как «нет прав / не найдена» (False)."""
        svc, db = self._svc()
        db.query.side_effect = _db_err()
        with pytest.raises(SQLAlchemyError):
            svc.delete_request("260814-001", user_id=1)
        db.rollback.assert_called()

    def test_add_media_to_request_db_error_propagates_with_rollback(self):
        svc, db = self._svc()
        db.query.side_effect = _db_err()
        with pytest.raises(SQLAlchemyError):
            svc.add_media_to_request("260814-001", ["file1"])
        db.rollback.assert_called()


# TestAssignmentServiceDbErrors удалён вместе со smart_assign_request (BUG-148).
