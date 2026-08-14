"""Unit tests for ShiftAssignmentService."""
from datetime import datetime, date
from unittest.mock import MagicMock, patch

from uk_management_bot.services.shift_assignment_service import (
    ShiftAssignmentService,
)
from uk_management_bot.utils.constants import ROLE_EXECUTOR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_shift(
    shift_id=1,
    user_id=None,
    status="planned",
    specialization_focus=None,
    planned_start=None,
    planned_end=None,
):
    shift = MagicMock()
    shift.id = shift_id
    shift.user_id = user_id
    shift.status = status
    shift.specialization_focus = specialization_focus
    planned_start = planned_start or datetime(2026, 4, 5, 9, 0)
    planned_end = planned_end or datetime(2026, 4, 5, 18, 0)
    shift.planned_start_time = planned_start
    shift.planned_end_time = planned_end
    shift.assigned_at = None
    shift.assigned_by_user_id = None
    shift.geographic_zone = None
    return shift


def _make_executor(
    user_id=10,
    first_name="Ivan",
    last_name="Petrov",
    role=ROLE_EXECUTOR,
    status="approved",
    specialization=None,
    rating=None,
):
    user = MagicMock()
    user.id = user_id
    user.first_name = first_name
    user.last_name = last_name
    # PR-31/DB-060: legacy .role dropped; roles JSON + active_role drive logic.
    user.roles = f'["{role}"]'
    user.active_role = role
    user.status = status
    user.specialization = specialization
    user.rating = rating
    user.telegram_id = user_id + 1000
    return user


def _row_unchanged(db, shift):
    """AUD5-ARCH-7: перед записью сервис перечитывает строку под блокировкой.

    Здесь дубль-БД возвращает ТУ ЖЕ смену — сценарий «строку никто не трогал».
    Реальная гонка (другое соединение меняет строку) проверяется на настоящей
    БД в tests/services/test_shift_assign_race.py; мок такое не воспроизводит.
    """
    (db.query.return_value.filter.return_value
       .populate_existing.return_value
       .with_for_update.return_value.first.return_value) = shift


def _make_service():
    """Build service with all dependencies mocked."""
    db = MagicMock()
    with (
        # AUD5-ARCH-3 волна 2: модуль резолва имён — подмодуль пакета .service
        patch("uk_management_bot.services.shift_assignment_service.service.AssignmentService"),
        patch("uk_management_bot.services.shift_assignment_service.service.NotificationService"),
    ):
        service = ShiftAssignmentService(db)
    service.db = db
    return service, db


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

class TestConstructor:
    def test_weights_sum_to_one(self):
        service, _ = _make_service()
        total = sum(service.weights.values())
        assert abs(total - 1.0) < 1e-9

    def test_weights_keys(self):
        service, _ = _make_service()
        expected = {"specialization", "workload", "rating", "availability", "preference", "geographic"}
        assert set(service.weights.keys()) == expected


# ---------------------------------------------------------------------------
# _calculate_specialization_match
# ---------------------------------------------------------------------------

class TestCalculateSpecializationMatch:
    def test_no_required_specs_returns_neutral(self):
        service, _ = _make_service()
        shift = _make_shift(specialization_focus=None)
        executor = _make_executor(specialization=None)
        assert service.scoring_engine._calculate_specialization_match(shift, executor) == 0.5

    def test_executor_no_specialization_returns_blocking(self):
        service, _ = _make_service()
        shift = _make_shift(specialization_focus=["plumbing"])
        executor = _make_executor(specialization=None)
        assert service.scoring_engine._calculate_specialization_match(shift, executor) == -1.0

    def test_missing_required_spec_returns_blocking(self):
        service, _ = _make_service()
        shift = _make_shift(specialization_focus=["plumbing", "electric"])
        executor = _make_executor(specialization=["plumbing"])
        assert service.scoring_engine._calculate_specialization_match(shift, executor) == -1.0

    def test_exact_match_returns_one(self):
        service, _ = _make_service()
        shift = _make_shift(specialization_focus=["plumbing"])
        executor = _make_executor(specialization=["plumbing"])
        assert service.scoring_engine._calculate_specialization_match(shift, executor) == 1.0

    def test_superset_returns_high(self):
        service, _ = _make_service()
        shift = _make_shift(specialization_focus=["plumbing"])
        executor = _make_executor(specialization=["plumbing", "electric"])
        assert service.scoring_engine._calculate_specialization_match(shift, executor) == 0.9

    def test_string_specialization_parsed(self):
        service, _ = _make_service()
        import json
        shift = _make_shift(specialization_focus=["plumbing"])
        executor = _make_executor(specialization=json.dumps(["plumbing"]))
        result = service.scoring_engine._calculate_specialization_match(shift, executor)
        assert result >= 0.9

    def test_invalid_json_string_treated_as_single_spec(self):
        service, _ = _make_service()
        shift = _make_shift(specialization_focus=["plumbing"])
        executor = _make_executor(specialization="plumbing")
        result = service.scoring_engine._calculate_specialization_match(shift, executor)
        assert result == 1.0


