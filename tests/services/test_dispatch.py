"""FEAT-группы (PR-3): авто-dispatch новой заявки на группу-специализацию.

Хелпер `services/dispatch` — тонкая best-effort обёртка над каноническим
run_command: category→specialization, system-principal «dispatcher»,
payload {group}. Здесь проверяем маппинг, форму команды/принципала и
best-effort (ошибка dispatch не поднимается наружу). Полный путь
SYSTEM_DISPATCH_ASSIGN {group} → group-назначение покрыт в test_workflow_runner.
"""

from __future__ import annotations

import pytest

import uk_management_bot.services.workflow_runner as wr
from uk_management_bot.services.dispatch import (
    _specialization_for,
    auto_dispatch_new_request_sync,
)
from uk_management_bot.utils.request_workflow import Action


def test_specialization_lookup():
    assert _specialization_for("Сантехника") == "plumber"
    assert _specialization_for("plumbing") == "plumber"
    # legacy-лейбл, которого не было в карте, но есть в каноне
    assert _specialization_for("Интернет") == "electrician"
    # Неизвестная категория → разнорабочий (как «Другое»): через хелпер, а не
    # прямой `.get()` — раньше такая заявка молча оставалась «Новая».
    assert _specialization_for("unknown-xyz") == "repair"
    assert _specialization_for(None) is None
    assert _specialization_for("") is None


def test_empty_category_does_not_dispatch(monkeypatch):
    called = []
    monkeypatch.setattr(wr, "run_command_sync",
                        lambda *a, **k: called.append(a))
    auto_dispatch_new_request_sync("260610-001", "")
    auto_dispatch_new_request_sync("260610-001", None)
    assert called == []


def test_unknown_category_dispatches_to_repair_group(monkeypatch):
    monkeypatch.setattr(
        "uk_management_bot.services.dispatch._auto_assign_enabled_sync",
        lambda *a, **k: True,
    )
    captured = {}

    def fake(_sf, num, principal, command, *a, **k):
        captured["payload"] = dict(command.payload)
        captured["action"] = command.action
        return object()

    monkeypatch.setattr(wr, "run_command_sync", fake)
    monkeypatch.setattr(
        "uk_management_bot.services.dispatch.pick_duty_executor_id",
        lambda *a, **k: None,
    )
    auto_dispatch_new_request_sync("260610-001", "unknown-xyz")
    assert captured["action"] == Action.ASSIGN_GROUP
    assert captured["payload"] == {"group": "repair"}


def test_known_category_without_duty_dispatches_group_command(monkeypatch):
    # Автоназначение теперь за выключателем (`auto_manager_config.enabled`), а
    # дефолт — выключено: без явного включения dispatch корректно молчит. Здесь
    # проверяется форма команды, поэтому флаг поднимаем явно.
    monkeypatch.setattr(
        "uk_management_bot.services.dispatch._auto_assign_enabled_sync",
        lambda *a, **k: True,
    )
    captured = {}

    def fake(_sf, num, principal, command, *a, **k):
        captured["num"] = num
        captured["action"] = command.action
        captured["payload"] = dict(command.payload)
        captured["principal"] = principal
        return object()

    monkeypatch.setattr(wr, "run_command_sync", fake)
    # Дежурного нет — инвариант «В работе ⟺ есть исполнитель»: заявка остаётся
    # «Новая», проставляется только группа (ASSIGN_GROUP статус не двигает).
    monkeypatch.setattr(
        "uk_management_bot.services.dispatch.pick_duty_executor_id",
        lambda *a, **k: None,
    )
    auto_dispatch_new_request_sync("260610-001", "Сантехника")
    assert captured["num"] == "260610-001"
    assert captured["action"] == Action.ASSIGN_GROUP
    assert captured["payload"] == {"group": "plumber"}
    assert captured["principal"].kind == "system"
    assert captured["principal"].system_actor == "dispatcher"


