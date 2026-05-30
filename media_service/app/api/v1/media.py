"""
API эндпоинты для работы с медиа-файлами
"""

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from fastapi.responses import JSONResponse, StreamingResponse, Response
from sqlalchemy.orm import Session
import io

from app.db.database import get_db
from app.services import MediaStorageService, MediaSearchService
from app.schemas import (
    MediaUploadRequest, MediaSearchRequest, MediaUpdateTagsRequest,
    MediaArchiveRequest, MediaDateRangeRequest, MediaFileResponse,
    MediaSearchResponse, MediaStatisticsResponse, MediaTimelineResponse,
    MediaDateRangeResponse, MediaUploadResponse, MediaFileUrlResponse,
    ErrorResponse, MediaTagResponse, MediaCategoryEnum, FileTypeEnum,
    MediaStatusEnum, MediaTelegramLookupResponse
)
from app.core.config import settings
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])


def _sniff_image_mime(data: bytes) -> Optional[str]:
    """Detect content type from magic bytes (first ~12 bytes). Returns None
    if not a recognised image/video signature so the caller can fall back."""
    if not data:
        return None
    if data.startswith(b"\xFF\xD8\xFF"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    # WEBP: "RIFF????WEBP"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    # HEIC/HEIF: bytes 4..12 contain "ftypheic" / "ftypheix" / "ftypmif1" / "ftypheis"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"heic", b"heix", b"heim", b"heis", b"mif1", b"msf1"):
            return "image/heic"
    # MP4: ftyp box with mp4* / isom / avc1 brands
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"mp42", b"isom", b"avc1", b"mp41"):
            return "video/mp4"
    return None


# Dependency для сервисов
async def get_storage_service() -> MediaStorageService:
    return MediaStorageService()


async def get_search_service() -> MediaSearchService:
    return MediaSearchService()


