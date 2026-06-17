"""PR1 (SSOT-кластер #1): golden-тесты чистой action-модели.

Фиксируют action-table из PR0 (docs/audit/2026-06-10-ssot-pr0-decisions.md):
переходы, per-action авторизацию (roles × ownership × assignment × shift ×
system-capabilities), payload-схемы, repeat_policy, normalize (dual-read
решений), проекции («Возвращена» наружу = «Исполнено») и согласованность
с HF-0-предикатом приёмки.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from uk_management_bot.utils.constants import (
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_CANCELLED,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_NEW,
)
from uk_management_bot.utils.request_workflow import (
    ACTION_TABLE,
    Action,
    ActionCommand,
    ActorContext,
    InvalidTransition,
    LegacyStatusIntent,
    NotAuthorized,
    Op,
    PayloadInvalid,
    PrincipalRef,
    RepeatConflict,
    RepeatRejected,
    RequestState,
    STATUS_RETURNED,
    WorkflowSnapshot,
    allowed_actions,
    check_repeat,
    is_terminal,
    normalize_status,
    plan_transition,
    project_infrasafe_status,
    project_public_status,
    resolve_command,
    validate_edits,
)

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)

OWNER_ID, NEIGHBOR_ID, STRANGER_ID, EXECUTOR_ID, MANAGER_ID = 1, 2, 3, 4, 5
APT = 10


def _state(status, *, confirmed=False, returned=False, executor=None):
    return RequestState(
        request_number="260610-001", user_id=OWNER_ID, status=status,
        manager_confirmed=confirmed, is_returned=returned,
        apartment_id=APT, executor_id=executor,
    )


def _snap(status, *, confirmed=False, returned=False, executor=None,
          assignment=None, shift=False, has_rating=False,
          assignment_type=None, assignment_group=None, unclaimed=False):
    return WorkflowSnapshot(
        request=_state(status, confirmed=confirmed, returned=returned,
                       executor=executor),
        has_rating=has_rating,
        active_assignment_executor_id=assignment,
        actor_has_active_shift=shift,
        active_assignment_type=assignment_type,
        active_assignment_group=assignment_group,
        active_assignment_unclaimed=unclaimed,
    )


def _user(uid, *roles, apartments=frozenset(), active=None,
          specializations=frozenset()):
    return ActorContext(
        kind="user", user_id=uid, system_actor=None,
        roles=frozenset(roles), active_role=active or (list(roles) or [None])[0],
        approved_apartment_ids=frozenset(apartments),
        specializations=frozenset(specializations),
    )


MANAGER = _user(MANAGER_ID, "manager")
OWNER = _user(OWNER_ID, "applicant")
NEIGHBOR = _user(NEIGHBOR_ID, "applicant", apartments={APT})
STRANGER = _user(STRANGER_ID, "applicant")
EXECUTOR = _user(EXECUTOR_ID, "executor")
DISPATCHER = ActorContext(kind="system", user_id=None, system_actor="dispatcher")
UNKNOWN_SYSTEM = ActorContext(kind="system", user_id=None, system_actor="reconcile")

USER_PRINCIPAL = PrincipalRef(kind="user", user_id=MANAGER_ID, source="telegram")
SYSTEM_PRINCIPAL = PrincipalRef(kind="system", user_id=None,
                                source="dispatcher", system_actor="dispatcher")


def _plan(snap, action, actor, payload=None, principal=USER_PRINCIPAL):
    return plan_transition(
        snap, ActionCommand("cmd-1", action, payload or {}), actor, principal, NOW)


def _patch_fields(result):
    return {f: (op, v) for f, op, v in result.patch}


# ===========================================================================
# normalize / проекции / терминальность
# ===========================================================================

class TestNormalize:
    @pytest.mark.parametrize("status,confirmed,returned,expected", [
        (REQUEST_STATUS_NEW, False, False, REQUEST_STATUS_NEW),
        (REQUEST_STATUS_EXECUTED, False, False, REQUEST_STATUS_EXECUTED),
        # Telegram-композит → канон Исполнено
        (REQUEST_STATUS_EXECUTED, True, False, REQUEST_STATUS_COMPLETED),
        # возврат (legacy-кодировка до cutover) → канон Возвращена
        (REQUEST_STATUS_COMPLETED, False, True, STATUS_RETURNED),
        (REQUEST_STATUS_COMPLETED, True, True, STATUS_RETURNED),
        (REQUEST_STATUS_COMPLETED, False, False, REQUEST_STATUS_COMPLETED),
        # канон-хранилище (после cutover): «Возвращена» → identity
        (STATUS_RETURNED, False, True, STATUS_RETURNED),
        (STATUS_RETURNED, False, False, STATUS_RETURNED),
        # странный legacy-промежуток (Выполнена+conf+returned) — НЕ сворачиваем
        (REQUEST_STATUS_EXECUTED, True, True, REQUEST_STATUS_EXECUTED),
        (REQUEST_STATUS_APPROVED, True, False, REQUEST_STATUS_APPROVED),
    ])
    def test_normalize(self, status, confirmed, returned, expected):
        assert normalize_status(
            _state(status, confirmed=confirmed, returned=returned)) == expected

    def test_projection_returned_is_completed_outward(self):
        st = _state(REQUEST_STATUS_COMPLETED, returned=True)  # канон Возвращена
        assert project_public_status(st) == REQUEST_STATUS_COMPLETED
        assert project_infrasafe_status(st) == REQUEST_STATUS_COMPLETED

    def test_projection_telegram_composite_is_completed(self):
        st = _state(REQUEST_STATUS_EXECUTED, confirmed=True)
        assert project_public_status(st) == REQUEST_STATUS_COMPLETED

    def test_terminal(self):
        assert is_terminal(REQUEST_STATUS_APPROVED)
        assert is_terminal(REQUEST_STATUS_CANCELLED)
        assert not is_terminal(STATUS_RETURNED)


# ===========================================================================
# PrincipalRef инварианты
# ===========================================================================

class TestPrincipal:
    def test_system_requires_system_actor(self):
        with pytest.raises(ValueError):
            PrincipalRef(kind="system", user_id=None, source="x")

    def test_user_requires_user_id(self):
        with pytest.raises(ValueError):
            PrincipalRef(kind="user", user_id=None, source="x")


# ===========================================================================
# allowed_actions — авторизационная матрица
# ===========================================================================

class TestAllowedActions:
    def test_manager_on_new(self):
        acts = allowed_actions(_snap(REQUEST_STATUS_NEW), MANAGER)
        assert acts == {Action.MANAGER_ASSIGN, Action.MANAGER_PURCHASE,
                        Action.CLARIFY_REQUEST, Action.CANCEL}

    def test_owner_applicant_on_new_can_only_cancel(self):
        assert allowed_actions(_snap(REQUEST_STATUS_NEW), OWNER) == {Action.CANCEL}

    def test_stranger_on_new_nothing(self):
        assert allowed_actions(_snap(REQUEST_STATUS_NEW), STRANGER) == frozenset()

    def test_system_dispatcher_on_new(self):
        assert allowed_actions(_snap(REQUEST_STATUS_NEW), DISPATCHER) == \
            {Action.SYSTEM_DISPATCH_ASSIGN}

    def test_system_capability_separation(self):
        """reconcile НЕ может действие диспетчера (capability-таблица)."""
        assert allowed_actions(_snap(REQUEST_STATUS_NEW), UNKNOWN_SYSTEM) == frozenset()

    def test_assigned_executor_with_shift(self):
        snap = _snap(REQUEST_STATUS_IN_PROGRESS, assignment=EXECUTOR_ID, shift=True)
        assert allowed_actions(snap, EXECUTOR) == \
            {Action.EXECUTOR_PURCHASE, Action.EXECUTOR_COMPLETE}

    def test_assigned_executor_without_shift_nothing(self):
        snap = _snap(REQUEST_STATUS_IN_PROGRESS, assignment=EXECUTOR_ID, shift=False)
        assert allowed_actions(snap, EXECUTOR) == frozenset()

    def test_unassigned_executor_nothing(self):
        snap = _snap(REQUEST_STATUS_IN_PROGRESS, assignment=999, shift=True)
        assert allowed_actions(snap, EXECUTOR) == frozenset()

    def test_owner_on_completed(self):
        acts = allowed_actions(_snap(REQUEST_STATUS_COMPLETED), OWNER)
        assert acts == {Action.APPLICANT_ACCEPT, Action.APPLICANT_RETURN}

    def test_neighbor_can_accept_not_return(self):
        acts = allowed_actions(_snap(REQUEST_STATUS_COMPLETED), NEIGHBOR)
        assert acts == {Action.APPLICANT_ACCEPT}

    def test_manager_on_returned(self):
        acts = allowed_actions(
            _snap(REQUEST_STATUS_COMPLETED, returned=True), MANAGER)
        assert acts == {Action.MANAGER_RETURN_TO_WORK,
                        Action.MANAGER_FORCE_ACCEPT, Action.CANCEL}

    def test_owner_on_returned_nothing(self):
        """Возвращена ждёт менеджера: житель повторно не принимает/не возвращает."""
        snap = _snap(REQUEST_STATUS_COMPLETED, returned=True)
        assert allowed_actions(snap, OWNER) == frozenset()

    def test_telegram_composite_treated_as_completed(self):
        """dual-read решений: Выполнена+confirmed == Исполнено для приёмки."""
        snap = _snap(REQUEST_STATUS_EXECUTED, confirmed=True)
        assert Action.APPLICANT_ACCEPT in allowed_actions(snap, OWNER)

    def test_terminal_nothing_for_anyone(self):
        for actor in (MANAGER, OWNER, EXECUTOR, DISPATCHER):
            assert allowed_actions(_snap(REQUEST_STATUS_APPROVED), actor) == frozenset()


# ===========================================================================
# plan_transition — happy paths и патчи
# ===========================================================================

class TestPlanTransition:
    def test_manager_confirm_patch(self):
        res = _plan(_snap(REQUEST_STATUS_EXECUTED), Action.MANAGER_CONFIRM,
                    MANAGER, {"confirmation_notes": "ok"})
        f = _patch_fields(res)
        assert res.new_canon_status == REQUEST_STATUS_COMPLETED
        assert f["status"] == (Op.SET, REQUEST_STATUS_COMPLETED)  # canonical-write
        assert f["manager_confirmed"] == (Op.SET, True)
        assert f["manager_confirmed_by"][0] == Op.SET_ACTOR
        assert f["manager_confirmed_at"][0] == Op.SET_NOW
        assert f["manager_confirmation_notes"] == (Op.SET, "ok")

    def test_applicant_accept_creates_rating(self):
        res = _plan(_snap(REQUEST_STATUS_COMPLETED), Action.APPLICANT_ACCEPT,
                    OWNER, {"rating": 5},
                    principal=PrincipalRef("user", OWNER_ID, "telegram"))
        assert res.new_canon_status == REQUEST_STATUS_APPROVED
        assert any(d.kind == "create_rating" and d.data["rating"] == 5
                   for d in res.domain_ops)
        assert _patch_fields(res)["completed_at"][0] == Op.SET_NOW

    def test_neighbor_accept_allowed(self):
        res = _plan(_snap(REQUEST_STATUS_COMPLETED), Action.APPLICANT_ACCEPT,
                    NEIGHBOR, {"rating": 4},
                    principal=PrincipalRef("user", NEIGHBOR_ID, "telegram"))
        assert res.new_canon_status == REQUEST_STATUS_APPROVED

    def test_applicant_return_storage_encoding(self):
        """После cutover (PR3+4) «Возвращена» пишется в хранилище НАПРЯМУЮ;
        is_returned=True остаётся как исторический флаг."""
        res = _plan(_snap(REQUEST_STATUS_COMPLETED), Action.APPLICANT_RETURN,
                    OWNER, {"return_reason": "не починили"},
                    principal=PrincipalRef("user", OWNER_ID, "telegram"))
        f = _patch_fields(res)
        assert res.new_canon_status == STATUS_RETURNED
        assert f["status"] == (Op.SET, STATUS_RETURNED)   # canonical-write
        assert f["is_returned"] == (Op.SET, True)
        assert f["return_reason"] == (Op.SET, "не починили")
        assert f["returned_by"][0] == Op.SET_ACTOR

    def test_canon_returned_snapshot_allows_manager_actions(self):
        """Канон-снимок (status=Возвращена напрямую) разрешает менеджеру
        re-open и force-accept — without dual-read encoding."""
        snap = _snap(STATUS_RETURNED)
        acts = allowed_actions(snap, MANAGER)
        assert Action.MANAGER_RETURN_TO_WORK in acts
        assert Action.MANAGER_FORCE_ACCEPT in acts
        res = _plan(snap, Action.MANAGER_RETURN_TO_WORK, MANAGER,
                    {"reason": "доделать"})
        assert res.new_canon_status == REQUEST_STATUS_IN_PROGRESS

    def test_return_emits_no_status_webhook(self):
        """Наружу Возвращена проецируется как Исполнено: public-статус не
        изменился → webhook request.status_changed НЕ эмитится (audit — да)."""
        res = _plan(_snap(REQUEST_STATUS_COMPLETED), Action.APPLICANT_RETURN,
                    OWNER, {"return_reason": "x"},
                    principal=PrincipalRef("user", OWNER_ID, "telegram"))
        kinds = [e.kind for e in res.events]
        assert "audit" in kinds
        assert "webhook" not in kinds

    def test_confirm_from_legacy_composite_emits_webhook(self):
        res = _plan(_snap(REQUEST_STATUS_EXECUTED), Action.MANAGER_CONFIRM, MANAGER)
        wh = [e for e in res.events if e.kind == "webhook"]
        assert len(wh) == 1
        assert wh[0].data["old_status"] == REQUEST_STATUS_EXECUTED
        assert wh[0].data["new_status"] == REQUEST_STATUS_COMPLETED

    def test_manager_return_to_work_from_returned(self):
        res = _plan(_snap(REQUEST_STATUS_COMPLETED, returned=True),
                    Action.MANAGER_RETURN_TO_WORK, MANAGER, {"reason": "доделать"})
        f = _patch_fields(res)
        assert res.new_canon_status == REQUEST_STATUS_IN_PROGRESS
        assert f["status"] == (Op.SET, REQUEST_STATUS_IN_PROGRESS)
        assert f["is_returned"] == (Op.SET, False)

    def test_force_accept_from_returned(self):
        res = _plan(_snap(REQUEST_STATUS_COMPLETED, returned=True),
                    Action.MANAGER_FORCE_ACCEPT, MANAGER)
        assert res.new_canon_status == REQUEST_STATUS_APPROVED

    def test_system_dispatch_assign(self):
        res = plan_transition(
            _snap(REQUEST_STATUS_NEW),
            ActionCommand("c", Action.SYSTEM_DISPATCH_ASSIGN, {"executor_id": 7}),
            DISPATCHER, SYSTEM_PRINCIPAL, NOW)
        f = _patch_fields(res)
        assert f["status"] == (Op.SET, REQUEST_STATUS_IN_PROGRESS)
        assert f["executor_id"] == (Op.SET, 7)
        assert any(d.kind == "create_assignment" for d in res.domain_ops)
        audit = [e for e in res.events if e.kind == "audit"][0]
        assert audit.data["principal_kind"] == "system"
        assert audit.data["principal_id"] == "dispatcher"

    def test_manager_assign_empty_payload_is_status_only(self):
        # PR2c: менеджер «берёт» Новую→В работе без выбора исполнителя.
        # Пустой payload ⇒ только status; ни create_assignment, ни assigned_*.
        res = _plan(_snap(REQUEST_STATUS_NEW), Action.MANAGER_ASSIGN, MANAGER)
        f = _patch_fields(res)
        assert f["status"] == (Op.SET, REQUEST_STATUS_IN_PROGRESS)
        assert "assigned_at" not in f and "assigned_by" not in f
        assert "executor_id" not in f and "assigned_group" not in f
        assert res.domain_ops == ()

    def test_manager_assign_with_executor_creates_assignment(self):
        # С executor_id ⇒ полное назначение (assigned_* + create_assignment).
        res = _plan(_snap(REQUEST_STATUS_NEW), Action.MANAGER_ASSIGN,
                    MANAGER, {"executor_id": EXECUTOR_ID})
        f = _patch_fields(res)
        assert f["executor_id"] == (Op.SET, EXECUTOR_ID)
        assert f["assigned_at"][0] == Op.SET_NOW
        assert f["assigned_by"][0] == Op.SET_ACTOR
        assert any(d.kind == "create_assignment" for d in res.domain_ops)

    def test_cancel_cancels_assignments(self):
        res = _plan(_snap(REQUEST_STATUS_IN_PROGRESS), Action.CANCEL,
                    MANAGER, {"reason": "дубль"})
        assert any(d.kind == "cancel_active_assignments" for d in res.domain_ops)

    def test_executor_complete_full_cycle_after_return(self):
        """repeatable: повторный EXECUTOR_COMPLETE легитимен после возврата
        (Возвращена →[manager]→ В работе →[executor]→ Выполнена)."""
        snap = _snap(REQUEST_STATUS_IN_PROGRESS, returned=False,
                     assignment=EXECUTOR_ID, shift=True)
        res = _plan(snap, Action.EXECUTOR_COMPLETE, EXECUTOR,
                    {"completion_report": "готово v2"},
                    principal=PrincipalRef("user", EXECUTOR_ID, "telegram"))
        assert res.new_canon_status == REQUEST_STATUS_EXECUTED


# ===========================================================================
# Авторизация: негативные
# ===========================================================================

class TestAuthorizationNegatives:
    def test_stranger_cannot_accept(self):
        with pytest.raises(NotAuthorized):
            _plan(_snap(REQUEST_STATUS_COMPLETED), Action.APPLICANT_ACCEPT,
                  STRANGER, {"rating": 5})

    def test_neighbor_cannot_return(self):
        with pytest.raises(NotAuthorized):
            _plan(_snap(REQUEST_STATUS_COMPLETED), Action.APPLICANT_RETURN,
                  NEIGHBOR, {"return_reason": "x"})

    def test_executor_without_shift_cannot_complete(self):
        snap = _snap(REQUEST_STATUS_IN_PROGRESS, assignment=EXECUTOR_ID, shift=False)
        with pytest.raises(NotAuthorized):
            _plan(snap, Action.EXECUTOR_COMPLETE, EXECUTOR)

    def test_system_cannot_do_user_action(self):
        with pytest.raises(NotAuthorized):
            plan_transition(
                _snap(REQUEST_STATUS_NEW),
                ActionCommand("c", Action.CANCEL, {"reason": "x"}),
                DISPATCHER, SYSTEM_PRINCIPAL, NOW)

    def test_applicant_cannot_cancel_in_progress(self):
        """Owner-applicant отменяет только из «Новая»."""
        with pytest.raises(NotAuthorized):
            _plan(_snap(REQUEST_STATUS_IN_PROGRESS), Action.CANCEL,
                  OWNER, {"reason": "передумал"})

    def test_wrong_state_is_invalid_transition(self):
        with pytest.raises(InvalidTransition):
            _plan(_snap(REQUEST_STATUS_NEW), Action.MANAGER_CONFIRM, MANAGER)


# ===========================================================================
# Payload-валидация
# ===========================================================================

class TestPayload:
    def test_missing_required(self):
        with pytest.raises(PayloadInvalid):
            _plan(_snap(REQUEST_STATUS_COMPLETED), Action.APPLICANT_ACCEPT,
                  OWNER, {})

    def test_wrong_type(self):
        with pytest.raises(PayloadInvalid):
            _plan(_snap(REQUEST_STATUS_COMPLETED), Action.APPLICANT_ACCEPT,
                  OWNER, {"rating": "five"})

    def test_unexpected_field(self):
        with pytest.raises(PayloadInvalid):
            _plan(_snap(REQUEST_STATUS_COMPLETED), Action.APPLICANT_ACCEPT,
                  OWNER, {"rating": 5, "manager_confirmed": True})


# ===========================================================================
# repeat_policy
# ===========================================================================

class TestRepeat:
    def test_confirm_repeat_is_noop(self):
        """MANAGER_CONFIRM на уже-Исполнено (любая кодировка) → no-op без событий."""
        snap = _snap(REQUEST_STATUS_EXECUTED, confirmed=True)  # канон Исполнено
        res = check_repeat(snap, ActionCommand("c", Action.MANAGER_CONFIRM, {}),
                           MANAGER)
        assert res is not None and res.no_op
        assert res.patch == () and res.events == ()

    def test_confirm_repeat_with_different_payload_conflicts(self):
        snap = _snap(REQUEST_STATUS_EXECUTED, confirmed=True)
        with pytest.raises(RepeatConflict):
            check_repeat(snap, ActionCommand(
                "c", Action.MANAGER_CONFIRM,
                {"confirmation_notes": "другие заметки"}), MANAGER)

    def test_accept_repeat_rejected(self):
        snap = _snap(REQUEST_STATUS_APPROVED)
        with pytest.raises(RepeatRejected):
            check_repeat(snap, ActionCommand(
                "c", Action.APPLICANT_ACCEPT, {"rating": 5}), OWNER)

    def test_not_a_repeat_returns_none(self):
        snap = _snap(REQUEST_STATUS_EXECUTED)  # canon = from, не to
        assert check_repeat(
            snap, ActionCommand("c", Action.MANAGER_CONFIRM, {}), MANAGER) is None


# ===========================================================================
# resolve_command — status-based вход
# ===========================================================================

class TestResolveCommand:
    def test_accept_target_owner_maps_to_applicant_accept(self):
        cmd = resolve_command(
            _snap(REQUEST_STATUS_COMPLETED), OWNER,
            LegacyStatusIntent("c", REQUEST_STATUS_APPROVED, {"rating": 5}))
        assert cmd.action == Action.APPLICANT_ACCEPT

    def test_accept_target_manager_maps_to_force_accept(self):
        cmd = resolve_command(
            _snap(REQUEST_STATUS_COMPLETED), MANAGER,
            LegacyStatusIntent("c", REQUEST_STATUS_APPROVED))
        assert cmd.action == Action.MANAGER_FORCE_ACCEPT

    def test_in_progress_target_from_new_is_assign(self):
        cmd = resolve_command(
            _snap(REQUEST_STATUS_NEW), MANAGER,
            LegacyStatusIntent("c", REQUEST_STATUS_IN_PROGRESS))
        assert cmd.action == Action.MANAGER_ASSIGN

    def test_in_progress_target_from_executed_is_return_to_work(self):
        cmd = resolve_command(
            _snap(REQUEST_STATUS_EXECUTED), MANAGER,
            LegacyStatusIntent("c", REQUEST_STATUS_IN_PROGRESS, {"reason": "r"}))
        assert cmd.action == Action.MANAGER_RETURN_TO_WORK

    def test_unmapped_target_raises(self):
        with pytest.raises(InvalidTransition):
            resolve_command(
                _snap(REQUEST_STATUS_NEW), OWNER,
                LegacyStatusIntent("c", REQUEST_STATUS_EXECUTED))


# ===========================================================================
# EXECUTOR_CLAIM — взятие group-заявки из пула (PR-1)
# ===========================================================================

PLUMBER = _user(EXECUTOR_ID, "executor", specializations={"plumber"})
PLUMBER_PRINCIPAL = PrincipalRef(kind="user", user_id=EXECUTOR_ID, source="telegram")


def _group_snap(*, group="plumber", unclaimed=True, shift=True, executor=None):
    """Заявка «В работе» с активным group-назначением (executor_id NULL)."""
    return _snap(
        REQUEST_STATUS_IN_PROGRESS, shift=shift, assignment=executor,
        assignment_type="group", assignment_group=group, unclaimed=unclaimed)


class TestExecutorClaim:
    def test_claim_allowed_on_shift_matching_spec_unclaimed(self):
        assert Action.EXECUTOR_CLAIM in allowed_actions(_group_snap(), PLUMBER)

    def test_claim_patch_converts_group_to_individual(self):
        res = _plan(_group_snap(), Action.EXECUTOR_CLAIM, PLUMBER,
                    principal=PLUMBER_PRINCIPAL)
        f = _patch_fields(res)
        assert f["status"] == (Op.SET, REQUEST_STATUS_IN_PROGRESS)
        assert f["executor_id"] == (Op.SET_ACTOR, None)
        assert f["assignment_type"] == (Op.SET, "individual")
        assert f["assigned_at"][0] == Op.SET_NOW
        assert f["assigned_group"] == (Op.CLEAR, None)
        assert any(d.kind == "claim_group_assignment" for d in res.domain_ops)

    def test_claim_denied_without_shift(self):
        assert Action.EXECUTOR_CLAIM not in allowed_actions(
            _group_snap(shift=False), PLUMBER)

    def test_claim_denied_wrong_spec(self):
        assert Action.EXECUTOR_CLAIM not in allowed_actions(
            _group_snap(group="electric"), PLUMBER)

    def test_claim_denied_individual_assignment(self):
        snap = _snap(REQUEST_STATUS_IN_PROGRESS, shift=True,
                     assignment_type="individual", unclaimed=False)
        assert Action.EXECUTOR_CLAIM not in allowed_actions(snap, PLUMBER)

    def test_claim_denied_already_claimed(self):
        snap = _group_snap(unclaimed=False, executor=99)
        assert Action.EXECUTOR_CLAIM not in allowed_actions(snap, PLUMBER)

    def test_claim_denied_wrong_status(self):
        snap = _snap(REQUEST_STATUS_NEW, shift=True, assignment_type="group",
                     assignment_group="plumber", unclaimed=True)
        assert Action.EXECUTOR_CLAIM not in allowed_actions(snap, PLUMBER)

    def test_claim_denied_for_manager(self):
        assert Action.EXECUTOR_CLAIM not in allowed_actions(_group_snap(), MANAGER)

    def test_claim_not_authorized_raises(self):
        with pytest.raises(NotAuthorized):
            _plan(_group_snap(shift=False), Action.EXECUTOR_CLAIM, PLUMBER,
                  principal=PLUMBER_PRINCIPAL)

    def test_claim_payload_rejects_extra_fields(self):
        with pytest.raises(PayloadInvalid):
            _plan(_group_snap(), Action.EXECUTOR_CLAIM, PLUMBER,
                  {"executor_id": 7}, principal=PLUMBER_PRINCIPAL)

    def test_legacy_in_progress_intent_does_not_resolve_to_claim(self):
        with pytest.raises(InvalidTransition):
            resolve_command(
                _group_snap(), PLUMBER,
                LegacyStatusIntent("c", REQUEST_STATUS_IN_PROGRESS))


# ===========================================================================
# MANAGER_ASSIGN — переназначение из «В работе» + симметрия legacy-полей (PR-1)
# ===========================================================================

class TestManagerReassign:
    def test_manager_assign_from_in_progress_allowed(self):
        snap = _snap(REQUEST_STATUS_IN_PROGRESS, assignment_type="group",
                     assignment_group="plumber", unclaimed=True)
        assert Action.MANAGER_ASSIGN in allowed_actions(snap, MANAGER)

    def test_assign_executor_sets_individual_and_clears_group(self):
        res = _plan(_snap(REQUEST_STATUS_NEW), Action.MANAGER_ASSIGN,
                    MANAGER, {"executor_id": EXECUTOR_ID})
        f = _patch_fields(res)
        assert f["executor_id"] == (Op.SET, EXECUTOR_ID)
        assert f["assignment_type"] == (Op.SET, "individual")
        assert f["assigned_group"] == (Op.CLEAR, None)

    def test_assign_group_clears_executor(self):
        snap = _snap(REQUEST_STATUS_IN_PROGRESS, executor=EXECUTOR_ID,
                     assignment_type="individual")
        res = _plan(snap, Action.MANAGER_ASSIGN, MANAGER, {"group": "plumber"})
        f = _patch_fields(res)
        assert f["assigned_group"] == (Op.SET, "plumber")
        assert f["assignment_type"] == (Op.SET, "group")
        assert f["executor_id"] == (Op.CLEAR, None)

    def test_reassign_from_in_progress_emits_create_assignment(self):
        # Инвариант «1 active» обеспечивает раннер (create_assignment сам
        # отменяет прошлое active-назначение перед вставкой) — см. runner-тест.
        snap = _snap(REQUEST_STATUS_IN_PROGRESS, assignment_type="group",
                     assignment_group="plumber", unclaimed=True)
        res = _plan(snap, Action.MANAGER_ASSIGN, MANAGER,
                    {"executor_id": EXECUTOR_ID})
        assert [d.kind for d in res.domain_ops] == ["create_assignment"]

    def test_assign_from_new_emits_create_assignment(self):
        res = _plan(_snap(REQUEST_STATUS_NEW), Action.MANAGER_ASSIGN,
                    MANAGER, {"group": "plumber"})
        assert [d.kind for d in res.domain_ops] == ["create_assignment"]

    def test_assign_both_group_and_executor_invalid(self):
        with pytest.raises(PayloadInvalid):
            _plan(_snap(REQUEST_STATUS_NEW), Action.MANAGER_ASSIGN, MANAGER,
                  {"group": "plumber", "executor_id": EXECUTOR_ID})

    def test_dispatch_both_group_and_executor_invalid(self):
        with pytest.raises(PayloadInvalid):
            plan_transition(
                _snap(REQUEST_STATUS_NEW),
                ActionCommand("c", Action.SYSTEM_DISPATCH_ASSIGN,
                              {"group": "plumber", "executor_id": 7}),
                DISPATCHER, SYSTEM_PRINCIPAL, NOW)

    def test_assign_empty_payload_still_status_only(self):
        res = _plan(_snap(REQUEST_STATUS_NEW), Action.MANAGER_ASSIGN, MANAGER)
        f = _patch_fields(res)
        assert f["status"] == (Op.SET, REQUEST_STATUS_IN_PROGRESS)
        assert res.domain_ops == ()


# ===========================================================================
# validate_edits
# ===========================================================================

class TestValidateEdits:
    def test_terminal_frozen(self):
        from uk_management_bot.utils.request_workflow import EditForbidden
        with pytest.raises(EditForbidden):
            validate_edits(_state(REQUEST_STATUS_APPROVED), {"urgency": "high"})

    def test_active_editable(self):
        validate_edits(_state(REQUEST_STATUS_IN_PROGRESS), {"urgency": "high"})

    def test_composite_completed_not_terminal(self):
        validate_edits(_state(REQUEST_STATUS_EXECUTED, confirmed=True),
                       {"urgency": "high"})

    def test_workflow_field_not_editable(self):
        from uk_management_bot.utils.request_workflow import EditForbidden
        with pytest.raises(EditForbidden):
            validate_edits(_state(REQUEST_STATUS_NEW), {"manager_confirmed": True})


# ===========================================================================
# Согласованность с HF-0
# ===========================================================================

class TestHF0Consistency:
    @pytest.mark.parametrize("status,confirmed,returned", [
        (REQUEST_STATUS_COMPLETED, False, False),
        (REQUEST_STATUS_COMPLETED, False, True),
        (REQUEST_STATUS_EXECUTED, True, False),
        (REQUEST_STATUS_EXECUTED, False, False),
        (REQUEST_STATUS_IN_PROGRESS, False, False),
        (REQUEST_STATUS_APPROVED, False, False),
    ])
    def test_awaiting_applicant_equals_canon_completed(self, status, confirmed,
                                                       returned):
        """HF-0 is_awaiting_applicant ≡ (канон-статус == Исполнено)."""
        from uk_management_bot.utils.workflow_predicates import is_awaiting_applicant

        st = _state(status, confirmed=confirmed, returned=returned)
        obj = SimpleNamespace(status=status, manager_confirmed=confirmed,
                              is_returned=returned)
        assert is_awaiting_applicant(obj) == \
            (normalize_status(st) == REQUEST_STATUS_COMPLETED)


# ===========================================================================
# Инварианты action-table
# ===========================================================================

class TestActionTableInvariants:
    def test_every_action_has_schema_and_spec(self):
        assert set(ACTION_TABLE) == set(Action)
        from uk_management_bot.utils.request_workflow import PAYLOAD_SCHEMAS
        assert set(PAYLOAD_SCHEMAS) == set(Action)

    def test_no_transitions_out_of_terminal(self):
        for action, spec in ACTION_TABLE.items():
            assert not (spec.from_statuses & {REQUEST_STATUS_APPROVED,
                                              REQUEST_STATUS_CANCELLED}), action

    def test_returned_handled_only_by_manager_actions(self):
        handlers = {a for a, s in ACTION_TABLE.items()
                    if STATUS_RETURNED in s.from_statuses}
        assert handlers == {Action.MANAGER_RETURN_TO_WORK,
                            Action.MANAGER_FORCE_ACCEPT, Action.CANCEL}