# ---------------------------------------------------------------------------
# _calculate_rating_score
# ---------------------------------------------------------------------------

class TestCalculateRatingScore:
    def test_no_rating_returns_neutral(self):
        service, _ = _make_service()
        executor = _make_executor(rating=None)
        del executor.rating  # simulate missing attribute
        score = service.scoring_engine._calculate_rating_score(executor)
        assert score == 0.5

    def test_rating_none_returns_neutral(self):
        service, _ = _make_service()
        executor = _make_executor(rating=None)
        assert service.scoring_engine._calculate_rating_score(executor) == 0.5

    def test_max_rating_5_returns_one(self):
        service, _ = _make_service()
        executor = _make_executor(rating=5.0)
        assert service.scoring_engine._calculate_rating_score(executor) == 1.0

    def test_min_rating_1_returns_zero(self):
        service, _ = _make_service()
        executor = _make_executor(rating=1.0)
        assert service.scoring_engine._calculate_rating_score(executor) == 0.0

    def test_mid_rating_3_returns_half(self):
        service, _ = _make_service()
        executor = _make_executor(rating=3.0)
        assert service.scoring_engine._calculate_rating_score(executor) == 0.5

    def test_clamps_above_five(self):
        service, _ = _make_service()
        executor = _make_executor(rating=10.0)
        assert service.scoring_engine._calculate_rating_score(executor) == 1.0

    def test_clamps_below_one(self):
        service, _ = _make_service()
        executor = _make_executor(rating=0.0)
        assert service.scoring_engine._calculate_rating_score(executor) == 0.0


# ---------------------------------------------------------------------------
# _calculate_preference_score
# ---------------------------------------------------------------------------

class TestCalculatePreferenceScore:
    def test_returns_neutral(self):
        service, _ = _make_service()
        shift = _make_shift()
        executor = _make_executor()
        assert service.scoring_engine._calculate_preference_score(shift, executor) == 0.5


# ---------------------------------------------------------------------------
# _calculate_geographic_score
# ---------------------------------------------------------------------------

class TestCalculateGeographicScore:
    def test_returns_neutral(self):
        service, _ = _make_service()
        shift = _make_shift()
        executor = _make_executor()
        assert service.scoring_engine._calculate_geographic_score(shift, executor) == 0.5


# ---------------------------------------------------------------------------
# _calculate_workload_score
# ---------------------------------------------------------------------------

class TestCalculateWorkloadScore:
    def test_zero_shifts_zero_requests_returns_one(self):
        service, db = _make_service()
        shift = _make_shift()
        executor = _make_executor()

        # Query chain: first call → Shift count, second → Request count
        shift_q = MagicMock()
        shift_q.filter.return_value.count.return_value = 0
        request_q = MagicMock()
        request_q.filter.return_value.count.return_value = 0
        db.query.side_effect = [shift_q, request_q]

        score = service.scoring_engine._calculate_workload_score(shift, executor)
        assert score == 1.0

    def test_max_shifts_and_requests_returns_zero(self):
        service, db = _make_service()
        shift = _make_shift()
        executor = _make_executor()

        shift_q = MagicMock()
        shift_q.filter.return_value.count.return_value = 7
        request_q = MagicMock()
        request_q.filter.return_value.count.return_value = 10
        db.query.side_effect = [shift_q, request_q]

        score = service.scoring_engine._calculate_workload_score(shift, executor)
        assert score == 0.0

    def test_db_error_propagates(self):
        """A4/AUD3-27: DB-ошибка больше НЕ маскируется нейтральной 0.5."""
        import pytest
        from sqlalchemy.exc import OperationalError, SQLAlchemyError

        service, db = _make_service()
        shift = _make_shift()
        executor = _make_executor()
        db.query.side_effect = OperationalError("SELECT 1", {}, RuntimeError("down"))
        with pytest.raises(SQLAlchemyError):
            service.scoring_engine._calculate_workload_score(shift, executor)


