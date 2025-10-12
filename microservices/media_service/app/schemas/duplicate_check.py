"""
Схемы для системы проверки дубликатов файлов
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from enum import Enum

from app.services.duplicate_checker import DuplicatePolicy


class DuplicateCheckRequest(BaseModel):
    """Запрос на проверку дубликатов файла"""
    request_number: str = Field(..., description="Номер заявки")
    category: str = Field(..., description="Категория файла")
    policy: DuplicatePolicy = Field(default=DuplicatePolicy.STRICT, description="Политика обработки дубликатов")


class DuplicateCheckResponse(BaseModel):
    """Ответ на запрос проверки дубликатов"""
    is_duplicate: bool = Field(..., description="Является ли файл дубликатом")
    existing_file_id: Optional[int] = Field(None, description="ID существующего файла")
    policy_applied: Optional[str] = Field(None, description="Примененная политика")
    message: Optional[str] = Field(None, description="Сообщение о результате")
    action_taken: Optional[str] = Field(None, description="Действие, которое будет выполнено")


class DuplicateStatsResponse(BaseModel):
    """Статистика по дубликатам"""
    total_files: int = Field(..., description="Общее количество файлов")
    unique_files: int = Field(..., description="Количество уникальных файлов")
    potential_duplicates: int = Field(..., description="Количество потенциальных дубликатов")
    duplicate_percentage: float = Field(..., description="Процент дубликатов")


class DuplicateCleanupRequest(BaseModel):
    """Запрос на очистку дубликатов"""
    dry_run: bool = Field(default=True, description="Только показать что будет удалено, не удалять реально")


class DuplicateCleanupResponse(BaseModel):
    """Ответ на запрос очистки дубликатов"""
    groups_found: int = Field(..., description="Количество найденных групп дубликатов")
    files_to_remove: int = Field(..., description="Количество файлов для удаления")
    space_saved_bytes: int = Field(..., description="Количество освобожденных байт")
    dry_run: bool = Field(..., description="Был ли это dry run")
    error: Optional[str] = Field(None, description="Ошибка если произошла")


class DuplicateConfigRequest(BaseModel):
    """Запрос на изменение конфигурации дубликатов"""
    enabled: bool = Field(..., description="Включена ли проверка дубликатов")
    default_policy: DuplicatePolicy = Field(..., description="Политика по умолчанию")
    hash_algorithm: str = Field(default="sha256", description="Алгоритм хеширования")


class DuplicateConfigResponse(BaseModel):
    """Ответ с конфигурацией дубликатов"""
    enabled: bool = Field(..., description="Включена ли проверка дубликатов")
    default_policy: str = Field(..., description="Политика по умолчанию")
    hash_algorithm: str = Field(..., description="Алгоритм хеширования")
    check_on_upload: bool = Field(..., description="Проверять при загрузке")
    log_duplicate_attempts: bool = Field(..., description="Логировать попытки дубликатов")


class MediaUploadWithDuplicateCheckRequest(BaseModel):
    """Запрос на загрузку файла с проверкой дубликатов"""
    request_number: str = Field(..., description="Номер заявки")
    category: str = Field(..., description="Категория файла")
    description: Optional[str] = Field(None, description="Описание файла")
    tags: Optional[str] = Field(None, description="Теги через запятую")
    uploaded_by: Optional[int] = Field(None, description="ID пользователя")
    duplicate_policy: DuplicatePolicy = Field(default=DuplicatePolicy.STRICT, description="Политика обработки дубликатов")


class MediaUploadWithDuplicateCheckResponse(BaseModel):
    """Ответ на загрузку файла с проверкой дубликатов"""
    media_file_id: int = Field(..., description="ID загруженного файла")
    file_url: str = Field(..., description="URL файла")
    message: str = Field(..., description="Сообщение о результате")
    duplicate_check_result: Optional[DuplicateCheckResponse] = Field(None, description="Результат проверки дубликатов")
    was_duplicate: bool = Field(default=False, description="Был ли файл дубликатом")
