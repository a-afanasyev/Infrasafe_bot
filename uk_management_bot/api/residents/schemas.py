"""Схемы раздела «Жители».

Имена намеренно не пересекаются с фронтовым `ResidentBrief` (житель квартиры в
карточке адреса) — это разные сущности, см. Т9 плана.
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class ResidentApartmentOut(BaseModel):
    """Привязка жителя к квартире вместе с адресной цепочкой (двор · дом · кв)."""
    id: int
    apartment_id: int
    apartment_number: str
    building_id: int
    building_address: Optional[str] = None
    yard_id: int
    yard_name: Optional[str] = None
    status: str
    is_owner: bool
    is_primary: bool
    requested_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    admin_comment: Optional[str] = None


class ResidentDocumentOut(BaseModel):
    """Метаданные документа.

    `file_id` СОЗНАТЕЛЬНО отсутствует: это токен доступа к файлу в Telegram —
    любой, кто его получил, скачает файл в обход нашей авторизации. Отдача
    самого файла — через прокси-эндпоинт (PR-5).
    """
    id: int
    document_type: str
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    verification_status: Optional[str] = None
    created_at: Optional[datetime] = None


class ResidentVerificationOut(BaseModel):
    id: int
    status: Optional[str] = None
    requested_info: Optional[Any] = None
    requested_at: Optional[datetime] = None
    requested_by: Optional[int] = None
    admin_notes: Optional[str] = None
    verified_by: Optional[int] = None
    verified_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ResidentListItemOut(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    status: str
    verification_status: str
    language: Optional[str] = None
    created_at: Optional[datetime] = None
    apartments_count: int = 0
    primary_address: Optional[str] = None


class ResidentListOut(BaseModel):
    items: list[ResidentListItemOut]
    total: int
    limit: int
    offset: int


class ResidentStatsOut(BaseModel):
    """Две пересекающиеся оси: статус аккаунта и статус верификации."""
    total: int
    pending: int
    approved: int
    blocked: int
    verification_pending: int
    verification_requested: int
    verified: int
    verification_rejected: int


class ResidentDetailOut(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    status: str
    verification_status: str
    verification_notes: Optional[str] = None
    verification_date: Optional[datetime] = None
    language: Optional[str] = None
    created_at: Optional[datetime] = None
    # Роли нужны фронту, чтобы прятать блокировку у мультиролевых: блокировка
    # общая на все роли (users.status), у сотрудника она снимает и рабочий доступ.
    roles: list[str] = []
    apartments: list[ResidentApartmentOut] = []
    documents: list[ResidentDocumentOut] = []
    latest_verification: Optional[ResidentVerificationOut] = None
