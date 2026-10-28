"""Блок ``sla`` конфига автоменеджера (SLA-лестница ИИ-менеджера, фаза 2).

Часы — int ≥ 0 (0 = выключено), вложенный merge поверх дефолтов на двух
уровнях (``in_progress_max`` по срочности, ``ladder`` по ступеням).
"""
import pytest

from uk_management_bot.services.auto_manager.config import DEFAULT_CONFIG, validate_config

DEFAULT_SLA = {
    "in_progress_max": {"low": 72, "medium": 48, "high": 12, "critical": 2},
    "clarification_max": 48,
    "executed_unconfirmed_max": 24,
    "completed_unaccepted_days": 3,
    "critical_unassigned_minutes": 30,
    "ladder": {"remind_executor": 0, "staff_group": 2, "manager": 4, "reassign": 8},
    "ladder_enabled": {"remind_executor": True, "staff_group": True, "manager": True, "reassign": True},
    "public_status": {"enabled": True, "min_urgency": "critical"},
}


def test_sla_defaults():
    assert DEFAULT_CONFIG["sla"] == DEFAULT_SLA
    assert validate_config({})["sla"] == DEFAULT_SLA


def test_sla_partial_nested_merge():
    cfg = validate_config({"sla": {"in_progress_max": {"critical": 1}, "ladder": {"reassign": 24}}})
    assert cfg["sla"]["in_progress_max"] == {"low": 72, "medium": 48, "high": 12, "critical": 1}
    assert cfg["sla"]["ladder"] == {"remind_executor": 0, "staff_group": 2, "manager": 4, "reassign": 24}
    assert cfg["sla"]["clarification_max"] == 48


def test_sla_zero_means_disabled_and_is_valid():
    cfg = validate_config({"sla": {"completed_unaccepted_days": 0, "clarification_max": 0}})
    assert cfg["sla"]["completed_unaccepted_days"] == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"clarification_max": -1},
        {"clarification_max": 1.5},
        {"clarification_max": True},
        {"clarification_max": "48"},
        {"in_progress_max": {"urgent": 1}},
        {"in_progress_max": {"low": -5}},
        {"in_progress_max": 5},
        {"ladder": {"teleport": 1}},
        {"ladder": {"manager": -1}},
        {"unknown": 1},
        "nope",
    ],
)
def test_sla_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        validate_config({"sla": bad})


def test_sla_validate_does_not_mutate_defaults():
    validate_config({"sla": {"in_progress_max": {"low": 1}, "ladder": {"manager": 99}}})
    assert DEFAULT_CONFIG["sla"]["in_progress_max"]["low"] == 72
    assert DEFAULT_CONFIG["sla"]["ladder"]["manager"] == 4


def test_sla_new_blocks_defaults_and_merge():
    sla = validate_config({})["sla"]
    assert sla["ladder_enabled"] == {"remind_executor": True, "staff_group": True, "manager": True, "reassign": True}
    assert sla["public_status"] == {"enabled": True, "min_urgency": "critical"}
    sla = validate_config({"sla": {"ladder_enabled": {"staff_group": False},
                                   "public_status": {"min_urgency": "high"}}})["sla"]
    assert sla["ladder_enabled"]["staff_group"] is False and sla["ladder_enabled"]["manager"] is True
    assert sla["public_status"] == {"enabled": True, "min_urgency": "high"}


@pytest.mark.parametrize("bad", [
    {"ladder_enabled": {"manager": 1}},
    {"ladder_enabled": {"nope": True}},
    {"public_status": {"enabled": "yes"}},
    {"public_status": {"min_urgency": "medium"}},
])
def test_sla_rejects_bad_new_blocks(bad):
    with pytest.raises(ValueError):
        validate_config({"sla": bad})
