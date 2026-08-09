"""API обратной связи (жалобы / пожелания).

- POST  ""                       — создать обращение (любой авторизованный; multipart, опц. фото)
- GET   ""                       — список (manager): фильтры type/status, пагинация
- GET   "/{fid}"                 — деталь (manager)
- PATCH "/{fid}"                 — статус / ответ (manager); ответ доставляется пользователю в Telegram
- GET   "/{fid}/media"           — метаданные вложений (manager)
- GET   "/{fid}/media/{mid}/file"— стрим байтов вложения (manager; для <img> в дашборде)
"""
import logging
from typing import Optional

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_current_user, get_db, require_roles
from uk_management_bot.api.feedback import service
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
from uk_management_bot.utils.media_sniff import sniff_media_mime
from uk_management_bot.utils.user_names import display_name

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_PHOTO_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif"}  # media-service allowlist (HEIC не входит)


# AUD5-APIFE-13: детекция — канон `utils/media_sniff` (он знает и видео);
# политика этой точки — только изображения, её держит ALLOWED_IMAGE_TYPES ниже,
# поэтому распознанное видео здесь по-прежнему отвергается.
_sniff_image_mime = sniff_media_mime
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
    """Имя с общим фолбэком (REFACTOR-133)."""
    return display_name(user)


def _media_base() -> str:
    return settings.MEDIA_SERVICE_URL.rstrip("/")


def _media_headers() -> dict:
    return {"X-API-Key": settings.MEDIA_SERVICE_API_KEY} if settings.MEDIA_SERVICE_API_KEY else {}


async def _deliver_feedback_safely(fid: int, ids, notify_text: str, photo) -> None:
    """Рассылка обращения менеджерам вне цикла запроса.

    ВСЁ под try, включая получение бота: исключение из BackgroundTask
    пробрасывается Starlette и завалило бы уже сформированный ответ
    (в CI — например, на невалидном токене).
    """
    try:
        await deliver_feedback_to_managers(
            _get_shared_bot(), telegram_ids=ids, text=notify_text, photo=photo
        )
    except Exception as e:
        logger.warning("feedback %s manager notify failed: %s", fid, e)


@router.post("", response_model=FeedbackOut)
@limiter.limit("10/minute")
async def create_feedback(
    request: Request,
    background: BackgroundTasks,
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
    fb = await service.persist_feedback(
        db, user_id=user.id, feedback_type=feedback_type, text=text, source="twa"
    )

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
                    await service.attach_media(db, fb, media_ids=[media_id])
            else:
                logger.warning("feedback %s media upload status %s", fb.id, resp.status_code)
        except Exception as e:
            logger.warning("feedback %s media upload failed: %s", fb.id, e)

    # 5) Уведомление менеджерам (best-effort).
    # AUD3-09: рассылка идёт ПОСЛЕ ответа фоновой задачей — она последовательна
    # по получателям, и inline-await подвешивал POST жителя на всю её длину.
    # Так же уже сделано в `api/shifts/executor_router._notify_many`; здесь
    # довели до того же вида. Данные для рассылки (БД) считаются до ответа —
    # в фоновую задачу уходит готовый DTO, сессия туда не утекает.
    try:
        ids = await manager_telegram_ids_async(db)
        notify_text = build_manager_notify_text(
            type_=feedback_type, text=text, author_name=_author_name(user),
            has_photo=bool(photo_bytes), lang="ru",
        )
        # Отдаём telegram_file_id от media-service (без повторной загрузки в Telegram);
        # bytes-fallback только если media-service недоступен.
        photo = tg_fid if tg_fid else (photo_bytes if photo_bytes else None)
        background.add_task(_deliver_feedback_safely, fb.id, ids, notify_text, photo)
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

    rows, total = await service.feedback_page(
        db, feedback_type=feedback_type, status=status, limit=limit, offset=offset,
    )

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
    fb = await service.feedback_by_id(db, fid)
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
    author = await service.author_of(db, fb.user_id)
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
    new_status = None
    if body.status is not None and body.status != fb.status:
        if body.status not in _STATUSES:
            raise HTTPException(status_code=422, detail="invalid status")
        if body.status not in _TRANSITIONS.get(fb.status, set()):
            raise HTTPException(status_code=422, detail=f"invalid transition {fb.status} -> {body.status}")
        new_status = body.status

    # Ответ: пустой/пробельный игнорируем (no-op); уведомляем автора только при изменении текста
    new_reply = None
    if body.reply is not None and body.reply.strip():
        candidate = body.reply.strip()
        if candidate != (fb.reply or ""):
            new_reply = candidate
    reply_changed = new_reply is not None

    await service.apply_feedback_edits(
        db, fb, status=new_status, reply=new_reply, replied_by=user.id if reply_changed else None,
    )

    author = await service.author_of(db, fb.user_id)

    if reply_changed and author and author.telegram_id:
        try:
            await send_feedback_reply_to_user(
                _get_shared_bot(), telegram_id=author.telegram_id,
                reply_text=fb.reply, lang=(author.language or "ru"),
            )
        except Exception as e:
            logger.warning("feedback %s reply notify failed: %s", fb.id, e)

    return _detail(fb, author)


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
