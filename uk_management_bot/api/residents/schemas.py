"""Схемы раздела «Жители».

Имена намеренно не пересекаются с фронтовым `ResidentBrief` (житель квартиры в
карточке адреса) — это разные сущности, см. Т9 плана.
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


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
    # Пользователь заблокировал бота (users.bot_blocked_at IS NOT NULL) —
    # бейдж в карточке; запрос номера/уведомления ему недоставимы.
    bot_blocked: bool = False


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
    bot_blocked: bool = False
    # Роли нужны фронту, чтобы прятать блокировку у мультиролевых: блокировка
    # общая на все роли (users.status), у сотрудника она снимает и рабочий доступ.
    roles: list[str] = []
    apartments: list[ResidentApartmentOut] = []
    documents: list[ResidentDocumentOut] = []
    latest_verification: Optional[ResidentVerificationOut] = None


# ── Входные схемы мутаций (PR-3) ─────────────────────────────────────
#
# `extra="forbid"` на КАЖДОЙ: гейт tests/api/test_input_schemas_forbid_extra.py
# фиксирует урок — незнакомый ключ во входном теле почти всегда опечатка или
# клиент новее бэкенда, и тихий дроп маскирует и то, и другое.

class ResidentCommentIn(BaseModel):
    """Необязательный комментарий менеджера (approve аккаунта / привязки)."""
    model_config = {"extra": "forbid"}
    comment: Optional[str] = Field(None, max_length=1000)


class ResidentBlockIn(BaseModel):
    model_config = {"extra": "forbid"}
    reason: str = Field(..., min_length=3, max_length=1000)


class ResidentRejectIn(BaseModel):
    model_config = {"extra": "forbid"}
    comment: str = Field(..., min_length=3, max_length=1000)


class ResidentAttachApartment(BaseModel):
    model_config = {"extra": "forbid"}
    apartment_id: int
    is_owner: bool = False
    # Игнорируется в пользу инварианта, когда approved-привязка первая: она
    # становится основной независимо от запроса (Т6).
    is_primary: bool = False


class ResidentUpdateBindingIn(BaseModel):
    """None = «поле не прислали» (не менять), а не «сбросить»."""
    model_config = {"extra": "forbid"}
    is_owner: Optional[bool] = None
    is_primary: Optional[bool] = None


# ── Верификация и документы (PR-5) ───────────────────────────────────

class ResidentRequestDocumentsIn(BaseModel):
    """Запрос документов у жителя.

    `document_types` — значения `DocumentType`; проверка допустимости и
    дедупликация в сервис-слое, чтобы список типов оставался одним источником.
    """
    model_config = {"extra": "forbid"}
    document_types: list[str] = Field(..., min_length=1)
    comment: str = Field(..., min_length=3, max_length=1000)


class ResidentVerificationNotesIn(BaseModel):
    """Необязательная заметка при подтверждении личности."""
    model_config = {"extra": "forbid"}
    notes: Optional[str] = Field(None, max_length=1000)


class ResidentVerificationRejectIn(BaseModel):
    """Причина отказа обязательна — житель её увидит."""
    model_config = {"extra": "forbid"}
    notes: str = Field(..., min_length=3, max_length=1000)
