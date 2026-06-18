"""ARCH-02 / PR-32: единое правило переброски исполнителя `apply_executor_reassign`.

Sync (`AssignmentService.reassign_executor`) и async
(`AsyncAssignmentService.reassign_executor`) делегируют сюда — бизнес-правило
живёт в одном месте (DoD «правила в одном месте, diff-доказательство»).
Тест фиксирует три ветки правила на лёгких объектах (правило мутирует только
атрибуты, БД не нужна).
"""
from types import SimpleNamespace

from uk_management_bot.services.assignment_service import apply_executor_reassign
from uk_management_bot.utils.constants import (
    ASSIGNMENT_TYPE_INDIVIDUAL,
    ASSIGNMENT_TYPE_GROUP,
)


def test_individual_active_updates_request_and_assignment():
    req = SimpleNamespace(executor_id=None)
    active = SimpleNamespace(assignment_type=ASSIGNMENT_TYPE_INDIVIDUAL, executor_id=1)
    apply_executor_reassign(req, active, 42)
    assert req.executor_id == 42
    assert active.executor_id == 42


def test_group_active_updates_request_only():
    req = SimpleNamespace(executor_id=None)
    active = SimpleNamespace(assignment_type=ASSIGNMENT_TYPE_GROUP, executor_id=None)
    apply_executor_reassign(req, active, 42)
    assert req.executor_id == 42
    # Групповое активное назначение не трогаем (executor_id остаётся пустым).
    assert active.executor_id is None


def test_no_active_assignment_updates_request_only():
    req = SimpleNamespace(executor_id=7)
    apply_executor_reassign(req, None, 42)
    assert req.executor_id == 42
