"""
Клиент для интеграции с Media Service
Используется основным UK Management Bot для работы с медиа-файлами
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, BinaryIO, Union
import httpx
from pathlib import Path

logger = logging.getLogger(__name__)


class MediaServiceClient:
    """
    Клиент для взаимодействия с Media Service API
    """

    def __init__(self, base_url: str, timeout: int = 30):
        """
        Инициализация клиента

        Args:
            base_url: Базовый URL Media Service (например, http://media-service:8000)
            timeout: Таймаут запросов в секундах
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            timeout=timeout,
            base_url=f"{self.base_url}/api/v1"
        )

    async def upload_request_media(
        self,
        request_number: str,
        file_path: Union[str, Path, BinaryIO],
        filename: Optional[str] = None,
        category: str = "request_photo",
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        uploaded_by: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Загрузка медиа-файла для заявки

        Args:
            request_number: Номер заявки
            file_path: Путь к файлу или файловый объект
            filename: Имя файла (если не указано, берется из пути)
            category: Категория файла
            description: Описание файла
            tags: Список тегов
            uploaded_by: ID пользователя, загрузившего файл

        Returns:
            Информация о загруженном файле
        """
        try:
            # Подготовка файла
            if isinstance(file_path, (str, Path)):
                file_path = Path(file_path)
                if not file_path.exists():
                    raise FileNotFoundError(f"Файл не найден: {file_path}")

                filename = filename or file_path.name
                file_content = file_path.read_bytes()
                file_obj = ("file", (filename, file_content))
            else:
                # Предполагаем, что это файловый объект
                file_content = file_path.read()
                if hasattr(file_path, 'name'):
                    filename = filename or Path(file_path.name).name
                else:
                    filename = filename or "upload"
                file_obj = ("file", (filename, file_content))

            # Подготовка данных формы
            data = {
                "request_number": request_number,
                "category": category
            }

            if description:
                data["description"] = description

            if tags:
                data["tags"] = ",".join(tags)

            if uploaded_by is not None:
                data["uploaded_by"] = str(uploaded_by)

            # Отправка запроса
            response = await self.client.post(
                "/media/upload",
                files=[file_obj],
                data=data
            )

            response.raise_for_status()
            result = response.json()

            logger.info(f"Media uploaded successfully for request {request_number}: {result['media_file']['id']}")
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error uploading media: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to upload media for request {request_number}: {e}")
            raise

    async def upload_report_media(
        self,
        request_number: str,
        file_path: Union[str, Path, BinaryIO],
        filename: Optional[str] = None,
        report_type: str = "completion_photo",
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        uploaded_by: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Загрузка медиа-файла для отчета

        Args:
            request_number: Номер заявки
            file_path: Путь к файлу или файловый объект
            filename: Имя файла
            report_type: Тип отчета
            description: Описание
            tags: Теги
            uploaded_by: ID пользователя

        Returns:
            Информация о загруженном файле отчета
        """
        try:
            # Подготовка файла (аналогично upload_request_media)
            if isinstance(file_path, (str, Path)):
                file_path = Path(file_path)
                if not file_path.exists():
                    raise FileNotFoundError(f"Файл не найден: {file_path}")

                filename = filename or file_path.name
                file_content = file_path.read_bytes()
                file_obj = ("file", (filename, file_content))
            else:
                file_content = file_path.read()
                if hasattr(file_path, 'name'):
                    filename = filename or Path(file_path.name).name
                else:
                    filename = filename or "report"
                file_obj = ("file", (filename, file_content))

            data = {
                "request_number": request_number,
                "report_type": report_type
            }

            if description:
                data["description"] = description

            if tags:
                data["tags"] = ",".join(tags)

            if uploaded_by is not None:
                data["uploaded_by"] = str(uploaded_by)

            response = await self.client.post(
                "/media/upload-report",
                files=[file_obj],
                data=data
            )

            response.raise_for_status()
            result = response.json()

            logger.info(f"Report media uploaded successfully for request {request_number}: {result['media_file']['id']}")
            return result

        except Exception as e:
            logger.error(f"Failed to upload report media for request {request_number}: {e}")
            raise

    async def get_request_media(
        self,
        request_number: str,
        category: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Получение всех медиа-файлов для заявки

        Args:
            request_number: Номер заявки
            category: Фильтр по категории
            limit: Лимит результатов

        Returns:
            Список медиа-файлов заявки
        """
        try:
            params = {"limit": limit}
            if category:
                params["category"] = category

            response = await self.client.get(
                f"/media/request/{request_number}",
                params=params
            )

            response.raise_for_status()
            result = response.json()

            logger.info(f"Retrieved {len(result)} media files for request {request_number}")
            return result

        except Exception as e:
            logger.error(f"Failed to get media for request {request_number}: {e}")
            raise

    async def search_media(
        self,
        query: Optional[str] = None,
        request_numbers: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        file_types: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        telegram_file_id: Optional[str] = None,
        uploaded_by: Optional[int] = None,
        status: str = "active",
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Поиск медиа-файлов с фильтрами

        Args:
            query: Текстовый поиск
            request_numbers: Номера заявок
            tags: Теги
            date_from: Дата начала
            date_to: Дата окончания
            file_types: Типы файлов
            categories: Категории
            telegram_file_id: Telegram file_id
            uploaded_by: ID пользователя
            status: Статус файлов
            limit: Лимит результатов
            offset: Смещение

        Returns:
            Результаты поиска с пагинацией
        """
        try:
            params = {
                "status": status,
                "limit": limit,
                "offset": offset
            }

            if query:
                params["query"] = query

            if request_numbers:
                params["request_numbers"] = ",".join(request_numbers)

            if tags:
                params["tags"] = ",".join(tags)

            if date_from:
                params["date_from"] = date_from.isoformat()

            if date_to:
                params["date_to"] = date_to.isoformat()

            if file_types:
                params["file_types"] = ",".join(file_types)

            if categories:
                params["categories"] = ",".join(categories)

            if telegram_file_id:
                params["telegram_file_id"] = telegram_file_id

            if uploaded_by is not None:
                params["uploaded_by"] = uploaded_by

            response = await self.client.get("/media/search", params=params)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Search returned {result['total_count']} results")
            return result

        except Exception as e:
            logger.error(f"Failed to search media: {e}")
            raise

    async def get_media_by_telegram_file_id(self, telegram_file_id: str) -> Dict[str, Any]:
        """
        Получение информации о медиа-файле по Telegram file_id

        Args:
            telegram_file_id: Идентификатор файла в Telegram

        Returns:
            Информация о файле. В случае наличия записи в БД содержит ключ
            ``media_file`` с данными Media Service и ``source = "database"``.
            Если запись отсутствует, возвращает сведения только из Telegram:
            ``source = "telegram"``, ``file_url`` и метаданные файла.
        """
        try:
            response = await self.client.get(f"/media/telegram/{telegram_file_id}")
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to get media by telegram file_id {telegram_file_id}: {e}")
            raise

    async def get_media_file(self, media_id: int) -> Dict[str, Any]:
        """
        Получение информации о медиа-файле по ID

        Args:
            media_id: ID медиа-файла

        Returns:
            Информация о медиа-файле
        """
        try:
            response = await self.client.get(f"/media/{media_id}")
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to get media file {media_id}: {e}")
            raise

    async def get_media_url(self, media_id: int) -> Optional[str]:
        """
        Получение URL для доступа к медиа-файлу

        Args:
            media_id: ID медиа-файла

        Returns:
            URL файла или None
        """
        try:
            response = await self.client.get(f"/media/{media_id}/url")
            response.raise_for_status()

            result = response.json()
            return result.get("file_url")

        except Exception as e:
            logger.error(f"Failed to get media URL {media_id}: {e}")
            return None

    async def update_media_tags(
        self,
        media_id: int,
        tags: List[str],
        replace: bool = False
    ) -> Dict[str, Any]:
        """
        Обновление тегов медиа-файла

        Args:
            media_id: ID медиа-файла
            tags: Новые теги
            replace: Заменить все теги или добавить

        Returns:
            Обновленная информация о файле
        """
        try:
            data = {
                "tags": tags,
                "replace": replace
            }

            response = await self.client.put(f"/media/{media_id}/tags", json=data)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to update tags for media {media_id}: {e}")
            raise

    async def archive_media(self, media_id: int, reason: Optional[str] = None) -> bool:
        """
        Архивация медиа-файла

        Args:
            media_id: ID медиа-файла
            reason: Причина архивации

        Returns:
            True если успешно
        """
        try:
            data = {}
            if reason:
                data["archive_reason"] = reason

            response = await self.client.post(f"/media/{media_id}/archive", json=data)
            response.raise_for_status()

            return True

        except Exception as e:
            logger.error(f"Failed to archive media {media_id}: {e}")
            return False

    async def delete_media(self, media_id: int) -> bool:
        """
        Удаление медиа-файла

        Args:
            media_id: ID медиа-файла

        Returns:
            True если успешно
        """
        try:
            response = await self.client.delete(f"/media/{media_id}")
            response.raise_for_status()

            return True

        except Exception as e:
            logger.error(f"Failed to delete media {media_id}: {e}")
            return False

    async def get_request_timeline(self, request_number: str) -> Dict[str, Any]:
        """
        Получение временной линии медиа-файлов для заявки

        Args:
            request_number: Номер заявки

        Returns:
            Временная линия с медиа-файлами
        """
        try:
            response = await self.client.get(f"/media/request/{request_number}/timeline")
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to get timeline for request {request_number}: {e}")
            raise

    async def get_popular_tags(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Получение популярных тегов

        Args:
            limit: Количество тегов

        Returns:
            Список популярных тегов
        """
        try:
            response = await self.client.get("/media/tags/popular", params={"limit": limit})
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to get popular tags: {e}")
            raise

    async def get_media_statistics(self) -> Dict[str, Any]:
        """
        Получение статистики медиа-файлов

        Returns:
            Статистика медиа-файлов
        """
        try:
            response = await self.client.get("/media/statistics")
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to get media statistics: {e}")
            raise

    async def find_similar_media(
        self,
        media_id: int,
        similarity_threshold: float = 0.7,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Поиск похожих медиа-файлов

        Args:
            media_id: ID исходного файла
            similarity_threshold: Порог схожести
            limit: Лимит результатов

        Returns:
            Список похожих файлов
        """
        try:
            params = {
                "similarity_threshold": similarity_threshold,
                "limit": limit
            }

            response = await self.client.get(f"/media/{media_id}/similar", params=params)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to find similar media for {media_id}: {e}")
            raise

    async def health_check(self) -> Dict[str, Any]:
        """
        Проверка здоровья сервиса

        Returns:
            Статус сервиса
        """
        try:
            response = await self.client.get("/health")
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise

    async def close(self):
        """
        Закрытие клиента
        """
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Convenience functions для простого использования
async def upload_request_photo(
    client: MediaServiceClient,
    request_number: str,
    photo_path: Union[str, Path],
    description: Optional[str] = None,
    uploaded_by: Optional[int] = None
) -> Dict[str, Any]:
    """
    Быстрая загрузка фото для заявки
    """
    return await client.upload_request_media(
        request_number=request_number,
        file_path=photo_path,
        category="request_photo",
        description=description,
        uploaded_by=uploaded_by
    )


async def upload_completion_photo(
    client: MediaServiceClient,
    request_number: str,
    photo_path: Union[str, Path],
    description: Optional[str] = None,
    uploaded_by: Optional[int] = None
) -> Dict[str, Any]:
    """
    Быстрая загрузка фото завершения работы
    """
    return await client.upload_report_media(
        request_number=request_number,
        file_path=photo_path,
        report_type="completion_photo",
        description=description,
        uploaded_by=uploaded_by
    )