@router.post("/upload", response_model=MediaUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: UploadFile = File(..., description="Медиа-файл для загрузки"),
    request_number: str = Form(..., description="Номер заявки"),
    category: MediaCategoryEnum = Form(default=MediaCategoryEnum.REQUEST_PHOTO, description="Категория файла"),
    description: Optional[str] = Form(None, description="Описание файла"),
    tags: Optional[str] = Form(None, description="Теги через запятую"),
    uploaded_by: Optional[int] = Form(None, description="ID пользователя"),
    storage_service: MediaStorageService = Depends(get_storage_service)
):
    """
    Загрузка медиа-файла для заявки
    """
    try:
        # Валидация файла
        if not file.filename:
            raise HTTPException(status_code=400, detail="Имя файла не указано")

        if file.size and file.size > settings.max_file_size:
            raise HTTPException(status_code=400, detail=f"Размер файла превышает {settings.max_file_size} байт")

        if file.content_type not in settings.allowed_file_types:
            raise HTTPException(status_code=400, detail=f"Тип файла {file.content_type} не разрешен")

        # Читаем содержимое файла
        file_data = await file.read()

        # Обработка тегов
        tags_list = []
        if tags:
            tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

        # Загружаем файл
        media_file = await storage_service.upload_request_media(
            request_number=request_number,
            file_data=file_data,
            filename=file.filename,
            content_type=file.content_type,
            category=category,
            description=description,
            tags=tags_list,
            uploaded_by=uploaded_by
        )

        logger.info(f"Media uploaded successfully: {media_file.id} for request {request_number}")

        return MediaUploadResponse(
            media_file=MediaFileResponse.model_validate(media_file),
            file_url=f"/api/v1/media/{media_file.id}/file",
            message="Файл успешно загружен"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload media: {e}")
        raise HTTPException(status_code=500, detail="Ошибка загрузки файла")


@router.post("/upload-report", response_model=MediaUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_report_media(
    file: UploadFile = File(..., description="Медиа-файл отчета"),
    request_number: str = Form(..., description="Номер заявки"),
    report_type: MediaCategoryEnum = Form(default=MediaCategoryEnum.COMPLETION_PHOTO, description="Тип отчета"),
    description: Optional[str] = Form(None, description="Описание"),
    tags: Optional[str] = Form(None, description="Теги через запятую"),
    uploaded_by: Optional[int] = Form(None, description="ID пользователя"),
    storage_service: MediaStorageService = Depends(get_storage_service)
):
    """
    Загрузка медиа-файла для отчета о выполнении
    """
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Имя файла не указано")

        file_data = await file.read()

        tags_list = []
        if tags:
            tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

        media_file = await storage_service.upload_report_media(
            request_number=request_number,
            file_data=file_data,
            filename=file.filename,
            content_type=file.content_type,
            report_type=report_type,
            description=description,
            tags=tags_list,
            uploaded_by=uploaded_by
        )

        logger.info(f"Report media uploaded successfully: {media_file.id}")

        return MediaUploadResponse(
            media_file=MediaFileResponse.model_validate(media_file),
            file_url=f"/api/v1/media/{media_file.id}/file",
            message="Файл отчета успешно загружен"
        )

    except Exception as e:
        logger.error(f"Failed to upload report media: {e}")
        raise HTTPException(status_code=500, detail="Ошибка загрузки файла отчета")


@router.get("/search", response_model=MediaSearchResponse)
async def search_media(
    query: Optional[str] = Query(None, description="Текстовый поиск"),
    request_numbers: Optional[str] = Query(None, description="Номера заявок через запятую"),
    tags: Optional[str] = Query(None, description="Теги через запятую"),
    date_from: Optional[datetime] = Query(None, description="Дата начала"),
    date_to: Optional[datetime] = Query(None, description="Дата окончания"),
    file_types: Optional[str] = Query(None, description="Типы файлов через запятую"),
    categories: Optional[str] = Query(None, description="Категории через запятую"),
    telegram_file_id: Optional[str] = Query(None, description="Telegram file_id"),
    uploaded_by: Optional[int] = Query(None, description="ID загрузившего пользователя"),
    status: MediaStatusEnum = Query(default=MediaStatusEnum.ACTIVE, description="Статус файлов"),
    limit: int = Query(default=50, ge=1, le=200, description="Лимит результатов"),
    offset: int = Query(default=0, ge=0, description="Смещение"),
    search_service: MediaSearchService = Depends(get_search_service)
):
    """
    Поиск медиа-файлов с фильтрами
    """
    try:
        # Обработка параметров
        request_numbers_list = None
        if request_numbers:
            request_numbers_list = [req.strip() for req in request_numbers.split(",") if req.strip()]

        tags_list = None
        if tags:
            tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

        file_types_list = None
        if file_types:
            file_types_list = [ft.strip() for ft in file_types.split(",") if ft.strip()]

        categories_list = None
        if categories:
            categories_list = [cat.strip() for cat in categories.split(",") if cat.strip()]

        # Выполняем поиск
        result = await search_service.search_media(
            query=query,
            request_numbers=request_numbers_list,
            tags=tags_list,
            date_from=date_from,
            date_to=date_to,
            file_types=file_types_list,
            categories=categories_list,
            telegram_file_id=telegram_file_id,
            uploaded_by=uploaded_by,
            status=status.value,
            limit=limit,
            offset=offset
        )

        # Преобразуем результаты в схемы
        media_files = [MediaFileResponse.model_validate(mf) for mf in result["results"]]

        return MediaSearchResponse(
            results=media_files,
            total_count=result["total_count"],
            limit=result["limit"],
            offset=result["offset"],
            has_more=result["has_more"],
            filters_applied=result["filters_applied"]
        )

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail="Ошибка поиска")


@router.get("/statistics", response_model=MediaStatisticsResponse)
async def get_media_statistics(
    search_service: MediaSearchService = Depends(get_search_service)
):
    """
    Получение статистики медиа-файлов
    """
    try:
        stats = await search_service.get_media_statistics()
        return MediaStatisticsResponse(**stats)

    except Exception as e:
        logger.error(f"Failed to get media statistics: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения статистики")


@router.get("/tags/popular", response_model=List[MediaTagResponse])
async def get_popular_tags(
    limit: int = Query(default=20, ge=1, le=100, description="Количество тегов"),
    search_service: MediaSearchService = Depends(get_search_service)
):
    """
    Получение популярных тегов
    """
    try:
        tags = await search_service.get_popular_tags(limit=limit)
        return [MediaTagResponse(**tag) for tag in tags]

    except Exception as e:
        logger.error(f"Failed to get popular tags: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения популярных тегов")


@router.get("/{media_id}/file")
async def get_media_file_stream(
    media_id: int,
    storage_service: MediaStorageService = Depends(get_storage_service),
    db: Session = Depends(get_db)
):
    """
    Stream media file bytes (token stays server-side)
    """
    try:
        from app.models.media import MediaFile

        media_file = db.query(MediaFile).filter(MediaFile.id == media_id).first()
        if not media_file:
            raise HTTPException(status_code=404, detail="Медиа-файл не найден")

        file_bytes, content_type = await storage_service.telegram.download_file(
            media_file.telegram_file_id
        )
        # mime_type stored at upload time can be wrong: some mobile pickers
        # report image/png for JPEGs (or vice-versa) and Telegram CDN
        # returns application/octet-stream regardless. Sniff the magic
        # bytes here — that's the authoritative content type and the only
        # one the browser will agree to render in <img>/<video>.
        effective_type = _sniff_image_mime(file_bytes) or (
            media_file.mime_type
            if media_file.mime_type and media_file.mime_type != "application/octet-stream"
            else content_type
        )
        safe_filename = (media_file.original_filename or "file").replace('"', "").replace("\r", "").replace("\n", "")[:255]
        return Response(
            content=file_bytes,
            media_type=effective_type,
            headers={
                "Content-Disposition": f'inline; filename="{safe_filename}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stream media file {media_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения файла")


@router.get("/telegram/{telegram_file_id}", response_model=MediaTelegramLookupResponse)
async def get_media_by_telegram_file_id(
    telegram_file_id: str,
    storage_service: MediaStorageService = Depends(get_storage_service),
    db: Session = Depends(get_db)
):
    """
    Получение информации о медиа-файле по Telegram file_id
    """
    try:
        from app.models.media import MediaFile
        media_file = db.query(MediaFile).filter(MediaFile.telegram_file_id == telegram_file_id).first()

        if media_file:
            return MediaTelegramLookupResponse(
                source="database",
                telegram_file_id=media_file.telegram_file_id,
                telegram_file_unique_id=media_file.telegram_file_unique_id,
                file_size=media_file.file_size,
                file_path=None,
                file_url=f"/api/v1/media/{media_file.id}/file",
                media_file=MediaFileResponse.model_validate(media_file)
            )

        # Fallback to Telegram API — file not in our DB
        try:
            file_info = await storage_service.telegram.get_file(telegram_file_id)
        except Exception:
            logger.warning(f"Telegram file {telegram_file_id} not found via API")
            raise HTTPException(status_code=404, detail="Файл в Telegram не найден или недоступен")

        return MediaTelegramLookupResponse(
            source="telegram",
            telegram_file_id=telegram_file_id,
            telegram_file_unique_id=getattr(file_info, "file_unique_id", None),
            file_size=getattr(file_info, "file_size", None),
            file_path=getattr(file_info, "file_path", None),
            file_url=f"/api/v1/media/telegram/{telegram_file_id}/file",
            media_file=None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get media by telegram file_id {telegram_file_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения медиа-файла")


@router.get("/telegram/{telegram_file_id}/file")
async def stream_telegram_file(
    telegram_file_id: str,
    storage_service: MediaStorageService = Depends(get_storage_service),
):
    """
    Stream file bytes by telegram_file_id (for files not in DB).
    Token stays server-side.
    """
    try:
        file_bytes, content_type = await storage_service.telegram.download_file(
            telegram_file_id
        )
        return Response(
            content=file_bytes,
            media_type=content_type,
            headers={
                "Content-Disposition": 'inline; filename="file"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    except TelegramAPIError:
        raise HTTPException(status_code=404, detail="Файл в Telegram не найден или недоступен")
    except Exception as e:
        logger.error(f"Failed to stream telegram file {telegram_file_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения файла")


@router.get("/{media_id}", response_model=MediaFileResponse)
async def get_media(
    media_id: int,
    db: Session = Depends(get_db)
):
    """
    Получение информации о медиа-файле по ID
    """
    try:
        from app.models.media import MediaFile

        media_file = db.query(MediaFile).filter(MediaFile.id == media_id).first()
        if not media_file:
            raise HTTPException(status_code=404, detail="Медиа-файл не найден")

        return MediaFileResponse.model_validate(media_file)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get media {media_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения медиа-файла")


@router.get("/{media_id}/url", response_model=MediaFileUrlResponse)
async def get_media_url(
    media_id: int,
    storage_service: MediaStorageService = Depends(get_storage_service),
    db: Session = Depends(get_db)
):
    """
    Получение URL для доступа к медиа-файлу
    """
    try:
        from app.models.media import MediaFile

        media_file = db.query(MediaFile).filter(MediaFile.id == media_id).first()
        if not media_file:
            raise HTTPException(status_code=404, detail="Медиа-файл не найден")

        return MediaFileUrlResponse(
            media_file_id=media_id,
            file_url=f"/api/v1/media/{media_id}/file",
            expires_at=None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get media URL {media_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения URL")


@router.put("/{media_id}/tags", response_model=MediaFileResponse)
async def update_media_tags(
    media_id: int,
    request: MediaUpdateTagsRequest,
    storage_service: MediaStorageService = Depends(get_storage_service)
):
    """
    Обновление тегов медиа-файла
    """
    try:
        media_file = await storage_service.update_media_tags(
            media_file_id=media_id,
            tags=request.tags,
            replace=request.replace
        )

        if not media_file:
            raise HTTPException(status_code=404, detail="Медиа-файл не найден")

        return MediaFileResponse.model_validate(media_file)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update tags for media {media_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка обновления тегов")


@router.post("/{media_id}/archive")
async def archive_media(
    media_id: int,
    request: MediaArchiveRequest,
    storage_service: MediaStorageService = Depends(get_storage_service)
):
    """
    Архивация медиа-файла
    """
    try:
        success = await storage_service.archive_media(
            media_file_id=media_id,
            archive_reason=request.archive_reason
        )

        if not success:
            raise HTTPException(status_code=404, detail="Медиа-файл не найден или не может быть заархивирован")

        return {"message": "Медиа-файл успешно заархивирован", "media_id": media_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to archive media {media_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка архивации")


@router.delete("/{media_id}")
async def delete_media(
    media_id: int,
    storage_service: MediaStorageService = Depends(get_storage_service)
):
    """
    Удаление медиа-файла
    """
    try:
        success = await storage_service.delete_media(media_file_id=media_id)

        if not success:
            raise HTTPException(status_code=404, detail="Медиа-файл не найден или не может быть удален")

        return {"message": "Медиа-файл успешно удален", "media_id": media_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete media {media_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка удаления")


@router.get("/request/{request_number}", response_model=List[MediaFileResponse])
async def get_request_media(
    request_number: str,
    category: Optional[MediaCategoryEnum] = Query(None, description="Фильтр по категории"),
    limit: int = Query(default=50, ge=1, le=200, description="Лимит результатов"),
    storage_service: MediaStorageService = Depends(get_storage_service)
):
    """
    Получение всех медиа-файлов для заявки
    """
    try:
        media_files = await storage_service.get_request_media(
            request_number=request_number,
            category=category.value if category else None,
            limit=limit
        )

        return [MediaFileResponse.model_validate(mf) for mf in media_files]

    except Exception as e:
        logger.error(f"Failed to get media for request {request_number}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения медиа для заявки")


@router.get("/request/{request_number}/timeline", response_model=MediaTimelineResponse)
async def get_request_timeline(
    request_number: str,
    search_service: MediaSearchService = Depends(get_search_service)
):
    """
    Получение временной линии медиа-файлов для заявки
    """
    try:
        timeline = await search_service.get_request_media_timeline(request_number)

        return MediaTimelineResponse(
            request_number=request_number,
            timeline=timeline,
            total_files=len(timeline)
        )

    except Exception as e:
        logger.error(f"Failed to get timeline for request {request_number}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения временной линии")



@router.post("/search/date-range", response_model=MediaDateRangeResponse)
async def search_by_date_range(
    request: MediaDateRangeRequest,
    search_service: MediaSearchService = Depends(get_search_service)
):
    """
    Поиск медиа-файлов по диапазону дат с группировкой
    """
    try:
        categories_list = None
        if request.categories:
            categories_list = [cat.value for cat in request.categories]

        result = await search_service.search_by_date_range(
            date_from=request.date_from,
            date_to=request.date_to,
            group_by=request.group_by,
            categories=categories_list
        )

        return MediaDateRangeResponse(**result)

    except Exception as e:
        logger.error(f"Failed to search by date range: {e}")
        raise HTTPException(status_code=500, detail="Ошибка поиска по дате")


@router.get("/{media_id}/similar", response_model=List[MediaFileResponse])
async def find_similar_media(
    media_id: int,
    similarity_threshold: float = Query(default=0.7, ge=0.0, le=1.0, description="Порог схожести"),
    limit: int = Query(default=10, ge=1, le=50, description="Лимит результатов"),
    search_service: MediaSearchService = Depends(get_search_service)
):
    """
    Поиск похожих медиа-файлов
    """
    try:
        similar_files = await search_service.find_similar_media(
            media_file_id=media_id,
            similarity_threshold=similarity_threshold,
            limit=limit
        )

        return [MediaFileResponse.model_validate(mf) for mf in similar_files]

    except Exception as e:
        logger.error(f"Failed to find similar media for {media_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка поиска похожих файлов")
