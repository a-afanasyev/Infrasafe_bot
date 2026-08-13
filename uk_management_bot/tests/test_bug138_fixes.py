"""BUG-138 — предсуществующие дефекты пакета services/shift_assignment_service/.

  1. request_engine.auto_assign_requests_to_shift_executors: назначает
     smart_assign_request, а в assignment_details писал executor_id/shift_id
     от проигнорированного best_shift (отчёт мог врать) + захардкоженный
     assigned_by=1;
  2. request_engine.sync_request_assignments_with_shifts: в цикле по каждому
     mismatched-назначению гонялся ПОЛНЫЙ auto_assign_requests_to_shift_executors
     (O(N²), вложенные коммиты), а reassigned инкрементировался без проверки
     фактического успеха переназначения;
  3. balancer._rebalance_shifts: мутация списка underloaded (`pop(i)` /
     `underloaded[i] = ...`) внутри итерации по нему же;
  4. scoring._calculate_availability_score: лог «Разрешено перекрытие»
     использовал overlap_specs из ПОСЛЕДНЕЙ итерации цикла.
"""
import inspect
import logging
from unittest.mock import MagicMock, patch

from uk_management_bot.services.shift_assignment_service import request_engine as re_mod
from uk_management_bot.services.shift_assignment_service.request_engine import (
    RequestAssignmentEngine,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q(all_result=None):
    q = MagicMock()
    q.filter.return_value.all.return_value = all_result or []
    return q


def _make_request(number="260813-001", specialization="plumbing"):
    request = MagicMock()
    request.request_number = number
    request.specialization = specialization
    request.priority = "normal"
    request.location = None
    return request


def _make_shift(shift_id=7, user_id=99):
    shift = MagicMock()
    shift.id = shift_id
    shift.user_id = user_id
    return shift


def _engine_for_auto_assign(shifts, requests):
    """Движок с mock-БД: первый query — смены, второй — заявки."""
    db = MagicMock()
    db.query.side_effect = [_q(shifts), _q(requests)]
    return RequestAssignmentEngine(db), db


def _engine_for_sync(mismatched):
    """Движок с mock-БД: главный query по RequestAssignment + подзапрос Shift."""
    db = MagicMock()
    main_q = MagicMock()
    main_q.join.return_value.filter.return_value.all.return_value = mismatched
    db.query.side_effect = [main_q, MagicMock()]
    return RequestAssignmentEngine(db), db


def _make_assignment(number="260813-001", executor_id=15):
    a = MagicMock()
    a.request_number = number
    a.executor_id = executor_id
    return a


# ---------------------------------------------------------------------------
# 1. auto_assign_requests_to_shift_executors — честный отчёт
# ---------------------------------------------------------------------------

class TestAutoAssignHonestReport:
    def test_details_report_actual_assignment_not_best_shift(self):
        """1: executor_id в отчёте — от ФАКТИЧЕСКОГО назначения, не от best_shift.

        smart_assign_request сам выбирает исполнителя (SmartDispatcher), best_shift
        участвует только как pre-check кандидата. Раньше в отчёт писались
        best_shift.user_id / best_shift.id — назначение могло уйти другому.
        """
        engine, _ = _engine_for_auto_assign([_make_shift()], [_make_request()])
        engine._find_best_shift_for_request = MagicMock(
            return_value=_make_shift(shift_id=7, user_id=99)
        )
        actual = MagicMock()
        actual.executor_id = 55  # реальный исполнитель ≠ best_shift.user_id
        with patch.object(re_mod, "AssignmentService") as svc_cls:
            svc_cls.return_value.smart_assign_request.return_value = actual
            result = engine.auto_assign_requests_to_shift_executors()

        assert result["status"] == "success"
        assert result["assigned_requests"] == 1
        detail = result["assignment_details"][0]
        assert detail["executor_id"] == 55, (
            f"в отчёте executor_id от проигнорированного best_shift: {detail}"
        )
        # shift_id из best_shift был бы враньём: механизм назначения (smart_assign_
        # request → RequestAssignment) смену не фиксирует.
        assert detail.get("shift_id") != 7, (
            f"в отчёте shift_id от проигнорированного best_shift: {detail}"
        )

    def test_system_assignment_does_not_hardcode_assigned_by_1(self):
        """1: системное автоназначение не подписывается user_id=1."""
        engine, _ = _engine_for_auto_assign([_make_shift()], [_make_request()])
        engine._find_best_shift_for_request = MagicMock(return_value=_make_shift())
        with patch.object(re_mod, "AssignmentService") as svc_cls:
            svc_cls.return_value.smart_assign_request.return_value = MagicMock()
            engine.auto_assign_requests_to_shift_executors()

        call = svc_cls.return_value.smart_assign_request.call_args
        assert call.kwargs.get("assigned_by") is None, (
            f"системное назначение подписано assigned_by={call.kwargs.get('assigned_by')!r}"
        )

    def test_no_candidate_shift_skips_assignment(self):
        """Регресс: pre-check best_shift сохранён — без кандидата не назначаем."""
        engine, _ = _engine_for_auto_assign([_make_shift()], [_make_request()])
        engine._find_best_shift_for_request = MagicMock(return_value=None)
        with patch.object(re_mod, "AssignmentService") as svc_cls:
            result = engine.auto_assign_requests_to_shift_executors()

        svc_cls.return_value.smart_assign_request.assert_not_called()
        assert result["failed_assignments"] == 1
        assert result["assignment_details"][0]["status"] == "failed"


# ---------------------------------------------------------------------------
# 2. sync_request_assignments_with_shifts — точечный ресинк
# ---------------------------------------------------------------------------

class TestSyncTargetedReassignment:
    def test_no_full_auto_assign_run_inside_loop(self):
        """2: по каждому mismatched — точечное переназначение, не полный прогон."""
        mismatched = [_make_assignment("260813-001"), _make_assignment("260813-002")]
        engine, _ = _engine_for_sync(mismatched)
        engine.auto_assign_requests_to_shift_executors = MagicMock()

        with patch.object(re_mod, "AssignmentService") as svc_cls:
            svc_cls.return_value.smart_assign_request.return_value = MagicMock()
            result = engine.sync_request_assignments_with_shifts()

        engine.auto_assign_requests_to_shift_executors.assert_not_called()
        numbers = [
            c.kwargs.get("request_number") or c.args[0]
            for c in svc_cls.return_value.smart_assign_request.call_args_list
        ]
        assert numbers == ["260813-001", "260813-002"]
        assert result["reassigned"] == 2

    def test_reassigned_counts_only_confirmed_success(self):
        """2: smart_assign_request вернул None → это failed, не reassigned."""
        mismatched = [_make_assignment("260813-001"), _make_assignment("260813-002")]
        engine, _ = _engine_for_sync(mismatched)

        with patch.object(re_mod, "AssignmentService") as svc_cls:
            svc_cls.return_value.smart_assign_request.return_value = None
            result = engine.sync_request_assignments_with_shifts()

        assert result["reassigned"] == 0, (
            f"reassigned={result['reassigned']} при нуле фактических переназначений"
        )
        assert result["failed_reassignments"] == 2

    def test_outer_commit_contract_preserved(self):
        """Регресс: контракт «sync коммитит сам в конце» сохранён."""
        engine, db = _engine_for_sync([_make_assignment()])
        with patch.object(re_mod, "AssignmentService") as svc_cls:
            svc_cls.return_value.smart_assign_request.return_value = MagicMock()
            engine.sync_request_assignments_with_shifts()
        assert db.commit.called

    def test_mismatched_assignment_is_cancelled(self):
        """Регресс: старое несоответствующее назначение отменяется."""
        assignment = _make_assignment()
        engine, _ = _engine_for_sync([assignment])
        with patch.object(re_mod, "AssignmentService") as svc_cls:
            svc_cls.return_value.smart_assign_request.return_value = MagicMock()
            engine.sync_request_assignments_with_shifts()
        assert assignment.status == "cancelled"


# ---------------------------------------------------------------------------
# 3. balancer._rebalance_shifts — без мутации итерируемого списка
# ---------------------------------------------------------------------------

class TestRebalanceNoListMutation:
    def test_source_does_not_mutate_underloaded_in_place(self):
        """3: `underloaded.pop(i)` / `underloaded[i] = ...` внутри итерации убраны.

        Поведенчески дефект ненаблюдаем (мутация шла прямо перед break), поэтому
        фикс фиксируется на уровне исходника: перераспределение обязано строить
        новый список, а не мутировать итерируемый.
        """
        import ast
        import textwrap

        from uk_management_bot.services.shift_assignment_service.balancer import (
            WorkloadBalancer,
        )
        src = textwrap.dedent(inspect.getsource(WorkloadBalancer._rebalance_shifts))
        tree = ast.parse(src)

        mutations = []
        for node in ast.walk(tree):
            # underloaded.pop(...)
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "pop"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "underloaded"):
                mutations.append(f"underloaded.pop @ line {node.lineno}")
            # underloaded[...] = ...
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (isinstance(target, ast.Subscript)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "underloaded"):
                        mutations.append(f"underloaded[...] = @ line {node.lineno}")

        assert not mutations, f"мутация итерируемого списка underloaded: {mutations}"

    def test_rebalance_behavior_regression(self):
        """Регресс: перенос смены overloaded → underloaded работает как раньше."""
        from uk_management_bot.services.shift_assignment_service.balancer import (
            WorkloadBalancer,
        )
        db = MagicMock()
        executor = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = executor
        balancer = WorkloadBalancer(db, scoring_engine=MagicMock())
        balancer._can_assign_shift = MagicMock(return_value=True)

        def shift_for(executor_id, shift_id):
            s = MagicMock()
            s.id = shift_id
            s.user_id = executor_id
            return s

        # executor 1 перегружен (4 смены), executor 2 недогружен (0 смен в списке)
        shifts = [shift_for(1, i) for i in range(1, 5)]
        distribution = {
            "executor_loads": {1: 4, 2: 0},
            "avg_load": 2.0,
        }
        result = balancer._rebalance_shifts(shifts, distribution)

        assert result["redistributions_performed"] >= 1
        moved = result["redistributions"][0]
        assert moved["from_executor"] == 1
        assert moved["to_executor"] == 2
        assert db.commit.called