# ---------------------------------------------------------------------------
# _calculate_conflict_penalties
# ---------------------------------------------------------------------------

class TestCalculateConflictPenalties:
    def test_few_shifts_no_penalty(self):
        service, db = _make_service()
        shift = _make_shift()
        executor = _make_executor()

        q = MagicMock()
        q.filter.return_value.count.return_value = 2
        db.query.return_value = q

        penalty = service.scoring_engine._calculate_conflict_penalties(shift, executor)
        assert penalty == 0.0

    def test_many_shifts_adds_penalty(self):
        service, db = _make_service()
        shift = _make_shift()
        executor = _make_executor()

        q = MagicMock()
        q.filter.return_value.count.return_value = 5
        db.query.return_value = q

        penalty = service.scoring_engine._calculate_conflict_penalties(shift, executor)
        assert penalty == 0.3


# ---------------------------------------------------------------------------
# _analyze_workload_distribution
# ---------------------------------------------------------------------------

class TestAnalyzeWorkloadDistribution:
    def test_no_assigned_shifts(self):
        service, _ = _make_service()
        shifts = [_make_shift(shift_id=i, user_id=None) for i in range(3)]
        result = service.workload_balancer._analyze_workload_distribution(shifts)
        assert result["unassigned_shifts"] == 3
        assert result["is_balanced"] is False

    def test_balanced_one_executor(self):
        service, _ = _make_service()
        shifts = [_make_shift(shift_id=i, user_id=1) for i in range(3)]
        result = service.workload_balancer._analyze_workload_distribution(shifts)
        assert result["is_balanced"] is True
        assert result["unique_executors"] == 1

    def test_unbalanced_two_executors(self):
        service, _ = _make_service()
        shifts = (
            [_make_shift(shift_id=i, user_id=1) for i in range(5)] +
            [_make_shift(shift_id=i + 10, user_id=2) for i in range(1)]
        )
        result = service.workload_balancer._analyze_workload_distribution(shifts)
        assert result["is_balanced"] is False

    def test_stats_keys_present(self):
        service, _ = _make_service()
        shifts = [_make_shift(user_id=1)]
        result = service.workload_balancer._analyze_workload_distribution(shifts)
        for key in ("total_shifts", "assigned_shifts", "unassigned_shifts", "avg_load", "max_load", "min_load"):
            assert key in result


# ---------------------------------------------------------------------------
# _get_available_executors
# ---------------------------------------------------------------------------

class TestGetAvailableExecutors:
    def test_returns_query_result(self):
        service, db = _make_service()
        executors = [_make_executor(user_id=i) for i in range(3)]
        q = MagicMock()
        q.filter.return_value.all.return_value = executors
        db.query.return_value = q
        result = service._get_available_executors()
        assert result == executors


# ---------------------------------------------------------------------------
# balance_executor_workload
# ---------------------------------------------------------------------------

class TestBalanceExecutorWorkload:
    def test_no_shifts_returns_message(self):
        service, db = _make_service()
        q = MagicMock()
        q.filter.return_value.all.return_value = []
        db.query.return_value = q
        result = service.balance_executor_workload(date.today())
        assert "message" in result

    def test_already_balanced_skips_rebalance(self):
        service, db = _make_service()
        # One executor with 1 shift = balanced
        shifts = [_make_shift(user_id=1)]
        q = MagicMock()
        q.filter.return_value.all.return_value = shifts
        db.query.return_value = q
        result = service.balance_executor_workload(date.today())
        # balanced → no rebalancing performed
        assert "distribution" in result or "message" in result

    def test_db_error_returns_error_dict(self):
        service, db = _make_service()
        db.query.side_effect = Exception("fail")
        result = service.balance_executor_workload(date.today())
        assert "error" in result


# ---------------------------------------------------------------------------
# resolve_assignment_conflicts
# ---------------------------------------------------------------------------

