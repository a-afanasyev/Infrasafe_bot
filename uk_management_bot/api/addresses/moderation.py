"""Addresses API — moderation entity (ARCH-05b).

Thin HTTP layer: auth-deps, request parsing, response mapping, HTTPException.
All data-access is in services/addresses/core.py (mutations) and
services/addresses/queries.py (reads).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.addresses.schemas import ModerationItemOut, ModerationAction
from uk_management_bot.database.models.user import User
from uk_management_bot.services.addresses import core, queries

router = APIRouter()


@router.get("/moderation", response_model=list[ModerationItemOut])
async def list_pending(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    rows = await queries.list_pending_moderation(db)

    out = []
    for ua, first_name, last_name, phone, apt_number, bld_address, yard_name in rows:
        name_parts = [first_name or "", last_name or ""]
        user_name = " ".join(p for p in name_parts if p).strip() or None

        out.append(ModerationItemOut(
            id=ua.id,
            user_id=ua.user_id,
            user_name=user_name,
            user_phone=phone,
            apartment_id=ua.apartment_id,
            apartment_number=apt_number,
            building_address=bld_address,
            yard_name=yard_name,
            status=ua.status,
            is_owner=ua.is_owner,
            is_primary=ua.is_primary,
            requested_at=ua.requested_at,
        ))
    return out


async def _build_moderation_response(db, ua) -> ModerationItemOut:
    """Map an approved/rejected UserApartment to the moderation response."""
    apt_row = await queries.get_apartment_location(db, ua.apartment_id)
    user_name, user_phone = await queries.get_user_name_phone(db, ua.user_id)

    return ModerationItemOut(
        id=ua.id,
        user_id=ua.user_id,
        user_name=user_name,
        user_phone=user_phone,
        apartment_id=ua.apartment_id,
        apartment_number=apt_row[0] if apt_row else "",
        building_address=apt_row[1] if apt_row else None,
        yard_name=apt_row[2] if apt_row else None,
        status=ua.status,
        is_owner=ua.is_owner,
        is_primary=ua.is_primary,
        requested_at=ua.requested_at,
    )


@router.post("/moderation/{item_id}/approve", response_model=ModerationItemOut)
async def approve_request(
    item_id: int,
    body: ModerationAction = ModerationAction(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    ua = await core.approve_apartment_request(
        db, user_apartment_id=item_id, reviewer_id=user.id, comment=body.comment
    )
    return await _build_moderation_response(db, ua)


@router.post("/moderation/{item_id}/reject", response_model=ModerationItemOut)
async def reject_request(
    item_id: int,
    body: ModerationAction,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    # Comment required for rejection (>= 3 chars)
    if not body.comment or len(body.comment.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Comment is required for rejection (at least 3 characters)",
        )

    ua = await core.reject_apartment_request(
        db, user_apartment_id=item_id, reviewer_id=user.id, comment=body.comment.strip()
    )
    return await _build_moderation_response(db, ua)
