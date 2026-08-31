"""BUG-148 — ретайр мёртвого авто-назначающего пути планировщика (решение
владельца 2026-08-19, вариант 2).

Путь был мёртв с рождения: `assignment_service.smart_assign_request` звал
`dispatcher.auto_assign_request` (SINGULAR) — метода с таким именем у
SmartDispatcher не было НИКОГДА, AttributeError гасился broad-except'ом, обе
планировочные джобы всегда отчитывались failed. Ретайр: джобы №8/№9
планировщика, прокси ShiftAssignmentService, RequestAssignmentEngine целиком,
smart_assign_request и оставшийся без потребителей SmartDispatcher целиком.

Пин РЕТАЙРА (дисциплина BUG-150/154/158): удалённые символы обязаны
отсутствовать, а живые соседи — остаться нетронутыми. Регистрация джоб
проверяется по исходнику планировщика: «удалил метод» и «снял джобу» —
разные вещи, висящая регистрация роняла бы планировщик на старте.
"""
from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest


class TestDeadModulesGone:
    def test_smart_dispatcher_module_retired(self):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("uk_management_bot.services.smart_dispatcher")

    def test_request_engine_module_retired(self):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(
                "uk_management_bot.services.shift_assignment_service.request_engine")


class TestDeadSymbolsGone:
    def test_assignment_service_has_no_smart_assign(self):
        from uk_management_bot.services.assignment_service import AssignmentService
        assert not hasattr(AssignmentService, "smart_assign_request")

    def test_shift_assignment_service_has_no_proxies(self):
        from uk_management_bot.services.shift_assignment_service import (
            ShiftAssignmentService,
        )
        assert not hasattr(ShiftAssignmentService, "auto_assign_requests_to_shift_executors")
        assert not hasattr(ShiftAssignmentService, "sync_request_assignments_with_shifts")

    def test_package_does_not_reexport_engine(self):
        import uk_management_bot.services.shift_assignment_service as pkg
        assert not hasattr(pkg, "RequestAssignmentEngine")


class TestSchedulerJobsUnregistered:
    def _source(self) -> str:
        import uk_management_bot.utils.shift_scheduler as mod
        return Path(inspect.getsourcefile(mod)).read_text(encoding="utf-8")

    def test_dead_jobs_not_registered(self):
        src = self._source()
        assert "auto_assign_requests" not in src
        assert "sync_assignments" not in src
        assert "_sync_request_assignments" not in src

    def test_live_neighbor_jobs_intact(self):
        """Живые соседи: авто-менеджер (реальное авто-назначение ночных
        заявок) и активация planned-смен ретайром не задеты."""
        src = self._source()
        assert "auto_manager_tick" in src
        assert "activate_scheduled" in src
        assert "auto_assign_empty" in src


class TestLiveAssignmentPathIntact:
    def test_assign_to_group_alive(self):
        """Живой менеджерский путь назначения группе (handlers/admin/shared)
        ретайром не тронут."""
        from uk_management_bot.services.assignment_service import AssignmentService
        assert hasattr(AssignmentService, "assign_to_group")
        assert hasattr(AssignmentService, "reassign_executor")
