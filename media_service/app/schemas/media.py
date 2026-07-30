"""
Pydantic схемы для Media API
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator
from enum import Enum


class StrictSchema(BaseModel):
    """Base class that rejects unexpected fields (defense-in-depth)."""
    model_config = ConfigDict(extra="forbid")


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
    FEEDBACK_PHOTO = "feedback_photo"
    # Контроль доступа (один канал «access», различение по category)
    ACCESS_PLATE = "access_plate"
    ACCESS_OVERVIEW = "access_overview"


class MediaStatusEnum(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"
    # Транзиентные состояния саги архивации/удаления
    # (media_storage._archive_or_delete_saga): резервирование коммитится ДО
    # Telegram-I/O, поэтому строка реально наблюдаема в этих статусах. Обязаны
    # быть в enum'е: `status` типизирован им в MediaFileResponse, и без этих
    # членов любой ответ, включающий такую строку, падал бы 500 на валидации.
    # Больнее всего на bare-эндпоинте GET /media/{id}: приватный прокси UK
    # (api/routes/media_proxy.py:proxy_media_file) зовёт его на КАЖДУЮ картинку,
    # чтобы разрешить media_id → request_number. Список GET /media/request/{n}
    # тут не страдает — он и так фильтрует status == "active".
    ARCHIVING = "archiving"
    DELETING = "deleting"


# Request schemas
class MediaUploadRequest(StrictSchema):
    request_number: str = Field(..., description="Номер заявки")
    category: MediaCategoryEnum = Field(default=MediaCategoryEnum.REQUEST_PHOTO, description="Категория файла")
    description: Optional[str] = Field(None, max_length=500, description="Описание файла")
    tags: Optional[List[str]] = Field(default=[], description="Теги")
    uploaded_by: Optional[int] = Field(None, description="ID пользователя, загрузившего файл")


class MediaSearchRequest(StrictSchema):
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


class MediaUpdateTagsRequest(StrictSchema):
    tags: List[str] = Field(..., description="Новые теги")
    replace: bool = Field(default=False, description="Заменить все теги или добавить к существующим")


class MediaArchiveRequest(StrictSchema):
    archive_reason: Optional[str] = Field(None, max_length=255, description="Причина архивации")


class PreviewWarmRequest(StrictSchema):
    # Потолок на пачку: прогрев идёт через семафор скачиваний, и слишком длинный
    # список держал бы соединение вызывающего минутами. UK шлёт медиа одного
    # отчёта (до 8) либо пачку свежих опубликованных.
    media_ids: List[int] = Field(..., min_length=1, max_length=200,
                                 description="ID медиа, для которых нужно построить превью")


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
    # Все четыре — nullable в БД (`MediaFile`), поэтому и здесь Optional. Раньше
    # они были объявлены обязательными, и ОДНА строка с NULL валила 500 на всю
    # выдачу `GET /media/request/{n}` (List[MediaFileResponse]) — тот же класс
    # дефекта, что уже закрыт валидатором `tags` ниже. Живой upload-путь их
    # всегда заполняет (endpoint отклоняет запрос без имени файла), так что
    # None здесь — про исторические и вручную созданные строки.
    #
    # `file_size` НЕ приводим к 0: потребитель (UK, `_filter_and_cap`) трактует
    # None как «размер неизвестен → в публичный отчёт не пускать». Ноль прошёл
    # бы проверку лимита и втащил в открытую ленту файл неизвестного веса.
    original_filename: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    description: Optional[str] = None
    caption: Optional[str] = None
    # Домен-нейтрально: у access-медиа (контроль доступа) request_number = None,
    # идентификатор хранится в тегах (ref:...). Для заявок поле как и раньше.
    request_number: Optional[str] = None
    uploaded_by_user_id: int
    category: MediaCategoryEnum
    tags: List[str] = []
    upload_source: Optional[str] = None
    status: MediaStatusEnum
    uploaded_at: datetime

    # `MediaFile.tags` — JSON-столбец БЕЗ NOT NULL, то есть в БД законно лежит
    # NULL (строки, залитые до появления тегирования, и любой путь, который их
    # не выставляет). Дефолт `= []` от этого не спасает: он применяется только
    # когда ключа нет, а не когда пришёл явный None — валидация падала, и один
    # такой файл ронял 500 на ВСЮ выдачу GET /media/request/{n}
    # (List[MediaFileResponse]), то есть галерею заявки целиком.
    @field_validator("tags", mode="before")
    @classmethod
    def _tags_none_to_empty(cls, v):
        return [] if v is None else v
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

    # То же, что в MediaFileResponse: NULL в столбце tags законен, и один такой
    # элемент не должен ронять весь timeline.
    @field_validator("tags", mode="before")
    @classmethod
    def _tags_none_to_empty(cls, v):
        return [] if v is None else v


class MediaTimelineResponse(BaseModel):
    request_number: str
    timeline: List[MediaTimelineItem]
    total_files: int


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
