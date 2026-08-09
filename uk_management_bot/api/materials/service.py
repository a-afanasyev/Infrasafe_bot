"""API-сервис-слой материалов (AUD5-ARCH-2 волна 2, ARCH-05a-канон).

Учётная логика остаётся в services/material_service.py (общая с ботом);
здесь — API-транзакционные обёртки (вызов доменного сервиса + commit) и
единственный прямой запрос списка номенклатуры. Доменные исключения
MaterialServiceError пролетают наверх — их маппит на HTTP роутер.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.material import Material
from uk_management_bot.services import material_service
from uk_management_bot.services.material_service import _escape_like
from uk_management_bot.utils.sql_search import ci_contains, is_postgres


async def list_material_rows(
    db: AsyncSession,
    *,
    q: Optional[str],
    is_active: Optional[bool],
    limit: int,
    offset: int,
) -> list[Material]:
    query = select(Material)
    if q:
        query = query.where(
            ci_contains(
                Material.name, f"%{_escape_like(q)}%", is_postgres=is_postgres(db),
            )
        )
    if is_active is not None:
        query = query.where(Material.is_active.is_(is_active))
    return (
        (await db.execute(query.order_by(Material.name).offset(offset).limit(limit)))
        .scalars()
        .all()
    )


async def create_material_tx(db: AsyncSession, *, name, unit, category, min_stock):
    material = await material_service.create_material(
        db, name=name, unit=unit, category=category, min_stock=min_stock,
    )
    await db.commit()
    return material


async def create_receipt_tx(
    db: AsyncSession, *, material_id, qty, unit_price, created_by,
    supplier, doc_number, doc_date, note,
):
    receipt = await material_service.create_receipt(
        db, material_id=material_id, qty=qty, unit_price=unit_price,
        created_by=created_by, supplier=supplier, doc_number=doc_number,
        doc_date=doc_date, note=note,
    )
    await db.commit()
    return receipt


async def create_issue_tx(
    db: AsyncSession, *, material_id, qty, created_by, doc_type,
    request_number, reason,
):
    issue = await material_service.issue_material(
        db, material_id=material_id, qty=qty, created_by=created_by,
        doc_type=doc_type, request_number=request_number, reason=reason,
    )
    await db.commit()
    return issue


async def adjust_tx(
    db: AsyncSession, *, material_id, direction, reason, created_by,
    qty, unit_price, reversal_of_issue_id, reversal_of_receipt_id,
):
    result = await material_service.adjust(
        db, material_id=material_id, direction=direction, reason=reason,
        created_by=created_by, qty=qty, unit_price=unit_price,
        reversal_of_issue_id=reversal_of_issue_id,
        reversal_of_receipt_id=reversal_of_receipt_id,
    )
    await db.commit()
    return result


async def update_material_tx(
    db: AsyncSession, material_id: int, *, name, unit, category, min_stock, is_active,
):
    material = await material_service.update_material(
        db, material_id, name=name, unit=unit, category=category,
        min_stock=min_stock, is_active=is_active,
    )
    await db.commit()
    return material
