"""API обратной связи (жалобы / пожелания).

- POST  ""                       — создать обращение (любой авторизованный; multipart, опц. фото)
- GET   ""                       — список (manager): фильтры type/status, пагинация
- GET   "/{fid}"                 — деталь (manager)
- PATCH "/{fid}"                 — статус / ответ (manager); ответ доставляется пользователю в Telegram
- GET   "/{fid}/media"           — метаданные вложений (manager)
- GET   "/{fid}/media/{mid}/file"— стрим байтов вложения (manager; для <img> в дашборде)
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_current_user, get_db, require_roles
from uk_management_bot.api.feedback.schemas import (
    FeedbackDetailOut,
    FeedbackListItem,
    FeedbackListOut,
    FeedbackOut,
    FeedbackUpdate,
)
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.feedback import Feedback
from uk_management_bot.database.models.user import User
from uk_management_bot.services.feedback_service import (
    FEEDBACK_TYPES,
    build_manager_notify_text,
    manager_telegram_ids_async,
)
from uk_management_bot.services.notification_service import (
    _get_shared_bot,
    deliver_feedback_to_managers,
    send_feedback_reply_to_user,
)

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_PHOTO_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif"}  # media-service allowlist (HEIC не входит)


def _sniff_image_mime(data: bytes) -> Optional[str]:
    """Определяет MIME по магическим байтам (client content_type подделываем)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None
_MIN_TEXT_LEN = 10
_MAX_TEXT_LEN = 4000
_STATUSES = {"new", "in_review", "resolved"}
# Допустимые переходы статуса (forward + reopen).
_TRANSITIONS = {
    "new": {"in_review", "resolved"},
    "in_review": {"resolved", "new"},
    "resolved": {"in_review"},
}


def _author_name(user: Optional[User]) -> Optional[str]:
    if not user:
        return None
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return name or (f"@{user.username}" if user.username else f"id{user.telegram_id}")


def _media_base() -> str:
    return settings.MEDIA_SERVICE_URL.rstrip("/")


def _media_headers() -> dict:
    return {"X-API-Key": settings.MEDIA_SERVICE_API_KEY} if settings.MEDIA_SERVICE_API_KEY else {}


@router.post("", response_model=FeedbackOut)
@limiter.limit("10/minute")
async def create_feedback(
    request: Request,
    feedback_type: str = Form(..., alias="type"),
    text: str = Form(...),
    file: Optional[UploadFile] = File(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1) Валидация
    if feedback_type not in FEEDBACK_TYPES:
        raise HTTPException(status_code=422, detail="type must be 'complaint' or 'wish'")
    text = (text or "").strip()
    if not (_MIN_TEXT_LEN <= len(text) <= _MAX_TEXT_LEN):
        raise HTTPException(status_code=422, detail=f"text length must be {_MIN_TEXT_LEN}..{_MAX_TEXT_LEN}")

    # 2) Фото (опционально): читаем байты один раз, проверяем размер и СОДЕРЖИМОЕ
    #    (content_type клиента подделываем → проверяем магические байты).
    photo_bytes: Optional[bytes] = None
    photo_ct: Optional[str] = None
    if file is not None:
        photo_bytes = await file.read()
        if len(photo_bytes) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=422, detail="photo too large (max 10MB)")
        photo_ct = _sniff_image_mime(photo_bytes)
        if photo_ct not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=422,
                detail="unsupported image type (allowed: JPEG, PNG, GIF)",
            )

    # 3) Сохраняем обращение
    fb = Feedback(user_id=user.id, type=feedback_type, text=text, media_files=[], source="twa")
    db.add(fb)
    await db.commit()
    await db.refresh(fb)

    # 4) Фото → media-service (best-effort; падение не валит сохранение)
    tg_fid: Optional[str] = None
    if photo_bytes:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{_media_base()}/api/v1/media/upload",
                    headers=_media_headers(),
                    files={"file": (file.filename or "feedback.jpg", photo_bytes, photo_ct)},
                    data={
                        "request_number": f"fb-{fb.id}",
                        "category": "feedback_photo",
                        "uploaded_by": str(user.id),
                    },
                )
            if resp.status_code in (200, 201):
                payload = resp.json().get("media_file", {})
                media_id = payload.get("id")
                tg_fid = payload.get("telegram_file_id")
                if media_id:
                    fb.media_files = [media_id]
                    await db.commit()
            else:
                logger.warning("feedback %s media upload status %s", fb.id, resp.status_code)
        except Exception as e:
            logger.warning("feedback %s media upload failed: %s", fb.id, e)

    # 5) Уведомление менеджерам (best-effort)
    try:
        ids = await manager_telegram_ids_async(db)
        notify_text = build_manager_notify_text(
            type_=feedback_type, text=text, author_name=_author_name(user),
            has_photo=bool(photo_bytes), lang="ru",
        )
        # Отдаём telegram_file_id от media-service (без повторной загрузки в Telegram);
        # bytes-fallback только если media-service недоступен.
        photo = tg_fid if tg_fid else (photo_bytes if photo_bytes else None)
        await deliver_feedback_to_managers(
            _get_shared_bot(), telegram_ids=ids, text=notify_text, photo=photo
        )
    except Exception as e:
        logger.warning("feedback %s manager notify failed: %s", fb.id, e)

    return FeedbackOut(id=fb.id, type=fb.type, status=fb.status, created_at=fb.created_at)