class TestResolveAssignmentConflicts:
    def test_shift_not_found(self):
        service, db = _make_service()
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q
        result = service.resolve_assignment_conflicts(999)
        assert "error" in result

    def test_shift_no_executor(self):
        service, db = _make_service()
        shift = _make_shift(user_id=None)
        q = MagicMock()
        q.filter.return_value.first.return_value = shift
        db.query.return_value = q
        result = service.resolve_assignment_conflicts(shift.id)
        assert "error" in result


# ---------------------------------------------------------------------------
# auto_assign_executors_to_shifts
# ---------------------------------------------------------------------------

class TestAutoAssignExecutorsToShifts:
    def test_empty_shifts_list(self):
        service, _ = _make_service()
        result = service.auto_assign_executors_to_shifts([])
        assert result["total_shifts"] == 0

    def test_all_shifts_already_assigned_no_force(self):
        service, db = _make_service()
        # Shifts with assigned user_id, force_reassign=False
        shifts = [_make_shift(user_id=5), _make_shift(shift_id=2, user_id=6)]
        # Stub audit db.add/commit
        db.add = MagicMock()
        db.commit = MagicMock()
        result = service.auto_assign_executors_to_shifts(shifts, force_reassign=False)
        assert result["successful_assignments"] == 0
        assert len(result["warnings"]) == 2

    def test_no_available_executors(self):
        service, db = _make_service()
        shifts = [_make_shift()]
        # _get_available_executors returns empty
        service._get_available_executors = MagicMock(return_value=[])
        db.add = MagicMock()
        db.commit = MagicMock()
        result = service.auto_assign_executors_to_shifts(shifts)
        assert result["successful_assignments"] == 0
        assert any("исполнителей" in w.lower() for w in result["warnings"])

    def test_successful_assignment(self):
        service, db = _make_service()
        shift = _make_shift()
        executor = _make_executor()
        service._get_available_executors = MagicMock(return_value=[executor])
        service._assign_single_shift = MagicMock(return_value={
            "success": True,
            "shift_id": shift.id,
            "executor_id": executor.id,
            "executor_name": "Ivan Petrov",
            "assignment_score": 0.8,
            "reasons": [],
            "minor_conflicts": 0,
        })
        service._update_executor_workload_cache = MagicMock()
        service._create_assignment_audit = MagicMock()
        service._notify_successful_assignments = MagicMock()
        result = service.auto_assign_executors_to_shifts([shift])
        assert result["successful_assignments"] == 1
        assert result["failed_assignments"] == 0

    def test_exception_returns_error_structure(self):
        service, db = _make_service()
        # Force exception in _get_available_executors
        service._get_available_executors = MagicMock(side_effect=Exception("boom"))
        shifts = [_make_shift()]
        result = service.auto_assign_executors_to_shifts(shifts)
        assert "error" in result
        assert result["failed_assignments"] == 1


# ---------------------------------------------------------------------------
# _check_assignment_conflicts
# ---------------------------------------------------------------------------

class TestCheckAssignmentConflicts:
    def test_executor_not_found(self):
        service, db = _make_service()
        shift = _make_shift()
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q
        conflicts = service.conflict_detector._check_assignment_conflicts(shift, 999)
        assert len(conflicts) == 1
        assert conflicts[0].severity == "critical"
        assert conflicts[0].type == "executor_not_found"

    def test_wrong_role_creates_high_conflict(self):
        service, db = _make_service()
        shift = _make_shift()
        executor = _make_executor(role="applicant")
        # availability score > 0.5 → no time conflict
        service.scoring_engine._calculate_availability_score = MagicMock(return_value=1.0)
        q = MagicMock()
        q.filter.return_value.first.return_value = executor
        db.query.return_value = q
        conflicts = service.conflict_detector._check_assignment_conflicts(shift, executor.id)
        types = [c.type for c in conflicts]
        assert "invalid_role" in types

    def test_no_conflicts_for_valid_executor(self):
        service, db = _make_service()
        shift = _make_shift()
        executor = _make_executor(role=ROLE_EXECUTOR, status="approved")
        service.scoring_engine._calculate_availability_score = MagicMock(return_value=1.0)
        q = MagicMock()
        q.filter.return_value.first.return_value = executor
        db.query.return_value = q
        conflicts = service.conflict_detector._check_assignment_conflicts(shift, executor.id)
        assert conflicts == []


