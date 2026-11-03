"""Addresses API — владельцы лицевых счетов из выгрузки Mening Uyim.

Тонкий HTTP-слой; данные — services/account_owners.py.
"""
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.addresses.schemas import (
    AccountOwnersImportOut,
    AccountOwnersSummaryOut,
)
from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.database.models.user import User
from uk_management_bot.services import account_owners as service

router = APIRouter()


@router.get("/account-owners/summary", response_model=AccountOwnersSummaryOut)
async def owners_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_action("addresses.manage")),
):
    return await service.owners_summary(db)


@router.post("/account-owners/import", response_model=AccountOwnersImportOut)
@limiter.limit("10/minute")
async def import_owners(
    request: Request,
    file: UploadFile = File(..., description="CSV «Лицевой счёт;ФИО» из Mening Uyim, до 5 МБ"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_action("addresses.manage")),
):
    """Загрузить владельцев лицевых счетов; заменяет предыдущую загрузку."""
    raw = await file.read(service.MAX_BYTES + 1)
    try:
        owners, skipped = service.parse_owners_csv(raw)
    except service.OwnersFileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    summary = await service.replace_owners(db, owners, skipped, actor_id=user.id)
    return AccountOwnersImportOut(**summary.__dict__)