@router.get("", response_model=FeedbackListOut)
async def list_feedback(
    feedback_type: Optional[str] = Query(None, alias="type"),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_roles("manager")),
    db: AsyncSession = Depends(get_db),
):
    if feedback_type and feedback_type not in FEEDBACK_TYPES:
        raise HTTPException(status_code=422, detail="invalid type filter")
    if status and status not in _STATUSES:
        raise HTTPException(status_code=422, detail="invalid status filter")

    conds = []
    if feedback_type:
        conds.append(Feedback.type == feedback_type)
    if status:
        conds.append(Feedback.status == status)

    # count и rows используют ОДИН и тот же inner-join, иначе пагинация разъедется,
    # если у обращения user_id ссылается на отсутствующего пользователя.
    total = (
        await db.execute(
            select(func.count(Feedback.id)).join(User, Feedback.user_id == User.id).where(*conds)
        )
    ).scalar() or 0
    rows = (
        await db.execute(
            select(Feedback, User)
            .join(User, Feedback.user_id == User.id)
            .where(*conds)
            .order_by(Feedback.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    items = [
        FeedbackListItem(
            id=fb.id, type=fb.type, status=fb.status, text=fb.text,
            has_media=bool(fb.media_files), author_name=_author_name(author),
            created_at=fb.created_at,
        )
        for fb, author in rows
    ]
    return FeedbackListOut(items=items, total=total)


async def _get_feedback_or_404(db: AsyncSession, fid: int) -> Feedback:
    fb = (await db.execute(select(Feedback).where(Feedback.id == fid))).scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return fb


def _detail(fb: Feedback, author: Optional[User]) -> FeedbackDetailOut:
    return FeedbackDetailOut(
        id=fb.id, type=fb.type, status=fb.status, text=fb.text, source=fb.source,
        media_ids=list(fb.media_files or []), reply=fb.reply, replied_at=fb.replied_at,
        author_name=_author_name(author),
        author_phone=getattr(author, "phone", None) if author else None,
        created_at=fb.created_at,
    )


@router.get("/{fid}", response_model=FeedbackDetailOut)
async def get_feedback(
    fid: int,
    user: User = Depends(require_roles("manager")),
    db: AsyncSession = Depends(get_db),
):
    fb = await _get_feedback_or_404(db, fid)
    author = (await db.execute(select(User).where(User.id == fb.user_id))).scalar_one_or_none()
    return _detail(fb, author)


@router.patch("/{fid}", response_model=FeedbackDetailOut)
async def update_feedback(
    fid: int,
    body: FeedbackUpdate,
    user: User = Depends(require_roles("manager")),
    db: AsyncSession = Depends(get_db),
):
    fb = await _get_feedback_or_404(db, fid)

    # Статус: валидируем переход (не просто membership)
    if body.status is not None and body.status != fb.status:
        if body.status not in _STATUSES:
            raise HTTPException(status_code=422, detail="invalid status")
        if body.status not in _TRANSITIONS.get(fb.status, set()):
            raise HTTPException(status_code=422, detail=f"invalid transition {fb.status} -> {body.status}")
        fb.status = body.status

    # Ответ: пустой/пробельный игнорируем (no-op); уведомляем автора только при изменении текста
    reply_changed = False
    if body.reply is not None and body.reply.strip():
        new_reply = body.reply.strip()
        if new_reply != (fb.reply or ""):
            fb.reply = new_reply
            fb.replied_at = datetime.now(timezone.utc)
            fb.replied_by = user.id
            reply_changed = True

    await db.commit()
    await db.refresh(fb)

    author = (await db.execute(select(User).where(User.id == fb.user_id))).scalar_one_or_none()

    if reply_changed and author and author.telegram_id:
        try:
            await send_feedback_reply_to_user(
                _get_shared_bot(), telegram_id=author.telegram_id,
                reply_text=fb.reply, lang=(author.language or "ru"),
            )
        except Exception as e:
            logger.warning("feedback %s reply notify failed: %s", fb.id, e)

    return _detail(fb, author)


@router.get("/{fid}/media")
async def feedback_media_list(
    fid: int,
    user: User = Depends(require_roles("manager")),
    db: AsyncSession = Depends(get_db),
):
    """Метаданные вложений по сохранённым media_id (источник истины — fb.media_files)."""
    fb = await _get_feedback_or_404(db, fid)
    out = []
    headers = _media_headers()
    async with httpx.AsyncClient(timeout=10) as client:
        for mid in (fb.media_files or []):
            try:
                resp = await client.get(f"{_media_base()}/api/v1/media/{mid}", headers=headers)
                if resp.status_code == 200:
                    m = resp.json()
                    out.append({
                        "id": m.get("id"),
                        "file_type": m.get("file_type"),
                        "mime_type": m.get("mime_type"),
                    })
            except Exception as e:
                logger.warning("feedback %s media meta %s failed: %s", fid, mid, e)
    return out


@router.get("/{fid}/media/{media_id}/file")
async def feedback_media_file(
    fid: int,
    media_id: int,
    user: User = Depends(require_roles("manager")),
    db: AsyncSession = Depends(get_db),
):
    """Стрим байтов вложения. IDOR-защита по членству media_id в fb.media_files."""
    fb = await _get_feedback_or_404(db, fid)
    # int-нормализация: media_files — JSON-колонка; защищаемся от дрейфа типа (str vs int).
    allowed_ids = {int(m) for m in (fb.media_files or [])}
    if media_id not in allowed_ids:
        raise HTTPException(status_code=404, detail="Media not found for this feedback")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{_media_base()}/api/v1/media/{media_id}/file", headers=_media_headers())
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Media service error")
    # Не отражаем произвольный content-type из апстрима: только картинки, иначе октеты.
    ct = (resp.headers.get("content-type") or "").split(";")[0].strip()
    if ct not in ALLOWED_IMAGE_TYPES:
        ct = "application/octet-stream"
    return Response(
        content=resp.content,
        media_type=ct,
        headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
    )