# ---------------------------------------------------------------------------
# _calculate_availability_score
# ---------------------------------------------------------------------------


class TestAssignSingleShift:
    def test_no_executors_returns_failure(self):
        service, db = _make_service()
        shift = _make_shift()
        service.scoring_engine._evaluate_executors_for_shift = MagicMock(return_value=[])

        result = service._assign_single_shift(shift, [])
        assert result["success"] is False
        assert "error" in result

    def test_successful_assignment(self):
        service, db = _make_service()
        shift = _make_shift()
        executor = _make_executor()

        score = MagicMock()
        score.executor_id = executor.id
        score.executor_name = "Ivan Petrov"
        score.total_score = 0.8
        score.reasons = []

        service.scoring_engine._evaluate_executors_for_shift = MagicMock(return_value=[score])
        service.conflict_detector._check_assignment_conflicts = MagicMock(return_value=[])
        db.add = MagicMock()
        db.commit = MagicMock()
        _row_unchanged(db, shift)

        result = service._assign_single_shift(shift, [executor])

        assert result["success"] is True
        assert result["executor_id"] == executor.id
        assert shift.user_id == executor.id

    def test_critical_conflict_prevents_assignment(self):
        service, db = _make_service()
        shift = _make_shift()
        executor = _make_executor()

        score = MagicMock()
        score.executor_id = executor.id
        score.executor_name = "Ivan Petrov"
        score.total_score = 0.8

        conflict = MagicMock()
        conflict.severity = "critical"

        service.scoring_engine._evaluate_executors_for_shift = MagicMock(return_value=[score])
        service.conflict_detector._check_assignment_conflicts = MagicMock(return_value=[conflict])
        service.conflict_detector._conflict_to_dict = MagicMock(return_value={})

        result = service._assign_single_shift(shift, [executor])

        assert result["success"] is False
        assert "conflicts" in result

    def test_db_exception_returns_error(self):
        service, db = _make_service()
        shift = _make_shift()
        executor = _make_executor()

        service.scoring_engine._evaluate_executors_for_shift = MagicMock(side_effect=Exception("boom"))

        result = service._assign_single_shift(shift, [executor])
        assert result["success"] is False
        assert "error" in result

    # ── AUD3-13: перебор кандидатов, а не только топового ──────────────────

    @staticmethod
    def _score(executor_id: int, total: float, name: str = "Ex"):
        s = MagicMock()
        s.executor_id = executor_id
        s.executor_name = name
        s.total_score = total
        s.reasons = []
        return s

    def test_falls_through_to_next_candidate_on_critical_conflict(self):
        """AUD3-13: топовый по агрегатной оценке может провалить hard-проверку.

        Раньше метод брал `executor_scores[0]`, и при критическом конфликте у
        него смена оставалась НЕназначенной — при живом втором кандидате без
        конфликтов. Агрегатный score и hard-конфликты — разные измерения, поэтому
        «лучший по score» не равно «назначаемый».
        """
        service, db = _make_service()
        shift = _make_shift()

        top, second = self._score(11, 0.9, "Top"), self._score(22, 0.5, "Second")
        service.scoring_engine._evaluate_executors_for_shift = MagicMock(
            return_value=[second, top]  # намеренно НЕ по порядку: сортирует метод
        )

        critical = MagicMock()
        critical.severity = "critical"
        service.conflict_detector._check_assignment_conflicts = MagicMock(
            side_effect=lambda sh, eid: [critical] if eid == 11 else []
        )
        service.conflict_detector._conflict_to_dict = MagicMock(return_value={})
        db.add = MagicMock()
        db.commit = MagicMock()
        _row_unchanged(db, shift)

        result = service._assign_single_shift(shift, [])

        assert result["success"] is True
        assert result["executor_id"] == 22, "должен быть назначен второй кандидат"
        assert shift.user_id == 22

    def test_minor_conflicts_do_not_trigger_fallthrough(self):
        """Границу не сдвигаем: low/medium никогда не блокировали назначение.

        Иначе «перебор» превратился бы в тихое изменение политики — топовый
        кандидат уступал бы место второму из-за незначительного конфликта.
        """
        service, db = _make_service()
        shift = _make_shift()

        top, second = self._score(11, 0.9), self._score(22, 0.5)
        service.scoring_engine._evaluate_executors_for_shift = MagicMock(
            return_value=[top, second]
        )
        minor = MagicMock()
        minor.severity = "medium"
        service.conflict_detector._check_assignment_conflicts = MagicMock(
            return_value=[minor]
        )
        db.add = MagicMock()
        db.commit = MagicMock()
        _row_unchanged(db, shift)

        result = service._assign_single_shift(shift, [])

        assert result["success"] is True
        assert result["executor_id"] == 11
        assert result["minor_conflicts"] == 1

    def test_all_candidates_blocked_reports_every_attempt(self):
        """Если заблокированы все — отчёт обязан показать ВСЕ попытки.

        Прежний контракт (`attempted_executor` — один id) сохранён для
        совместимости с `handlers/shift_management/assignment_a.py`, но одного id
        теперь недостаточно: без списка попыток менеджер не понимает, перебор
        вообще был или метод сдался на первом.
        """
        service, db = _make_service()
        shift = _make_shift()

        service.scoring_engine._evaluate_executors_for_shift = MagicMock(
            return_value=[self._score(11, 0.9), self._score(22, 0.5)]
        )
        critical = MagicMock()
        critical.severity = "high"
        service.conflict_detector._check_assignment_conflicts = MagicMock(
            return_value=[critical]
        )
        service.conflict_detector._conflict_to_dict = MagicMock(return_value={"x": 1})

        result = service._assign_single_shift(shift, [])

        assert result["success"] is False
        assert result["attempted_executor"] == 11, "контракт для существующего хендлера"
        assert result["attempted_executors"] == [11, 22]
        assert result["conflicts"], "конфликты топового кандидата — основная причина"
        assert shift.user_id is None, "ни один кандидат не должен быть записан"


