from sqlalchemy.orm import Session
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.shift import Shift
import logging
from uk_management_bot.utils.datetime_utils import as_utc, utc_now
from datetime import datetime
# ARCH-116: показ времени смен — только через канон бизнес-зоны.
from uk_management_bot.utils.business_time import fmt_datetime

from uk_management_bot.services.notification_service.channel import (
    send_to_channel,
    send_to_user,
)

logger = logging.getLogger(__name__)


def notify_shift_started(db: Session, user: User, shift: Shift) -> None:
    try:
        logger.info(f"Notification: shift_started user_id={user.id} shift_id={shift.id}")
    except Exception as e:
        logger.error(f"Ошибка уведомления о старте смены: {e}")


def notify_shift_ended(db: Session, user: User, shift: Shift) -> None:
    try:
        logger.info(f"Notification: shift_ended user_id={user.id} shift_id={shift.id}")
    except Exception as e:
        logger.error(f"Ошибка уведомления о завершении смены: {e}")


# ====== Async helpers for full notifications (3.3) ======
def _format_duration_hm(start_time: datetime, end_time: datetime | None) -> tuple[int, int]:
    # ARCH-137 A2: вычитание идёт в Python, а start_time приезжает из БД aware
    # (Postgres) или naive (sqlite) — без нормализации обеих сторон это TypeError
    # на проде при end_time=None. as_utc() выравнивает оба случая.
    end = as_utc(end_time) if end_time else utc_now()
    total_minutes = max(0, int((end - as_utc(start_time)).total_seconds() // 60))
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return hours, minutes


def build_shift_started_message(user: User, shift: Shift, for_channel: bool = False) -> str:
    started = fmt_datetime(shift.start_time) if shift.start_time else ''
    if for_channel:
        return f"🔔 Смена начата: user_id={user.telegram_id} в {started}"
    return f"✅ Ваша смена начата в {started}"


def build_shift_ended_message(user: User, shift: Shift, for_channel: bool = False) -> str:
    hours, minutes = _format_duration_hm(shift.start_time, shift.end_time)
    duration = f"{hours} ч {minutes} мин"
    ended = fmt_datetime(shift.end_time) if shift.end_time else ''
    if for_channel:
        return f"📤 Смена завершена: user_id={user.telegram_id} в {ended} (длительность {duration})"
    return f"✅ Смена завершена в {ended}. Длительность: {duration}"


async def async_notify_shift_started(bot, db: Session, user: User, shift: Shift) -> None:
    try:
        await send_to_user(bot, user.telegram_id, build_shift_started_message(user, shift, for_channel=False))
        await send_to_channel(bot, build_shift_started_message(user, shift, for_channel=True))
    except Exception as e:
        logger.warning(f"Ошибка async уведомления о старте смены: {e}")


async def async_notify_shift_ended(bot, db: Session, user: User, shift: Shift) -> None:
    try:
        await send_to_user(bot, user.telegram_id, build_shift_ended_message(user, shift, for_channel=False))
        await send_to_channel(bot, build_shift_ended_message(user, shift, for_channel=True))
    except Exception as e:
        logger.warning(f"Ошибка async уведомления о завершении смены: {e}")
