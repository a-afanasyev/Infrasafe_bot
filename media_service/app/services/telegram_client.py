"""
Telegram клиент для работы с каналами
"""

import logging
from typing import Optional, Union, Tuple
import httpx
from aiogram import Bot
from aiogram.types import InputFile, BufferedInputFile, Message
from aiogram.exceptions import TelegramAPIError

from app.core.config import settings

logger = logging.getLogger(__name__)


class TelegramClientService:
    """Сервис для работы с Telegram API"""

    def __init__(self):
        self.bot = Bot(token=settings.telegram_bot_token)

    async def send_photo(
        self,
        chat_id: Union[int, str],
        photo: Union[InputFile, BufferedInputFile, str],
        caption: Optional[str] = None,
        parse_mode: Optional[str] = "HTML"
    ) -> Optional[Message]:
        """
        Отправка фото в канал
        """
        try:
            message = await self.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode=parse_mode
            )
            logger.info(f"Photo sent to {chat_id}, message_id: {message.message_id}")
            return message

        except TelegramAPIError as e:
            logger.error(f"Failed to send photo to {chat_id}: {e}")
            raise

    async def send_video(
        self,
        chat_id: Union[int, str],
        video: Union[InputFile, BufferedInputFile, str],
        caption: Optional[str] = None,
        parse_mode: Optional[str] = "HTML"
    ) -> Optional[Message]:
        """
        Отправка видео в канал
        """
        try:
            message = await self.bot.send_video(
                chat_id=chat_id,
                video=video,
                caption=caption,
                parse_mode=parse_mode
            )
            logger.info(f"Video sent to {chat_id}, message_id: {message.message_id}")
            return message

        except TelegramAPIError as e:
            logger.error(f"Failed to send video to {chat_id}: {e}")
            raise

    async def send_document(
        self,
        chat_id: Union[int, str],
        document: Union[InputFile, BufferedInputFile, str],
        caption: Optional[str] = None,
        parse_mode: Optional[str] = "HTML"
    ) -> Optional[Message]:
        """
        Отправка документа в канал
        """
        try:
            message = await self.bot.send_document(
                chat_id=chat_id,
                document=document,
                caption=caption,
                parse_mode=parse_mode
            )
            logger.info(f"Document sent to {chat_id}, message_id: {message.message_id}")
            return message

        except TelegramAPIError as e:
            logger.error(f"Failed to send document to {chat_id}: {e}")
            raise

    async def edit_message_caption(
        self,
        chat_id: Union[int, str],
        message_id: int,
        caption: str,
        parse_mode: Optional[str] = "HTML"
    ) -> bool:
        """
        Редактирование подписи сообщения
        """
        try:
            await self.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=caption,
                parse_mode=parse_mode
            )
            logger.info(f"Caption updated for message {message_id} in {chat_id}")
            return True

        except TelegramAPIError as e:
            logger.error(f"Failed to edit caption for message {message_id} in {chat_id}: {e}")
            return False

    async def get_file(self, file_id: str):
        """
        Получение информации о файле
        """
        try:
            file_info = await self.bot.get_file(file_id)
            return file_info

        except TelegramAPIError as e:
            logger.error(f"Failed to get file info for {file_id}: {e}")
            raise

    async def get_file_url(self, file_id: str) -> Optional[str]:
        """
        Получение URL файла
        """
        try:
            file_info = await self.get_file(file_id)
            file_url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_info.file_path}"
            return file_url

        except Exception as e:
            logger.error(f"Failed to get file URL for {file_id}: {e}")
            return None

    async def download_file(self, file_id: str) -> Tuple[bytes, str]:
        """
        Download file bytes from Telegram by file_id.
        Returns (file_bytes, content_type).
        Token stays server-side — never exposed to clients.
        """
        file_info = await self.get_file(file_id)
        url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_info.file_path}"

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "application/octet-stream")
        return resp.content, content_type

    async def delete_message(
        self,
        chat_id: Union[int, str],
        message_id: int
    ) -> bool:
        """
        Удаление сообщения
        """
        try:
            await self.bot.delete_message(
                chat_id=chat_id,
                message_id=message_id
            )
            logger.info(f"Message {message_id} deleted from {chat_id}")
            return True

        except TelegramAPIError as e:
            logger.error(f"Failed to delete message {message_id} from {chat_id}: {e}")
            return False

    async def get_chat(self, chat_id: Union[int, str]):
        """
        Получение информации о чате/канале
        """
        try:
            chat = await self.bot.get_chat(chat_id)
            return chat

        except TelegramAPIError as e:
            logger.error(f"Failed to get chat info for {chat_id}: {e}")
            raise

    async def close(self):
        """
        Закрытие соединения

        ARC-01: закрывать явно (`await close()` / async-context), НЕ из `__del__` —
        деструктор с `create_task(self.close())` на deprecated `get_event_loop()`
        мог оставить aiohttp-сессию незакрытой (утечка соединения) без сигнала.
        """
        await self.bot.session.close()