# ---------------------------------------------------------------------------
# _evaluate_executors_for_shift
# ---------------------------------------------------------------------------

class TestEvaluateExecutorsForShift:
    def test_no_executors_returns_empty(self):
        service, _ = _make_service()
        shift = _make_shift()
        result = service.scoring_engine._evaluate_executors_for_shift(shift, [])
        assert result == []

    def test_skips_executors_with_zero_score(self):
        service, db = _make_service()
        shift = _make_shift()
        executor = _make_executor()

        zero_score = MagicMock()
        zero_score.total_score = 0.0

        service.scoring_engine._calculate_executor_score = MagicMock(return_value=zero_score)

        result = service.scoring_engine._evaluate_executors_for_shift(shift, [executor])
        assert result == []

    def test_includes_executors_with_positive_score(self):
        service, db = _make_service()
        shift = _make_shift()
        executor = _make_executor()

        positive_score = MagicMock()
        positive_score.total_score = 0.7

        service.scoring_engine._calculate_executor_score = MagicMock(return_value=positive_score)

        result = service.scoring_engine._evaluate_executors_for_shift(shift, [executor])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# reassign_on_absence — AUD3-12
# ---------------------------------------------------------------------------


class TestReassignOnAbsence:
    """AUD3-12: семантика переназначения при отсутствии исполнителя.

    Дефект был не «нет rollback», а спекулятивная мутация: `shift.user_id = None`
    ставилось ДО попытки назначения, а `_assign_single_shift` коммитит внутри
    себя. При неудачной попытке смена оставалась грязной, и **следующий** удачный
    внутренний commit (для другой смены пачки) записывал это обнуление — смена
    молча теряла исполнителя, без единой записи в аудите. Внешний `rollback()`
    тут бесполезен: коммит уже произошёл.

    Решение владельца 2026-07-26: (1) не мутировать до попытки; (2) если замены
    нет — снимать исполнителя ЯВНО и с аудитом. Итог в БД тот же, что получался
    случайно, но теперь он решение, а не побочный эффект, и у него есть след.
    """

    ABSENT = 77

    def _service_with_shift(self, shift):
        service, db = _make_service()
        db.query.return_value.filter.return_value.all.return_value = [shift]
        service._get_available_executors = MagicMock(return_value=[_make_executor(user_id=10)])
        db.add = MagicMock()
        db.commit = MagicMock()
        return service, db

    def test_does_not_clear_executor_before_attempt(self):
        """Ключевое: на момент попытки смена ещё ЗА отсутствующим исполнителем.

        Иначе неудачная попытка оставляет грязный объект, который запишет чужой
        commit. Проверяется значением, ВИДИМЫМ внутри `_assign_single_shift`, —
        именно там раньше уже стоял None.
        """
        shift = _make_shift(user_id=self.ABSENT)
        service, db = self._service_with_shift(shift)

        seen = {}

        def _attempt(sh, executors):
            seen["user_id_at_attempt"] = sh.user_id
            sh.user_id = 10
            return {'success': True, 'shift_id': sh.id, 'executor_id': 10}

        service._assign_single_shift = MagicMock(side_effect=_attempt)

        result = service.reassign_on_absence(self.ABSENT)

        assert seen["user_id_at_attempt"] == self.ABSENT, (
            "смена обнулена ДО попытки — вернулась спекулятивная мутация AUD3-12"
        )
        assert result['reassigned'] == 1

    def test_failed_reassignment_unassigns_explicitly_with_audit(self):
        """Замены нет → снимаем явно И пишем аудит.

        До фикса смена тоже оказывалась с NULL, но БЕЗ следа: отличие именно в
        записи аудита, поэтому она и проверяется.
        """
        shift = _make_shift(user_id=self.ABSENT)
        service, db = self._service_with_shift(shift)
        service._assign_single_shift = MagicMock(return_value={
            'success': False, 'shift_id': shift.id, 'error': 'Нет подходящих исполнителей',
        })

        result = service.reassign_on_absence(self.ABSENT, reason="sick-leave")

        assert result['failed'] == 1
        assert shift.user_id is None, "смена должна остаться явно непокрытой"
        actions = [
            call.args[0].action
            for call in db.add.call_args_list
            if call.args and hasattr(call.args[0], "action")
        ]
        assert "SHIFT_UNASSIGNED_NO_REPLACEMENT" in actions, (
            "снятие исполнителя без записи в аудит — это и был исходный дефект: "
            f"в аудит попало только {actions}"
        )

    def test_absent_executor_excluded_from_candidates(self):
        """Отсутствующего нельзя предлагать заменой самому себе.

        `_get_available_executors()` отдаёт всех approved-исполнителей, включая
        отсутствующего, — переназначение на него было бы no-op'ом, замаскированным
        под успех.
        """
        shift = _make_shift(user_id=self.ABSENT)
        service, db = _make_service()
        db.query.return_value.filter.return_value.all.return_value = [shift]
        service._get_available_executors = MagicMock(return_value=[
            _make_executor(user_id=self.ABSENT), _make_executor(user_id=10),
        ])
        db.add = MagicMock()
        db.commit = MagicMock()

        passed = {}

        def _attempt(sh, executors):
            passed["ids"] = [e.id for e in executors]
            sh.user_id = 10
            return {'success': True, 'shift_id': sh.id, 'executor_id': 10}

        service._assign_single_shift = MagicMock(side_effect=_attempt)

        service.reassign_on_absence(self.ABSENT)

        assert self.ABSENT not in passed["ids"], (
            "отсутствующий исполнитель остался в списке кандидатов на свою же смену"
        )
        assert 10 in passed["ids"]

    def test_no_shifts_returns_message(self):
        """Регресс: пустой набор смен — не ошибка."""
        service, db = _make_service()
        db.query.return_value.filter.return_value.all.return_value = []
        result = service.reassign_on_absence(self.ABSENT)
        assert 'message' in result

    def test_exception_rolls_back_session(self):
        """AUD3-12 (error-path): сбой обязан откатить сессию.

        До этой точки в сессии могут висеть незакоммиченные мутации — явное
        снятие исполнителя и записи аудита. Без rollback они уедут в БД с первым
        же commit'ом следующего вызова по этой сессии, то есть тем же механизмом,
        который и был исходным дефектом.
        """
        shift = _make_shift(user_id=self.ABSENT)
        service, db = self._service_with_shift(shift)
        service._assign_single_shift = MagicMock(side_effect=Exception("boom"))

        result = service.reassign_on_absence(self.ABSENT)

        assert 'error' in result
        assert db.rollback.called, "сессия не откатана — грязные мутации уедут с чужим commit'ом"
