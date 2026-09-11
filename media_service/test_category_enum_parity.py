"""SSOT-гейт категорий загрузки.

Ручка `/media/upload` валидирует `category` через `MediaCategoryEnum`, а канал
выбирается по `FileCategories.CATEGORY_TO_CHANNEL`. UK-прокси
(`uk_management_bot/api/routes/media_proxy.py`, `FileCategories`) пропускает
request_photo/video/document и completion_photo/video — каждая из них обязана
быть членом enum, иначе загрузка mp4/mov из дашборда/TWA падает здесь 422
(дефект, пойманный QA 2026-09-12).
"""
from app.core.config import FileCategories
from app.schemas.media import MediaCategoryEnum

UK_PROXY_CATEGORIES = (
    FileCategories.REQUEST_PHOTO,
    FileCategories.REQUEST_VIDEO,
    FileCategories.REQUEST_DOCUMENT,
    FileCategories.COMPLETION_PHOTO,
    FileCategories.COMPLETION_VIDEO,
)


def test_uk_proxy_categories_are_accepted_by_upload_enum():
    accepted = {member.value for member in MediaCategoryEnum}
    missing = [c for c in UK_PROXY_CATEGORIES if c not in accepted]
    assert missing == [], f"категории UK-прокси без члена MediaCategoryEnum: {missing}"


def test_uk_proxy_categories_have_channel_mapping():
    unmapped = [c for c in UK_PROXY_CATEGORIES if c not in FileCategories.CATEGORY_TO_CHANNEL]
    assert unmapped == [], f"категории без канала в CATEGORY_TO_CHANNEL: {unmapped}"
