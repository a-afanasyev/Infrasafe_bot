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

