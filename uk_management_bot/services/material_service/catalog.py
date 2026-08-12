"""Async-каталог (API): карточки материалов — create/update.

Block-move из services/material_service.py (AUD5-ARCH-3 волна 9), тела
байт-в-байт.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.material import Material, MaterialReceipt

from ._core import (
    MaterialConflictError,
    MaterialNotFoundError,
    MaterialValidationError,
    parse_qty,
    validate_unit,
)

async def create_material(db: AsyncSession, *, name: str, unit: str,
                          category: Optional[str] = None,
                          min_stock=None) -> Material:
    """Создать карточку материала. name UNIQUE навсегда (409 при дубле)."""
    name = (name or "").strip()
    if not name:
        raise MaterialValidationError("название обязательно")
    validate_unit(unit)
    if min_stock is not None:
        min_stock = parse_qty(min_stock)
    existing = (
        await db.execute(select(Material).where(Material.name == name))
    ).scalar_one_or_none()
    if existing is not None:
        raise MaterialConflictError(
            f"материал «{name}» уже существует (id={existing.id}"
            f"{', деактивирован — реактивируйте' if not existing.is_active else ''})"
        )
    material = Material(name=name, unit=unit, category=category, min_stock=min_stock)
    db.add(material)
    await db.flush()
    return material


async def update_material(db: AsyncSession, material_id: int, *,
                          name: Optional[str] = None,
                          category: Optional[str] = None,
                          min_stock=..., is_active: Optional[bool] = None,
                          unit: Optional[str] = None) -> Material:
    """PATCH карточки. unit менять запрещено при наличии движений.

    Переименование НЕ переписывает историю: журнал хранит snapshot material_name.
    """
    material = (
        await db.execute(select(Material).where(Material.id == material_id))
    ).scalar_one_or_none()
    if material is None:
        raise MaterialNotFoundError(f"материал {material_id} не найден")
    if unit is not None and unit != material.unit:
        validate_unit(unit)
        has_moves = (
            await db.execute(
                select(MaterialReceipt.id)
                .where(MaterialReceipt.material_id == material_id)
                .limit(1)
            )
        ).first() is not None
        if has_moves:
            raise MaterialConflictError(
                "единицу измерения нельзя менять: по материалу есть движения"
            )
        material.unit = unit
    if name is not None:
        name = name.strip()
        if not name:
            raise MaterialValidationError("название не может быть пустым")
        if name != material.name:
            dup = (
                await db.execute(
                    select(Material.id).where(
                        Material.name == name, Material.id != material_id
                    )
                )
            ).first()
            if dup is not None:
                raise MaterialConflictError(f"материал «{name}» уже существует")
            material.name = name
    if category is not None:
        material.category = category or None
    if min_stock is not ...:
        material.min_stock = parse_qty(min_stock) if min_stock is not None else None
    if is_active is not None:
        material.is_active = is_active
    await db.flush()
    return material
