"""API модуля «Паспорт дома»: ``/api/v2/passports``.

Флаг ``settings.PASSPORT_ENABLED`` гейтит весь роутер единым 404. Паспорта всех
домов площадки видны сотрудникам с правом (как реестр лифтов), поэтому действия
``passport.*`` — в ``STAFF_WIDE_ACTIONS`` матрицы ``tests/api/test_idor_matrix.py``.

Подписание и возврат в работу — отдельные маршруты под ``passport.sign``: так
право видно в каталоге и в снимке ``tests/rbac_baseline``, а не спрятано в коде.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.api.passports.schemas import (
    DB_ID_MAX,
    PassportPatchIn,
    PassportReopenIn,
    PassportSignIn,
    PassportStatusIn,
)
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User
from uk_management_bot.services.building_passport import schema
from uk_management_bot.services.building_passport import service as svc
from uk_management_bot.services.building_passport.service import Actor, PassportError
from uk_management_bot.utils.user_names import display_name


async def _require_enabled() -> None:
    if not settings.PASSPORT_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(dependencies=[Depends(_require_enabled)])

_read = require_action("passport.read")
_edit = require_action("passport.edit")
_sign = require_action("passport.sign")
BuildingId = Path(ge=1, le=DB_ID_MAX)
RevisionNo = Path(ge=1, le=100_000)


def _actor(user: User) -> Actor:
    return Actor(user.id, display_name(user) or f"#{user.id}")


def _http(exc: PassportError) -> HTTPException:
    return HTTPException(status_code=exc.http_status, detail={"code": exc.code, "keys": list(exc.keys)})


async def _write(db: AsyncSession, call) -> dict[str, Any]:
    try:
        result = await call
    except PassportError as exc:
        await db.rollback()
        raise _http(exc) from None
    await db.commit()
    return result


async def _read_or_404(call) -> Any:
    try:
        return await call
    except PassportError as exc:
        raise _http(exc) from None


@router.get("/schema")
async def get_schema(user: User = Depends(_read)) -> dict[str, Any]:
    return schema.public_schema()


@router.get("")
async def list_passports(db: AsyncSession = Depends(get_db), user: User = Depends(_read)) -> list[dict[str, Any]]:
    return await svc.overview(db)


@router.get("/buildings/{building_id}")
async def get_passport(building_id: int = BuildingId, db: AsyncSession = Depends(get_db),
                       user: User = Depends(_read)) -> dict[str, Any]:
    return await _read_or_404(svc.view(db, building_id))


@router.patch("/buildings/{building_id}")
async def patch_passport(body: PassportPatchIn, building_id: int = BuildingId,
                         db: AsyncSession = Depends(get_db), user: User = Depends(_edit)) -> dict[str, Any]:
    return await _write(db, svc.patch(
        db, building_id, _actor(user), expected_version=body.expected_version, values=body.values,
        unknown=body.unknown, absent=body.absent, shared_from=body.shared_from, meta=body.meta))


@router.post("/buildings/{building_id}/status")
async def set_status(body: PassportStatusIn, building_id: int = BuildingId,
                     db: AsyncSession = Depends(get_db), user: User = Depends(_edit)) -> dict[str, Any]:
    return await _write(db, svc.set_status(
        db, building_id, _actor(user), status=body.status, expected_version=body.expected_version))


@router.post("/buildings/{building_id}/sign")
async def sign_passport(body: PassportSignIn, building_id: int = BuildingId,
                        db: AsyncSession = Depends(get_db), user: User = Depends(_sign)) -> dict[str, Any]:
    return await _write(db, svc.set_status(
        db, building_id, _actor(user), status="signed", expected_version=body.expected_version, can_sign=True))


@router.post("/buildings/{building_id}/reopen")
async def reopen_passport(body: PassportReopenIn, building_id: int = BuildingId,
                          db: AsyncSession = Depends(get_db), user: User = Depends(_sign)) -> dict[str, Any]:
    return await _write(db, svc.set_status(
        db, building_id, _actor(user), status="collecting", expected_version=body.expected_version,
        reason=body.reason, can_sign=True))


@router.get("/buildings/{building_id}/history")
async def get_history(building_id: int = BuildingId, db: AsyncSession = Depends(get_db),
                      user: User = Depends(_read)) -> list[dict[str, Any]]:
    return await _read_or_404(svc.history(db, building_id))


@router.get("/buildings/{building_id}/revisions")
async def list_revisions(building_id: int = BuildingId, db: AsyncSession = Depends(get_db),
                         user: User = Depends(_read)) -> list[dict[str, Any]]:
    return await _read_or_404(svc.revisions(db, building_id))


@router.get("/buildings/{building_id}/revisions/{revision_no}")
async def get_revision(building_id: int = BuildingId, revision_no: int = RevisionNo,
                       db: AsyncSession = Depends(get_db), user: User = Depends(_read)) -> dict[str, Any]:
    return await _read_or_404(svc.revision(db, building_id, revision_no))
