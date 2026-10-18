"""
Утилиты для работы с медиа-файлами через Media Service
"""
import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List
from io import BytesIO
from aiogram import Bot
from uk_management_bot.integrations import get_media_client
from uk_management_bot.utils.document_crypto import document_aad, encrypt
from uk_management_bot.utils.media_sniff import sniff_media_mime

logger = logging.getLogger(__name__)


async def upload_telegram_file_to_media_service(
    bot: Bot,
    file_id: str,
    request_number: str,
    category: str = "request_photo",
    description: Optional[str] = None,
    uploaded_by: Optional[int] = None
) -> Optional[dict]:
    """
    Загружает файл из Telegram в Media Service

    Args:
        bot: Экземпляр бота
        file_id: File ID из Telegram
        request_number: Номер заявки
        category: Категория файла (request_photo, request_video, etc.)
        description: Описание файла
        uploaded_by: ID пользователя, загрузившего файл

    Returns:
        Информация о загруженном файле или None при ошибке
    """
    try:
        media_client = get_media_client()
        if not media_client:
            logger.warning("Media Service недоступен, пропускаем загрузку файла")
            return None

        # Скачиваем файл из Telegram
        file = await bot.get_file(file_id)
        file_bytes = BytesIO()
        await bot.download_file(file.file_path, file_bytes)
        file_bytes.seek(0)

        # Определяем имя файла
        file_extension = file.file_path.split('.')[-1] if '.' in file.file_path else 'jpg'
        filename = f"{request_number}_{category}.{file_extension}"

        # Загружаем в Media Service
        result = await media_client.upload_request_media(
            request_number=request_number,
            file_path=file_bytes,
            filename=filename,
            category=category,
            description=description,
            uploaded_by=uploaded_by
        )

        logger.info(f"Файл загружен в Media Service: {result['media_file']['id']}")
        return result

    except Exception as e:
        logger.error(f"Ошибка загрузки файла в Media Service: {e}")
        return None


async def upload_multiple_telegram_files(
    bot: Bot,
    file_ids: List[str],
    request_number: str,
    uploaded_by: Optional[int] = None
) -> List[dict]:
    """
    Загружает несколько файлов из Telegram в Media Service

    Args:
        bot: Экземпляр бота
        file_ids: Список file_id из Telegram
        request_number: Номер заявки
        uploaded_by: ID пользователя

    Returns:
        Список информации о загруженных файлах
    """
    results = []
    for i, file_id in enumerate(file_ids, 1):
        # Определяем категорию по индексу
        category = "request_photo"  # По умолчанию фото

        result = await upload_telegram_file_to_media_service(
            bot=bot,
            file_id=file_id,
            request_number=request_number,
            category=category,
            description=f"Медиа-файл #{i} к заявке",
            uploaded_by=uploaded_by
        )

        if result:
            results.append(result)

    return results


async def upload_report_file_to_media_service(
    bot: Bot,
    file_id: str,
    request_number: str,
    report_type: str = "completion_photo",
    description: Optional[str] = None,
    uploaded_by: Optional[int] = None
) -> Optional[dict]:
    """
    Загружает фото отчета в Media Service

    Args:
        bot: Экземпляр бота
        file_id: File ID из Telegram
        request_number: Номер заявки
        report_type: Тип отчета (completion_photo, completion_video)
        description: Описание
        uploaded_by: ID пользователя

    Returns:
        Информация о загруженном файле или None
    """
    try:
        media_client = get_media_client()
        if not media_client:
            logger.warning("Media Service недоступен, пропускаем загрузку отчета")
            return None

        # Скачиваем файл из Telegram
        file = await bot.get_file(file_id)
        file_bytes = BytesIO()
        await bot.download_file(file.file_path, file_bytes)
        file_bytes.seek(0)

        # Определяем имя файла
        file_extension = file.file_path.split('.')[-1] if '.' in file.file_path else 'jpg'
        filename = f"{request_number}_report.{file_extension}"

        # Загружаем в Media Service
        result = await media_client.upload_report_media(
            request_number=request_number,
            file_path=file_bytes,
            filename=filename,
            report_type=report_type,
            description=description,
            uploaded_by=uploaded_by
        )

        logger.info(f"Отчет загружен в Media Service: {result['media_file']['id']}")
        return result

    except Exception as e:
        logger.error(f"Ошибка загрузки отчета в Media Service: {e}")
        return None


#: Типы документа жителя (по байтам): фото-сканы и PDF — то, что покажет дашборд.
_DOCUMENT_IMAGE_TYPES = frozenset({"image/jpeg", "image/png"})


