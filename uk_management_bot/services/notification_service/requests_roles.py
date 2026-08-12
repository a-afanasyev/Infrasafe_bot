from sqlalchemy.orm import Session
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
import logging
from uk_management_bot.utils.constants import (
    NOTIFICATION_TYPE_STATUS_CHANGED,
    NOTIFICATION_TYPE_PURCHASE,
    NOTIFICATION_TYPE_CLARIFICATION,
)

from uk_management_bot.services.notification_service.channel import send_to_user

logger = logging.getLogger(__name__)


def notify_status_changed(db: Session, request: Request, old_status: str, new_status: str) -> None:
    """Отправка уведомлений о смене статуса. Пока лог-заглушка.

    В будущем здесь может быть отправка в канал/чат или адресные уведомления.
    """
    try:
        logger.info(
            f"Notification: type={NOTIFICATION_TYPE_STATUS_CHANGED}, request_number={request.request_number}, old={old_status}, new={new_status}"
        )
        if new_status == "Закуп":
            logger.info(f"Notification: type={NOTIFICATION_TYPE_PURCHASE}, request_number={request.request_number}")
        if new_status == "Уточнение":
            logger.info(f"Notification: type={NOTIFICATION_TYPE_CLARIFICATION}, request_number={request.request_number}")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о смене статуса: {e}")


# ====== Request status notifications (3.4) ======
# AUD6-P1-6: легаси `async_notify_request_status_changed` (заявителю,
# исполнителю и в канал одним вызовом, нелокализованным текстом) удалён —
# на одни и те же переходы он слал других получателей с другим текстом, чем
# API-путь. Адресную часть исполняет матрица интентов
# (`workflow_notifications.dispatch_notify_intents{,_sync}`), канальную —
# `workflow_notifications.notify_channel_status_changed`, который использует
# билдер ниже.
def _build_request_status_message_channel(request: Request, old_status: str, new_status: str) -> str:
    return (
        f"🔔 Заявка #{request.request_number}: {old_status} → {new_status}\n"
        f"Категория: {request.category}"
    )


# ====== 6.8 Role switch and action denied notifications ======
def build_role_switched_message(user: User, old_role: str, new_role: str) -> str:
    """Строит локализованное сообщение о смене активной роли."""
    try:
        from uk_management_bot.utils.helpers import get_text
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
        from uk_management_bot.utils.helpers import get_text
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
