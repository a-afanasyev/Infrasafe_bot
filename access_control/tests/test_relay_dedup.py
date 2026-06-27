"""Unit-тесты relay adapter и edge-дедупа по command_id (§9.2, §14.2 п.11).

MockRelay моделирует физическое реле: считает число открытий по command_id и
дедуплицирует повторный open того же command_id (реле срабатывает ≤1 раза).
Без БД — чистая логика адаптера.
"""
from __future__ import annotations

import pytest

from access_control.integrations.relay import (
    HTTPRelay,
    MockRelay,
    RelayCommand,
    RelayResult,
)


def test_mock_relay_opens_once() -> None:
    relay = MockRelay()
    res = relay.open(RelayCommand(command_id="cmd-1", barrier_id=7))
    assert isinstance(res, RelayResult)
    assert res.opened is True
    assert res.deduplicated is False
    assert relay.open_count("cmd-1") == 1


def test_mock_relay_dedups_same_command_id() -> None:
    """Повторный open того же command_id НЕ открывает реле второй раз (крит. 5)."""
    relay = MockRelay()
    first = relay.open(RelayCommand(command_id="cmd-2", barrier_id=7))
    second = relay.open(RelayCommand(command_id="cmd-2", barrier_id=7))
    third = relay.open(RelayCommand(command_id="cmd-2", barrier_id=7))

    # Физическое открытие ровно одно, несмотря на 3 вызова.
    assert relay.open_count("cmd-2") == 1
    assert first.deduplicated is False
    assert second.deduplicated is True
    assert third.deduplicated is True
    # Сохранённый результат возвращается повторно.
    assert second.command_id == first.command_id
    assert second.opened == first.opened


def test_mock_relay_separate_command_ids_open_independently() -> None:
    relay = MockRelay()
    relay.open(RelayCommand(command_id="a", barrier_id=1))
    relay.open(RelayCommand(command_id="b", barrier_id=1))
    assert relay.open_count("a") == 1
    assert relay.open_count("b") == 1


def test_http_relay_is_thin_skeleton_no_call_without_client() -> None:
    """HTTPRelay — скелет: без сконфигурированного клиента не делает реальный вызов."""
    relay = HTTPRelay(base_url="http://edge.local")
    with pytest.raises(RuntimeError):
        relay.open(RelayCommand(command_id="x", barrier_id=1))