# ---------------------------------------------------------------------------
# 4. scoring._calculate_availability_score — лог по каждому перекрытию
# ---------------------------------------------------------------------------

class TestAvailabilityOverlapLogging:
    def test_logs_each_actual_overlap(self, caplog):
        """4: по одному сообщению на каждое фактическое перекрытие, со СВОИМИ спеками."""
        from uk_management_bot.services.shift_assignment_service import scoring as sc_mod
        from uk_management_bot.services.shift_assignment_service.scoring import (
            ScoringEngine,
        )

        db = MagicMock()
        overlap_a = MagicMock()
        overlap_a.specialization_focus = ["electric"]
        overlap_b = MagicMock()
        overlap_b.specialization_focus = ["hvac"]
        db.query.return_value.filter.return_value.all.return_value = [
            overlap_a, overlap_b,
        ]

        engine = ScoringEngine(db, weights=MagicMock())
        shift = MagicMock()
        shift.id = 1
        shift.specialization_focus = ["plumbing"]
        executor = MagicMock()
        executor.id = 10

        with caplog.at_level(logging.DEBUG, logger=sc_mod.logger.name):
            score = engine._calculate_availability_score(shift, executor)

        assert score == 0.8
        allowed = [r.message for r in caplog.records if "Разрешено перекрытие" in r.message]
        assert len(allowed) == 2, (
            f"лог не по каждому перекрытию: {allowed}"
        )
        assert any("electric" in m for m in allowed), (
            f"перекрытие A не отражено своими спеками: {allowed}"
        )
        assert any("hvac" in m for m in allowed), (
            f"перекрытие B не отражено своими спеками: {allowed}"
        )
