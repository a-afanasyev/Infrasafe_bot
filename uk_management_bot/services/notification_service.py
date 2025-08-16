from sqlalchemy.orm import Session
from database.models.request import Request
from database.models.user import User
from database.models.shift import Shift
import logging
from utils.constants import (
    NOTIFICATION_TYPE_STATUS_CHANGED,
    NOTIFICATION_TYPE_PURCHASE,
    NOTIFICATION_TYPE_CLARIFICATION,
)
from config.settings import settings
from datetime import datetime

logger = logging.getLogger(__name__)


def notify_status_changed(db: Session, request: Request, old_status: str, new_status: str) -> None:
    """Отправка уведомлений о смене статуса. Пока лог-заглушка.

    В будущем здесь может быть отправка в канал/чат или адресные уведомления.
    """
    try:
        logger.info(
            f"Notification: type={NOTIFICATION_TYPE_STATUS_CHANGED}, request_id={request.id}, old={old_status}, new={new_status}"
        )
        if new_status == "Закуп":
            logger.info(f"Notification: type={NOTIFICATION_TYPE_PURCHASE}, request_id={request.id}")
        if new_status == "Уточнение":
            logger.info(f"Notification: type={NOTIFICATION_TYPE_CLARIFICATION}, request_id={request.id}")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о смене статуса: {e}")


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
    end = end_time or datetime.now()
    total_minutes = max(0, int((end - start_time).total_seconds() // 60))
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return hours, minutes


def build_shift_started_message(user: User, shift: Shift, for_channel: bool = False) -> str:
    started = shift.start_time.strftime('%d.%m.%Y %H:%M') if shift.start_time else ''
    if for_channel:
        return f"🔔 Смена начата: user_id={user.telegram_id} в {started}"
    return f"✅ Ваша смена начата в {started}"


def build_shift_ended_message(user: User, shift: Shift, for_channel: bool = False) -> str:
    hours, minutes = _format_duration_hm(shift.start_time, shift.end_time)
    duration = f"{hours} ч {minutes} мин"
    ended = shift.end_time.strftime('%d.%m.%Y %H:%M') if shift.end_time else ''
    if for_channel:
        return f"📤 Смена завершена: user_id={user.telegram_id} в {ended} (длительность {duration})"
    return f"✅ Смена завершена в {ended}. Длительность: {duration}"


async def send_to_channel(bot, text: str) -> None:
    try:
        channel_id = settings.TELEGRAM_CHANNEL_ID
        if not channel_id:
            return
        await bot.send_message(channel_id, text)
    except Exception as e:
        logger.warning(f"Не удалось отправить сообщение в канал: {e}")


async def send_to_user(bot, user_telegram_id: int, text: str) -> None:
    try:
        await bot.send_message(user_telegram_id, text)
    except Exception as e:
        logger.warning(f"Не удалось отправить сообщение пользователю {user_telegram_id}: {e}")


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


# ====== Request status notifications (3.4) ======
def _build_request_status_message_user(request: Request, old_status: str, new_status: str) -> str:
    return (
        f"📌 Статус вашей заявки #{request.id} изменён: {old_status} → {new_status}\n"
        f"Категория: {request.category}\n"
        f"Адрес: {request.address[:60]}{'…' if len(request.address) > 60 else ''}"
    )


def _build_request_status_message_executor(request: Request, old_status: str, new_status: str) -> str:
    return (
        f"📌 Статус заявки #{request.id} изменён: {old_status} → {new_status}\n"
        f"Категория: {request.category} — назначена вам"
    )


def _build_request_status_message_channel(request: Request, old_status: str, new_status: str) -> str:
    return (
        f"🔔 Заявка #{request.id}: {old_status} → {new_status}\n"
        f"Категория: {request.category}"
    )


async def async_notify_request_status_changed(
    bot,
    db: Session,
    request: Request,
    old_status: str,
    new_status: str,
) -> None:
    try:
        # Пользователь-заявитель
        try:
            from database.models.user import User as UserModel
            applicant = db.query(UserModel).filter(UserModel.id == request.user_id).first()
            if applicant and applicant.telegram_id:
                await send_to_user(
                    bot,
                    applicant.telegram_id,
                    _build_request_status_message_user(request, old_status, new_status),
                )
        except Exception as e:
            logger.warning(f"Не удалось уведомить заявителя по заявке #{request.id}: {e}")

        # Исполнитель (если назначен)
        try:
            if request.executor_id:
                from database.models.user import User as UserModel
                executor = db.query(UserModel).filter(UserModel.id == request.executor_id).first()
                if executor and executor.telegram_id:
                    await send_to_user(
                        bot,
                        executor.telegram_id,
                        _build_request_status_message_executor(request, old_status, new_status),
                    )
        except Exception as e:
            logger.warning(f"Не удалось уведомить исполнителя по заявке #{request.id}: {e}")

        # Канал (если настроен)
        await send_to_channel(bot, _build_request_status_message_channel(request, old_status, new_status))
    except Exception as e:
        logger.warning(f"Ошибка async уведомления о смене статуса заявки #{request.id}: {e}")


# ====== 6.8 Role switch and action denied notifications ======
def build_role_switched_message(user: User, old_role: str, new_role: str) -> str:
    """Строит локализованное сообщение о смене активной роли."""
    try:
        from utils.helpers import get_text
        language = getattr(user, "language", "ru") or "ru"
        role_key = f"roles.{new_role}"
        role_display = get_text(role_key, language=language)
        return get_text("role.switched_notify", language=language, role=role_display)
    except Exception:
        return f"Режим переключён: {new_role}"


async def async_notify_role_switched(bot, db: Session, user: User, old_role: str, new_role: str) -> None:
    """Отправляет пользователю уведомление о смене режима (best-effort)."""
    try:
        text = build_role_switched_message(user, old_role, new_role)
        await send_to_user(bot, user.telegram_id, text)
    except Exception as e:
        logger.warning(f"Ошибка отправки уведомления о смене режима: {e}")


def build_action_denied_message(reason_key: str, language: str = "ru") -> str:
    """Строит локализованное уведомление об отказе с причиной.

    reason_key ожидает короткое значение: 'not_in_shift' | 'permission_denied' | 'invalid_transition'
    """
    try:
        from utils.helpers import get_text
        title = get_text("notify.denied_title", language=language)
        reason_text = get_text(f"notify.reason.{reason_key}", language=language)
        return f"{title}:\n{reason_text}"
    except Exception:
        fallback = {
            "not_in_shift": "Действие отклонено: вы не в смене.",
            "permission_denied": "Действие отклонено: недостаточно прав.",
            "invalid_transition": "Действие отклонено: недопустимый переход статуса.",
        }
        return fallback.get(reason_key, "Действие отклонено")


async def async_notify_action_denied(bot, db: Session, user_telegram_id: int, reason_key: str) -> None:
    """Адресное уведомление пользователю об отказе, локализованное по его языку (best-effort)."""
    try:
        user = db.query(User).filter(User.telegram_id == user_telegram_id).first()
        language = getattr(user, "language", "ru") if user else "ru"
        text = build_action_denied_message(reason_key, language=language)
        await send_to_user(bot, user_telegram_id, text)
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление об отказе пользователю {user_telegram_id}: {e}")

