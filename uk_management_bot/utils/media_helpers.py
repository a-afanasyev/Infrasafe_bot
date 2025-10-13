"""
Утилиты для работы с медиа-файлами через Media Service
"""
import logging
from typing import Optional, List
from io import BytesIO
from aiogram import Bot
from uk_management_bot.integrations import get_media_client

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


async def upload_document_to_media_service(
    bot: Bot,
    file_id: str,
    user_telegram_id: int,
    description: Optional[str] = None
) -> Optional[dict]:
    """
    Загружает документ пользователя в Media Service (в канал ARCHIVE)

    Args:
        bot: Экземпляр бота
        file_id: File ID из Telegram
        user_telegram_id: Telegram ID пользователя (для идентификации в ARCHIVE)
        description: Описание документа

    Returns:
        Информация о загруженном документе или None
    """
    try:
        media_client = get_media_client()
        if not media_client:
            logger.warning("Media Service недоступен, пропускаем загрузку документа")
            return None

        # Скачиваем файл из Telegram
        file = await bot.get_file(file_id)
        file_bytes = BytesIO()
        await bot.download_file(file.file_path, file_bytes)
        file_bytes.seek(0)

        # Определяем имя файла
        file_extension = file.file_path.split('.')[-1] if '.' in file.file_path else 'jpg'
        filename = f"user_{user_telegram_id}_doc.{file_extension}"

        # Используем специальный request_number для документов пользователей
        request_number = f"USER_{user_telegram_id}"

        # Загружаем в Media Service с категорией archive (документы пользователей в ARCHIVE канале)
        result = await media_client.upload_request_media(
            request_number=request_number,
            file_path=file_bytes,
            filename=filename,
            category="archive",
            description=description or f"Документ пользователя {user_telegram_id}",
            uploaded_by=user_telegram_id
        )

        logger.info(f"Документ пользователя загружен в Media Service: {result['media_file']['id']}")
        return result

    except Exception as e:
        logger.error(f"Ошибка загрузки документа в Media Service: {e}")
        return None


async def delete_user_documents_from_media_service(
    user_telegram_id: int
) -> bool:
    """
    Удаляет все документы пользователя из Media Service (из канала ARCHIVE)

    Args:
        user_telegram_id: Telegram ID пользователя

    Returns:
        True если успешно удалены или нет файлов для удаления
    """
    try:
        media_client = get_media_client()
        if not media_client:
            logger.warning("Media Service недоступен, пропускаем удаление документов")
            return True  # Считаем успешным, так как сервис недоступен

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
                return True

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

            logger.info(f"Удалено {deleted_count} из {len(user_files)} документов пользователя {user_telegram_id} из Media Service")
            return True

        except Exception as e:
            logger.error(f"Ошибка получения файлов пользователя {user_telegram_id}: {e}")
            return False

    except Exception as e:
        logger.error(f"Ошибка удаления документов пользователя {user_telegram_id} из Media Service: {e}")
        return False
