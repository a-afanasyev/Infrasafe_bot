"""
Telegram клиент для работы с каналами
"""

import asyncio
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
        # Семафор на весь путь скачивания (get_file + GET файла): без него одна
        # загрузка публичной витрины давала десятки одновременных обращений к
        # Telegram, а очередь из них выедала воркеры и пул соединений
        # (инцидент 2026-07-25, см. app/services/preview_cache.py).
        from app.services.preview_cache import download_semaphore

        async with download_semaphore():
            # AUD6-P2-03: ретрай с backoff — сетевые сбои Telegram транзиентны,
            # а ретраев внутри media раньше не было вовсе (они жили только на
            # стороне потребителя, и не на всех путях). Клиентские 4xx (файл
            # удалён/недоступен) не ретраятся — повтор их не лечит.
            last_exc: Optional[Exception] = None
            for attempt, delay in enumerate((0.0, 0.5, 1.5), start=1):
                if delay:
                    await asyncio.sleep(delay)
                try:
                    file_info = await self.get_file(file_id)
                    url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_info.file_path}"

                    async with httpx.AsyncClient(timeout=60) as client:
                        resp = await client.get(url)
                        resp.raise_for_status()

                    content_type = resp.headers.get("content-type", "application/octet-stream")
                    return resp.content, content_type
                except httpx.HTTPStatusError as e:
                    if e.response is not None and 400 <= e.response.status_code < 500:
                        raise
                    last_exc = e
                    logger.warning("download_file %s: попытка %d не удалась: %s",
                                   file_id, attempt, e)
                except (httpx.HTTPError, TelegramAPIError) as e:
                    last_exc = e
                    logger.warning("download_file %s: попытка %d не удалась: %s",
                                   file_id, attempt, e)
            assert last_exc is not None
            raise last_exc

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