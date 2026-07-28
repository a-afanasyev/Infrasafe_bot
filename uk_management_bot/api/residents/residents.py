"""Раздел «Жители» — чтения (PR-1).

Тонкий HTTP-слой: auth-deps, парсинг query, маппинг в схемы. Весь data-access
— в `services/residents/queries.py` (гейт: tests/api/test_residents_router_inventory.py).

RBAC — `manager`, как во всём домене адресов/смен.
"""
from enum import Enum

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.residents.schemas import (
    ResidentApartmentOut,
    ResidentDetailOut,
    ResidentDocumentOut,
    ResidentListItemOut,
    ResidentListOut,
    ResidentStatsOut,
    ResidentVerificationOut,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.services.residents import queries
from uk_management_bot.services.residents.exceptions import ResidentNotFound
from uk_management_bot.utils.auth_helpers import parse_roles_safe

router = APIRouter()

_manager_only = require_roles("manager")


def _enum_value(value) -> str | None:
    """Enum-колонки моделей отдают питоновский Enum — наружу нужен его value."""
    if value is None:
        return None
    return value.value if isinstance(value, Enum) else str(value)


def _format_address(yard_name: str | None, building_address: str | None, number: str) -> str:
    """«Двор · дом · кв. N» — те же три уровня, что и в адресном разделе."""
    parts = [p for p in (yard_name, building_address) if p]
    parts.append(f"кв. {number}")
    return " · ".join(parts)


@router.get("", response_model=ResidentListOut)
async def list_residents(
    status: str | None = Query(None, description="pending | approved | blocked"),
    verification_status: str | None = Query(None, description="pending | requested | verified | rejected"),
    yard_id: int | None = Query(None),
    building_id: int | None = Query(None),
    apartment_id: int | None = Query(None),
    q: str | None = Query(None, description="ФИО или телефон"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    users, total = await queries.list_residents(
        db,
        status=status, verification_status=verification_status,
        yard_id=yard_id, building_id=building_id, apartment_id=apartment_id,
        q=q, limit=limit, offset=offset,
    )
    user_ids = [u.id for u in users]
    counts = await queries.apartments_count_map(db, user_ids)
    primaries = await queries.primary_address_map(db, user_ids)

    items = []
    for u in users:
        primary = primaries.get(u.id)
        items.append(ResidentListItemOut(
            id=u.id,
            telegram_id=u.telegram_id,
            username=u.username,
            first_name=u.first_name,
            last_name=u.last_name,
            phone=u.phone,
            status=u.status,
            verification_status=u.verification_status,
            language=u.language,
            created_at=u.created_at,
            apartments_count=counts.get(u.id, 0),
            primary_address=_format_address(*primary) if primary else None,
        ))
    return ResidentListOut(items=items, total=total, limit=limit, offset=offset)


# ВАЖНО: /stats объявлен ДО /{resident_id} — иначе динамический маршрут
# перехватил бы «stats» и отдал 422 на несовпадение int.
@router.get("/stats", response_model=ResidentStatsOut)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    return ResidentStatsOut(**await queries.get_stats(db))


@router.get("/{resident_id}", response_model=ResidentDetailOut)
async def get_resident(
    resident_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    resident = await queries.get_resident(db, resident_id)
    if resident is None:
        raise ResidentNotFound("Житель не найден")

    apartment_rows = await queries.list_resident_apartments(db, resident.id)
    documents = await queries.list_resident_documents(db, resident.id)
    verification = await queries.get_latest_verification(db, resident.id)

    return ResidentDetailOut(
        id=resident.id,
        telegram_id=resident.telegram_id,
        username=resident.username,
        first_name=resident.first_name,
        last_name=resident.last_name,
        phone=resident.phone,
        status=resident.status,
        verification_status=resident.verification_status,
        verification_notes=resident.verification_notes,
        verification_date=resident.verification_date,
        language=resident.language,
        created_at=resident.created_at,
        roles=parse_roles_safe(resident.roles),
        apartments=[
            ResidentApartmentOut(
                id=ua.id,
                apartment_id=apt.id,
                apartment_number=apt.apartment_number,
                building_id=bld.id,
                building_address=bld.address,
                yard_id=yard.id,
                yard_name=yard.name,
                status=ua.status,
                is_owner=ua.is_owner,
                is_primary=ua.is_primary,
                requested_at=ua.requested_at,
                reviewed_at=ua.reviewed_at,
                admin_comment=ua.admin_comment,
            )
            for ua, apt, bld, yard in apartment_rows
        ],
        documents=[
            ResidentDocumentOut(
                id=doc.id,
                document_type=_enum_value(doc.document_type) or "other",
                file_name=doc.file_name,
                file_size=doc.file_size,
                verification_status=_enum_value(doc.verification_status),
                created_at=doc.created_at,
            )
            for doc in documents
        ],
        latest_verification=ResidentVerificationOut(
            id=verification.id,
            status=_enum_value(verification.status),
            requested_info=verification.requested_info,
            requested_at=verification.requested_at,
            requested_by=verification.requested_by,
            admin_notes=verification.admin_notes,
            verified_by=verification.verified_by,
            verified_at=verification.verified_at,
            created_at=verification.created_at,
        ) if verification is not None else None,
    )
