"""Юнит-тесты порогов простоя и конфига модуля «Лифты» (Ф2a)."""
import copy
from datetime import datetime, timedelta, timezone
from types import MappingProxyType

import pytest

from uk_management_bot.services.elevator_service import (
    DEFAULT_ELEVATORS_CONFIG,
    DOWNTIME_STATUSES,
    ElevatorValidationError,
    downtime_threshold_reached,
    merge_config,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
D = timedelta(days=1)
THRESHOLDS = {"not_working": 7, "under_repair": None}


# ---------------------------------------------------------------------------
# downtime_threshold_reached
# ---------------------------------------------------------------------------

class TestDowntimeThresholdReached:
    def test_reached_at_threshold(self):
        assert downtime_threshold_reached("not_working", NOW - 7 * D, NOW, THRESHOLDS) is True

    def test_not_yet(self):
        since = NOW - 6 * D - timedelta(hours=23)
        assert downtime_threshold_reached("not_working", since, NOW, THRESHOLDS) is False

    def test_none_threshold_means_never(self):
        assert downtime_threshold_reached("under_repair", NOW - 400 * D, NOW, THRESHOLDS) is False

    def test_missing_key_means_never(self):
        assert downtime_threshold_reached("not_working", NOW - 400 * D, NOW, {}) is False

    @pytest.mark.parametrize("status", ["working", "maintenance"])
    def test_non_downtime_statuses_false(self, status):
        thresholds = {**THRESHOLDS, status: 1}
        assert downtime_threshold_reached(status, NOW - 400 * D, NOW, thresholds) is False

    def test_status_since_none_false(self):
        assert downtime_threshold_reached("not_working", None, NOW, THRESHOLDS) is False

    def test_naive_raises(self):
        with pytest.raises(ValueError):
            downtime_threshold_reached("not_working", datetime(2026, 1, 1), NOW, THRESHOLDS)


# ---------------------------------------------------------------------------
# DEFAULT_ELEVATORS_CONFIG / merge_config
# ---------------------------------------------------------------------------

class TestDefaultConfig:
    def test_frozen(self):
        assert isinstance(DEFAULT_ELEVATORS_CONFIG, MappingProxyType)
        with pytest.raises(TypeError):
            DEFAULT_ELEVATORS_CONFIG["module_public"] = True  # type: ignore[index]
        with pytest.raises(TypeError):
            DEFAULT_ELEVATORS_CONFIG["downtime_threshold_days"]["not_working"] = 1  # type: ignore[index]

    def test_values(self):
        cfg = DEFAULT_ELEVATORS_CONFIG
        assert cfg["module_public"] is False
        assert dict(cfg["downtime_threshold_days"]) == {"not_working": 7, "under_repair": None}
        assert dict(cfg["resident_notifications"]) == {
            "repair_started": True,
            "maintenance_started": True,
            "back_in_service": True,
        }
        assert tuple(cfg["staff_reminders"]["maintenance"]) == (30, 14, 7)
        assert cfg["staff_reminders"]["overdue_weekly"] is True
        assert set(cfg["downtime_threshold_days"]) == set(DOWNTIME_STATUSES)


class TestMergeConfig:
    def test_none_none_gives_defaults_as_plain_dict(self):
        result = merge_config(None, None)
        assert type(result) is dict
        assert type(result["staff_reminders"]) is dict
        assert result["staff_reminders"]["maintenance"] == [30, 14, 7]
        assert result["module_public"] is False

    def test_stored_then_patch_precedence(self):
        stored = {"module_public": True, "downtime_threshold_days": {"not_working": 3}}
        patch = {"downtime_threshold_days": {"under_repair": 10}}
        result = merge_config(stored, patch)
        assert result["module_public"] is True
        assert result["downtime_threshold_days"] == {"not_working": 3, "under_repair": 10}

    def test_patch_overrides_stored(self):
        result = merge_config({"module_public": True}, {"module_public": False})
        assert result["module_public"] is False

    def test_patch_can_set_threshold_none(self):
        result = merge_config(
            {"downtime_threshold_days": {"not_working": 3}},
            {"downtime_threshold_days": {"not_working": None}},
        )
        assert result["downtime_threshold_days"]["not_working"] is None

    def test_stages_list_replaced_not_merged(self):
        result = merge_config(None, {"staff_reminders": {"maintenance": [60, 30]}})
        assert result["staff_reminders"]["maintenance"] == [60, 30]
        assert result["staff_reminders"]["certification"] == [30, 14, 7]

    def test_inputs_not_mutated(self):
        stored = {"downtime_threshold_days": {"not_working": 3}}
        patch = {"staff_reminders": {"maintenance": [10]}}
        s_copy, p_copy = copy.deepcopy(stored), copy.deepcopy(patch)
        result = merge_config(stored, patch)
        result["staff_reminders"]["maintenance"].append(1)
        result["downtime_threshold_days"]["not_working"] = 99
        assert stored == s_copy and patch == p_copy
        assert DEFAULT_ELEVATORS_CONFIG["staff_reminders"]["maintenance"] == (30, 14, 7)

    @pytest.mark.parametrize("bad", [0, 366, -5, "7", 7.5, True])
    def test_threshold_out_of_range(self, bad):
        with pytest.raises(ElevatorValidationError):
            merge_config(None, {"downtime_threshold_days": {"not_working": bad}})

    def test_threshold_unknown_status(self):
        with pytest.raises(ElevatorValidationError):
            merge_config(None, {"downtime_threshold_days": {"working": 5}})

    @pytest.mark.parametrize(
        "bad", [[], [7, 14], [30, 30], [0], [400], [7, "1"], "30,14", None]
    )
    def test_bad_stages(self, bad):
        with pytest.raises(ElevatorValidationError):
            merge_config(None, {"staff_reminders": {"certification": bad}})

    def test_stages_accept_tuple(self):
        result = merge_config(None, {"staff_reminders": {"contract": (90, 30)}})
        assert result["staff_reminders"]["contract"] == [90, 30]

    @pytest.mark.parametrize(
        "key,value",
        [
            ("module_public", "yes"),
            ("resident_notifications", {"repair_started": 1}),
            ("resident_notifications", {"unknown": True}),
            ("staff_reminders", {"overdue_weekly": "no"}),
            ("staff_reminders", {"unknown": [1]}),
            ("staff_reminders", None),
            ("downtime_threshold_days", [7]),
        ],
    )
    def test_type_errors(self, key, value):
        with pytest.raises(ElevatorValidationError):
            merge_config(None, {key: value})

    def test_unknown_top_level_key(self):
        with pytest.raises(ElevatorValidationError):
            merge_config(None, {"bogus": 1})

    def test_non_mapping_input(self):
        with pytest.raises(ElevatorValidationError):
            merge_config([], None)  # type: ignore[arg-type]
