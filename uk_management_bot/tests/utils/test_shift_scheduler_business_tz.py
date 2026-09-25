"""A9-P3-8 / A9-P3-10: планировщик смен — бизнес-зона cron-триггеров,
локализованные уведомления менеджерам и fail-fast при сбое setup_jobs.

До правки `AsyncIOScheduler()` и все `CronTrigger` жили в UTC контейнера:
«перебалансировка в 06:00» срабатывала в 11:00 по Ташкенту, «пн 08:00» — в
13:00. Решение владельца 2026-09-23: время в комментариях = местное время
Ташкента, триггеры несут `BUSINESS_TZ`.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apscheduler.triggers.cron import CronTrigger

from uk_management_bot.utils.business_time import BUSINESS_TZ

LOCALES = Path(__file__).resolve().parents[2] / "config" / "locales"


@pytest.fixture(autouse=True)
def _container_local_tz_is_utc():
    """Эмулируем прод-контейнер: локальная зона процесса = UTC.

    APScheduler 3.x без явной зоны берёт `tzlocal.get_localzone()` — и у
    планировщика, и у КАЖДОГО `CronTrigger` (в момент конструирования, а не из
    планировщика). На машине разработчика в Ташкенте дефект невидим, поэтому
    локальную зону прибиваем к UTC.
    """
    with patch("apscheduler.schedulers.base.get_localzone", return_value=timezone.utc), \
            patch("apscheduler.triggers.cron.get_localzone", return_value=timezone.utc):
        yield


def _real_scheduler():
    """ShiftScheduler с НАСТОЯЩИМ AsyncIOScheduler (не стартованным)."""
    from uk_management_bot.utils.shift_scheduler import ShiftScheduler

    sched = ShiftScheduler()
    sched.setup_jobs()
    return sched


def _cron_jobs(sched):
    return {
        job.id: job.trigger
        for job in sched.scheduler.get_jobs()
        if isinstance(job.trigger, CronTrigger)
    }


def _tz_key(tz) -> str:
    return getattr(tz, "key", None) or str(tz)


# ---------------------------------------------------------------------------
# A9-P3-8: бизнес-зона
# ---------------------------------------------------------------------------

def test_scheduler_itself_runs_in_business_tz():
    from uk_management_bot.utils.shift_scheduler import ShiftScheduler

    sched = ShiftScheduler()
    assert _tz_key(sched.scheduler.timezone) == _tz_key(BUSINESS_TZ)


def test_every_cron_trigger_carries_business_tz():
    jobs = _cron_jobs(_real_scheduler())
    # Все cron-джобы на месте — иначе проверка ниже ничего не значит.
    assert set(jobs) == {
        "auto_create_shifts", "rebalance_assignments",
        "cleanup_expired", "weekly_planning", "executor_open_tasks",
    }
    for job_id, trigger in jobs.items():
        assert _tz_key(trigger.timezone) == _tz_key(BUSINESS_TZ), job_id


@pytest.mark.parametrize(
    "job_id, now_utc, expected_utc",
    [
        # «06:00» по Ташкенту (UTC+5) = 01:00 UTC.
        ("rebalance_assignments",
         datetime(2026, 9, 23, 0, 0, tzinfo=timezone.utc),
         datetime(2026, 9, 23, 1, 0, tzinfo=timezone.utc)),
        # «00:30» по Ташкенту = 19:30 UTC предыдущего дня.
        ("auto_create_shifts",
         datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
         datetime(2026, 9, 23, 19, 30, tzinfo=timezone.utc)),
        # «пн 08:00» по Ташкенту = пн 03:00 UTC (2026-09-28 — понедельник).
        ("weekly_planning",
         datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
         datetime(2026, 9, 28, 3, 0, tzinfo=timezone.utc)),
        # «вс 02:00» по Ташкенту = сб 21:00 UTC (2026-09-26 — суббота).
        ("cleanup_expired",
         datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
         datetime(2026, 9, 26, 21, 0, tzinfo=timezone.utc)),
        # Фаза 4: «18:00» по Ташкенту = 13:00 UTC.
        ("executor_open_tasks",
         datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
         datetime(2026, 9, 23, 13, 0, tzinfo=timezone.utc)),
    ],
)
def test_next_fire_time_is_tashkent_wall_clock(job_id, now_utc, expected_utc):
    if _tz_key(BUSINESS_TZ) != "Asia/Tashkent":
        pytest.skip("ожидания посчитаны для Asia/Tashkent")
    trigger = _cron_jobs(_real_scheduler())[job_id]
    fire = trigger.get_next_fire_time(None, now_utc)
    assert fire == expected_utc
    assert fire.astimezone(BUSINESS_TZ).tzinfo is not None


# ---------------------------------------------------------------------------
# A9-P3-8: тексты уведомлений менеджерам — через get_text (ru/uz)
# ---------------------------------------------------------------------------

_SCHEDULER_KEYS = (
    "auto_created_title", "auto_created_body",
    "transfers_expired_title", "transfers_expired_body",
    "weekly_planning_title", "weekly_planning_body",
)


@pytest.mark.parametrize("lang", ["ru", "uz"])
def test_scheduler_manager_notification_keys_exist(lang):
    data = json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    section = data["shift_scheduler"]
    for key in _SCHEDULER_KEYS:
        assert section.get(key), f"{lang}: shift_scheduler.{key}"
    for key in ("auto_created_body", "transfers_expired_body", "weekly_planning_body"):
        assert "{total}" in section[key], f"{lang}: {key} без {{total}}"


def test_uz_texts_are_translated_not_copied():
    ru = json.loads((LOCALES / "ru.json").read_text(encoding="utf-8"))["shift_scheduler"]
    uz = json.loads((LOCALES / "uz.json").read_text(encoding="utf-8"))["shift_scheduler"]
    for key in _SCHEDULER_KEYS:
        assert ru[key] != uz[key], key


async def test_auto_create_notifies_managers_by_locale_keys():
    """Джоба передаёт КЛЮЧИ, а не готовый русский текст."""
    from uk_management_bot.utils.shift_scheduler import ShiftScheduler

    notif = MagicMock()
    notif.send_manager_notification_i18n = AsyncMock()
    with patch("uk_management_bot.utils.shift_scheduler.AsyncIOScheduler"):
        sched = ShiftScheduler(notification_service=notif)
    with patch.object(ShiftScheduler, "_auto_create_shifts_sync", return_value=15):
        await sched._auto_create_shifts()

    notif.send_manager_notification_i18n.assert_awaited_once_with(
        "shift_scheduler.auto_created_title",
        "shift_scheduler.auto_created_body",
        total=15,
    )


async def test_i18n_manager_notification_renders_per_manager_language():
    from uk_management_bot.services.notification_service import NotificationService

    svc = NotificationService(MagicMock(), bot=MagicMock())
    sent: list = []

    async def _send(bot, tg_id, text):
        sent.append((tg_id, text))
        return True

    channel = AsyncMock(return_value=True)
    with patch(
        "uk_management_bot.services.feedback_service.manager_recipients_sync",
        return_value=[(101, "ru"), (202, "uz")],
    ), patch(
        "uk_management_bot.services.notification_service.service.send_to_user",
        side_effect=_send,
    ), patch(
        "uk_management_bot.services.notification_service.service.send_to_channel",
        channel,
    ):
        await svc.send_manager_notification_i18n(
            "shift_scheduler.weekly_planning_title",
            "shift_scheduler.weekly_planning_body",
            total=42,
        )

    by_id = dict(sent)
    assert set(by_id) == {101, 202}
    assert by_id[101] != by_id[202]
    assert "42" in by_id[101] and "42" in by_id[202]
    assert "shift_scheduler." not in by_id[101] + by_id[202]  # ключ не «протёк»
    channel.assert_awaited_once()


# ---------------------------------------------------------------------------
# A9-P3-10: сбой setup_jobs → планировщик НЕ стартует с частью джоб
# ---------------------------------------------------------------------------

def _mocked_scheduler():
    from uk_management_bot.utils.shift_scheduler import ShiftScheduler

    with patch("uk_management_bot.utils.shift_scheduler.AsyncIOScheduler") as cls:
        aps = MagicMock()
        cls.return_value = aps
        sched = ShiftScheduler()
    return sched, aps


def test_setup_jobs_propagates_error():
    sched, aps = _mocked_scheduler()
    aps.add_job.side_effect = [None, None, RuntimeError("boom")]
    with pytest.raises(RuntimeError):
        sched.setup_jobs()


async def test_start_with_broken_setup_does_not_run_partial_scheduler():
    sched, aps = _mocked_scheduler()
    aps.add_job.side_effect = [None, None, RuntimeError("boom")]

    await sched.start()  # бот не падает целиком

    assert sched.is_running is False
    aps.start.assert_not_called()
    aps.remove_all_jobs.assert_called_once()
    assert sched.start_error and "boom" in sched.start_error
    status = (await sched.get_status())
    assert status["is_running"] is False
    assert "boom" in status["start_error"]


async def test_successful_start_clears_start_error():
    sched, aps = _mocked_scheduler()
    await sched.start()
    assert sched.is_running is True
    assert sched.start_error is None
    assert (await sched.get_status())["start_error"] is None
