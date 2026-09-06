"""Напоминания персоналу по лифтам (Ф6): сбор за тик + запись стадий (sqlite).

Пять видов: стадии ТО/освидетельствования по графику, просрочка ТО (еженедельно
с 8-го дня), договор и освидетельствование лифта (стадии + еженедельно после
истечения), длительный простой по порогам конфига. Каждый тик идемпотентен:
стадия продвигается один раз, повтор тика молчит.
"""

from __future__ import annotations

import html
from datetime import date, datetime, timedelta, timezone

import pytest

from uk_management_bot.database.models.elevator import Elevator, ElevatorMaintenanceOccurrence
from uk_management_bot.services.elevator_service import (
    ElevatorValidationError,
    complete_occurrence_sync,
    elevator_label,
    merge_config,
    status_label,
    update_passport_sync,
)
from uk_management_bot.services.elevator_service.reminders import (
    RemindersBatch,
    StageAdvance,
    apply_reminders_sync,
    collect_reminders_sync,
)
from uk_management_bot.utils.business_time import business_today, fmt_date
from uk_management_bot.utils.helpers import get_text

pytestmark = pytest.mark.integration

# 12:00Z = 17:00 Ташкента → бизнес-дата совпадает с UTC-датой
NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
TODAY = date(2026, 9, 5)

MGR_RU, MGR_UZ, TECH, TECH_ALIAS, PLUMBER, TECH_BLOCKED, BOTH, TECH_DELETED = range(21, 29)
TG = {uid: 7000 + uid for uid in range(21, 29)}
MANAGERS = {TG[MGR_RU], TG[MGR_UZ], TG[BOTH]}
ALL_STAFF = MANAGERS | {TG[TECH], TG[TECH_ALIAS]}


def _staff(seed):
    return [
        seed.user(MGR_RU, TG[MGR_RU], roles='["manager"]'),
        seed.user(MGR_UZ, TG[MGR_UZ], roles='["manager"]', language="uz"),
        seed.user(TECH, TG[TECH], roles='["executor"]', specialization='["elevator"]'),
        # legacy-алиас «maintenance» резолвится в elevator
        seed.user(TECH_ALIAS, TG[TECH_ALIAS], roles='["executor"]', specialization="maintenance"),
        seed.user(PLUMBER, TG[PLUMBER], roles='["executor"]', specialization='["plumber"]'),
        seed.user(TECH_BLOCKED, TG[TECH_BLOCKED], roles='["executor"]',
                  specialization='["elevator"]', bot_blocked_at=NOW),
        seed.user(BOTH, TG[BOTH], roles='["manager", "executor"]', specialization='["elevator"]'),
        seed.user(TECH_DELETED, TG[TECH_DELETED], roles='["executor"]',
                  specialization='["elevator"]', deleted_at=NOW),
    ]


def _seed(db, seed, *extra, **elevator_kwargs):
    db.add_all([seed.yard(), seed.building(), *_staff(seed),
                seed.elevator(1, **{"status": "working", **elevator_kwargs}), *extra])
    db.commit()


def _occ(id, due_on, *, kind="maintenance", state="planned", elevator_id=1, **extra):
    return ElevatorMaintenanceOccurrence(id=id, elevator_id=elevator_id, kind=kind, due_on=due_on,
                                         state=state, **extra)


def _config(**staff_reminders):
    return merge_config(None, {"staff_reminders": staff_reminders} if staff_reminders else None)


def _tick(db, *, now=NOW, config=None) -> RemindersBatch:
    batch = collect_reminders_sync(db, now=now, today=business_today(now), config=config or _config())
    apply_reminders_sync(db, batch)
    db.commit()
    return batch


def _recipients(batch) -> set[int]:
    return {m.telegram_id for m in batch.staff_messages}


def _text(key, db, lang="ru", **params) -> str:
    label = html.escape(elevator_label(db.get(Elevator, 1), lang))
    return get_text(f"elevators.remind.{key}", language=lang, label=label, **params)


def _when(days: int, lang: str = "ru") -> str:
    key = "elevators.remind.when_today" if days == 0 else "elevators.remind.when_in_days"
    return get_text(key, language=lang, days=days)


def _aware(value):
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


