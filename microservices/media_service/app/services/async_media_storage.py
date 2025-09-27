"""
Async Media Storage Service - Full async implementation
Основной сервис для работы с медиа-хранилищем в Telegram каналах
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Union, Dict, Any, BinaryIO
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, update, delete as delete_stmt
from aiogram.types import InputFile, BufferedInputFile, Message

from app.models.media import MediaFile, MediaChannel, MediaTag, MediaUploadSession
from app.services.telegram_client import TelegramClientService
from app.core.config import settings, FileCategories, TelegramChannels, ErrorMessages
from app.db.async_database import get_async_db_context

logger = logging.getLogger(__name__)


class AsyncMediaStorageService:
    """Async version of Media Storage Service"""

    def __init__(self):
        self.telegram = TelegramClientService()
        self.channels_cache = {}

    async def upload_request_media(
        self,
        request_number: str,
        file_data: bytes,
        filename: str,
        content_type: str,
        category: str = FileCategories.REQUEST_PHOTO,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        uploaded_by: int = None
    ) -> MediaFile:
        """
        Загружает медиа-файл для заявки в соответствующий канал
        """
        logger.info(f"Uploading request media for {request_number}, category: {category}")

        # Валидация
        await self._validate_file(file_data, content_type)

        async with get_async_db_context() as db:
            try:
                # 1. Определяем канал для загрузки
                channel = await self._get_channel_for_category(db, category)

                # 2. Подготавливаем файл
                file_obj = BufferedInputFile(file_data, filename=filename)

                # 3. Загружаем в Telegram канал
                message = await self.telegram.send_media_to_channel(
                    channel.channel_id,
                    file_obj,
                    caption=await self._build_media_caption(
                        request_number, description, tags, category
                    )
                )

                # 4. Создаем запись в БД
                media_file = MediaFile(
                    request_number=request_number,
                    filename=filename,
                    file_size=len(file_data),
                    content_type=content_type,
                    category=category,
                    description=description,
                    tags=tags or [],
                    telegram_message_id=message.message_id,
                    telegram_channel_id=channel.channel_id,
                    uploaded_by=uploaded_by,
                    status="active"
                )

                db.add(media_file)
                await db.flush()
                await db.refresh(media_file)

                # 5. Обновляем статистику тегов
                if tags:
                    await self._update_tags_usage(db, tags)

                logger.info(f"Successfully uploaded media file {media_file.id} for request {request_number}")
                return media_file

            except Exception as e:
                logger.error(f"Failed to upload media for request {request_number}: {e}")
                raise

    async def get_request_media(
        self,
        request_number: str,
        category: Optional[str] = None,
        limit: int = 50
    ) -> List[MediaFile]:
        """
        Получает все медиа-файлы для заявки
        """
        async with get_async_db_context() as db:
            query = select(MediaFile).where(
                MediaFile.request_number == request_number,
                MediaFile.status == "active"
            )

            if category:
                query = query.where(MediaFile.category == category)

            query = query.order_by(MediaFile.uploaded_at.desc()).limit(limit)
            result = await db.execute(query)
            media_files = result.scalars().all()
            logger.info(f"Found {len(media_files)} media files for request {request_number}")
            return media_files

    async def get_media_by_tags(
        self,
        tags: List[str],
        match_all: bool = False,
        limit: int = 100
    ) -> List[MediaFile]:
        """
        Поиск медиа-файлов по тегам
        """
        async with get_async_db_context() as db:
            if match_all:
                # Все теги должны присутствовать
                query = select(MediaFile).where(
                    MediaFile.status == "active"
                )
                for tag in tags:
                    query = query.where(MediaFile.tags.contains([tag]))
            else:
                # Любой из тегов
                query = select(MediaFile).where(
                    and_(
                        MediaFile.status == "active",
                        or_(*[MediaFile.tags.contains([tag]) for tag in tags])
                    )
                )

            query = query.order_by(MediaFile.uploaded_at.desc()).limit(limit)
            result = await db.execute(query)
            return result.scalars().all()

    async def update_media_tags(
        self,
        media_file_id: int,
        tags: List[str],
        replace: bool = False
    ) -> Optional[MediaFile]:
        """
        Обновляет теги медиа-файла
        """
        async with get_async_db_context() as db:
            result = await db.execute(select(MediaFile).where(MediaFile.id == media_file_id))
            media_file = result.scalar_one_or_none()

            if not media_file:
                logger.warning(f"Media file {media_file_id} not found")
                return None

            if replace:
                media_file.tags = tags
            else:
                # Объединяем существующие и новые теги
                existing_tags = set(media_file.tags or [])
                new_tags = existing_tags.union(set(tags))
                media_file.tags = list(new_tags)

            # Обновляем подпись в Telegram канале
            await self._update_channel_caption(media_file)

            # Обновляем статистику тегов
            await self._update_tags_usage(db, tags)

            logger.info(f"Updated tags for media file {media_file_id}")
            return media_file

    async def archive_media(
        self,
        media_file_id: int,
        archive_reason: Optional[str] = None
    ) -> bool:
        """
        Архивирует медиа-файл (перемещает в архивный канал)
        """
        async with get_async_db_context() as db:
            result = await db.execute(select(MediaFile).where(MediaFile.id == media_file_id))
            media_file = result.scalar_one_or_none()

            if not media_file:
                logger.warning(f"Media file {media_file_id} not found")
                return False

            try:
                # 1. Копируем в архивный канал
                archive_channel = await self._get_channel_for_category(db, FileCategories.ARCHIVE)
                await self._copy_to_archive(media_file, archive_channel, archive_reason)

                # 2. Обновляем статус
                media_file.status = "archived"
                media_file.archived_at = datetime.now(timezone.utc)

                logger.info(f"Media file {media_file_id} archived successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to archive media file {media_file_id}: {e}")
                return False

    async def delete_media(self, media_file_id: int) -> bool:
        """
        Удаляет медиа-файл
        """
        async with get_async_db_context() as db:
            result = await db.execute(select(MediaFile).where(MediaFile.id == media_file_id))
            media_file = result.scalar_one_or_none()

            if not media_file:
                logger.warning(f"Media file {media_file_id} not found")
                return False

            try:
                # 1. Удаляем из Telegram канала
                await self.telegram.delete_channel_message(
                    media_file.telegram_channel_id,
                    media_file.telegram_message_id
                )

                # 2. Удаляем из БД
                await db.execute(delete_stmt(MediaFile).where(MediaFile.id == media_file_id))

                logger.info(f"Media file {media_file_id} deleted successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to delete media file {media_file_id}: {e}")
                return False

    async def _get_channel_for_category(self, db: AsyncSession, category: str) -> MediaChannel:
        """
        Получает канал для определенной категории файлов
        """
        # Mapping category to channel purpose
        category_to_purpose = {
            FileCategories.REQUEST_PHOTO: TelegramChannels.REQUESTS,
            FileCategories.REPORT_PHOTO: TelegramChannels.REPORTS,
            FileCategories.ARCHIVE: TelegramChannels.ARCHIVE,
        }

        purpose = category_to_purpose.get(category, TelegramChannels.REQUESTS)

        # Проверяем кэш
        if purpose in self.channels_cache:
            return self.channels_cache[purpose]

        # Запрашиваем из БД
        result = await db.execute(
            select(MediaChannel).where(
                MediaChannel.purpose == purpose,
                MediaChannel.is_active == True
            )
        )
        channel = result.scalar_one_or_none()

        if not channel:
            raise ValueError(f"No active channel found for purpose: {purpose}")

        # Проверяем channel_id и получаем его при необходимости
        if not channel.channel_id:
            async with get_async_db_context() as db_inner:
                result_inner = await db_inner.execute(
                    select(MediaChannel).where(MediaChannel.id == channel.id)
                )
                db_channel = result_inner.scalar_one_or_none()
                if db_channel:
                    channel_id = await self.telegram.resolve_channel_id(channel.channel_username)
                    db_channel.channel_id = channel_id
                    await db_inner.commit()
                    channel.channel_id = channel_id

        # Кэшируем
        self.channels_cache[purpose] = channel
        return channel

    async def _validate_file(self, file_data: bytes, content_type: str):
        """
        Валидация загружаемого файла
        """
        # Проверка размера
        if len(file_data) > settings.max_file_size:
            raise ValueError(f"File size exceeds limit: {len(file_data)} > {settings.max_file_size}")

        # Проверка типа файла
        if content_type not in settings.allowed_file_types:
            raise ValueError(f"File type not allowed: {content_type}")

    async def _build_media_caption(
        self,
        request_number: str,
        description: Optional[str],
        tags: Optional[List[str]],
        category: str
    ) -> str:
        """
        Строит подпись для медиа-файла в Telegram
        """
        caption = f"📋 Заявка: {request_number}\n"
        caption += f"📂 Категория: {category}\n"

        if description:
            caption += f"📝 Описание: {description}\n"

        if tags:
            tags_str = " ".join([f"#{tag}" for tag in tags])
            caption += f"🏷 Теги: {tags_str}\n"

        caption += f"📅 Загружено: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"

        return caption

    async def _update_channel_caption(self, media_file: MediaFile):
        """
        Обновляет подпись медиа-файла в Telegram канале
        """
        try:
            new_caption = await self._build_media_caption(
                media_file.request_number,
                media_file.description,
                media_file.tags,
                media_file.category
            )

            await self.telegram.edit_channel_message_caption(
                media_file.telegram_channel_id,
                media_file.telegram_message_id,
                new_caption
            )
        except Exception as e:
            logger.warning(f"Failed to update channel caption for media file {media_file.id}: {e}")

    async def _update_tags_usage(self, db: AsyncSession, tags: List[str]):
        """
        Обновляет статистику использования тегов
        """
        for tag_name in tags:
            result = await db.execute(select(MediaTag).where(MediaTag.tag_name == tag_name))
            tag = result.scalar_one_or_none()

            if tag:
                tag.usage_count = (tag.usage_count or 0) + 1
            else:
                # Создаем новый тег
                new_tag = MediaTag(
                    tag_name=tag_name,
                    tag_category="user",
                    usage_count=1,
                    is_system=False
                )
                db.add(new_tag)

    async def _copy_to_archive(
        self,
        media_file: MediaFile,
        archive_channel: MediaChannel,
        archive_reason: Optional[str]
    ):
        """
        Копирует медиа-файл в архивный канал
        """
        # Строим новую подпись для архива
        archive_caption = f"🗃 АРХИВ\n"
        archive_caption += f"📋 Заявка: {media_file.request_number}\n"
        archive_caption += f"📅 Архивировано: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n"

        if archive_reason:
            archive_caption += f"💭 Причина: {archive_reason}\n"

        # Пересылаем сообщение в архивный канал
        await self.telegram.forward_channel_message(
            from_channel_id=media_file.telegram_channel_id,
            message_id=media_file.telegram_message_id,
            to_channel_id=archive_channel.channel_id,
            new_caption=archive_caption
        )