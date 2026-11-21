"""API модуля «Паспорт дома»: ``/api/v2/passports``.

Флаг ``settings.PASSPORT_ENABLED`` гейтит весь роутер единым 404. Паспорта всех
домов площадки видны сотрудникам с правом (как реестр лифтов), поэтому действия
``passport.*`` — в ``STAFF_WIDE_ACTIONS`` матрицы ``tests/api/test_idor_matrix.py``.

Подписание и возврат в работу — отдельные маршруты под ``passport.sign``: так
право видно в каталоге и в снимке ``tests/rbac_baseline``, а не спрятано в коде.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.api.passports.schemas import (
    DB_ID_MAX,
    PassportPatchIn,
    PassportReopenIn,
    PassportSignIn,
    PassportStatusIn,
)
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import AsyncSessionLocal
from uk_management_bot.services.building_passport import export, photos, schema
from uk_management_bot.services.building_passport import service as svc
from uk_management_bot.services.building_passport.service import Actor, PassportError
from uk_management_bot.services.executor_completion import COMPLETION_PHOTO_MAX_BYTES
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
PhotoId = Path(ge=1, le=DB_ID_MAX)
PHOTO_RATE_LIMIT = "60/minute"
_MEDIA = photos.Media()  # тесты подменяют медиа-сервис здесь


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


# ── фото разделов ───────────────────────────────────────────────────────────

@router.post("/buildings/{building_id}/photos")
@limiter.limit(PHOTO_RATE_LIMIT)
async def upload_photo(
    request: Request,
    building_id: int = BuildingId,
    photo: UploadFile = File(..., description="JPEG/PNG, до 8 МиБ"),
    section: str = Form(..., max_length=40, description="Ключ раздела схемы"),
    op_key: str = Form(..., description="UUID операции; повтор с ним же не создаёт второй файл"),
    db: AsyncSession = Depends(get_db), user: User = Depends(_edit),
) -> dict[str, Any]:
    """Фото раздела. 409 ``in_progress`` и 503 ``media_unavailable`` — повторить с тем же
    ключом; 409 ``key_reused`` / ``photo_limit`` / ``signed``; 413/415/422 — файл, ключ, раздел."""
    photo_bytes = await photo.read(COMPLETION_PHOTO_MAX_BYTES + 1)
    await db.close()  # сервис открывает свои сессии; не держим транзакцию через загрузку
    try:
        return await photos.upload(AsyncSessionLocal, building_id, _actor(user), section=section,
                                   op_key=op_key, photo_bytes=photo_bytes, media=_MEDIA)
    except PassportError as exc:
        raise _http(exc) from None


@router.delete("/buildings/{building_id}/photos/{photo_id}", status_code=204)
async def delete_photo(building_id: int = BuildingId, photo_id: int = PhotoId,
                       db: AsyncSession = Depends(get_db), user: User = Depends(_edit)) -> Response:
    """Убрать фото из рабочего набора. Файл, вошедший в подписанную редакцию, остаётся в медиа."""
    media_id = await _write(db, photos.remove(db, building_id, photo_id, _actor(user)))
    if media_id is not None:
        await _MEDIA.delete(media_id)
    return Response(status_code=204)


@router.get("/buildings/{building_id}/photos/{photo_id}/file")
async def photo_file(building_id: int = BuildingId, photo_id: int = PhotoId,
                     original: bool = Query(False, description="true — оригинал, иначе превью"),
                     db: AsyncSession = Depends(get_db), user: User = Depends(_read)) -> Response:
    from uk_management_bot.integrations import get_media_client

    media_id = await _read_or_404(photos.media_id_of(db, building_id, photo_id))
    await db.close()
    client = get_media_client()
    file = await client.download_media_file(media_id, preview=not original) if client is not None else None
    if file is None:
        raise HTTPException(status_code=503, detail={"code": "media_unavailable", "keys": []})
    body, content_type = file
    return Response(content=body, media_type=content_type, headers={"Cache-Control": "private, max-age=3600"})


# ── выгрузка ────────────────────────────────────────────────────────────────

Lang = Query("ru", description="Язык листов «Дополнение УК» и «Разбивка»; форма всегда дословно")


def _xlsx(body: bytes, name: str) -> Response:
    return Response(content=body, media_type=export.XLSX_MIME,
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"', "Cache-Control": "no-store"})  # html-raw: имя файла из чисел, не Telegram


@router.get("/export.xlsx")
async def export_summary(lang: Literal["ru", "uz"] = Lang, db: AsyncSession = Depends(get_db),
                         user: User = Depends(_read)) -> Response:
    """Сводная по последним подписанным редакциям: дом в строке, пункт в столбце."""
    houses = [{**h, "mark": f"№{h['revision_no']}"} for h in await svc.latest_revisions(db)]
    return _xlsx(export.render_summary(schema.public_schema(), houses, lang), "passports-summary")


@router.get("/buildings/{building_id}/export.xlsx")
async def export_working(building_id: int = BuildingId, lang: Literal["ru", "uz"] = Lang,
                         db: AsyncSession = Depends(get_db), user: User = Depends(_read)) -> Response:
    """Рабочее состояние паспорта, с пометкой «черновик»."""
    view = await _read_or_404(svc.view(db, building_id))
    body = export.render(schema=schema.public_schema(), form=schema.etalon(), values=view["values"],
                         unknown=view["unknown"], absent=view["absent"], meta=view["meta"], address=view["address"],
                         revision_no=None, organization=settings.MANAGEMENT_COMPANY_NAME, lang=lang)
    return _xlsx(body, f"passport-{building_id}-draft")


@router.get("/buildings/{building_id}/revisions/{revision_no}/export.xlsx")
async def export_revision(building_id: int = BuildingId, revision_no: int = RevisionNo,
                          lang: Literal["ru", "uz"] = Lang, db: AsyncSession = Depends(get_db),
                          user: User = Depends(_read)) -> Response:
    """Подписанная редакция — по её собственной копии схемы и эталона формы."""
    r = await _read_or_404(svc.revision(db, building_id, revision_no))
    body = export.render(schema=r["schema"], form=r["form"], values=r["values"], unknown=r["unknown"],
                         absent=r["absent"], meta=r["meta"], address=r["meta"].get("address") or "",
                         revision_no=revision_no, organization=settings.MANAGEMENT_COMPANY_NAME, lang=lang)
    return _xlsx(body, f"passport-{building_id}-rev{revision_no}")