class TestMaintenanceStages:
    def test_stage_advances_once_to_managers_and_technicians(self, el_db, el_seed):
        due = TODAY + timedelta(days=20)
        _seed(el_db, el_seed, _occ(1, due))

        batch = _tick(el_db)

        assert _recipients(batch) == ALL_STAFF
        assert len(batch.staff_messages) == len(ALL_STAFF), "один адресат — одно сообщение"
        by_tg = {m.telegram_id: m.text for m in batch.staff_messages}
        assert by_tg[TG[MGR_RU]] == _text("maintenance_due", el_db, date=fmt_date(due), when=_when(20))
        assert by_tg[TG[MGR_UZ]] == _text("maintenance_due", el_db, "uz", date=fmt_date(due), when=_when(20, "uz"))
        assert batch.advances == (StageAdvance("occurrence", 1, "reminder_stage", 30),)
        assert el_db.get(ElevatorMaintenanceOccurrence, 1).reminder_stage == 30

        assert _tick(el_db).staff_messages == ()

    def test_skipped_stages_collapse_into_one_message(self, el_db, el_seed):
        _seed(el_db, el_seed, _occ(1, TODAY + timedelta(days=5)))

        batch = _tick(el_db)

        assert batch.advances == (StageAdvance("occurrence", 1, "reminder_stage", 7),)
        assert len(batch.staff_messages) == len(ALL_STAFF)

    def test_next_stage_fires_when_reached(self, el_db, el_seed):
        due = TODAY + timedelta(days=20)
        _seed(el_db, el_seed, _occ(1, due))
        _tick(el_db)  # стадия 30

        assert _tick(el_db, now=NOW + timedelta(days=5)) == RemindersBatch()  # 15 дней: ещё 30
        batch = _tick(el_db, now=NOW + timedelta(days=6))  # 14 дней

        assert batch.advances == (StageAdvance("occurrence", 1, "reminder_stage", 14),)
        assert el_db.get(ElevatorMaintenanceOccurrence, 1).reminder_stage == 14
        # пауза тиков: 14 → сразу 7 одним сообщением
        later = _tick(el_db, now=NOW + timedelta(days=15))
        assert later.advances == (StageAdvance("occurrence", 1, "reminder_stage", 7),)

    def test_stages_come_from_config_per_kind(self, el_db, el_seed):
        due = TODAY + timedelta(days=50)
        _seed(el_db, el_seed, _occ(1, due), _occ(2, due, kind="certification"))

        batch = _tick(el_db, config=_config(certification=[60, 10]))

        # ТО (30/14/7) ещё не в окне; освидетельствование по своему списку — уже
        assert batch.advances == (StageAdvance("occurrence", 2, "reminder_stage", 60),)
        assert {m.text for m in batch.staff_messages if m.telegram_id == TG[MGR_RU]} == {
            _text("certification_due", el_db, date=fmt_date(due), when=_when(50))
        }

    def test_due_today_says_today_not_zero_days(self, el_db, el_seed):
        _seed(el_db, el_seed, _occ(1, TODAY))

        batch = _tick(el_db)

        by_tg = {m.telegram_id: m.text for m in batch.staff_messages}
        assert by_tg[TG[MGR_RU]] == _text("maintenance_due", el_db, date=fmt_date(TODAY), when=_when(0))
        assert "сегодня" in by_tg[TG[MGR_RU]] and "0" not in by_tg[TG[MGR_RU]].split(fmt_date(TODAY))[1]
        assert "bugun" in by_tg[TG[MGR_UZ]]
        assert batch.advances == (StageAdvance("occurrence", 1, "reminder_stage", 7),)

    def test_stored_stage_survives_config_shrink(self, el_db, el_seed):
        _seed(el_db, el_seed, _occ(1, TODAY + timedelta(days=5), reminder_stage=60))

        batch = _tick(el_db, config=_config(maintenance=[14, 7]))

        assert batch.advances == (StageAdvance("occurrence", 1, "reminder_stage", 7),)

    def test_done_cancelled_and_archived_are_ignored(self, el_db, el_seed):
        due = TODAY + timedelta(days=3)
        _seed(
            el_db, el_seed,
            _occ(1, due, state="done"), _occ(2, due, state="cancelled"),
            el_seed.elevator(2, entrance=2, archived_at=NOW), _occ(3, due, elevator_id=2),
        )

        assert _tick(el_db) == RemindersBatch()


class TestMaintenanceOverdue:
    def test_weekly_from_day_eight(self, el_db, el_seed):
        due = TODAY - timedelta(days=8)
        _seed(el_db, el_seed, _occ(1, due))

        batch = _tick(el_db)

        assert _recipients(batch) == ALL_STAFF
        assert batch.staff_messages[0].text == _text(
            "maintenance_overdue", el_db, date=fmt_date(due), days=8
        )
        assert batch.advances == (StageAdvance("occurrence", 1, "overdue_reminded_at", NOW),)
        assert _aware(el_db.get(ElevatorMaintenanceOccurrence, 1).overdue_reminded_at) == NOW

        assert _tick(el_db, now=NOW + timedelta(days=3)).staff_messages == ()
        again = _tick(el_db, now=NOW + timedelta(days=7))
        assert _recipients(again) == ALL_STAFF

    def test_grace_week_is_silent(self, el_db, el_seed):
        _seed(el_db, el_seed, _occ(1, TODAY - timedelta(days=7)))
        assert _tick(el_db) == RemindersBatch()

    def test_overdue_weekly_flag_off(self, el_db, el_seed):
        _seed(el_db, el_seed, _occ(1, TODAY - timedelta(days=30)))
        assert _tick(el_db, config=_config(overdue_weekly=False)) == RemindersBatch()

    def test_certification_occurrence_overdue_has_own_text(self, el_db, el_seed):
        due = TODAY - timedelta(days=10)
        _seed(el_db, el_seed, _occ(1, due, kind="certification"))

        batch = _tick(el_db)

        assert batch.staff_messages[0].text == _text(
            "certification_overdue", el_db, date=fmt_date(due), days=10
        )


