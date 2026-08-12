import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.telegram_client import (
    SEND_TIMEOUT,
    UPLOAD_TIMEOUT,
)

from uk_management_bot.services.notification_service.channel import (
    _resolve_channel_id,
)

logger = logging.getLogger(__name__)


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
                await bot.send_message(
                    chat_id, text, parse_mode="HTML", request_timeout=SEND_TIMEOUT
                )
            else:
                if isinstance(photo, (bytes, bytearray)):
                    from aiogram.types import BufferedInputFile
                    media = BufferedInputFile(bytes(photo), filename="feedback.jpg")
                else:
                    media = photo  # уже telegram file_id (str)
                # Загрузка байтов легитимно дольше текста — свой профиль.
                msg = await bot.send_photo(
                    chat_id,
                    media,
                    caption=text,
                    parse_mode="HTML",
                    request_timeout=UPLOAD_TIMEOUT,
                )
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
        await bot.send_message(
            telegram_id, body, parse_mode="HTML", request_timeout=SEND_TIMEOUT
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить ответ на обращение пользователю {telegram_id}: {e}")

