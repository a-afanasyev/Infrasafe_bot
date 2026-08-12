"""Авторизация per-action (PR0 Р2): SYSTEM_CAPABILITIES + предикаты-гарды.

Block-move из utils/request_workflow.py (AUD5-ARCH-3 волна 10), тела
байт-в-байт.
"""

from __future__ import annotations

from typing import Mapping

from uk_management_bot.utils.constants import (
    REQUEST_STATUS_NEW,
    ROLE_APPLICANT,
    ROLE_EXECUTOR,
    ROLE_MANAGER,
)

from .projections import normalize_status
from .types import Action, ActorContext, WorkflowSnapshot

# ---------------------------------------------------------------------------
# Авторизация per-action (PR0 Р2)
# ---------------------------------------------------------------------------

# SYSTEM-capabilities: какой системный процесс какие действия может.
SYSTEM_CAPABILITIES: Mapping[str, frozenset[Action]] = {
    "dispatcher": frozenset({Action.SYSTEM_DISPATCH_ASSIGN}),
    # auto_manager: авто-менеджер (планировщик ночных заявок) — повышение
    # group→individual своим действием + резидуальный случай «Новая» через
    # уже существующий dispatch-assign (используется отдельной задачей).
    "auto_manager": frozenset({Action.SYSTEM_AUTO_PROMOTE,
                               Action.SYSTEM_DISPATCH_ASSIGN}),
    # "reconcile": frozenset(),  # появится при необходимости
}


def _is_manager(actor: ActorContext) -> bool:
    return actor.kind == "user" and ROLE_MANAGER in actor.roles


def _is_assigned_executor(snap: WorkflowSnapshot, actor: ActorContext) -> bool:
    if actor.kind != "user" or ROLE_EXECUTOR not in actor.roles:
        return False
    assigned = snap.active_assignment_executor_id or snap.request.executor_id
    return assigned is not None and assigned == actor.user_id


def _executor_can_work(snap: WorkflowSnapshot, actor: ActorContext) -> bool:
    return _is_assigned_executor(snap, actor) and snap.actor_has_active_shift


def _executor_can_claim(snap: WorkflowSnapshot, actor: ActorContext) -> bool:
    """Исполнитель может взять заявку из группового пула.

    Условия: роль executor + on-shift-now + активное group-назначение без
    исполнителя (unclaimed) + его group_specialization входит в специализации
    актора. После взятия unclaimed=False → действие исчезает из allowed.
    """
    if actor.kind != "user" or ROLE_EXECUTOR not in actor.roles:
        return False
    if not snap.actor_has_active_shift:
        return False
    if not snap.active_assignment_unclaimed:
        return False
    group = snap.active_assignment_group
    return group is not None and group in actor.specializations


def _system_can_promote(snap: WorkflowSnapshot, actor: ActorContext) -> bool:
    """Авто-менеджер может повысить group→individual только пока назначение
    ещё unclaimed И заявка ещё без индивидуального исполнителя.

    Race-защита: если менеджер между read планировщика и его write уже
    заменил group-назначение на individual (или другой исполнитель успел
    claim), snapshot, загруженный ПОД FOR UPDATE в run_command, это отразит —
    authorize провалится, patch не применится. rowcount-guard в
    workflow_runner._apply_domain_op_* — вторая линия защиты той же гонки.
    """
    return snap.active_assignment_unclaimed and snap.request.executor_id is None


def _is_owner(snap: WorkflowSnapshot, actor: ActorContext) -> bool:
    return actor.kind == "user" and snap.request.user_id == actor.user_id


def _can_accept(snap: WorkflowSnapshot, actor: ActorContext) -> bool:
    """owner ИЛИ одобренный сосед — семантика HF-0 can_accept."""
    if actor.kind != "user":
        return False
    if _is_owner(snap, actor):
        return True
    apt = snap.request.apartment_id
    return apt is not None and apt in actor.approved_apartment_ids


def _can_cancel(snap: WorkflowSnapshot, actor: ActorContext) -> bool:
    if _is_manager(actor):
        return True
    # applicant-owner может отменить только свою НОВУЮ заявку
    return (_is_owner(snap, actor) and ROLE_APPLICANT in actor.roles
            and normalize_status(snap.request) == REQUEST_STATUS_NEW)