class TestContract:
    def test_stage_to_managers_only_then_silent(self, el_db, el_seed):
        until = TODAY + timedelta(days=10)
        _seed(el_db, el_seed, contract_until=until)

        batch = _tick(el_db)

        assert _recipients(batch) == MANAGERS
        assert batch.staff_messages[0].text == _text("contract_due", el_db, date=fmt_date(until), when=_when(10))
        assert batch.advances == (StageAdvance("elevator", 1, "contract_reminder_stage", 14),)
        assert el_db.get(Elevator, 1).contract_reminder_stage == 14
        assert _tick(el_db) == RemindersBatch()

    def test_expired_weekly(self, el_db, el_seed):
        until = TODAY - timedelta(days=1)
        _seed(el_db, el_seed, contract_until=until, contract_reminder_stage=7)

        batch = _tick(el_db)

        assert _recipients(batch) == MANAGERS
        assert batch.staff_messages[0].text == _text("contract_expired", el_db, date=fmt_date(until), days=1)
        assert batch.advances == (StageAdvance("elevator", 1, "contract_overdue_reminded_at", NOW),)
        assert _tick(el_db, now=NOW + timedelta(days=6)) == RemindersBatch()
        assert _recipients(_tick(el_db, now=NOW + timedelta(days=7))) == MANAGERS

    def test_renewal_resets_stage_and_weekly_marker(self, el_db, el_seed):
        _seed(el_db, el_seed, contract_until=TODAY - timedelta(days=1))
        _tick(el_db)

        update_passport_sync(el_db, 1, {"contract_until": TODAY + timedelta(days=400)},
                             actor_user_id=MGR_RU, expected_version=None, now=NOW)
        el_db.commit()

        elevator = el_db.get(Elevator, 1)
        assert (elevator.contract_reminder_stage, elevator.contract_overdue_reminded_at) == (0, None)
        assert _tick(el_db) == RemindersBatch()

    def test_not_commissioned_elevator_is_skipped(self, el_db, el_seed):
        _seed(el_db, el_seed, commissioned=False, contract_until=TODAY + timedelta(days=3))
        assert _tick(el_db) == RemindersBatch()


class TestCertification:
    def test_stage_uses_certification_config(self, el_db, el_seed):
        until = TODAY + timedelta(days=45)
        _seed(el_db, el_seed, cert_valid_until=until)

        assert _tick(el_db) == RemindersBatch()
        batch = _tick(el_db, config=_config(certification=[60, 7]))

        assert _recipients(batch) == MANAGERS
        assert batch.staff_messages[0].text == _text("cert_due", el_db, date=fmt_date(until), when=_when(45))
        assert batch.advances == (StageAdvance("elevator", 1, "cert_reminder_stage", 60),)

    def test_completing_certification_via_calendar_resets_weekly_marker(self, el_db, el_seed):
        """Истёкшее освидетельствование → тик напомнил → освидетельствование
        закрыто через календарь с новыми реквизитами → (0, None) → тик молчит."""
        _seed(el_db, el_seed, _occ(1, TODAY, kind="certification"),
              cert_valid_until=TODAY - timedelta(days=20), cert_reminder_stage=7)
        first = _tick(el_db)
        assert StageAdvance("elevator", 1, "cert_overdue_reminded_at", NOW) in first.advances

        complete_occurrence_sync(
            el_db, 1, actor_user_id=MGR_RU, comment=None, now=NOW,
            cert_fields={"cert_number": "C-9", "cert_valid_until": TODAY + timedelta(days=400)},
        )
        el_db.commit()

        elevator = el_db.get(Elevator, 1)
        assert (elevator.cert_reminder_stage, elevator.cert_overdue_reminded_at) == (0, None)
        assert _tick(el_db) == RemindersBatch()

    def test_expired_weekly(self, el_db, el_seed):
        until = TODAY - timedelta(days=20)
        _seed(el_db, el_seed, cert_valid_until=until)

        batch = _tick(el_db)

        assert batch.staff_messages[0].text == _text("cert_expired", el_db, date=fmt_date(until), days=20)
        assert batch.advances == (StageAdvance("elevator", 1, "cert_overdue_reminded_at", NOW),)
        assert _tick(el_db) == RemindersBatch()


