"""Заявка без адреса из справочника не уходит в работу (решение владельца 2026-11-07).

Адрес заявки — двор, дом или квартира из справочника. Legacy-текст («4g 10
etaj») блокирует назначение исполнителя и адресацию группе; закрыть уже
начатую работу можно. Проверка — в `plan_transition`, через него идут бот,
дашборд, автоназначение и ИИ-менеджер.
"""
from dataclasses import replace

import pytest

from uk_management_bot.utils.constants import (
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_NEW,
)
from uk_management_bot.utils.request_workflow import Action, AddressNotBound

from .test_request_workflow import (
    DISPATCHER,
    EXECUTOR_ID,
    MANAGER,
    SYSTEM_PRINCIPAL,
    _plan,
    _snap,
)


def _unbound(snap):
    return replace(snap, request=replace(snap.request, address_bound=False))


def test_manager_assign_refused_without_address():
    with pytest.raises(AddressNotBound, match="справочника"):
        _plan(_unbound(_snap(REQUEST_STATUS_NEW)), Action.MANAGER_ASSIGN,
              MANAGER, {"executor_id": EXECUTOR_ID})


def test_dispatch_to_group_refused_without_address():
    # ASSIGN_GROUP статус не меняет, но выдаёт заявку дежурным — тоже «в работу».
    with pytest.raises(AddressNotBound):
        _plan(_unbound(_snap(REQUEST_STATUS_NEW)), Action.ASSIGN_GROUP,
              DISPATCHER, {"group": "plumber"}, principal=SYSTEM_PRINCIPAL)


def test_started_work_can_still_be_completed():
    # Заявка, ушедшая в работу до правила, не застревает.
    snap = _unbound(_snap(REQUEST_STATUS_IN_PROGRESS, executor=EXECUTOR_ID))
    result = _plan(snap, Action.MANAGER_COMPLETE, MANAGER)
    assert result.new_canon_status != REQUEST_STATUS_IN_PROGRESS


def test_bound_address_assigns_as_before():
    result = _plan(_snap(REQUEST_STATUS_NEW), Action.MANAGER_ASSIGN,
                   MANAGER, {"executor_id": EXECUTOR_ID})
    assert result.new_canon_status == REQUEST_STATUS_IN_PROGRESS