class DocumentUploadError(Exception):
    """Документ не загружен: reason = "unsupported" (повтор не поможет) | "unavailable"."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class EncryptedUpload:
    media_id: int
    key: bytes
    document_uuid: str


async def upload_encrypted_document(
    bot: Bot, file_id: str, *, user_id: int, document_type: str,
) -> EncryptedUpload:
    """Скачать документ из Telegram, зашифровать и положить в медиа-сервис.

    Тип — по байтам (jpeg/png/PDF). Ключ и uuid возвращаются вызывающему для
    строки `UserDocument`; AAD связывает blob с (uuid, users.id, тип). Без
    медиа-сервиса строка не создаётся — исключение вместо тихого пропуска.
    """
    client = get_media_client()
    if client is None:
        raise DocumentUploadError("unavailable")
    try:
        file = await bot.get_file(file_id)
        buffer = BytesIO()
        await bot.download_file(file.file_path, buffer)
    except Exception as e:  # noqa: BLE001 — сеть Telegram
        logger.warning("Документ пользователя %s не скачан из Telegram: %s", user_id, e)
        raise DocumentUploadError("unavailable") from e
    data = buffer.getvalue()
    if sniff_media_mime(data) not in _DOCUMENT_IMAGE_TYPES and not data.startswith(b"%PDF-"):
        raise DocumentUploadError("unsupported")

    document_uuid = str(uuid.uuid4())
    key, blob = encrypt(data, document_aad(document_uuid, user_id, document_type))
    # Один повтор: разовый таймаут медиа-сервиса → Telegram иначе теряет файл жителя.
    # ponytail: таймаут после фактической отправки оставит в архиве осиротевший
    # нечитаемый blob (ключа нет нигде) — безвредно.
    for attempt in (1, 2):
        try:
            media_id = await client.upload_resident_document(blob, uploaded_by=user_id)
            break
        except Exception as e:  # noqa: BLE001 — недоступный медиа-сервис
            logger.warning("Документ пользователя %s не загружен в Media Service (попытка %s): %s",
                           user_id, attempt, e)
            if attempt == 2:
                raise DocumentUploadError("unavailable") from e
    return EncryptedUpload(media_id=media_id, key=key, document_uuid=document_uuid)


class MediaCleanupResult(str, Enum):
    """Исход зачистки документов пользователя в Media Service.

    ⚠ Раньше функция возвращала `bool` и отдавала **True** в том числе когда
    сервис недоступен («считаем успешным»). Вызывающий не мог отличить
    «удалено» от «не пытались», а цена этой лжи высокая: строки `UserDocument`
    к моменту вызова уже удалены одной транзакцией, то есть сканы паспортов
    остаются в Media Service и в Telegram, но исчезают из карточки — и ни
    следа в логах. Находка аудита 2026-07-29.

    Истинность (`bool`) сохранена совместимой с прежним `if await …`, но
    трактуется честно: истинны только исходы, после которых чистить нечего.
    """

    DELETED = "deleted"
    NOTHING_TO_DELETE = "nothing_to_delete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"

    def __bool__(self) -> bool:
        return self in (MediaCleanupResult.DELETED, MediaCleanupResult.NOTHING_TO_DELETE)


async def delete_user_documents_from_media_service(
    user_telegram_id: int
) -> MediaCleanupResult:
    """Удаляет все документы пользователя из Media Service (канал ARCHIVE).

    Args:
        user_telegram_id: Telegram ID пользователя

    Returns:
        `MediaCleanupResult` — исход, а не «успех». Вызывающий обязан
        различать их: `telegram_id` и есть ручка для повторного запуска
        зачистки, если она не состоялась.
    """
    try:
        media_client = get_media_client()
        if not media_client:
            logger.warning(
                "Media Service недоступен — документы пользователя %s НЕ удалены; "
                "повторить зачистку по этому telegram_id",
                user_telegram_id,
            )
            return MediaCleanupResult.UNAVAILABLE

        # Формируем request_number для документов пользователя
        request_number = f"USER_{user_telegram_id}"

        # Получаем все файлы пользователя с категорией archive
        try:
            user_files = await media_client.get_request_media(
                request_number=request_number,
                category="archive"
            )

            if not user_files:
                logger.info(f"Нет документов для удаления у пользователя {user_telegram_id}")
                return MediaCleanupResult.NOTHING_TO_DELETE

            # Удаляем каждый файл
            deleted_count = 0
            for file_info in user_files:
                media_id = file_info.get('id')
                if media_id:
                    success = await media_client.delete_media(media_id)
                    if success:
                        deleted_count += 1
                        logger.info(f"Удален документ {media_id} пользователя {user_telegram_id}")
                    else:
                        logger.warning(f"Не удалось удалить документ {media_id} пользователя {user_telegram_id}")

            if deleted_count == len(user_files):
                logger.info(
                    "Удалены все %s документов пользователя %s из Media Service",
                    deleted_count, user_telegram_id,
                )
                return MediaCleanupResult.DELETED
            # Частичная зачистка — тоже не успех: прежний код возвращал True и
            # здесь, скрывая оставшиеся файлы.
            logger.warning(
                "Удалено %s из %s документов пользователя %s — остальные остались "
                "в Media Service; повторить зачистку по этому telegram_id",
                deleted_count, len(user_files), user_telegram_id,
            )
            return MediaCleanupResult.PARTIAL

        except Exception as e:
            logger.error(f"Ошибка получения файлов пользователя {user_telegram_id}: {e}")
            return MediaCleanupResult.FAILED

    except Exception as e:
        logger.error(f"Ошибка удаления документов пользователя {user_telegram_id} из Media Service: {e}")
        return MediaCleanupResult.FAILED
