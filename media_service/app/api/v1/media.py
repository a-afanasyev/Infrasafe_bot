"""
API эндпоинты для работы с медиа-файлами
"""

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services import MediaStorageService, MediaSearchService
from app.schemas import (
    MediaUploadRequest, MediaSearchRequest, MediaUpdateTagsRequest,
    MediaArchiveRequest, MediaDateRangeRequest, MediaFileResponse,
    MediaSearchResponse, MediaStatisticsResponse, MediaTimelineResponse,
    MediaDateRangeResponse, MediaUploadResponse, MediaFileUrlResponse,
    ErrorResponse, MediaTagResponse, MediaCategoryEnum, FileTypeEnum,
    MediaStatusEnum
)
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])


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

        # Получаем URL файла
        file_url = await storage_service.get_media_file_url(media_file)

        logger.info(f"Media uploaded successfully: {media_file.id} for request {request_number}")

        return MediaUploadResponse(
            media_file=MediaFileResponse.model_validate(media_file),
            file_url=file_url,
            message="Файл успешно загружен"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload media: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки файла: {str(e)}")


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

        file_url = await storage_service.get_media_file_url(media_file)

        logger.info(f"Report media uploaded successfully: {media_file.id}")

        return MediaUploadResponse(
            media_file=MediaFileResponse.model_validate(media_file),
            file_url=file_url,
            message="Файл отчета успешно загружен"
        )

    except Exception as e:
        logger.error(f"Failed to upload report media: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки файла отчета: {str(e)}")


@router.get("/search", response_model=MediaSearchResponse)
async def search_media(
    query: Optional[str] = Query(None, description="Текстовый поиск"),
    request_numbers: Optional[str] = Query(None, description="Номера заявок через запятую"),
    tags: Optional[str] = Query(None, description="Теги через запятую"),
    date_from: Optional[datetime] = Query(None, description="Дата начала"),
    date_to: Optional[datetime] = Query(None, description="Дата окончания"),
    file_types: Optional[str] = Query(None, description="Типы файлов через запятую"),
    categories: Optional[str] = Query(None, description="Категории через запятую"),
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
        raise HTTPException(status_code=500, detail=f"Ошибка поиска: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Ошибка получения статистики: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Ошибка получения популярных тегов: {str(e)}")


@router.get("/{media_id}/file")
async def get_media_file_redirect(
    media_id: int,
    storage_service: MediaStorageService = Depends(get_storage_service),
    db: Session = Depends(get_db)
):
    """
    Редирект на прямую ссылку медиа-файла
    """
    try:
        from app.models.media import MediaFile
        from fastapi.responses import RedirectResponse

        media_file = db.query(MediaFile).filter(MediaFile.id == media_id).first()
        if not media_file:
            raise HTTPException(status_code=404, detail="Медиа-файл не найден")

        file_url = await storage_service.get_media_file_url(media_file)
        return RedirectResponse(url=file_url)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to redirect to media file {media_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения файла: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Ошибка получения медиа-файла: {str(e)}")


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

        file_url = await storage_service.get_media_file_url(media_file)

        return MediaFileUrlResponse(
            media_file_id=media_id,
            file_url=file_url,
            expires_at=None  # Telegram URLs не имеют явного времени истечения
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get media URL {media_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения URL: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Ошибка обновления тегов: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Ошибка архивации: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Ошибка удаления: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Ошибка получения медиа для заявки: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Ошибка получения временной линии: {str(e)}")



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
        raise HTTPException(status_code=500, detail=f"Ошибка поиска по дате: {str(e)}")


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
        raise HTTPException(status_code=500, detail=f"Ошибка поиска похожих файлов: {str(e)}")