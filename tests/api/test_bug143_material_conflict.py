"""BUG-143 — material_service.catalog.create_material: гонка select-then-insert.

Два конкурентных create одного имени проходят дубль-проверку одновременно;
второй INSERT бьётся об UNIQUE(name) и падал немапленным IntegrityError → 500.
Фикс: catch IntegrityError → rollback → MaterialConflictError (роутер уже
мапит её в 409). Настоящая PG-гонка — в test_materials_pg_concurrency.py
(test_concurrent_create_same_name_second_conflicts); здесь — юнит на маппинг.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from uk_management_bot.services.material_service import (
    MaterialConflictError,
    create_material,
)


def _db_losing_the_race() -> MagicMock:
    """AsyncSession-мок: дубль-SELECT никого не видит (обе стороны гонки
    прошли проверку), а flush INSERT'а бьётся об UNIQUE(name)."""
    db = MagicMock()
    select_result = MagicMock()
    select_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=select_result)
    db.add = MagicMock()
    db.flush = AsyncMock(
        side_effect=IntegrityError(
            "INSERT INTO materials ...", {},
            Exception('duplicate key value violates unique constraint "materials_name_key"'),
        )
    )
    db.rollback = AsyncMock()
    return db


async def test_integrity_error_on_flush_maps_to_conflict():
    db = _db_losing_the_race()
    with pytest.raises(MaterialConflictError):
        await create_material(db, name="Гоночный дубль", unit="pcs")


async def test_session_rolled_back_before_conflict_raised():
    db = _db_losing_the_race()
    with pytest.raises(MaterialConflictError):
        await create_material(db, name="Гоночный дубль", unit="pcs")
    db.rollback.assert_awaited_once()
