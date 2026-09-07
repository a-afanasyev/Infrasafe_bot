"""Гейт: список допустимых значений `sort` в API == белый список в домене.

Значение колонки живёт в двух местах: `Literal` в схеме роутера (он отбивает
чужое значение на входе, 422) и словарь выражений в домене (он превращает
значение в `ORDER BY`). Списки заполняются руками, и разъезд молчаливый:
добавили колонку в домен, забыли в `Literal` — легальный клик по заголовку
даёт 422; добавили наоборот — значение проходит валидацию и молча не
сортирует. Оба конца проверяются здесь.
"""
from __future__ import annotations

import typing

import pytest

from uk_management_bot.api.elevators.schemas import ElevatorSortField
from uk_management_bot.api.residents.schemas import ResidentSortField
from uk_management_bot.api.shifts.schemas import EmployeeSortField
from uk_management_bot.api.shifts.service.employees import EMPLOYEE_SORT_IDS
from uk_management_bot.services.elevator_service.registry import REGISTRY_SORT_IDS
from uk_management_bot.services.residents.queries import RESIDENT_SORT_IDS

PAIRS = [
    ("лифты", ElevatorSortField, REGISTRY_SORT_IDS),
    ("жители", ResidentSortField, RESIDENT_SORT_IDS),
    ("сотрудники", EmployeeSortField, EMPLOYEE_SORT_IDS),
]


@pytest.mark.parametrize("section, literal, domain_ids", PAIRS, ids=[p[0] for p in PAIRS])
def test_api_literal_matches_domain_whitelist(section, literal, domain_ids):
    allowed_in_api = set(typing.get_args(literal))
    allowed_in_domain = set(domain_ids)
    assert allowed_in_api == allowed_in_domain, (
        f"{section}: список сортировок разъехался. "
        f"только в API: {sorted(allowed_in_api - allowed_in_domain)}; "
        f"только в домене: {sorted(allowed_in_domain - allowed_in_api)}"
    )