class TestDowntime:
    def test_threshold_reached_weekly_to_managers(self, el_db, el_seed):
        since = NOW - timedelta(days=8)
        _seed(el_db, el_seed, status="not_working", status_since=since)

        batch = _tick(el_db)

        assert _recipients(batch) == MANAGERS
        by_tg = {m.telegram_id: m.text for m in batch.staff_messages}
        assert by_tg[TG[MGR_UZ]] == _text(
            "downtime", el_db, "uz", status=status_label("not_working", "uz"),
            date=fmt_date(since), days=8,
        )
        assert batch.advances == (StageAdvance("elevator", 1, "downtime_reminded_at", NOW),)
        assert _tick(el_db, now=NOW + timedelta(days=2)) == RemindersBatch()
        assert _recipients(_tick(el_db, now=NOW + timedelta(days=7))) == MANAGERS

    def test_below_threshold_and_null_threshold_are_silent(self, el_db, el_seed):
        _seed(
            el_db, el_seed,
            el_seed.elevator(2, entrance=2, status="under_repair", status_since=NOW - timedelta(days=90)),
            status="not_working", status_since=NOW - timedelta(days=6),
        )
        assert _tick(el_db) == RemindersBatch()

    def test_threshold_from_config(self, el_db, el_seed):
        _seed(el_db, el_seed, status="under_repair", status_since=NOW - timedelta(days=3))
        config = merge_config(None, {"downtime_threshold_days": {"under_repair": 2}})

        batch = _tick(el_db, config=config)

        assert batch.advances == (StageAdvance("elevator", 1, "downtime_reminded_at", NOW),)


class TestRecipients:
    def test_manager_with_technician_role_gets_one_message_per_event(self, el_db, el_seed):
        _seed(el_db, el_seed, _occ(1, TODAY + timedelta(days=5)), _occ(2, TODAY + timedelta(days=6)))

        batch = _tick(el_db)

        per_event = [m for m in batch.staff_messages if m.telegram_id == TG[BOTH]]
        assert len(per_event) == 2
        assert len(batch.staff_messages) == 2 * len(ALL_STAFF)

    def test_no_recipients_still_advances_stage(self, el_db, el_seed):
        el_db.add_all([el_seed.yard(), el_seed.building(), el_seed.elevator(1),
                       _occ(1, TODAY + timedelta(days=5))])
        el_db.commit()

        batch = _tick(el_db)

        assert batch.staff_messages == ()
        assert el_db.get(ElevatorMaintenanceOccurrence, 1).reminder_stage == 7


class TestBusinessDate:
    def test_window_uses_business_today_not_utc_date(self, el_db, el_seed):
        # 20:30Z 5 сентября = 01:30 6 сентября по Ташкенту → до 13.09 ровно 7 дней
        evening = datetime(2026, 9, 5, 20, 30, tzinfo=timezone.utc)
        _seed(el_db, el_seed, _occ(1, date(2026, 9, 13)))

        batch = _tick(el_db, now=evening)

        assert batch.advances == (StageAdvance("occurrence", 1, "reminder_stage", 7),)
        # первый адресат — MGR_RU (менеджеры идут первыми, по user.id)
        assert batch.staff_messages[0].telegram_id == TG[MGR_RU]
        assert batch.staff_messages[0].text == _text(
            "maintenance_due", el_db, date="13.09.2026", when=_when(7)
        )


class TestApply:
    def test_unknown_field_is_rejected(self, el_db, el_seed):
        _seed(el_db, el_seed)
        with pytest.raises(ElevatorValidationError):
            apply_reminders_sync(el_db, RemindersBatch(advances=(StageAdvance("elevator", 1, "version", 9),)))
        with pytest.raises(ElevatorValidationError):
            apply_reminders_sync(el_db, RemindersBatch(advances=(StageAdvance("request", 1, "reminder_stage", 9),)))

    def test_elevator_version_is_not_bumped(self, el_db, el_seed):
        """Метки напоминаний — не правка паспорта: менеджер не должен ловить 409 по версии."""
        _seed(el_db, el_seed, contract_until=TODAY - timedelta(days=1),
              status="not_working", status_since=NOW - timedelta(days=30))

        batch = _tick(el_db)

        assert {a.field for a in batch.advances} == {"contract_overdue_reminded_at", "downtime_reminded_at"}
        assert el_db.get(Elevator, 1).version == 1

    def test_missing_row_is_skipped(self, el_db, el_seed):
        _seed(el_db, el_seed)
        applied = apply_reminders_sync(
            el_db, RemindersBatch(advances=(StageAdvance("occurrence", 999, "reminder_stage", 7),))
        )
        assert applied == 0
