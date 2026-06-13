from sqlalchemy.orm import Session
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.shift import Shift
import logging
from uk_management_bot.utils.constants import (
    NOTIFICATION_TYPE_STATUS_CHANGED,
    NOTIFICATION_TYPE_PURCHASE,
    NOTIFICATION_TYPE_CLARIFICATION,
)
from uk_management_bot.config.settings import settings
from uk_management_bot.utils.helpers import get_text
from datetime import datetime

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


# BUG-BOT-016: Default placeholder в .env.template — не валидный канал, должен игнорироваться
_CHANNEL_ID_PLACEHOLDERS = frozenset({
    "@your_notifications_channel",
    "your_notifications_channel",
    "your_channel_id",
    "@your_channel",
})


def _resolve_channel_id() -> str | None:
    """Возвращает channel_id если он задан и не является placeholder'ом."""
    raw = settings.TELEGRAM_CHANNEL_ID
    if not raw:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    if stripped in _CHANNEL_ID_PLACEHOLDERS:
        return None
    return stripped


async def send_to_channel(bot, text: str) -> None:
    try:
        channel_id = _resolve_channel_id()
        if not channel_id:
            return
        await bot.send_message(channel_id, text)
    except Exception as e:
        logger.warning(f"Не удалось отправить сообщение в канал: {e}")


async def send_to_user(bot, user_telegram_id: int, text: str) -> bool:
    """Отправить сообщение пользователю. Возвращает True при успешной доставке,
    False при ошибке (Telegram 403/400, network) — BUG-BOT-036: caller'ы должны
    различать фактическую доставку и проглоченный сбой."""
    try:
        await bot.send_message(user_telegram_id, text)
        return True
    except Exception as e:
        logger.warning(f"Не удалось отправить сообщение пользователю {user_telegram_id}: {e}")
        return False


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


def build_document_request_message(user: User, request_text: str, document_type: str = None, for_channel: bool = False) -> str:
    """Формирует сообщение о запросе документов"""
    if for_channel:
        return f"📋 Запрос документов: user_id={user.telegram_id}, тип: {document_type}, запрос: {request_text}"
    
    # Получаем название типа документа
    document_names = {
        'passport': 'паспорт',
        'property_deed': 'свидетельство о собственности',
        'rental_agreement': 'договор аренды',
        'utility_bill': 'квитанцию ЖКХ',
        'other': 'дополнительные документы'
    }
    
    doc_name = document_names.get(document_type, document_type) if document_type else "дополнительные документы"
    
    message = f"📋 **Администратор запросил документы**\n\n"
    message += f"🔍 **Требуемый документ:** {doc_name}\n\n"
    message += f"💬 **Комментарий:**\n{request_text}\n\n"
    message += f"📤 Пожалуйста, загрузите запрошенный документ в ближайшее время."
    
    return message


async def async_notify_document_request(bot, db: Session, user: User, request_text: str, document_type: str = None) -> None:
    """Отправляет уведомление о запросе документов"""
    try:
        await send_to_user(bot, user.telegram_id, build_document_request_message(user, request_text, document_type, for_channel=False))
        await send_to_channel(bot, build_document_request_message(user, request_text, document_type, for_channel=True))
    except Exception as e:
        logger.warning(f"Ошибка async уведомления о запросе документов: {e}")


def build_multiple_documents_request_message(user: User, request_text: str, document_types: list, for_channel: bool = False) -> str:
    """Формирует сообщение о запросе множественных документов"""
    if for_channel:
        return f"📋 Запрос документов: user_id={user.telegram_id}, типы: {document_types}, запрос: {request_text}"
    
    # Получаем названия типов документов
    document_names = {
        'passport': 'паспорт',
        'property_deed': 'свидетельство о собственности',
        'rental_agreement': 'договор аренды',
        'utility_bill': 'квитанцию ЖКХ',
        'other': 'дополнительные документы'
    }
    
    doc_names = []
    for doc_type in document_types:
        doc_name = document_names.get(doc_type, doc_type)
        doc_names.append(doc_name)
    
    doc_list = ", ".join(doc_names)
    
    message = f"📋 **Администратор запросил документы**\n\n"
    message += f"🔍 **Требуемые документы:**\n{doc_list}\n\n"
    message += f"💬 **Комментарий:**\n{request_text}\n\n"
    message += f"📤 Пожалуйста, загрузите все запрошенные документы в ближайшее время."
    
    return message


