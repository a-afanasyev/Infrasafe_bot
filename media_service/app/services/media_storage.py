"""
Основной сервис для работы с медиа-хранилищем в Telegram каналах
Реализация на основе спецификации docs/Archive/2026-09-23-root-reports/photo.md (архив)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from aiogram.types import BufferedInputFile, Message

from app.models.media import MediaFile, MediaChannel, MediaTag
import html

from app.utils.display_tz import display_instant_str, display_now_str
from app.services.telegram_client import DeleteOutcome, TelegramClientService, get_telegram_client
from app.core.config import settings, FileCategories, TelegramChannels, ErrorMessages
from dataclasses import dataclass

from app.db.database import get_db_context, run_sync, sync_unit

logger = logging.getLogger(__name__)




class ChannelNotConfiguredError(RuntimeError):
    """Целевой канал не сконфигурирован (например, CHANNEL_ACCESS пуст).

    Поднимается при ленивой валидации домен-нейтральной загрузки — endpoint
    маппит это в HTTP 503 (сервис временно не сконфигурирован для домена).
    """


class PublicationReservationError(RuntimeError):
    """Archive/delete не смогли зарезервировать файл: не active, или
    publication_locked=True (файл сейчас опубликован на публичном табло)."""



@dataclass(frozen=True)
class ChannelRef:
    """Снимок канала вне сессии (AUD7-ARCH-01).

    Telegram-загрузка идёт по этому снимку, а не по ORM-объекту: сессия, в
    которой канал прочитан, закрывается до внешнего I/O.
    """

    id: int
    purpose: str
    channel_name: str
    channel_id: Optional[int]
    channel_username: Optional[str]

    @classmethod
    def from_row(cls, row: MediaChannel) -> "ChannelRef":
        return cls(
            id=row.id,
            purpose=row.purpose,
            channel_name=row.channel_name,
            channel_id=row.channel_id,
            channel_username=row.channel_username,
        )

def _find_active_channel(db: Session, channel_purpose: str) -> Optional[MediaChannel]:
    """Активный канал по purpose (или None).

    `.is_(True)` — SQL-предикат, а не питоновское сравнение: даёт тот же
    `WHERE is_active` и снимает E712, не полагаясь на неявную истинность колонки.
    """
    return db.query(MediaChannel).filter(
        MediaChannel.purpose == channel_purpose,
        MediaChannel.is_active.is_(True),
    ).first()


class MediaStorageService:
    """Основной сервис для работы с медиа-хранилищем в Telegram каналах

    A9-P2-15: сервис лёгкий и живёт один запрос, а Telegram-клиент (Bot +
    aiohttp-сессия + httpx-пул) — общий процессный, им владеет lifespan
    приложения. Поэтому у сервиса нет close(): закрытие отсюда рвало бы
    сессию всем остальным запросам. Прежний `channels_cache` жил столько же,
    сколько сервис (один запрос) и ничего не кэшировал — убран: канал читается
    одной короткой выборкой.
    """

    def __init__(self, telegram: Optional[TelegramClientService] = None):
        self.telegram = telegram if telegram is not None else get_telegram_client()

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

        AUD7-ARCH-01: три короткие DB-единицы в рабочем потоке (канал →
        [Telegram] → метаданные+теги); сессия не пересекает Telegram-загрузку.
        """
        logger.info(f"Uploading request media for {request_number}, category: {category}")

        # Валидация
        await self._validate_file(file_data, content_type)

        try:
            # 1. Определяем канал для загрузки (своя сессия, закрыта до I/O)
            channel = await run_sync(self._resolve_channel_sync, category)

            # 2. Подготавливаем файл
            file_obj = BufferedInputFile(file_data, filename=filename)

            # 3. Генерируем подпись с тегами
            caption = self._generate_caption(request_number, description, tags)

            # 4. Загружаем в Telegram канал — без открытой сессии
            message = await self._upload_to_channel(channel, file_obj, caption, content_type)

            # 5–6. Метаданные + статистика тегов — одна короткая транзакция
            media_file = await run_sync(
                self._persist_upload_sync, message, request_number, category,
                description, tags, uploaded_by, filename, content_type, len(file_data),
            )

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

        try:
            # AUD7-ARCH-01: канал — своя короткая сессия, закрыта до Telegram I/O.
            channel = await run_sync(
                self._resolve_domain_channel_sync, channel_purpose, configured
            )

            file_obj = BufferedInputFile(file_data, filename=filename)
            caption = self._generate_domain_caption(ref, description, all_tags)

            message = await self._upload_to_channel(
                channel, file_obj, caption, content_type
            )

            media_file = await run_sync(
                self._persist_upload_sync, message, None, category, description,
                all_tags, uploaded_by, filename, content_type, len(file_data),
            )

            logger.info(f"Domain media uploaded successfully: {media_file.id}")
            return media_file

        except Exception as e:
            logger.error(f"Failed to upload domain media (ref={ref}): {e}")
            raise

    @sync_unit
    def get_request_media(
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

    async def update_media_tags(
        self,
        media_file_id: int,
        tags: List[str],
        replace: bool = False
    ) -> Optional[MediaFile]:
        """
        Обновляет теги медиа-файла

        AUD7-ARCH-01: теги и статистика — одна короткая транзакция в потоке,
        подпись в Telegram правится уже по отсоединённому объекту.
        """
        media_file = await run_sync(self._apply_tags_sync, media_file_id, tags, replace)
        if media_file is None:
            logger.warning(f"Media file {media_file_id} not found")
            return None

        # Обновляем подпись в Telegram канале — вне сессии
        await self._update_channel_caption(media_file)

        logger.info(f"Updated tags for media file {media_file_id}")
        return media_file

    def _apply_tags_sync(
        self, media_file_id: int, tags: List[str], replace: bool
    ) -> Optional[MediaFile]:
        with get_db_context() as db:
            media_file = db.query(MediaFile).filter(MediaFile.id == media_file_id).first()
            if not media_file:
                return None

            if replace:
                media_file.tags = tags
            else:
                # Объединяем существующие и новые теги
                existing_tags = set(media_file.tags or [])
                media_file.tags = list(existing_tags.union(set(tags)))

            # Обновляем статистику тегов
            self._update_tags_usage(db, tags)
            db.flush()
            db.refresh(media_file)
            db.expunge(media_file)
            return media_file

    async def archive_media(
        self,
        media_file_id: int,
        archive_reason: Optional[str] = None
    ) -> bool:
        """
        Архивирует медиа-файл (перемещает в архивный канал).

        Двухфазная сага (см. delete_media для симметричной реализации):
          Фаза 1 — резервирование status="archiving" одним атомарным UPDATE
                    (WHERE status='active' AND publication_locked=false),
                    коммитится отдельно, ДО любого сетевого I/O.
          Фаза 2 — копирование в архив (Telegram I/O) в свежей сессии;
                    успех → status="archived"; неудача → компенсация
                    (status обратно "active", ничего не потеряно).
        """
        return await self._archive_or_delete_saga(
            media_file_id, reserving_status="archiving", archive_reason=archive_reason
        )

    async def delete_media(self, media_file_id: int) -> bool:
        """
        Удаляет медиа-файл. Та же двухфазная сага, что и archive_media,
        но с reserving_status="deleting" — умышленно ДРУГОЕ транзиентное
        состояние, чем "archiving": будущий crash-recovery процесс должен
        уметь отличить «файл, возможно, уже удалён из Telegram» (deleting)
        от «файл точно ещё на месте, просто не скопирован» (archiving) —
        это разная степень риска при восстановлении после сбоя.
        """
        return await self._archive_or_delete_saga(
            media_file_id, reserving_status="deleting", archive_reason=None
        )

    async def _archive_or_delete_saga(
        self,
        media_file_id: int,
        reserving_status: str,
        archive_reason: Optional[str],
    ) -> bool:
        """Общая двухфазная сага для archive_media/delete_media.

        reserving_status: "archiving" (archive_media) или "deleting" (delete_media).
        """
        if reserving_status == "archiving":
            is_archive = True
        elif reserving_status == "deleting":
            is_archive = False
        else:
            # Только внутренний вызывающий (archive_media/delete_media) может
            # передать сюда значение — но проверяем явно, а не полагаемся на
            # тихий fallthrough в ветку delete: опечатка или будущий третий
            # транзиентный статус не должны молча трактоваться как удаление.
            raise ValueError(f"Unknown reserving_status: {reserving_status}")

        # === Фаза 1: резервирование, своя короткая транзакция (в потоке) ===
        reserved = await run_sync(self._reserve_sync, media_file_id, reserving_status)
        if reserved is None:
            logger.warning(f"Media file {media_file_id} not found")
            return False
        if not reserved:
            raise PublicationReservationError(
                f"media file {media_file_id} not archivable: not active or publication-locked"
            )

        # === Фаза 2: Telegram I/O по снимку строки, финализация — отдельной
        # короткой транзакцией (AUD7-ARCH-01: сессия не держится через I/O) ===
        media_file = await run_sync(self._load_detached_sync, media_file_id)
        try:
            if is_archive:
                archive_channel = await run_sync(
                    self._resolve_channel_sync, FileCategories.ARCHIVE
                )
                await self._copy_to_archive(media_file, archive_channel, archive_reason)
                await run_sync(
                    self._set_status_sync, media_file_id, "archived",
                    archived_at=datetime.now(timezone.utc),
                )
                logger.info(f"Media file {media_file_id} archived successfully")
            else:
                # A9-P3-23: delete_message не бросает — итог категорией.
                # Раньше результат не проверялся, и сетевой сбой молча давал
                # «deleted». Теперь:
                #   TRANSIENT (сеть/5xx/429) → компенсация ниже, вызывающий повторит;
                #   UNDELETABLE (нет can_delete_messages, старше 48 ч, Forbidden)
                #     → повтор не поможет: файл скрывается из системы, как и до
                #     фикса (иначе GDPR-очистка и ретеншн проваливались бы
                #     систематически), сообщение в канале фиксируется WARNING-ом.
                result = await self.telegram.delete_message(
                    chat_id=media_file.telegram_channel_id,
                    message_id=media_file.telegram_message_id
                )
                outcome = result.outcome
                if outcome is DeleteOutcome.TRANSIENT:
                    raise RuntimeError(
                        f"Telegram временно не удалил сообщение {media_file.telegram_message_id} "
                        f"в {media_file.telegram_channel_id}: {result.reason}"
                    )
                if outcome is DeleteOutcome.UNDELETABLE:
                    logger.warning(
                        "Media file %s: сообщение осталось в канале, удалить нельзя: "
                        "%s (channel=%s message_id=%s)",
                        media_file_id, result.reason, media_file.telegram_channel_id,
                        media_file.telegram_message_id,
                    )
                elif outcome not in (DeleteOutcome.DELETED, DeleteOutcome.ALREADY_GONE):
                    raise RuntimeError(f"Неожиданный итог delete_message: {outcome!r}")
                await run_sync(self._set_status_sync, media_file_id, "deleted")
                logger.info(f"Media file {media_file_id} deleted successfully")

            return True

        except Exception as e:
            action = "archive" if is_archive else "delete"
            logger.error(f"Failed to {action} media file {media_file_id}: {e}")
            # Компенсация: I/O не удался, байты никуда не делись —
            # возвращаем резервирование.
            await run_sync(self._set_status_sync, media_file_id, "active")
            return False

    def _reserve_sync(self, media_file_id: int, reserving_status: str) -> Optional[bool]:
        """None — файла нет; False — не active / заблокирован; True — зарезервирован."""
        with get_db_context() as db:
            exists = db.query(MediaFile.id).filter(MediaFile.id == media_file_id).first()
            if exists is None:
                return None
            return db.execute(
                update(MediaFile)
                .where(
                    MediaFile.id == media_file_id,
                    MediaFile.status == "active",
                    MediaFile.publication_locked.is_(False),
                )
                .values(status=reserving_status)
                .returning(MediaFile.id)
            ).first() is not None

    def _load_detached_sync(self, media_file_id: int) -> MediaFile:
        with get_db_context() as db:
            media_file = db.query(MediaFile).filter(MediaFile.id == media_file_id).first()
            if media_file is None:
                raise ValueError(f"media file {media_file_id} vanished after reservation")
            db.expunge(media_file)
            return media_file

    def _set_status_sync(
        self, media_file_id: int, status: str, *, archived_at: Optional[datetime] = None
    ) -> None:
        values: Dict[str, Any] = {"status": status}
        if archived_at is not None:
            values["archived_at"] = archived_at
        with get_db_context() as db:
            db.execute(update(MediaFile).where(MediaFile.id == media_file_id).values(**values))

    @sync_unit
    def acquire_publication_lock(self, media_file_id: int) -> bool:
        """Атомарно резервирует файл под публикацию.

        Успех только на текущий активный файл. Повторный вызов на уже
        заблокированном active-файле — идемпотентный успех. False означает
        либо отсутствие файла, либо не-active статус (archived/deleted/
        транзиентные archiving/deleting).
        """
        with get_db_context() as db:
            locked = db.execute(
                update(MediaFile)
                .where(
                    MediaFile.id == media_file_id,
                    MediaFile.status == "active",
                )
                .values(publication_locked=True)
                .returning(MediaFile.id)
            ).first() is not None
        return locked

    @sync_unit
    def release_publication_lock(self, media_file_id: int) -> None:
        """Снимает publication_locked. Идемпотентно — не ошибается, если
        файла нет или он уже не заблокирован."""
        with get_db_context() as db:
            db.execute(
                update(MediaFile)
                .where(MediaFile.id == media_file_id)
                .values(publication_locked=False)
            )

    @sync_unit
    def resolve_stale_transitions(self, older_than_minutes: int) -> Dict[str, int]:
        """Довести до терминального состояния строки, застрявшие в транзиентных
        статусах саги `_reserve_and_run` (крэш процесса между резервированием и
        финализацией).

        Направления РАЗНЫЕ и не взаимозаменяемы:

        * ``archiving`` → ``active``: до финализации байты гарантированно на
          месте (копирование в архивный канал байты не удаляет), значит файл
          безопасно вернуть в оборот и повторить архивацию позже.
        * ``deleting`` → ``deleted``: Telegram-сообщение могло быть УЖЕ удалено,
          то есть байтов может не быть. Возврат в ``active`` отдал бы наружу
          ссылку на возможно исчезнувший файл — терминальным считаем
          ``deleted``. Это единственный безопасный вывод в отсутствии
          подтверждения от Telegram.

        Порог по времени защищает от гонки с живой сагой: строка, которую прямо
        сейчас обрабатывает `_reserve_and_run`, младше порога и не трогается.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        with get_db_context() as db:
            reverted = db.execute(
                update(MediaFile)
                .where(MediaFile.status == "archiving", MediaFile.updated_at < cutoff)
                .values(status="active")
            ).rowcount
            finalized = db.execute(
                update(MediaFile)
                .where(MediaFile.status == "deleting", MediaFile.updated_at < cutoff)
                .values(status="deleted")
            ).rowcount
        if reverted or finalized:
            logger.info(
                "resolve_stale_transitions: archiving→active %d, deleting→deleted %d",
                reverted, finalized,
            )
        return {"archiving_reverted": reverted, "deleting_finalized": finalized}

    @sync_unit
    def list_publication_locks(
        self, limit: int, offset: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Возвращает (rows, total_count) для всех publication_locked=true
        файлов, упорядоченных по id, с пагинацией.

        Каждая строка — минимум {"id", "status", "updated_at"}: status/
        updated_at понадобятся будущей логике reconciliation (обнаружение
        зависших transient-статусов), хотя в этой задаче их никто не
        потребляет.
        """
        with get_db_context() as db:
            query = db.query(MediaFile).filter(MediaFile.publication_locked.is_(True))
            total = query.count()
            media_files = (
                query.order_by(MediaFile.id).offset(offset).limit(limit).all()
            )
            rows = [
                {"id": mf.id, "status": mf.status, "updated_at": mf.updated_at}
                for mf in media_files
            ]
        return rows, total

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

        # AUD8-SEC-01: parse_mode=HTML — любой свободный текст экранируется
        # (канон BUG-174/178), иначе житель вставляет ссылку/теги в канал.
        if description:
            caption_parts.append(f"📝 {html.escape(description)}")

        # Теги
        if tags:
            hashtags = [f"#{html.escape(tag.replace(' ', '_'))}" for tag in tags]
            caption_parts.append(" ".join(hashtags))

        # Системная информация
        caption_parts.append(f"⏰ {display_now_str()}")

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
        # AUD8-SEC-01: html.escape всех свободных полей (parse_mode=HTML).
        if ref:
            caption_parts.append(f"🔑 {html.escape(ref)}")
        if description:
            caption_parts.append(f"📝 {html.escape(description)}")
        if tags:
            hashtags = [
                "#" + html.escape(t.replace(" ", "_").replace(":", "_").replace("|", "_"))
                for t in tags
            ]
            caption_parts.append(" ".join(hashtags))
        caption_parts.append(f"⏰ {display_now_str()}")
        return "\n".join(caption_parts)

    def _resolve_domain_channel_sync(
        self, channel_purpose: str, configured_value: str
    ) -> ChannelRef:
        """Активный канал по purpose (создаётся при отсутствии) — снимком.

        Канал «access» (и др. домен-каналы) может отсутствовать в БД на уже
        развёрнутых инсталляциях (init_db создаёт дефолтные каналы лишь на пустой
        БД). Здесь создаём строку из env-значения идемпотентно. Своя короткая
        сессия (AUD7-ARCH-01), закрыта до Telegram I/O.

        A9-P3-23: две первые загрузки в новый домен обе видят «канала нет» и
        обе вставляют `uk_media_<purpose>` (channel_name UNIQUE) — проигравший
        получал IntegrityError → 500. Теперь проигравший перечитывает строку
        победителя новой сессией.
        """
        try:
            return self._get_or_create_domain_channel_sync(channel_purpose, configured_value)
        except IntegrityError:
            logger.info(
                "Concurrent auto-provision of media channel purpose=%s: "
                "reusing the row created by the parallel request",
                channel_purpose,
            )
            with get_db_context() as db:
                channel = _find_active_channel(db, channel_purpose)
                if channel is None:
                    # Конфликт не с активным каналом нашего purpose (например,
                    # деактивированная строка с тем же channel_name) — это
                    # конфигурационная проблема, а не гонка.
                    raise
                return ChannelRef.from_row(channel)

    def _get_or_create_domain_channel_sync(
        self, channel_purpose: str, configured_value: str
    ) -> ChannelRef:
        with get_db_context() as db:
            channel = _find_active_channel(db, channel_purpose)
            if channel is None:
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
            return ChannelRef.from_row(channel)

    def _resolve_channel_sync(self, category: str) -> ChannelRef:
        """
        Канал для загрузки по категории файла — снимком, своей короткой сессией.
        """
        channel_purpose = FileCategories.get_channel_for_category(category)

        with get_db_context() as db:
            channel = _find_active_channel(db, channel_purpose)
            if not channel:
                raise ValueError(f"{ErrorMessages.CHANNEL_NOT_FOUND}: {channel_purpose}")
            return ChannelRef.from_row(channel)

    def _remember_channel_id_sync(self, channel: ChannelRef, chat_id: int) -> None:
        """Первая отправка в канал по username: запомнить numeric chat_id."""
        with get_db_context() as db:
            db_channel = db.query(MediaChannel).filter(MediaChannel.id == channel.id).first()
            if db_channel:
                db_channel.channel_id = chat_id

    async def _upload_to_channel(
        self,
        channel: ChannelRef,
        file_obj: BufferedInputFile,
        caption: str,
        content_type: str
    ) -> Message:
        """
        Загружает файл в указанный Telegram канал (по снимку канала, без сессии)
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

            # Обновляем ID канала если нужно — отдельной короткой транзакцией
            if not channel.channel_id:
                await run_sync(self._remember_channel_id_sync, channel, message.chat.id)

            return message

        except Exception as e:
            logger.error(f"Failed to upload to channel {channel.channel_name}: {e}")
            raise

    def _persist_upload_sync(
        self,
        message: Message,
        request_number: Optional[str],
        category: str,
        description: Optional[str],
        tags: Optional[List[str]],
        uploaded_by: Optional[int],
        filename: str,
        content_type: str,
        file_size: int,
    ) -> MediaFile:
        """Метаданные + статистика тегов одной короткой транзакцией; наружу —
        отсоединённый объект (сессия закрыта при выходе)."""
        with get_db_context() as db:
            media_file = self._save_media_metadata(
                db, message, request_number, category, description,
                tags, uploaded_by, filename, content_type, file_size
            )
            if tags:
                self._update_tags_usage(db, tags)
            db.flush()
            # Обновляем объект, чтобы загрузить все поля, и отсоединяем
            db.refresh(media_file)
            db.expunge(media_file)
            return media_file

    def _save_media_metadata(
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

    def _update_tags_usage(self, db: Session, tags: List[str]):
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

    def _generate_archive_caption(self, media_file: MediaFile, archive_reason: Optional[str]) -> str:
        """Подпись архивной копии; причина — свободный текст, экранируется (AUD8-SEC-01)."""
        caption = "🗄️ АРХИВ\n"
        caption += f"📋 #{media_file.request_number}\n"
        caption += f"📅 Оригинал: {display_instant_str(media_file.uploaded_at)}\n"
        if archive_reason:
            caption += f"💬 {html.escape(archive_reason)}\n"
        return caption

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

            archive_caption = self._generate_archive_caption(media_file, archive_reason)

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
