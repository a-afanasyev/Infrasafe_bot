"""
Pydantic схемы для Media API
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class FileTypeEnum(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    DOCUMENT = "document"


class MediaCategoryEnum(str, Enum):
    REQUEST_PHOTO = "request_photo"
    COMPLETION_PHOTO = "completion_photo"
    DAMAGE_PHOTO = "damage_photo"
    MATERIALS_PHOTO = "materials_photo"
    PROCESS_VIDEO = "process_video"
    DOCUMENT = "document"
    ARCHIVE = "archive"


class MediaStatusEnum(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


# Request schemas
class MediaUploadRequest(BaseModel):
    request_number: str = Field(..., description="Номер заявки")
    category: MediaCategoryEnum = Field(default=MediaCategoryEnum.REQUEST_PHOTO, description="Категория файла")
    description: Optional[str] = Field(None, max_length=500, description="Описание файла")
    tags: Optional[List[str]] = Field(default=[], description="Теги")
    uploaded_by: Optional[int] = Field(None, description="ID пользователя, загрузившего файл")


class MediaSearchRequest(BaseModel):
    query: Optional[str] = Field(None, description="Текстовый поиск")
    request_numbers: Optional[List[str]] = Field(None, description="Номера заявок")
    tags: Optional[List[str]] = Field(None, description="Теги для фильтрации")
    date_from: Optional[datetime] = Field(None, description="Дата начала")
    date_to: Optional[datetime] = Field(None, description="Дата окончания")
    file_types: Optional[List[FileTypeEnum]] = Field(None, description="Типы файлов")
    categories: Optional[List[MediaCategoryEnum]] = Field(None, description="Категории")
    telegram_file_id: Optional[str] = Field(None, description="Telegram file_id")
    uploaded_by: Optional[int] = Field(None, description="ID загрузившего пользователя")
    status: MediaStatusEnum = Field(default=MediaStatusEnum.ACTIVE, description="Статус файлов")
    limit: int = Field(default=50, ge=1, le=200, description="Лимит результатов")
    offset: int = Field(default=0, ge=0, description="Смещение для пагинации")


class MediaUpdateTagsRequest(BaseModel):
    tags: List[str] = Field(..., description="Новые теги")
    replace: bool = Field(default=False, description="Заменить все теги или добавить к существующим")


class MediaArchiveRequest(BaseModel):
    archive_reason: Optional[str] = Field(None, max_length=255, description="Причина архивации")


class MediaDateRangeRequest(BaseModel):
    date_from: datetime = Field(..., description="Дата начала")
    date_to: datetime = Field(..., description="Дата окончания")
    group_by: str = Field(default="day", pattern="^(day|week|month)$", description="Группировка")
    categories: Optional[List[MediaCategoryEnum]] = Field(None, description="Фильтр по категориям")


# Response schemas
class MediaTagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tag: str
    count: int
    category: Optional[str] = None
    color: Optional[str] = None
    is_system: bool = False


class MediaFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_channel_id: int
    telegram_message_id: int
    telegram_file_id: str
    file_type: FileTypeEnum
    original_filename: str
    file_size: int
    mime_type: str
    description: Optional[str] = None
    caption: Optional[str] = None
    request_number: str
    uploaded_by_user_id: int
    category: MediaCategoryEnum
    tags: List[str] = []
    upload_source: str
    status: MediaStatusEnum
    uploaded_at: datetime
    archived_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MediaSearchResponse(BaseModel):
    results: List[MediaFileResponse]
    total_count: int
    limit: int
    offset: int
    has_more: bool
    filters_applied: Dict[str, Any]


class MediaTelegramLookupResponse(BaseModel):
    source: Literal["database", "telegram"]
    telegram_file_id: str
    telegram_file_unique_id: Optional[str] = None
    file_size: Optional[int] = None
    file_path: Optional[str] = None
    file_url: Optional[str] = None
    media_file: Optional[MediaFileResponse] = None


class MediaStatisticsResponse(BaseModel):
    total_files: int
    total_size_bytes: int
    total_size_mb: float
    file_types: List[Dict[str, Any]]
    categories: List[Dict[str, Any]]
    daily_uploads: List[Dict[str, Any]]
    top_tags: List[MediaTagResponse]


class MediaTimelineItem(BaseModel):
    id: int
    timestamp: str
    file_type: FileTypeEnum
    category: MediaCategoryEnum
    description: Optional[str] = None
    tags: List[str] = []
    file_size: int
    filename: str


class MediaTimelineResponse(BaseModel):
    request_number: str
    timeline: List[MediaTimelineItem]
    total_files: int


class MediaDateRangeResponse(BaseModel):
    date_range: Dict[str, str]
    group_by: str
    categories: Optional[List[str]] = None
    data: List[Dict[str, Any]]
    total_files: int
    total_size_mb: float


class MediaUploadResponse(BaseModel):
    media_file: MediaFileResponse
    file_url: Optional[str] = None
    message: str = "Файл успешно загружен"


class MediaFileUrlResponse(BaseModel):
    media_file_id: int
    file_url: Optional[str] = None
    expires_at: Optional[datetime] = None


class MediaBulkOperationResponse(BaseModel):
    success_count: int
    failed_count: int
    errors: List[str] = []
    message: str


# Error response schemas
class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ValidationErrorResponse(BaseModel):
    error: str = "validation_error"
    message: str
    errors: List[Dict[str, Any]]


# Health check schema
class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "media-service"
    version: str = "1.0.0"
    timestamp: datetime
    dependencies: Dict[str, str] = {}
