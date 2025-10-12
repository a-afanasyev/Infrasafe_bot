"""
API эндпоинты для работы с проверкой дубликатов файлов
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import JSONResponse

from app.services.media_storage import MediaStorageService
from app.services.duplicate_checker import DuplicateCheckerService, DuplicatePolicy
from app.core.exceptions import (
    FileUploadFailed, InvalidFileType, FileTooLarge, ValidationError,
    DuplicateFileDetected, DuplicatePolicyViolation, InternalServerError
)
from app.core.error_codes import MediaErrorCode
from app.schemas.duplicate_check import (
    DuplicateCheckRequest, DuplicateCheckResponse, DuplicateStatsResponse,
    DuplicateCleanupRequest, DuplicateCleanupResponse, DuplicateConfigResponse,
    MediaUploadWithDuplicateCheckRequest, MediaUploadWithDuplicateCheckResponse
)
from app.schemas.media import MediaFileResponse, ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/duplicate-check", tags=["duplicate-check"])


# Dependency для сервисов
async def get_storage_service() -> MediaStorageService:
    return MediaStorageService()


async def get_duplicate_checker_service() -> DuplicateCheckerService:
    return DuplicateCheckerService()


@router.post("/check", response_model=DuplicateCheckResponse)
async def check_file_duplicate(
    file: UploadFile = File(..., description="Файл для проверки на дубликаты"),
    request_number: str = Form(..., description="Номер заявки"),
    category: str = Form(..., description="Категория файла"),
    policy: DuplicatePolicy = Form(default=DuplicatePolicy.STRICT, description="Политика обработки дубликатов"),
    duplicate_checker: DuplicateCheckerService = Depends(get_duplicate_checker_service)
):
    """
    Проверка файла на дубликаты без загрузки
    """
    try:
        # Читаем содержимое файла
        file_data = await file.read()
        
        # Выполняем проверку дубликатов
        result = await duplicate_checker.check_duplicate(
            request_number=request_number,
            category=category,
            file_data=file_data,
            policy=policy
        )
        
        # Преобразуем результат в схему ответа
        response = DuplicateCheckResponse(
            is_duplicate=result.is_duplicate,
            existing_file_id=result.existing_file.id if result.existing_file else None,
            policy_applied=result.policy_applied.value if result.policy_applied else None,
            message=result.message,
            action_taken=result.action_taken
        )
        
        logger.info(f"Duplicate check completed for request {request_number}: {result.is_duplicate}")
        return response
        
    except Exception as e:
        logger.error(f"Error checking duplicate: {e}")
        raise InternalServerError(
            details={
                "error": str(e),
                "request_number": request_number,
                "category": category
            }
        )


@router.post("/upload", response_model=MediaUploadWithDuplicateCheckResponse)
async def upload_media_with_duplicate_check(
    file: UploadFile = File(..., description="Медиа-файл для загрузки"),
    request_number: str = Form(..., description="Номер заявки"),
    category: str = Form(..., description="Категория файла"),
    description: str = Form(None, description="Описание файла"),
    tags: str = Form(None, description="Теги через запятую"),
    uploaded_by: int = Form(None, description="ID пользователя"),
    duplicate_policy: DuplicatePolicy = Form(default=DuplicatePolicy.STRICT, description="Политика обработки дубликатов"),
    storage_service: MediaStorageService = Depends(get_storage_service)
):
    """
    Загрузка медиа-файла с проверкой дубликатов
    """
    try:
        # Читаем содержимое файла
        file_data = await file.read()
        
        # Обработка тегов
        tags_list = []
        if tags:
            tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        
        # Загружаем файл с проверкой дубликатов
        result = await storage_service.upload_request_media_with_duplicate_check(
            request_number=request_number,
            file_data=file_data,
            filename=file.filename,
            content_type=file.content_type,
            category=category,
            description=description,
            tags=tags_list,
            uploaded_by=uploaded_by,
            duplicate_policy=duplicate_policy
        )
        
        if not result["success"]:
            if result["was_duplicate"]:
                raise DuplicateFileDetected(
                    details={
                        "message": result["message"],
                        "request_number": request_number,
                        "category": category,
                        "filename": file.filename
                    }
                )
            else:
                raise FileUploadFailed(
                    details={
                        "message": result["message"],
                        "request_number": request_number,
                        "category": category,
                        "filename": file.filename
                    }
                )
        
        # Преобразуем результат в схему ответа
        response = MediaUploadWithDuplicateCheckResponse(
            media_file_id=result["media_file"].id,
            file_url=result["file_url"],
            message=result["message"],
            was_duplicate=result["was_duplicate"]
        )
        
        # Добавляем результат проверки дубликатов если есть
        if result.get("duplicate_check_result"):
            duplicate_result = result["duplicate_check_result"]
            response.duplicate_check_result = DuplicateCheckResponse(
                is_duplicate=duplicate_result.is_duplicate,
                existing_file_id=duplicate_result.existing_file.id if duplicate_result.existing_file else None,
                policy_applied=duplicate_result.policy_applied.value if duplicate_result.policy_applied else None,
                message=duplicate_result.message,
                action_taken=duplicate_result.action_taken
            )
        
        logger.info(f"Media uploaded with duplicate check: {result['media_file'].id}")
        return response
        
    except (FileUploadFailed, InvalidFileType, FileTooLarge, DuplicateFileDetected, 
            DuplicatePolicyViolation, ValidationError, InternalServerError):
        raise
    except Exception as e:
        logger.error(f"Error uploading media with duplicate check: {e}")
        raise FileUploadFailed(
            details={
                "error": str(e),
                "request_number": request_number,
                "filename": file.filename
            }
        )


@router.get("/stats", response_model=DuplicateStatsResponse)
async def get_duplicate_stats(
    duplicate_checker: DuplicateCheckerService = Depends(get_duplicate_checker_service)
):
    """
    Получение статистики по дубликатам файлов
    """
    try:
        stats = await duplicate_checker.get_duplicate_stats()
        
        response = DuplicateStatsResponse(
            total_files=stats["total_files"],
            unique_files=stats["unique_files"],
            potential_duplicates=stats["potential_duplicates"],
            duplicate_percentage=stats["duplicate_percentage"]
        )
        
        logger.info(f"Duplicate stats retrieved: {stats['potential_duplicates']} duplicates found")
        return response
        
    except Exception as e:
        logger.error(f"Error getting duplicate stats: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения статистики: {str(e)}")


@router.post("/cleanup", response_model=DuplicateCleanupResponse)
async def cleanup_duplicates(
    request: DuplicateCleanupRequest,
    duplicate_checker: DuplicateCheckerService = Depends(get_duplicate_checker_service)
):
    """
    Очистка дубликатов файлов
    """
    try:
        cleanup_result = await duplicate_checker.cleanup_duplicates(dry_run=request.dry_run)
        
        response = DuplicateCleanupResponse(
            groups_found=cleanup_result["groups_found"],
            files_to_remove=cleanup_result["files_to_remove"],
            space_saved_bytes=cleanup_result["space_saved_bytes"],
            dry_run=cleanup_result["dry_run"],
            error=cleanup_result.get("error")
        )
        
        action = "completed" if not request.dry_run else "dry run completed"
        logger.info(f"Duplicate cleanup {action}: {cleanup_result['files_to_remove']} files processed")
        return response
        
    except Exception as e:
        logger.error(f"Error cleaning up duplicates: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка очистки дубликатов: {str(e)}")


@router.get("/config", response_model=DuplicateConfigResponse)
async def get_duplicate_config(
    duplicate_checker: DuplicateCheckerService = Depends(get_duplicate_checker_service)
):
    """
    Получение текущей конфигурации системы проверки дубликатов
    """
    try:
        response = DuplicateConfigResponse(
            enabled=True,  # Система всегда включена
            default_policy=duplicate_checker.default_policy.value,
            hash_algorithm="sha256",
            check_on_upload=True,
            log_duplicate_attempts=True
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting duplicate config: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения конфигурации: {str(e)}")


@router.post("/config", response_model=DuplicateConfigResponse)
async def update_duplicate_config(
    config: DuplicateConfigResponse,
    duplicate_checker: DuplicateCheckerService = Depends(get_duplicate_checker_service)
):
    """
    Обновление конфигурации системы проверки дубликатов
    """
    try:
        # Обновляем политику по умолчанию
        if hasattr(DuplicatePolicy, config.default_policy.upper()):
            duplicate_checker.default_policy = DuplicatePolicy(config.default_policy.upper())
        
        logger.info(f"Duplicate config updated: policy={config.default_policy}")
        
        return config
        
    except Exception as e:
        logger.error(f"Error updating duplicate config: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка обновления конфигурации: {str(e)}")


@router.get("/health")
async def duplicate_check_health():
    """
    Проверка здоровья системы проверки дубликатов
    """
    return {
        "status": "healthy",
        "service": "duplicate-check",
        "version": "1.0.0",
        "features": {
            "hash_calculation": "enabled",
            "duplicate_detection": "enabled",
            "policy_management": "enabled",
            "cleanup_tools": "enabled"
        }
    }