async def async_notify_multiple_documents_request(bot, db: Session, user: User, request_text: str, document_types: list) -> None:
    """Отправляет уведомление о запросе множественных документов"""
    try:
        await send_to_user(bot, user.telegram_id, build_multiple_documents_request_message(user, request_text, document_types, for_channel=False))
        await send_to_channel(bot, build_multiple_documents_request_message(user, request_text, document_types, for_channel=True))
    except Exception as e:
        logger.warning(f"Ошибка async уведомления о запросе множественных документов: {e}")


# ====== Shared Bot instance for notifications ======

_shared_bot = None


def _get_shared_bot():
    """Get or create a shared Bot instance for sending notifications."""
    global _shared_bot
    if _shared_bot is None:
        from aiogram import Bot
        _shared_bot = Bot(token=settings.BOT_TOKEN)
    return _shared_bot


# ====== Уведомления для системы верификации ======

class NotificationService:
    """Сервис уведомлений для системы верификации"""

    def __init__(self, db: Session, bot=None):
        self.db = db
        self.bot = bot

    def _get_bot(self):
        """Return the bot instance — prefer injected, fall back to shared singleton."""
        return self.bot or _get_shared_bot()

    def _get_user_lang(self, user) -> str:
        """Get language from user object, default to 'ru'."""
        return getattr(user, 'language', None) or 'ru'
    
    async def send_verification_request_notification(self, user_id: int, info_type: str, comment: str) -> None:
        """
        Отправить уведомление о запросе дополнительной информации
        
        Args:
            user_id: ID пользователя
            info_type: Тип запрашиваемой информации
            comment: Комментарий администратора
        """
        try:
            from uk_management_bot.database.models.user import User
            
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.error(f"Пользователь {user_id} не найден для отправки уведомления")
                return
            
            # Формируем сообщение
            lang = self._get_user_lang(user)
            info_name = get_text(f"info_types.{info_type}", language=lang)

            message = (
                f"{get_text('notifications.request_additional_info_title', language=lang)}\n\n"
                f"{get_text('notifications.admin_requests_info', language=lang).replace('{info_name}', info_name)}\n\n"
                f"{get_text('notifications.comment', language=lang).replace('{comment}', comment)}\n\n"
                f"{get_text('notifications.please_provide_info', language=lang)}"
            )
            
            # Отправляем уведомление пользователю
            bot = self._get_bot()
            await bot.send_message(user.telegram_id, message)
            logger.info(f"Уведомление о запросе информации отправлено пользователю {user_id}")
                
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о запросе информации: {e}")
    
    async def send_verification_approved_notification(self, user_id: int) -> None:
        """
        Отправить уведомление об одобрении верификации
        
        Args:
            user_id: ID пользователя
        """
        try:
            from uk_management_bot.database.models.user import User
            
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.error(f"Пользователь {user_id} не найден для отправки уведомления")
                return
            
            lang = self._get_user_lang(user)
            message = (
                f"{get_text('notifications.verification_approved_title', language=lang)}\n\n"
                f"{get_text('notifications.verification_approved_body', language=lang)}"
            )
            
            # Отправляем уведомление пользователю
            bot = self._get_bot()
            await bot.send_message(user.telegram_id, message)
            logger.info(f"Уведомление об одобрении верификации отправлено пользователю {user_id}")
                
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об одобрении верификации: {e}")
    
    async def send_verification_rejected_notification(self, user_id: int) -> None:
        """
        Отправить уведомление об отклонении верификации
        
        Args:
            user_id: ID пользователя
        """
        try:
            from uk_management_bot.database.models.user import User
            
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.error(f"Пользователь {user_id} не найден для отправки уведомления")
                return
            
            lang = self._get_user_lang(user)
            message = (
                f"{get_text('notifications.verification_rejected_title', language=lang)}\n\n"
                f"{get_text('notifications.verification_rejected_body', language=lang)}"
            )
            
            # Отправляем уведомление пользователю
            bot = self._get_bot()
            await bot.send_message(user.telegram_id, message)
            logger.info(f"Уведомление об отклонении верификации отправлено пользователю {user_id}")
                
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об отклонении верификации: {e}")
    
    async def send_document_approved_notification(self, user_id: int, document_type: str) -> None:
        """
        Отправить уведомление об одобрении документа
        
        Args:
            user_id: ID пользователя
            document_type: Тип документа
        """
        try:
            from uk_management_bot.database.models.user import User
            
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.error(f"Пользователь {user_id} не найден для отправки уведомления")
                return
            
            lang = self._get_user_lang(user)
            doc_name = get_text(f"document_types.{document_type}", language=lang)

            message = (
                f"{get_text('notifications.document_approved_title', language=lang)}\n\n"
                f"{get_text('notifications.document_approved_body', language=lang).replace('{doc_name}', doc_name)}"
            )
            
            # Отправляем уведомление пользователю
            bot = self._get_bot()
            await bot.send_message(user.telegram_id, message)
            logger.info(f"Уведомление об одобрении документа отправлено пользователю {user_id}")
                
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об одобрении документа: {e}")
    
    async def send_document_rejected_notification(self, user_id: int, document_type: str, reason: str = None) -> None:
        """
        Отправить уведомление об отклонении документа
        
        Args:
            user_id: ID пользователя
            document_type: Тип документа
            reason: Причина отклонения
        """
        try:
            from uk_management_bot.database.models.user import User
            
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.error(f"Пользователь {user_id} не найден для отправки уведомления")
                return
            
            lang = self._get_user_lang(user)
            doc_name = get_text(f"document_types.{document_type}", language=lang)

            message = (
                f"{get_text('notifications.document_rejected_title', language=lang)}\n\n"
                f"{get_text('notifications.document_rejected_body', language=lang).replace('{doc_name}', doc_name)}"
            )

            if reason:
                message += f"\n\n{get_text('notifications.document_rejected_reason', language=lang).replace('{reason}', reason)}"

            message += f"\n\n{get_text('notifications.please_upload_correct', language=lang)}"
            
            # Отправляем уведомление пользователю
            bot = self._get_bot()
            await bot.send_message(user.telegram_id, message)
            logger.info(f"Уведомление об отклонении документа отправлено пользователю {user_id}")
                
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об отклонении документа: {e}")
    
    async def send_access_rights_granted_notification(self, user_id: int, access_level: str, details: str = None) -> None:
        """
        Отправить уведомление о предоставлении прав доступа
        
        Args:
            user_id: ID пользователя
            access_level: Уровень доступа
            details: Детали доступа
        """
        try:
            from uk_management_bot.database.models.user import User
            
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.error(f"Пользователь {user_id} не найден для отправки уведомления")
                return
            
            lang = self._get_user_lang(user)
            level_name = get_text(f"access_levels.{access_level}", language=lang)

            message = (
                f"{get_text('notifications.access_granted_title', language=lang)}\n\n"
                f"{get_text('notifications.access_granted_body', language=lang).replace('{level_name}', level_name)}"
            )

            if details:
                message += f"\n\n{get_text('notifications.access_details', language=lang).replace('{details}', details)}"
            
            # Отправляем уведомление пользователю
            bot = self._get_bot()
            await bot.send_message(user.telegram_id, message)
            logger.info(f"Уведомление о предоставлении прав доступа отправлено пользователю {user_id}")
                
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о предоставлении прав доступа: {e}")
    
    async def send_access_rights_revoked_notification(self, user_id: int, access_level: str, reason: str = None) -> None:
        """
        Отправить уведомление об отзыве прав доступа
        
        Args:
            user_id: ID пользователя
            access_level: Уровень доступа
            reason: Причина отзыва
        """
        try:
            from uk_management_bot.database.models.user import User
            
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.error(f"Пользователь {user_id} не найден для отправки уведомления")
                return
            
            lang = self._get_user_lang(user)
            level_name = get_text(f"access_levels.{access_level}", language=lang)

            message = (
                f"{get_text('notifications.access_revoked_title', language=lang)}\n\n"
                f"{get_text('notifications.access_revoked_body', language=lang).replace('{level_name}', level_name)}"
            )

            if reason:
                message += f"\n\n{get_text('notifications.access_revoked_reason', language=lang).replace('{reason}', reason)}"
            
            # Отправляем уведомление пользователю
            bot = self._get_bot()
            await bot.send_message(user.telegram_id, message)
            logger.info(f"Уведомление об отзыве прав доступа отправлено пользователю {user_id}")
                
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об отзыве прав доступа: {e}")

    def notify_user(self, user_id: int, title: str, message: str) -> None:
        """
        BUG-BOT-029: общий метод отправки уведомления пользователю по
        внутреннему user_id (а не telegram_id). Используется планировщиком
        `ShiftTransferService.process_expired_transfers` и связанными методами.

        Sync-сигнатура сохранена для обратной совместимости с существующими
        не-async вызывающими (см. `_notify_transfer_*`). Внутри планирует
        отправку через asyncio loop, или выполняет fallback-логирование.

        Args:
            user_id: ID пользователя в БД (`User.id`).
            title: Заголовок уведомления (рендерится первой строкой).
            message: Тело уведомления.
        """
        try:
            from uk_management_bot.database.models.user import User

            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"notify_user: пользователь user_id={user_id} не найден")
                return

            text = f"{title}\n{message}" if title else message
            bot = self._get_bot()

            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(send_to_user(bot, user.telegram_id, text))
            except RuntimeError:
                # Нет запущенного loop — выполняем синхронно через asyncio.run
                asyncio.run(send_to_user(bot, user.telegram_id, text))
        except Exception as e:
            logger.warning(f"notify_user: ошибка отправки user_id={user_id}: {e}")

    async def notify_user_async(self, user_id: int, title: str, message: str) -> bool:
        """BUG-BOT-036: async-вариант notify_user с реальным признаком доставки.

        Ожидает завершения отправки и возвращает True только если сообщение
        фактически доставлено (False — пользователь не найден или send_to_user
        вернул False). Используется планировщиком, которому нужны delivered-метрики;
        sync `notify_user` остаётся для fire-and-forget вызовов.
        """
        from uk_management_bot.database.models.user import User

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.warning(f"notify_user_async: пользователь user_id={user_id} не найден")
            return False

        text = f"{title}\n{message}" if title else message
        bot = self._get_bot()
        return await send_to_user(bot, user.telegram_id, text)

    async def send_system_notification(self, title: str, message: str) -> None:
        """
        Отправить системное уведомление в канал

        Args:
            title: Заголовок уведомления
            message: Текст сообщения
        """
        try:
            bot = self._get_bot()
            system_message = f"{title}\n{message}"
            await send_to_channel(bot, system_message)
            logger.info(f"Системное уведомление отправлено: {title}")
        except Exception as e:
            logger.warning(f"Ошибка отправки системного уведомления: {e}")


