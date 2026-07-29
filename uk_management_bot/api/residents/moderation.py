"""Раздел «Жители» — мутации аккаунта и привязок к квартирам (PR-3).

Тонкий HTTP-слой: парсинг тела, вызов `services/residents/core.py`, маппинг в
схему ответа. Доменные исключения ловит `exception_handlers` (404/409/422),
поэтому try/except здесь нет.

Уведомления шлются ПОСЛЕ успешной мутации и никогда не роняют запрос — см.
`notify.py`. Адрес для текста уведомления берётся из карточки жителя уже после
операции: так в сообщении гарантированно тот адрес, который житель увидит.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.api.residents import notify
from uk_management_bot.api.residents.schemas import (
    ResidentApartmentOut,
    ResidentAttachApartment,
    ResidentBlockIn,
    ResidentCommentIn,
    ResidentRejectIn,
    ResidentUpdateBindingIn,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.services.residents import core, queries

router = APIRouter()

_manager_only = require_roles("manager")

#: Мутации раздела. Конвенция проекта — лимит на маршруте (общего
#: `default_limits` нет). ⚠ auth-зависимости идут ДО лимитера: это защита не
#: от неаутентифицированного флуда, а от злоупотребления сессией менеджера.
_WRITE_LIMIT = "30/minute"


def _format_address(yard_name: str | None, building_address: str | None, number: str) -> str:
    parts = [p for p in (yard_name, building_address) if p]
    parts.append(f"кв. {number}")
    return " · ".join(parts)


async def _binding_out(db: AsyncSession, resident_id: int, ua_id: int) -> ResidentApartmentOut:
    """Свежая привязка с адресом — читается после мутации, не из ORM-объекта.

    `_ensure_single_primary` мог поменять флаги у СОСЕДНИХ привязок, поэтому
    отдавать надо перечитанное состояние, а не то, что вернул мутатор.
    """
    for ua, apt, bld, yard in await queries.list_resident_apartments(db, resident_id):
        if ua.id != ua_id:
            continue
        return ResidentApartmentOut(
            id=ua.id, apartment_id=apt.id, apartment_number=apt.apartment_number,
            building_id=bld.id, building_address=bld.address,
            yard_id=yard.id, yard_name=yard.name,
            status=ua.status, is_owner=ua.is_owner, is_primary=ua.is_primary,
            requested_at=ua.requested_at, reviewed_at=ua.reviewed_at,
            admin_comment=ua.admin_comment,
        )
    raise AssertionError("привязка исчезла между мутацией и чтением")


async def _address_of(db: AsyncSession, resident_id: int, ua_id: int) -> str:
    for ua, apt, bld, yard in await queries.list_resident_apartments(db, resident_id):
        if ua.id == ua_id:
            return _format_address(yard.name, bld.address, apt.apartment_number)
    return ""


# ───────────────────────── аккаунт ─────────────────────────

@router.post("/{resident_id}/approve")
@limiter.limit(_WRITE_LIMIT)
async def approve_account(
    request: Request,
    resident_id: int,
    body: ResidentCommentIn = ResidentCommentIn(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    resident = await core.approve_account(
        db, resident_id=resident_id, actor_id=user.id, comment=body.comment,
    )
    await notify.notify_account_approved(resident)
    return {"id": resident.id, "status": resident.status}


@router.post("/{resident_id}/block")
@limiter.limit(_WRITE_LIMIT)
async def block_account(
    request: Request,
    resident_id: int,
    body: ResidentBlockIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    # Уведомления о блокировке нет — parity с ботом: житель узнаёт о ней при
    # следующей попытке входа, отдельное сообщение бот тоже не шлёт.
    resident = await core.block_account(
        db, resident_id=resident_id, actor_id=user.id, reason=body.reason,
    )
    return {"id": resident.id, "status": resident.status}


@router.post("/{resident_id}/unblock")
@limiter.limit(_WRITE_LIMIT)
async def unblock_account(
    request: Request,
    resident_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    resident = await core.unblock_account(db, resident_id=resident_id, actor_id=user.id)
    return {"id": resident.id, "status": resident.status}


# ───────────────────────── привязки ─────────────────────────

@router.post("/{resident_id}/apartments", response_model=ResidentApartmentOut, status_code=201)
@limiter.limit(_WRITE_LIMIT)
async def attach_apartment(
    request: Request,
    resident_id: int,
    body: ResidentAttachApartment,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    ua = await core.attach_apartment(
        db, resident_id=resident_id, apartment_id=body.apartment_id, actor_id=user.id,
        is_owner=body.is_owner, is_primary=body.is_primary,
    )
    out = await _binding_out(db, resident_id, ua.id)
    resident = await queries.get_resident(db, resident_id)
    if resident is not None:
        await notify.notify_apartment_attached(
            resident, _format_address(out.yard_name, out.building_address, out.apartment_number),
        )
    return out


@router.post("/{resident_id}/apartments/{ua_id}/approve", response_model=ResidentApartmentOut)
@limiter.limit(_WRITE_LIMIT)
async def approve_binding(
    request: Request,
    resident_id: int,
    ua_id: int,
    body: ResidentCommentIn = ResidentCommentIn(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    await core.approve_binding(
        db, resident_id=resident_id, ua_id=ua_id, actor_id=user.id, comment=body.comment,
    )
    out = await _binding_out(db, resident_id, ua_id)
    resident = await queries.get_resident(db, resident_id)
    if resident is not None:
        await notify.notify_binding_approved(
            resident, _format_address(out.yard_name, out.building_address, out.apartment_number),
        )
    return out


@router.post("/{resident_id}/apartments/{ua_id}/reject", response_model=ResidentApartmentOut)
@limiter.limit(_WRITE_LIMIT)
async def reject_binding(
    request: Request,
    resident_id: int,
    ua_id: int,
    body: ResidentRejectIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    await core.reject_binding(
        db, resident_id=resident_id, ua_id=ua_id, actor_id=user.id, comment=body.comment,
    )
    out = await _binding_out(db, resident_id, ua_id)
    resident = await queries.get_resident(db, resident_id)
    if resident is not None:
        await notify.notify_binding_rejected(
            resident,
            _format_address(out.yard_name, out.building_address, out.apartment_number),
            body.comment.strip(),
        )
    return out


@router.patch("/{resident_id}/apartments/{ua_id}", response_model=ResidentApartmentOut)
@limiter.limit(_WRITE_LIMIT)
async def update_binding(
    request: Request,
    resident_id: int,
    ua_id: int,
    body: ResidentUpdateBindingIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    await core.update_binding(
        db, resident_id=resident_id, ua_id=ua_id, actor_id=user.id,
        is_owner=body.is_owner, is_primary=body.is_primary,
    )
    return await _binding_out(db, resident_id, ua_id)


@router.delete("/{resident_id}/apartments/{ua_id}", status_code=204)
@limiter.limit(_WRITE_LIMIT)
async def remove_binding(
    request: Request,
    resident_id: int,
    ua_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    # Адрес нужен для текста уведомления, а после удаления его уже не прочитать.
    address = await _address_of(db, resident_id, ua_id)
    resident = await queries.get_resident(db, resident_id)

    await core.remove_binding(db, resident_id=resident_id, ua_id=ua_id, actor_id=user.id)

    if resident is not None:
        await notify.notify_binding_removed(resident, address)
    return None