def test_best_effort_swallows_dispatch_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("seeded system user missing")

    monkeypatch.setattr(
        "uk_management_bot.services.dispatch._auto_assign_enabled_sync",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(wr, "run_command_sync", boom)
    # не должно поднять исключение (заявка уже создана)
    auto_dispatch_new_request_sync("260610-001", "Сантехника")


def test_duty_executor_found_assigns_person(monkeypatch):
    """Есть дежурный → SYSTEM_DISPATCH_ASSIGN на него, «Новая»→«В работе».

    Инвариант «В работе ⟺ есть исполнитель» (решение владельца 2026-08-17):
    раньше путь создания безусловно ставил ГРУППОВОЕ назначение и уводил заявку
    в «В работе» без человека — незабранная висела ничьей.
    """
    monkeypatch.setattr(
        "uk_management_bot.services.dispatch._auto_assign_enabled_sync",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "uk_management_bot.services.dispatch.pick_duty_executor_id",
        lambda *a, **k: 77,
    )
    captured = {}

    def fake(_sf, num, principal, command, *a, **k):
        captured["action"] = command.action
        captured["payload"] = dict(command.payload)
        return object()

    monkeypatch.setattr(wr, "run_command_sync", fake)
    auto_dispatch_new_request_sync("260610-002", "Сантехника")
    assert captured["action"] == Action.SYSTEM_DISPATCH_ASSIGN
    assert captured["payload"] == {"executor_id": 77}


# ── «Инженерный разбор» → инженер (роль engineer) ───────────────────────


def _engineering_harness(monkeypatch, engineer_id):
    from types import SimpleNamespace

    import uk_management_bot.services.auto_manager.rule_engine as re_mod
    import uk_management_bot.services.dispatch as dispatch_mod

    monkeypatch.setattr(re_mod, "select_engineer",
                        lambda *a, **k: SimpleNamespace(id=engineer_id) if engineer_id else None)
    monkeypatch.setattr(re_mod, "select_executor",
                        lambda *a, **k: pytest.fail("рутинный подбор для engineering"))
    # Общий выключатель автоназначения выключен — эскалацию он не держит.
    monkeypatch.setattr(dispatch_mod, "_auto_assign_enabled_sync", lambda *a, **k: False)
    monkeypatch.setattr(dispatch_mod, "_notify_assigned_sync", lambda *a, **k: None)
    calls = []

    def fake(_sf, num, principal, command, *a, **k):
        calls.append((principal.system_actor, command.action, dict(command.payload)))
        return object()

    monkeypatch.setattr(wr, "run_command_sync", fake)
    return calls


class _NoDb:
    def close(self):
        pass


def test_engineering_goes_to_engineer_even_when_auto_assign_off(monkeypatch):
    calls = _engineering_harness(monkeypatch, 42)
    result = auto_dispatch_new_request_sync("261027-001", "Инженерный разбор",
                                            session_factory=_NoDb)
    assert result.kind == "assigned" and result.executor_id == 42
    assert calls == [("dispatcher", Action.SYSTEM_DISPATCH_ASSIGN, {"executor_id": 42})]


def test_engineering_without_engineer_stays_new_without_group(monkeypatch):
    """Без инженера — «Новая» БЕЗ группы repair (разнорабочий уже не помог)."""
    calls = _engineering_harness(monkeypatch, None)
    result = auto_dispatch_new_request_sync("261027-001", "engineering", session_factory=_NoDb)
    assert result.kind == "no_engineer"
    assert calls == []



# ── ИИ-менеджер (mode="ai"): триаж ДО подбора исполнителя ─────────────────

AI_CFG = {"min_confidence": 0.7, "clarify_enabled": True, "dedup_enabled": True}


def _ai_harness(monkeypatch, *, ai_cfg, triage_outcome=None, triage_exc=None, executor_id=77):
    """enabled=True; AI-блок — через `_ai_config_sync`; apply — заглушка."""
    import uk_management_bot.services.ai_manager.apply as apply_mod
    import uk_management_bot.services.dispatch as dispatch_mod
    from uk_management_bot.services.ai_manager.apply import TriageOutcome

    monkeypatch.setattr(dispatch_mod, "_auto_assign_enabled_sync", lambda *a, **k: True)
    monkeypatch.setattr(dispatch_mod, "_ai_config_sync", lambda *a, **k: ai_cfg)
    monkeypatch.setattr(dispatch_mod, "_notify_assigned_sync", lambda *a, **k: None)
    picks = []

    def pick(category, db=None, *a, **k):
        picks.append(category)
        return executor_id

    monkeypatch.setattr(dispatch_mod, "pick_assignee_id", pick)
    triage_calls = []

    def fake_apply(request_number, cfg, session_factory=None):
        triage_calls.append((request_number, cfg))
        if triage_exc is not None:
            raise triage_exc
        return triage_outcome or TriageOutcome()

    monkeypatch.setattr(apply_mod, "apply_triage_sync", fake_apply)
    commands = []

    def fake_run(_sf, num, principal, command, *a, **k):
        commands.append((principal.system_actor, command.action, dict(command.payload)))
        return object()

    monkeypatch.setattr(wr, "run_command_sync", fake_run)
    return picks, triage_calls, commands


def test_rule_mode_never_touches_ai_package(monkeypatch):
    """Golden: без AI-блока (флаг/режим выключены) dispatch идёт прежним путём."""
    picks, triage_calls, commands = _ai_harness(
        monkeypatch, ai_cfg=None, triage_exc=AssertionError("ИИ вызван в rule-режиме"))
    result = auto_dispatch_new_request_sync("261028-001", "Сантехника", session_factory=_NoDb)
    assert result.kind == "assigned" and result.executor_id == 77
    assert triage_calls == []
    assert picks == ["Сантехника"]
    assert commands == [("dispatcher", Action.SYSTEM_DISPATCH_ASSIGN, {"executor_id": 77})]


def test_ai_mode_runs_triage_before_pick_and_falls_through(monkeypatch):
    picks, triage_calls, commands = _ai_harness(monkeypatch, ai_cfg=AI_CFG)
    result = auto_dispatch_new_request_sync("261028-001", "Сантехника", session_factory=_NoDb)
    assert triage_calls == [("261028-001", AI_CFG)]
    assert result.kind == "assigned" and result.executor_id == 77
    assert picks == ["Сантехника"]
    assert commands == [("dispatcher", Action.SYSTEM_DISPATCH_ASSIGN, {"executor_id": 77})]


def test_ai_mode_clarified_stops_dispatch(monkeypatch):
    from uk_management_bot.services.ai_manager.apply import TriageOutcome

    picks, _, commands = _ai_harness(monkeypatch, ai_cfg=AI_CFG,
                                     triage_outcome=TriageOutcome(clarified=True))
    result = auto_dispatch_new_request_sync("261028-001", "Сантехника", session_factory=_NoDb)
    assert result.kind == "clarified" and result.specialization == "plumber"
    assert picks == [] and commands == []


def test_ai_mode_category_change_repicks_by_new_category(monkeypatch):
    from uk_management_bot.services.ai_manager.apply import TriageOutcome

    picks, _, commands = _ai_harness(monkeypatch, ai_cfg=AI_CFG,
                                     triage_outcome=TriageOutcome(category="electricity"))
    result = auto_dispatch_new_request_sync("261028-001", "Сантехника", session_factory=_NoDb)
    assert picks == ["electricity"]
    assert result.kind == "assigned" and result.specialization == "electrician"
    assert commands == [("dispatcher", Action.SYSTEM_DISPATCH_ASSIGN, {"executor_id": 77})]


def test_ai_mode_triage_exception_degrades_to_rule_path(monkeypatch):
    picks, _, commands = _ai_harness(monkeypatch, ai_cfg=AI_CFG, triage_exc=RuntimeError("boom"))
    result = auto_dispatch_new_request_sync("261028-001", "Сантехника", session_factory=_NoDb)
    assert result.kind == "assigned"
    assert picks == ["Сантехника"] and len(commands) == 1


def test_ai_mode_skipped_for_engineering(monkeypatch):
    """«Инженерный разбор» — инженеру всегда, триаж не вызывается."""
    calls = _engineering_harness(monkeypatch, 42)
    import uk_management_bot.services.dispatch as dispatch_mod
    monkeypatch.setattr(dispatch_mod, "_ai_config_sync",
                        lambda *a, **k: pytest.fail("AI-конфиг читается для engineering"))
    result = auto_dispatch_new_request_sync("261027-001", "engineering", session_factory=_NoDb)
    assert result.kind == "assigned" and calls


def test_ai_config_sync_requires_flag_and_mode(monkeypatch, el_db):
    from uk_management_bot.config.settings import settings
    from uk_management_bot.services.auto_manager.config import save_config_sync
    from uk_management_bot.services.dispatch import _ai_config_sync

    save_config_sync(el_db, {"enabled": True, "mode": "ai", "ai": {"min_confidence": 0.8}})
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", False)
    assert _ai_config_sync(el_db) is None
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", True)
    assert _ai_config_sync(el_db)["min_confidence"] == 0.8
    save_config_sync(el_db, {"enabled": True, "mode": "rule"})
    assert _ai_config_sync(el_db) is None


def test_ai_config_sync_is_best_effort(monkeypatch):
    from uk_management_bot.config.settings import settings
    from uk_management_bot.services.dispatch import _ai_config_sync

    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", True)

    class Boom:
        def query(self, *a, **k):
            raise RuntimeError("db down")

    assert _ai_config_sync(Boom()) is None


@pytest.mark.asyncio
async def test_ai_mode_async_clarified_stops_dispatch(monkeypatch):
    import uk_management_bot.services.ai_manager.apply as apply_mod
    import uk_management_bot.services.dispatch as dispatch_mod
    from uk_management_bot.services.ai_manager.apply import TriageOutcome
    from uk_management_bot.services.dispatch import auto_dispatch_new_request_async

    async def enabled(*a, **k):
        return True

    monkeypatch.setattr(dispatch_mod, "_auto_assign_enabled_async", enabled)
    monkeypatch.setattr(dispatch_mod, "_ai_config_sync", lambda *a, **k: AI_CFG)
    monkeypatch.setattr(apply_mod, "apply_triage_sync",
                        lambda n, cfg, session_factory=None: TriageOutcome(clarified=True))
    published = []

    async def publish(number):
        published.append(number)

    monkeypatch.setattr(dispatch_mod, "_publish_updated", publish)
    monkeypatch.setattr(dispatch_mod, "pick_assignee_id",
                        lambda *a, **k: pytest.fail("подбор после уточнения"))

    async def no_run(*a, **k):
        pytest.fail("команда dispatch после уточнения")

    monkeypatch.setattr(wr, "run_command_async", no_run)
    result = await auto_dispatch_new_request_async("261028-001", "Сантехника", session_factory=_NoDb)
    assert result.kind == "clarified"
    assert published == ["261028-001"]


@pytest.mark.asyncio
async def test_ai_mode_async_category_change_repicks(monkeypatch):
    import uk_management_bot.services.ai_manager.apply as apply_mod
    import uk_management_bot.services.dispatch as dispatch_mod
    from uk_management_bot.services.ai_manager.apply import TriageOutcome
    from uk_management_bot.services.dispatch import auto_dispatch_new_request_async

    async def enabled(*a, **k):
        return True

    monkeypatch.setattr(dispatch_mod, "_auto_assign_enabled_async", enabled)
    monkeypatch.setattr(dispatch_mod, "_ai_config_sync", lambda *a, **k: AI_CFG)
    monkeypatch.setattr(apply_mod, "apply_triage_sync",
                        lambda n, cfg, session_factory=None: TriageOutcome(category="electricity"))
    picks = []
    monkeypatch.setattr(dispatch_mod, "pick_assignee_id",
                        lambda category, db=None, *a, **k: picks.append(category) or 5)
    commands = []

    async def fake_run(_sf, num, principal, command, *a, **k):
        commands.append((command.action, dict(command.payload)))
        return type("O", (), {"post_commit_intents": [], "old_state": None})()

    monkeypatch.setattr(wr, "run_command_async", fake_run)

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(dispatch_mod, "_publish_status_changed", noop)
    from uk_management_bot.services import workflow_notifications
    monkeypatch.setattr(workflow_notifications, "dispatch_notify_intents_detached", noop)
    result = await auto_dispatch_new_request_async("261028-001", "Сантехника", session_factory=_NoDb)
    assert picks == ["electricity"]
    assert result.kind == "assigned" and result.specialization == "electrician"
    assert commands == [(Action.SYSTEM_DISPATCH_ASSIGN, {"executor_id": 5})]
