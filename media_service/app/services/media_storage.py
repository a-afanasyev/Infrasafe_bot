"""
Основной сервис для работы с медиа-хранилищем в Telegram каналах
Реализация на основе спецификации photo.md
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Union, Dict, Any, BinaryIO
from sqlalchemy.orm import Session
from aiogram.types import InputFile, BufferedInputFile, Message

from app.models.media import MediaFile, MediaChannel, MediaTag, MediaUploadSession
from app.services.telegram_client import TelegramClientService
from app.core.config import settings, FileCategories, TelegramChannels, ErrorMessages
from app.db.database import get_db_context

logger = logging.getLogger(__name__)


class ChannelNotConfiguredError(RuntimeError):
    """Целевой канал не сконфигурирован (например, CHANNEL_ACCESS пуст).

    Поднимается при ленивой валидации домен-нейтральной загрузки — endpoint
    маппит это в HTTP 503 (сервис временно не сконфигурирован для домена).
    """


class MediaStorageService:
    """Основной сервис для работы с медиа-хранилищем в Telegram каналах"""

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

        with get_db_context() as db:
            try:
                # 1. Определяем канал для загрузки
                channel = await self._get_channel_for_category(db, category)

                # 2. Подготавливаем файл
                file_obj = BufferedInputFile(file_data, filename=filename)

                # 3. Генерируем подпись с тегами
                caption = self._generate_caption(request_number, description, tags)

                # 4. Загружаем в Telegram канал
                message = await self._upload_to_channel(channel, file_obj, caption, content_type)

                # 5. Сохраняем метаданные в БД
                media_file = await self._save_media_metadata(
                    db, message, request_number, category, description,
                    tags, uploaded_by, filename, content_type, len(file_data)
                )

                # 6. Обновляем статистику тегов
                if tags:
                    await self._update_tags_usage(db, tags)

                # Обновляем объект, чтобы загрузить все поля
                db.refresh(media_file)
                # Делаем объект независимым от сессии
                db.expunge(media_file)

                logger.info(f"Media uploaded successfully: {media_file.id}")
                return media_file

            except Exception as e:
                logger.error(f"Failed to upload media for {request_number}: {e}")
                raise

    async def upload_report_media(
        self,
        request_number: str,
        file_data: bytes,
        filename: str,
        content_type: str,
        report_type: str = FileCategories.COMPLETION_PHOTO,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        uploaded_by: int = None
    ) -> MediaFile:
        """
        Загружает медиа-файлы для отчетов о выполнении
        """
        logger.info(f"Uploading report media for {request_number}, type: {report_type}")

        # Добавляем системные теги для отчетов
        system_tags = [f"report_{report_type}", f"req_{request_number}"]
        all_tags = (tags or []) + system_tags

        # Используем общий метод загрузки
        media_file = await self.upload_request_media(
            request_number=request_number,
            file_data=file_data,
            filename=filename,
            content_type=content_type,
            category=report_type,
            description=description,
            tags=all_tags,
            uploaded_by=uploaded_by
        )

        logger.info(f"Report media uploaded successfully: {media_file.id}")
        return media_file

    async def upload_domain_media(
        self,
        channel_purpose: str,
        category: str,
        ref: str,
        file_data: bytes,
        filename: str,
        content_type: str,
        uploaded_by: Optional[int] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> MediaFile:
        """Домен-нейтральная загрузка медиа в произвольный канал по purpose.

        Не требует request_number (как у заявок) — вместо него домен-нейтральный
        ``ref`` (например, "controller|event_id"). Используется доменом контроля
        доступа (канал «access», категории access_plate/access_overview).

        Переиспользует внутренний путь отправки в Telegram (``_upload_to_channel``)
        и сохранения метаданных (``_save_media_metadata``) — TG-логика не дублируется.

        request_number в БД остаётся NULL (поле nullable), ``ref`` сохраняется в
        тегах как ``ref:<ref>`` (и в caption Telegram) — без риска переполнения
        VARCHAR(20) request_number и без миграции схемы.

        Raises:
            ChannelNotConfiguredError: целевой канал не сконфигурирован (env пуст).
        """
        logger.info(
            f"Uploading domain media: purpose={channel_purpose}, "
            f"category={category}, ref={ref}"
        )

        # Валидация файла (размер/тип) — как у заявок
        await self._validate_file(file_data, content_type)

        # Ленивая валидация конфигурации канала
        configured = self._configured_channel_value(channel_purpose)
        if not configured:
            raise ChannelNotConfiguredError(
                f"{channel_purpose} channel not configured "
                f"(set CHANNEL_{channel_purpose.upper()} env)"
            )

        # ref домен-нейтрален: храним в тегах, request_number оставляем None
        all_tags = list(tags or [])
        if ref:
            ref_tag = f"ref:{ref}"
            if ref_tag not in all_tags:
                all_tags.append(ref_tag)

        with get_db_context() as db:
            try:
                channel = await self._get_or_create_domain_channel(
                    db, channel_purpose, configured
                )

                file_obj = BufferedInputFile(file_data, filename=filename)
                caption = self._generate_domain_caption(ref, description, all_tags)

                message = await self._upload_to_channel(
                    channel, file_obj, caption, content_type
                )

                media_file = await self._save_media_metadata(
                    db, message, None, category, description,
                    all_tags, uploaded_by, filename, content_type, len(file_data)
                )

                if all_tags:
                    await self._update_tags_usage(db, all_tags)

                db.refresh(media_file)
                db.expunge(media_file)

                logger.info(f"Domain media uploaded successfully: {media_file.id}")
                return media_file

            except Exception as e:
                logger.error(f"Failed to upload domain media (ref={ref}): {e}")
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
        with get_db_context() as db:
            query = db.query(MediaFile).filter(
                MediaFile.request_number == request_number,
                MediaFile.status == "active"
            )

            if category:
                query = query.filter(MediaFile.category == category)

            media_files = query.order_by(MediaFile.uploaded_at.desc()).limit(limit).all()
            # MEDIA-01: detach objects from the session before the context exits,
            # otherwise the API layer hits DetachedInstanceError on field access
            # when serialising the response (this caused the 500 on
            # GET /api/v1/media/request/{request_number}).
            for mf in media_files:
                db.expunge(mf)
            logger.info(f"Found {len(media_files)} media files for request {request_number}")
            return media_files

    async def get_media_by_tags(
        self,
        tags: List[str],
        operator: str = "AND",
        limit: int = 100
    ) -> List[MediaFile]:
        """
        Поиск медиа-файлов по тегам
        """
        with get_db_context() as db:
            from sqlalchemy import and_, or_

            if operator.upper() == "AND":
                # Все теги должны присутствовать
                conditions = []
                for tag in tags:
                    conditions.append(MediaFile.tags.contains([tag]))
                query = db.query(MediaFile).filter(and_(*conditions))
            else:
                # Любой из тегов
                conditions = []
                for tag in tags:
                    conditions.append(MediaFile.tags.contains([tag]))
                query = db.query(MediaFile).filter(or_(*conditions))

            media_files = query.filter(MediaFile.status == "active").limit(limit).all()
            logger.info(f"Found {len(media_files)} media files for tags {tags}")
            return media_files

    async def get_media_file_url(self, media_file: MediaFile) -> Optional[str]:
        """
        Генерирует URL для доступа к файлу
        """
        try:
            file_url = await self.telegram.get_file_url(media_file.telegram_file_id)
            logger.info(f"Generated URL for media file {media_file.id}")
            return file_url

        except Exception as e:
            logger.error(f"Failed to generate URL for media file {media_file.id}: {e}")
            return None

    async def update_media_tags(
        self,
        media_file_id: int,
        tags: List[str],
        replace: bool = False
    ) -> Optional[MediaFile]:
        """
        Обновляет теги медиа-файла
        """
        with get_db_context() as db:
            media_file = db.query(MediaFile).filter(MediaFile.id == media_file_id).first()
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
        with get_db_context() as db:
            media_file = db.query(MediaFile).filter(MediaFile.id == media_file_id).first()
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
        with get_db_context() as db:
            media_file = db.query(MediaFile).filter(MediaFile.id == media_file_id).first()
            if not media_file:
                logger.warning(f"Media file {media_file_id} not found")
                return False

            try:
                # Удаляем из Telegram канала
                await self.telegram.delete_message(
                    chat_id=media_file.telegram_channel_id,
                    message_id=media_file.telegram_message_id
                )

                # Помечаем как удаленный
                media_file.status = "deleted"

                logger.info(f"Media file {media_file_id} deleted successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to delete media file {media_file_id}: {e}")
                return False

    # === HELPER METHODS ===

    async def _validate_file(self, file_data: bytes, content_type: str):
        """
        Валидация файла
        """
        # Проверка размера
        if len(file_data) > settings.max_file_size:
            raise ValueError(ErrorMessages.FILE_TOO_LARGE)

        # Проверка типа файла
        if content_type not in settings.allowed_file_types:
            raise ValueError(ErrorMessages.FILE_TYPE_NOT_ALLOWED)

    def _generate_caption(
        self,
        request_number: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        Генерирует подпись для медиа-файла
        """
        caption_parts = []

        # Основная информация
        caption_parts.append(f"📋 #{request_number}")

        if description:
            caption_parts.append(f"📝 {description}")

        # Теги
        if tags:
            hashtags = [f"#{tag.replace(' ', '_')}" for tag in tags]
            caption_parts.append(" ".join(hashtags))

        # Системная информация
        caption_parts.append(f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}")

        return "\n".join(caption_parts)

    def _configured_channel_value(self, channel_purpose: str) -> str:
        """Возвращает env-значение канала по purpose, читая settings ЖИВО.

        TelegramChannels.CHANNEL_MAPPING — снимок на момент импорта; здесь нужен
        актуальный settings (важно для ленивой валидации и тестов).
        """
        live_mapping = {
            TelegramChannels.REQUESTS: settings.channel_requests,
            TelegramChannels.REPORTS: settings.channel_reports,
            TelegramChannels.ARCHIVE: settings.channel_archive,
            TelegramChannels.BACKUP: settings.channel_backup,
            TelegramChannels.ACCESS: settings.channel_access,
        }
        return live_mapping.get(channel_purpose, "")

    def _generate_domain_caption(
        self,
        ref: Optional[str],
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Подпись для домен-нейтрального медиа (без привязки к заявке)."""
        caption_parts = []
        if ref:
            caption_parts.append(f"🔑 {ref}")
        if description:
            caption_parts.append(f"📝 {description}")
        if tags:
            hashtags = [
                "#" + t.replace(" ", "_").replace(":", "_").replace("|", "_")
                for t in tags
            ]
            caption_parts.append(" ".join(hashtags))
        caption_parts.append(f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        return "\n".join(caption_parts)

    async def _get_or_create_domain_channel(
        self, db: Session, channel_purpose: str, configured_value: str
    ) -> MediaChannel:
        """Возвращает активный канал по purpose, создавая запись при отсутствии.

        Канал «access» (и др. домен-каналы) может отсутствовать в БД на уже
        развёрнутых инсталляциях (init_db создаёт дефолтные каналы лишь на пустой
        БД). Здесь создаём строку из env-значения идемпотентно.
        """
        channel = db.query(MediaChannel).filter(
            MediaChannel.purpose == channel_purpose,
            MediaChannel.is_active == True  # noqa: E712
        ).first()
        if channel:
            return channel

        channel = MediaChannel(
            channel_name=f"uk_media_{channel_purpose}",
            channel_username=configured_value,
            purpose=channel_purpose,
            category="photo",
            is_active=True,
        )
        db.add(channel)
        db.flush()
        logger.info(
            f"Auto-provisioned media channel: purpose={channel_purpose}, "
            f"username={configured_value}"
        )
        return channel

    async def _get_channel_for_category(self, db: Session, category: str) -> MediaChannel:
        """
        Определяет канал для загрузки по категории файла
        """
        channel_purpose = FileCategories.get_channel_for_category(category)

        # Проверяем кэш
        if channel_purpose in self.channels_cache:
            return self.channels_cache[channel_purpose]

        # Загружаем из БД
        channel = db.query(MediaChannel).filter(
            MediaChannel.purpose == channel_purpose,
            MediaChannel.is_active == True
        ).first()

        if not channel:
            raise ValueError(f"{ErrorMessages.CHANNEL_NOT_FOUND}: {channel_purpose}")

        # Кэшируем
        self.channels_cache[channel_purpose] = channel
        return channel

    async def _upload_to_channel(
        self,
        channel: MediaChannel,
        file_obj: BufferedInputFile,
        caption: str,
        content_type: str
    ) -> Message:
        """
        Загружает файл в указанный Telegram канал
        """
        try:
            # Определяем ID канала (если еще не установлен)
            chat_id = channel.channel_id if channel.channel_id else channel.channel_username

            if content_type.startswith('image/'):
                message = await self.telegram.send_photo(
                    chat_id=chat_id,
                    photo=file_obj,
                    caption=caption
                )
            elif content_type.startswith('video/'):
                message = await self.telegram.send_video(
                    chat_id=chat_id,
                    video=file_obj,
                    caption=caption
                )
            else:
                message = await self.telegram.send_document(
                    chat_id=chat_id,
                    document=file_obj,
                    caption=caption
                )

            # Обновляем ID канала если нужно
            if not channel.channel_id:
                with get_db_context() as db:
                    db_channel = db.query(MediaChannel).filter(MediaChannel.id == channel.id).first()
                    if db_channel:
                        db_channel.channel_id = message.chat.id

            return message

        except Exception as e:
            logger.error(f"Failed to upload to channel {channel.channel_name}: {e}")
            raise

    async def _save_media_metadata(
        self,
        db: Session,
        message: Message,
        request_number: str,
        category: str,
        description: Optional[str],
        tags: Optional[List[str]],
        uploaded_by: Optional[int],
        filename: str,
        content_type: str,
        file_size: int
    ) -> MediaFile:
        """
        Сохраняет метаданные медиа-файла в БД
        """
        # Определяем тип файла
        if message.photo:
            file_type = "photo"
            telegram_file_id = message.photo[-1].file_id  # Берем самое большое разрешение
        elif message.video:
            file_type = "video"
            telegram_file_id = message.video.file_id
        elif message.document:
            file_type = "document"
            telegram_file_id = message.document.file_id
        else:
            raise ValueError("Unknown file type")

        # MEDIA-02: Telegram returns the same telegram_file_id for the same
        # file content across uploads. The DB has UNIQUE(telegram_file_id);
        # a naive INSERT raises IntegrityError → 500. Look up an existing row
        # first and reuse it (idempotent) — the freshly-posted Telegram
        # message in this case is a harmless duplicate post, but we don't
        # explode for the caller. Same payload, same row.
        existing = (
            db.query(MediaFile)
            .filter(MediaFile.telegram_file_id == telegram_file_id)
            .first()
        )
        if existing is not None:
            logger.warning(
                f"Duplicate telegram_file_id={telegram_file_id} for request "
                f"{request_number}; reusing existing media_file id={existing.id}"
            )
            return existing

        media_file = MediaFile(
            telegram_channel_id=message.chat.id,
            telegram_message_id=message.message_id,
            telegram_file_id=telegram_file_id,
            file_type=file_type,
            original_filename=filename,
            file_size=file_size,
            mime_type=content_type,
            description=description,
            caption=message.caption,
            request_number=request_number,
            uploaded_by_user_id=uploaded_by or 0,
            category=category,
            tags=tags or [],
            upload_source="api"
        )

        db.add(media_file)
        db.flush()  # Получаем ID

        return media_file

    async def _update_tags_usage(self, db: Session, tags: List[str]):
        """
        Обновляет статистику использования тегов
        """
        for tag_name in tags:
            tag = db.query(MediaTag).filter(MediaTag.tag_name == tag_name).first()
            if tag:
                tag.increment_usage()
            else:
                # Создаем новый тег
                new_tag = MediaTag(tag_name=tag_name, usage_count=1)
                db.add(new_tag)

    async def _update_channel_caption(self, media_file: MediaFile):
        """
        Обновляет подпись в Telegram канале
        """
        try:
            new_caption = self._generate_caption(
                media_file.request_number,
                media_file.description,
                media_file.tag_list
            )

            await self.telegram.edit_message_caption(
                chat_id=media_file.telegram_channel_id,
                message_id=media_file.telegram_message_id,
                caption=new_caption
            )

        except Exception as e:
            logger.error(f"Failed to update caption for media {media_file.id}: {e}")

    async def _copy_to_archive(
        self,
        media_file: MediaFile,
        archive_channel: MediaChannel,
        archive_reason: Optional[str]
    ):
        """
        Копирует файл в архивный канал
        """
        try:
            # Получаем URL оригинального файла
            file_url = await self.telegram.get_file_url(media_file.telegram_file_id)
            if not file_url:
                raise ValueError("Failed to get file URL")

            # Генерируем подпись для архива
            archive_caption = f"🗄️ АРХИВ\n"
            archive_caption += f"📋 #{media_file.request_number}\n"
            archive_caption += f"📅 Оригинал: {media_file.uploaded_at.strftime('%d.%m.%Y %H:%M')}\n"
            if archive_reason:
                archive_caption += f"💬 {archive_reason}\n"

            # Отправляем в архивный канал
            if media_file.is_image:
                await self.telegram.send_photo(
                    chat_id=archive_channel.channel_id,
                    photo=media_file.telegram_file_id,
                    caption=archive_caption
                )
            elif media_file.is_video:
                await self.telegram.send_video(
                    chat_id=archive_channel.channel_id,
                    video=media_file.telegram_file_id,
                    caption=archive_caption
                )

        except Exception as e:
            logger.error(f"Failed to copy media {media_file.id} to archive: {e}")
            raise

    async def close(self):
        """
        Закрытие соединений
        """
        await self.telegram.close()