# ====== Request status notifications (3.4) ======
def _build_request_status_message_user(request: Request, old_status: str, new_status: str) -> str:
    return (
        f"📌 Статус вашей заявки #{request.request_number} изменён: {old_status} → {new_status}\n"
        f"Категория: {request.category}\n"
        f"Адрес: {request.address[:60]}{'…' if len(request.address) > 60 else ''}"
    )


def _build_request_status_message_executor(request: Request, old_status: str, new_status: str) -> str:
    return (
        f"📌 Статус заявки #{request.request_number} изменён: {old_status} → {new_status}\n"
        f"Категория: {request.category} — назначена вам"
    )


def _build_request_status_message_channel(request: Request, old_status: str, new_status: str) -> str:
    return (
        f"🔔 Заявка #{request.request_number}: {old_status} → {new_status}\n"
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
            from uk_management_bot.database.models.user import User as UserModel
            applicant = db.query(UserModel).filter(UserModel.id == request.user_id).first()
            if applicant and applicant.telegram_id:
                await send_to_user(
                    bot,
                    applicant.telegram_id,
                    _build_request_status_message_user(request, old_status, new_status),
                )
        except Exception as e:
            logger.warning(f"Не удалось уведомить заявителя по заявке #{request.request_number}: {e}")

        # Исполнитель (если назначен)
        try:
            if request.executor_id:
                from uk_management_bot.database.models.user import User as UserModel
                executor = db.query(UserModel).filter(UserModel.id == request.executor_id).first()
                if executor and executor.telegram_id:
                    await send_to_user(
                        bot,
                        executor.telegram_id,
                        _build_request_status_message_executor(request, old_status, new_status),
                    )
        except Exception as e:
            logger.warning(f"Не удалось уведомить исполнителя по заявке #{request.request_number}: {e}")

        # Канал (если настроен)
        await send_to_channel(bot, _build_request_status_message_channel(request, old_status, new_status))
    except Exception as e:
        logger.warning(f"Ошибка async уведомления о смене статуса заявки #{request.request_number}: {e}")


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


# ====== Feedback (обратная связь) уведомления ======
async def deliver_feedback_to_managers(bot, *, telegram_ids, text: str, photo=None):
    """Рассылает обращение менеджерам (DM) + в канал (если настроен).

    photo: ``str`` — готовый telegram file_id (шлём как есть); ``bytes`` — новые
    байты (первая отправка через BufferedInputFile, дальше переиспользуем
    полученный file_id); ``None`` — текстовое сообщение.

    Текст ДОЛЖЕН быть уже экранирован вызывающим (parse_mode=HTML). Возвращает
    captured telegram file_id первого успешно отправленного фото (для durable-
    ссылки) или None. Best-effort: ошибки отправки конкретному чату логируются,
    но не прерывают рассылку.
    """
    captured = None
    targets = list(telegram_ids)
    channel_id = _resolve_channel_id()
    if channel_id:
        targets.append(channel_id)

    for chat_id in targets:
        try:
            if photo is None:
                await bot.send_message(chat_id, text, parse_mode="HTML")
            else:
                if isinstance(photo, (bytes, bytearray)):
                    from aiogram.types import BufferedInputFile
                    media = BufferedInputFile(bytes(photo), filename="feedback.jpg")
                else:
                    media = photo  # уже telegram file_id (str)
                msg = await bot.send_photo(chat_id, media, caption=text, parse_mode="HTML")
                fid = msg.photo[-1].file_id if getattr(msg, "photo", None) else None
                captured = captured or fid
                # После первой загрузки байтов переключаемся на file_id, чтобы
                # не грузить одни и те же байты в Telegram повторно.
                if isinstance(photo, (bytes, bytearray)) and fid:
                    photo = fid
        except Exception as e:
            logger.warning(f"Не удалось отправить обращение менеджеру {chat_id}: {e}")
    return captured


async def send_feedback_reply_to_user(bot, *, telegram_id: int, reply_text: str, lang: str = "ru") -> None:
    """Отправляет пользователю ответ менеджера на обращение (best-effort)."""
    try:
        import html
        body = get_text("feedback.reply_to_user", language=lang, reply=html.escape(reply_text))
        await bot.send_message(telegram_id, body, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Не удалось отправить ответ на обращение пользователю {telegram_id}: {e}")

