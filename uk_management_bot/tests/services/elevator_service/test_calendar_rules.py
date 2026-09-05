"""Юнит-тесты календарных правил ТО/освидетельствований (Ф2a)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from uk_management_bot.services.elevator_service import (
    ElevatorStateError,
    ElevatorValidationError,
    assert_occurrence_editable,
    generate_occurrence_dates,
    is_overdue,
    next_reminder_stage,
    should_remind_overdue,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# generate_occurrence_dates
# ---------------------------------------------------------------------------

class TestGenerateOccurrenceDates:
    def test_monthly_from_start_inclusive(self):
        dates = generate_occurrence_dates(date(2026, 1, 15), 1, 3)
        assert dates == (date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15))

    def test_returns_tuple(self):
        assert isinstance(generate_occurrence_dates(date(2026, 1, 1), 1, 1), tuple)

    def test_end_of_month_clamped_not_cascaded(self):
        dates = generate_occurrence_dates(date(2026, 1, 31), 1, 3)
        # 2026 — не високосный; день исходной даты сохраняется, где возможно
        assert dates == (date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31))

    def test_leap_year_february(self):
        dates = generate_occurrence_dates(date(2028, 1, 31), 1, 2)
        assert dates[1] == date(2028, 2, 29)

    def test_quarterly_crosses_year(self):
        dates = generate_occurrence_dates(date(2026, 11, 30), 3, 3)
        assert dates == (date(2026, 11, 30), date(2027, 2, 28), date(2027, 5, 30))

    def test_max_step_24_months(self):
        dates = generate_occurrence_dates(date(2026, 5, 1), 24, 2)
        assert dates == (date(2026, 5, 1), date(2028, 5, 1))

    def test_max_count_36(self):
        assert len(generate_occurrence_dates(date(2026, 1, 1), 1, 36)) == 36

    @pytest.mark.parametrize("every", [0, -1, 25])
    def test_every_months_out_of_range(self, every):
        with pytest.raises(ElevatorValidationError):
            generate_occurrence_dates(date(2026, 1, 1), every, 1)

    @pytest.mark.parametrize("count", [0, -3, 37])
    def test_count_out_of_range(self, count):
        with pytest.raises(ElevatorValidationError):
            generate_occurrence_dates(date(2026, 1, 1), 1, count)

    def test_bool_is_not_int(self):
        with pytest.raises(ElevatorValidationError):
            generate_occurrence_dates(date(2026, 1, 1), True, 1)


# ---------------------------------------------------------------------------
# assert_occurrence_editable
# ---------------------------------------------------------------------------

class TestAssertOccurrenceEditable:
    def test_planned_ok(self):
        assert_occurrence_editable("planned")

    @pytest.mark.parametrize("state", ["done", "cancelled"])
    def test_terminal_states_frozen(self, state):
        with pytest.raises(ElevatorStateError):
            assert_occurrence_editable(state)

    def test_unknown_state_is_validation_error(self):
        with pytest.raises(ElevatorValidationError):
            assert_occurrence_editable("weird")


# ---------------------------------------------------------------------------
# next_reminder_stage
# ---------------------------------------------------------------------------

DUE = date(2026, 10, 1)


class TestNextReminderStage:
    def test_too_early_none(self):
        assert next_reminder_stage(DUE, DUE - timedelta(days=31), 0) is None

    def test_stage_1_at_30_days(self):
        assert next_reminder_stage(DUE, DUE - timedelta(days=30), 0) == 1

    def test_stage_1_between_30_and_14(self):
        assert next_reminder_stage(DUE, DUE - timedelta(days=20), 0) == 1

    def test_idempotent_same_stage(self):
        assert next_reminder_stage(DUE, DUE - timedelta(days=20), 1) is None

    def test_stage_2_at_14_days(self):
        assert next_reminder_stage(DUE, DUE - timedelta(days=14), 1) == 2

    def test_skips_missed_stages(self):
        # тик впервые за 5 дней до срока: сразу стадия 3, одно сообщение
        assert next_reminder_stage(DUE, DUE - timedelta(days=5), 0) == 3

    def test_stage_3_on_due_day(self):
        assert next_reminder_stage(DUE, DUE, 2) == 3

    def test_all_sent_none(self):
        assert next_reminder_stage(DUE, DUE, 3) is None

    def test_after_due_none(self):
        assert next_reminder_stage(DUE, DUE + timedelta(days=1), 0) is None

    def test_custom_stages(self):
        assert next_reminder_stage(DUE, DUE - timedelta(days=60), 0, stages=(90, 60)) == 2

    @pytest.mark.parametrize("stages", [(), (7, 14), (30, 30), (0, -1), (400,)])
    def test_bad_stages_rejected(self, stages):
        with pytest.raises(ElevatorValidationError):
            next_reminder_stage(DUE, DUE, 0, stages=stages)

    @pytest.mark.parametrize("stage", [-1, 4])
    def test_bad_current_stage_rejected(self, stage):
        with pytest.raises(ElevatorValidationError):
            next_reminder_stage(DUE, DUE, stage)


# ---------------------------------------------------------------------------
# is_overdue / should_remind_overdue
# ---------------------------------------------------------------------------

class TestOverdue:
    def test_not_overdue_before_and_on_due(self):
        assert is_overdue(DUE, DUE - timedelta(days=1)) is False
        assert is_overdue(DUE, DUE) is False

    def test_grace_day_7_not_overdue(self):
        assert is_overdue(DUE, DUE + timedelta(days=7)) is False

    def test_day_8_overdue(self):
        assert is_overdue(DUE, DUE + timedelta(days=8)) is True

    def test_custom_grace(self):
        assert is_overdue(DUE, DUE + timedelta(days=1), grace_days=0) is True

    def test_negative_grace_rejected(self):
        with pytest.raises(ElevatorValidationError):
            is_overdue(DUE, DUE, grace_days=-1)


NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)


class TestShouldRemindOverdue:
    def test_never_reminded(self):
        assert should_remind_overdue(None, NOW) is True

    def test_within_week_no(self):
        assert should_remind_overdue(NOW - timedelta(days=6, hours=23), NOW) is False

    def test_exactly_week_yes(self):
        assert should_remind_overdue(NOW - timedelta(days=7), NOW) is True

    def test_custom_period(self):
        assert should_remind_overdue(NOW - timedelta(days=3), NOW, period_days=3) is True

    def test_naive_raises(self):
        with pytest.raises(ValueError):
            should_remind_overdue(datetime(2026, 10, 1), NOW)
        with pytest.raises(ValueError):
            should_remind_overdue(None, datetime(2026, 10, 1))

    def test_bad_period_rejected(self):
        with pytest.raises(ElevatorValidationError):
            should_remind_overdue(None, NOW, period_days=0)
