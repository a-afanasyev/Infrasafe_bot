"""
Вспомогательные функции для интеграции Media Service с основным ботом
"""

import logging
from typing import Optional, List, Dict, Any
from io import BytesIO
from aiogram.types import Message, PhotoSize, Video, Document
from aiogram import Bot

from .media_client import MediaServiceClient

logger = logging.getLogger(__name__)


class BotMediaIntegration:
    """
    Класс для интеграции Media Service с Telegram ботом
    """

    def __init__(self, media_client: MediaServiceClient, bot: Bot):
        self.media_client = media_client
        self.bot = bot

    async def handle_request_photo(
        self,
        message: Message,
        request_number: str,
        user_id: int,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Обработка фото для заявки из сообщения Telegram

        Args:
            message: Сообщение с фото
            request_number: Номер заявки
            user_id: ID пользователя
            description: Описание фото
            tags: Теги

        Returns:
            Информация о загруженном файле или None
        """
        try:
            if not message.photo:
                logger.warning("Message has no photo")
                return None

            # Берем фото наибольшего размера
            photo: PhotoSize = message.photo[-1]

            # Скачиваем файл
            file_info = await self.bot.get_file(photo.file_id)
            file_data = await self.bot.download_file(file_info.file_path)

            # Создаем BytesIO объект
            file_obj = BytesIO(file_data.read())
            file_obj.name = f"photo_{request_number}_{photo.file_unique_id}.jpg"

            # Загружаем в Media Service
            result = await self.media_client.upload_request_media(
                request_number=request_number,
                file_path=file_obj,
                filename=file_obj.name,
                category="request_photo",
                description=description,
                tags=tags,
                uploaded_by=user_id
            )

            logger.info(f"Request photo uploaded for {request_number}: {result['media_file']['id']}")
            return result

        except Exception as e:
            logger.error(f"Failed to handle request photo: {e}")
            return None

    async def handle_completion_photo(
        self,
        message: Message,
        request_number: str,
        user_id: int,
        description: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Обработка фото завершения работы

        Args:
            message: Сообщение с фото
            request_number: Номер заявки
            user_id: ID пользователя
            description: Описание

        Returns:
            Информация о загруженном файле
        """
        try:
            if not message.photo:
                return None

            photo = message.photo[-1]
            file_info = await self.bot.get_file(photo.file_id)
            file_data = await self.bot.download_file(file_info.file_path)

            file_obj = BytesIO(file_data.read())
            file_obj.name = f"completion_{request_number}_{photo.file_unique_id}.jpg"

            result = await self.media_client.upload_report_media(
                request_number=request_number,
                file_path=file_obj,
                filename=file_obj.name,
                report_type="completion_photo",
                description=description,
                uploaded_by=user_id
            )

            logger.info(f"Completion photo uploaded for {request_number}: {result['media_file']['id']}")
            return result

        except Exception as e:
            logger.error(f"Failed to handle completion photo: {e}")
            return None

    async def handle_video(
        self,
        message: Message,
        request_number: str,
        user_id: int,
        category: str = "process_video",
        description: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Обработка видео из сообщения

        Args:
            message: Сообщение с видео
            request_number: Номер заявки
            user_id: ID пользователя
            category: Категория видео
            description: Описание

        Returns:
            Информация о загруженном видео
        """
        try:
            video: Video = message.video
            if not video:
                return None

            file_info = await self.bot.get_file(video.file_id)
            file_data = await self.bot.download_file(file_info.file_path)

            file_obj = BytesIO(file_data.read())
            file_obj.name = f"video_{request_number}_{video.file_unique_id}.mp4"

            result = await self.media_client.upload_request_media(
                request_number=request_number,
                file_path=file_obj,
                filename=file_obj.name,
                category=category,
                description=description,
                uploaded_by=user_id
            )

            logger.info(f"Video uploaded for {request_number}: {result['media_file']['id']}")
            return result

        except Exception as e:
            logger.error(f"Failed to handle video: {e}")
            return None

    async def handle_document(
        self,
        message: Message,
        request_number: str,
        user_id: int,
        description: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Обработка документа из сообщения

        Args:
            message: Сообщение с документом
            request_number: Номер заявки
            user_id: ID пользователя
            description: Описание

        Returns:
            Информация о загруженном документе
        """
        try:
            document: Document = message.document
            if not document:
                return None

            file_info = await self.bot.get_file(document.file_id)
            file_data = await self.bot.download_file(file_info.file_path)

            file_obj = BytesIO(file_data.read())
            file_obj.name = document.file_name or f"document_{request_number}_{document.file_unique_id}"

            result = await self.media_client.upload_request_media(
                request_number=request_number,
                file_path=file_obj,
                filename=file_obj.name,
                category="document",
                description=description,
                uploaded_by=user_id
            )

            logger.info(f"Document uploaded for {request_number}: {result['media_file']['id']}")
            return result

        except Exception as e:
            logger.error(f"Failed to handle document: {e}")
            return None

    async def get_request_media_gallery(
        self,
        request_number: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Получение галереи медиа для заявки (для отображения в боте)

        Args:
            request_number: Номер заявки
            limit: Лимит файлов

        Returns:
            Список медиа-файлов с URL для отображения
        """
        try:
            media_files = await self.media_client.get_request_media(
                request_number=request_number,
                limit=limit
            )

            # Получаем URL для каждого файла
            gallery = []
            for media_file in media_files:
                file_url = await self.media_client.get_media_url(media_file["id"])
                gallery.append({
                    "id": media_file["id"],
                    "file_type": media_file["file_type"],
                    "category": media_file["category"],
                    "description": media_file["description"],
                    "uploaded_at": media_file["uploaded_at"],
                    "file_url": file_url,
                    "telegram_file_id": media_file["telegram_file_id"]
                })

            return gallery

        except Exception as e:
            logger.error(f"Failed to get media gallery for {request_number}: {e}")
            return []

    async def create_media_summary(self, request_number: str) -> Dict[str, Any]:
        """
        Создание сводки по медиа-файлам заявки

        Args:
            request_number: Номер заявки

        Returns:
            Сводка с количеством файлов по типам
        """
        try:
            media_files = await self.media_client.get_request_media(request_number)

            summary = {
                "total_files": len(media_files),
                "photos": 0,
                "videos": 0,
                "documents": 0,
                "categories": {},
                "latest_upload": None,
                "total_size_mb": 0
            }

            for media_file in media_files:
                # Подсчет по типам
                if media_file["file_type"] == "photo":
                    summary["photos"] += 1
                elif media_file["file_type"] == "video":
                    summary["videos"] += 1
                elif media_file["file_type"] == "document":
                    summary["documents"] += 1

                # Подсчет по категориям
                category = media_file["category"]
                summary["categories"][category] = summary["categories"].get(category, 0) + 1

                # Размер файлов
                summary["total_size_mb"] += media_file["file_size"] / (1024 * 1024)

                # Последняя загрузка
                uploaded_at = media_file["uploaded_at"]
                if not summary["latest_upload"] or uploaded_at > summary["latest_upload"]:
                    summary["latest_upload"] = uploaded_at

            # Округляем размер
            summary["total_size_mb"] = round(summary["total_size_mb"], 2)

            return summary

        except Exception as e:
            logger.error(f"Failed to create media summary for {request_number}: {e}")
            return {
                "total_files": 0,
                "photos": 0,
                "videos": 0,
                "documents": 0,
                "categories": {},
                "latest_upload": None,
                "total_size_mb": 0
            }


async def process_media_message(
    message: Message,
    request_number: str,
    user_id: int,
    media_client: MediaServiceClient,
    bot: Bot,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Универсальная функция обработки медиа-сообщений

    Args:
        message: Сообщение от пользователя
        request_number: Номер заявки
        user_id: ID пользователя
        media_client: Клиент Media Service
        bot: Экземпляр бота
        description: Описание
        tags: Теги

    Returns:
        Результат загрузки или None
    """
    integration = BotMediaIntegration(media_client, bot)

    if message.photo:
        return await integration.handle_request_photo(
            message, request_number, user_id, description, tags
        )
    elif message.video:
        return await integration.handle_video(
            message, request_number, user_id, "process_video", description
        )
    elif message.document:
        return await integration.handle_document(
            message, request_number, user_id, description
        )

    return None


def format_media_summary_text(summary: Dict[str, Any]) -> str:
    """
    Форматирование сводки медиа-файлов для отображения в боте

    Args:
        summary: Сводка медиа-файлов

    Returns:
        Отформатированный текст
    """
    if summary["total_files"] == 0:
        return "📁 Медиа-файлы отсутствуют"

    text = f"📁 Медиа-файлы ({summary['total_files']} шт.):\n"

    if summary["photos"] > 0:
        text += f"📸 Фото: {summary['photos']}\n"

    if summary["videos"] > 0:
        text += f"🎥 Видео: {summary['videos']}\n"

    if summary["documents"] > 0:
        text += f"📄 Документы: {summary['documents']}\n"

    if summary["total_size_mb"] > 0:
        text += f"💾 Размер: {summary['total_size_mb']} МБ\n"

    if summary["latest_upload"]:
        text += f"🕒 Последняя загрузка: {summary['latest_upload'][:16]}\n"

    return text