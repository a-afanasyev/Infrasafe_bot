from sqlalchemy.orm import Session
from uk_management_bot.database.models.user import User
import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.telegram_client import SEND_TIMEOUT
# ARCH-116: показ времени смен — только через канон бизнес-зоны.
from uk_management_bot.utils.business_time import fmt_datetime

from uk_management_bot.services.notification_service.channel import (
    _resolve_channel_id,
    send_to_channel,
    send_to_user,
)
from uk_management_bot.services.notification_service.shared_bot import (
    _get_shared_bot,
)

logger = logging.getLogger(__name__)


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
    
    def collect_verification_request_message(self, user_id: int, info_type: str, comment: str):
        """Fetch-фаза уведомления о запросе информации (AUD3-07, B3-канон
        collect/send): sync SQL + текст, БЕЗ сети. → (telegram_id, text) | None."""
        from uk_management_bot.database.models.user import User

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"Пользователь {user_id} не найден для отправки уведомления")
            return None

        # Формируем сообщение
        lang = self._get_user_lang(user)
        info_name = get_text(f"info_types.{info_type}", language=lang)

        message = (
            f"{get_text('notifications.request_additional_info_title', language=lang)}\n\n"
            f"{get_text('notifications.admin_requests_info', language=lang).replace('{info_name}', info_name)}\n\n"
            f"{get_text('notifications.comment', language=lang).replace('{comment}', comment)}\n\n"
            f"{get_text('notifications.please_provide_info', language=lang)}"
        )
        return user.telegram_id, message

    async def send_verification_request_notification(self, user_id: int, info_type: str, comment: str) -> None:
        """
        Отправить уведомление о запросе дополнительной информации
        
        Args:
            user_id: ID пользователя
            info_type: Тип запрашиваемой информации
            comment: Комментарий администратора
        """
        try:
            pair = self.collect_verification_request_message(user_id, info_type, comment)
            if pair is None:
                return
            telegram_id, message = pair

            # Отправляем уведомление пользователю
            bot = self._get_bot()
            await bot.send_message(telegram_id, message, request_timeout=SEND_TIMEOUT)
            logger.info(f"Уведомление о запросе информации отправлено пользователю {user_id}")
                
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о запросе информации: {e}")
    
    def collect_verification_approved_message(self, user_id: int):
        """Fetch-фаза уведомления (approved) — sync SQL + текст, без сети.
        → (telegram_id, text) | None."""
        from uk_management_bot.database.models.user import User

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"Пользователь {user_id} не найден для отправки уведомления")
            return None

        lang = self._get_user_lang(user)
        message = (
            f"{get_text('notifications.verification_approved_title', language=lang)}\n\n"
            f"{get_text('notifications.verification_approved_body', language=lang)}"
        )
        return user.telegram_id, message

    async def send_verification_approved_notification(self, user_id: int) -> None:
        """
        Отправить уведомление об одобрении верификации
        
        Args:
            user_id: ID пользователя
        """
        try:
            pair = self.collect_verification_approved_message(user_id)
            if pair is None:
                return
            telegram_id, message = pair

            # Отправляем уведомление пользователю
            bot = self._get_bot()
            await bot.send_message(telegram_id, message, request_timeout=SEND_TIMEOUT)
            logger.info(f"Уведомление об одобрении верификации отправлено пользователю {user_id}")
                
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об одобрении верификации: {e}")
    
    def collect_verification_rejected_message(self, user_id: int):
        """Fetch-фаза уведомления (rejected) — sync SQL + текст, без сети.
        → (telegram_id, text) | None."""
        from uk_management_bot.database.models.user import User

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"Пользователь {user_id} не найден для отправки уведомления")
            return None

        lang = self._get_user_lang(user)
        message = (
            f"{get_text('notifications.verification_rejected_title', language=lang)}\n\n"
            f"{get_text('notifications.verification_rejected_body', language=lang)}"
        )
        return user.telegram_id, message

    async def send_verification_rejected_notification(self, user_id: int) -> None:
        """
        Отправить уведомление об отклонении верификации
        
        Args:
            user_id: ID пользователя
        """
        try:
            pair = self.collect_verification_rejected_message(user_id)
            if pair is None:
                return
            telegram_id, message = pair

            # Отправляем уведомление пользователю
            bot = self._get_bot()
            await bot.send_message(telegram_id, message, request_timeout=SEND_TIMEOUT)
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
            await bot.send_message(user.telegram_id, message, request_timeout=SEND_TIMEOUT)
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
            await bot.send_message(user.telegram_id, message, request_timeout=SEND_TIMEOUT)
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
            await bot.send_message(user.telegram_id, message, request_timeout=SEND_TIMEOUT)
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
            await bot.send_message(user.telegram_id, message, request_timeout=SEND_TIMEOUT)
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
            except RuntimeError:
                # COD-03: нет running loop — НЕ крутим asyncio.run на шаренном боте
                # (aiohttp-сессия привязана к loop полла → «Event loop is closed»).
                # Все sync-вызыватели живут внутри async-флоу, так что в проде сюда
                # не попадаем; лог фиксирует нештатный (скрипт/тест) путь.
                logger.warning(
                    f"notify_user: нет running loop — уведомление user_id={user_id} пропущено"
                )
                return

            # Fire-and-forget на живом loop, но с done-callback: конец тихого
            # проглатывания — ошибки/недоставка/отмена отправки логируются.
            task = loop.create_task(send_to_user(bot, user.telegram_id, text))

            def _log_send_result(t: "asyncio.Task") -> None:
                try:
                    if t.cancelled():
                        logger.warning(f"notify_user: отправка отменена user_id={user_id}")
                        return
                    exc = t.exception()
                    if exc is not None:
                        logger.warning(f"notify_user: ошибка отправки user_id={user_id}: {exc!r}")
                    elif t.result() is False:
                        logger.warning(f"notify_user: не доставлено user_id={user_id}")
                except Exception as cb_e:
                    logger.warning(f"notify_user: done-callback error user_id={user_id}: {cb_e}")

            task.add_done_callback(_log_send_result)
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

    async def send_manager_notification(self, title: str, message: str) -> None:
        """Уведомление менеджерам: DM каждому approved-менеджеру + ops-канал.

        Аудитория берётся из канонического ``manager_telegram_ids_sync`` (approved,
        не soft-deleted, роль manager) — единый источник с feedback-рассылкой.
        Best-effort: сбой отдельного получателя логируется, не бросается.
        Ранее метод не существовал → вызовы планировщика молча падали (COD).
        """
        # Локальный импорт: избегаем циклического импорта на загрузке модуля.
        from uk_management_bot.services.feedback_service import manager_telegram_ids_sync

        bot = self._get_bot()
        text = f"{title}\n{message}" if title else message
        try:
            tg_ids = manager_telegram_ids_sync(self.db)
        except Exception as e:
            logger.error(f"send_manager_notification: ошибка выборки менеджеров: {e}")
            tg_ids = []

        sent = 0
        for tg_id in tg_ids:
            if await send_to_user(bot, tg_id, text):
                sent += 1
            else:
                logger.warning(f"send_manager_notification: не доставлено tg={tg_id}")

        await send_to_channel(bot, text)  # ops-канал (гейт _resolve_channel_id)
        logger.info(
            f"send_manager_notification: доставлено {sent}/{len(tg_ids)} менеджерам; "
            f"канал={'on' if _resolve_channel_id() else 'off'}"
        )

    async def send_shift_reminder(self, executor_id: int, shift, time_until: str) -> None:
        """Напоминание исполнителю о предстоящей смене (только DM, локализованно).

        ``executor_id`` — внутренний ``User.id`` (= ``shift.user_id``), резолвится
        по ``self.db``. Ранее метод не существовал → вызовы планировщика молча
        падали (COD).
        """
        user = self.db.query(User).filter(User.id == executor_id).first()
        if not user or not user.telegram_id:
            logger.warning(
                f"send_shift_reminder: исполнитель user_id={executor_id} не найден / без telegram_id"
            )
            return

        lang = self._get_user_lang(user)
        started = fmt_datetime(shift.start_time) if getattr(shift, "start_time", None) else ""
        title = get_text('notifications.shift_reminder_title', language=lang)
        body = get_text(
            'notifications.shift_reminder_body',
            language=lang,
            time_until=time_until,
            started=started,
        )
        if not await send_to_user(self._get_bot(), user.telegram_id, f"{title}\n{body}"):
            logger.warning(f"send_shift_reminder: не доставлено user_id={executor_id}")

