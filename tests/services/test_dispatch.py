"""FEAT-группы (PR-3): авто-dispatch новой заявки на группу-специализацию.

Хелпер `services/dispatch` — тонкая best-effort обёртка над каноническим
run_command: category→specialization, system-principal «dispatcher»,
payload {group}. Здесь проверяем маппинг, форму команды/принципала и
best-effort (ошибка dispatch не поднимается наружу). Полный путь
SYSTEM_DISPATCH_ASSIGN {group} → group-назначение покрыт в test_workflow_runner.
"""

from __future__ import annotations

import uk_management_bot.services.workflow_runner as wr
from uk_management_bot.services.dispatch import (
    _specialization_for,
    auto_dispatch_new_request_sync,
)
from uk_management_bot.utils.request_workflow import Action


def test_specialization_lookup():
    assert _specialization_for("Сантехника") == "plumber"
    assert _specialization_for("plumbing") == "plumber"
    assert _specialization_for("unknown-xyz") is None
    assert _specialization_for(None) is None
    assert _specialization_for("") is None


def test_unknown_category_does_not_dispatch(monkeypatch):
    called = []
    monkeypatch.setattr(wr, "run_command_sync",
                        lambda *a, **k: called.append(a))
    auto_dispatch_new_request_sync("260610-001", "unknown-xyz")
    assert called == []


def test_known_category_dispatches_group_command(monkeypatch):
    captured = {}

    def fake(_sf, num, principal, command, *a, **k):
        captured["num"] = num
        captured["action"] = command.action
        captured["payload"] = dict(command.payload)
        captured["principal"] = principal
        return object()

    monkeypatch.setattr(wr, "run_command_sync", fake)
    auto_dispatch_new_request_sync("260610-001", "Сантехника")
    assert captured["num"] == "260610-001"
    assert captured["action"] == Action.SYSTEM_DISPATCH_ASSIGN
    assert captured["payload"] == {"group": "plumber"}
    assert captured["principal"].kind == "system"
    assert captured["principal"].system_actor == "dispatcher"


def test_best_effort_swallows_dispatch_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("seeded system user missing")

    monkeypatch.setattr(wr, "run_command_sync", boom)
    # не должно поднять исключение (заявка уже создана)
    auto_dispatch_new_request_sync("260610-001", "Сантехника")
