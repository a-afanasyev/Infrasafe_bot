"""Публичный API клиентского SDK Media Service.

Документированная точка входа (см. media_service/README.md «Интеграция с
основным ботом»):

    from media_service.client import MediaServiceClient, BotMediaIntegration
    from media_service.client import upload_request_photo, upload_completion_photo

Раньше файл был пуст → документированный импорт падал; потребители обходили
это через ``sys.path.insert(<client_dir>)`` + ``from media_client import ...``.

Примечание по деплою: in-repo потребители (бот — ``uk_management_bot/
integrations/media_client.py``; access_control — ``integrations/media.py``)
намеренно держат свои клиенты, т.к. их образы не содержат ``media_service/``.
Этот SDK — эталонный/публикуемый клиент сервиса (вбит в media-образ,
``Dockerfile: COPY client/``).
"""
from .media_client import (
    MediaServiceClient,
    upload_request_photo,
    upload_completion_photo,
)
from .integration_helper import (
    BotMediaIntegration,
    process_media_message,
    format_media_summary_text,
)

__all__ = [
    "MediaServiceClient",
    "upload_request_photo",
    "upload_completion_photo",
    "BotMediaIntegration",
    "process_media_message",
    "format_media_summary_text",
]
