"""Раздел «Жители» — выдача документов менеджеру (PR-5).

Документы жителя лежат в Telegram: в БД хранится только `file_id`. Отдавать
его клиенту нельзя — это готовый токен скачивания в обход нашей авторизации,
поэтому файл проксируется: сервер сам ходит в Bot API и отдаёт байты.

Три вещи, которые здесь сделаны иначе, чем в медиа-прокси заявок, и это
намеренно:

1. **Свой классификатор типов.** `utils/media_sniff.sniff_media_mime` гейтит
   ЗАГРУЗКУ медиа заявок; расширить его набором «pdf» значило бы заодно
   разрешить pdf там. Здесь нужен ровно обратный по смыслу список: что мы
   готовы ОТДАТЬ менеджеру (jpeg/png/pdf), а не что готовы принять.

2. **Файл скачивается в буфер ДО отправки заголовков.** Стримить и обрывать
   на превышении лимита нельзя: статус уже ушёл клиенту, и вместо 413 он
   получит обрезанный файл с кодом 200. Лимит Bot API — 20 МБ: ровно 20
   отдаём, больше — 413.

3. **`Content-Disposition: attachment` для всего, кроме изображений** (PDF в
   том числе): просмотр pdf в браузере — это исполнение стороннего документа
   в контексте нашего домена.
"""
import logging
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api import telegram_send
from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.api.residents.schemas import ResidentDocumentOut
from uk_management_bot.database.models.user import User
from uk_management_bot.services.residents import queries
from uk_management_bot.services.residents.exceptions import ResidentNotFound

logger = logging.getLogger(__name__)

router = APIRouter()

_manager_only = require_roles("manager")

#: Лимит Bot API на скачивание файла: ровно лимит — отдаём, больше — 413
#: (`download_file` прерывает чтение при `size > max_bytes`).
_TG_FILE_LIMIT = 20 * 1024 * 1024
_TIMEOUT = 30

#: Что раздел готов ОТДАВАТЬ. Отдельно от `sniff_media_mime` — см. модульный
#: докстринг; там политика загрузки заявок, здесь политика выдачи документов.
_INLINE_TYPES = frozenset({"image/jpeg", "image/png"})

#: Метаданные — обычное чтение. Сам файл строже: маршрут ходит во внешний
#: Telegram и держит до 20 МБ в памяти на запрос, поэтому цена вызова здесь
#: несопоставима с остальными чтениями раздела.
_READ_LIMIT = "60/minute"
_FILE_LIMIT = "30/minute"


def _sniff_document_mime(data: bytes) -> str | None:
    """MIME документа по магическим байтам или None, если тип не поддержан.

    None означает «не отдаём»: подставлять тип из имени файла или из ответа
    Telegram нельзя — имя задаёт житель, а мы отдаём эти байты менеджеру в
    браузер.
    """
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:5] == b"%PDF-":
        return "application/pdf"
    return None


async def _require_document(db: AsyncSession, resident_id: int, doc_id: int):
    """Документ ИМЕННО этого жителя (Т3): чужой doc_id → 404."""
    for doc in await queries.list_resident_documents(db, resident_id):
        if doc.id == doc_id:
            return doc
    raise ResidentNotFound("Документ не найден")


@router.get("/{resident_id}/documents", response_model=list[ResidentDocumentOut])
@limiter.limit(_READ_LIMIT)
async def list_documents(
    request: Request,
    resident_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    """Метаданные документов. `file_id` наружу не уходит — см. схему."""
    resident = await queries.get_resident(db, resident_id)
    if resident is None:
        raise ResidentNotFound("Житель не найден")

    from enum import Enum as _Enum

    def _value(v):
        return v.value if isinstance(v, _Enum) else (str(v) if v is not None else None)

    return [
        ResidentDocumentOut(
            id=d.id,
            document_type=_value(d.document_type) or "other",
            file_name=d.file_name,
            file_size=d.file_size,
            verification_status=_value(d.verification_status),
            created_at=d.created_at,
        )
        for d in await queries.list_resident_documents(db, resident_id)
    ]


def _telegram_unavailable(doc_id: int, resident_id: int, reason: str) -> NoReturn:
    """Лог (причина — без URL с токеном) + 502 менеджеру."""
    logger.warning("Не удалось получить документ %s жителя %s: %s",
                   doc_id, resident_id, reason)
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Telegram недоступен",
    )


@router.get("/{resident_id}/documents/{doc_id}/file")
@limiter.limit(_FILE_LIMIT)
async def get_document_file(
    request: Request,
    resident_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    resident = await queries.get_resident(db, resident_id)
    if resident is None:
        raise ResidentNotFound("Житель не найден")
    doc = await _require_document(db, resident_id, doc_id)

    # A9-P2-9: getFile и скачивание — через общий модуль отправки (общий
    # клиент; текст сетевых ошибок без URL с токеном).
    meta = await telegram_send.get_file(doc.file_id, timeout=_TIMEOUT)
    if meta.http_status == 400:
        # Telegram отвечает 400 и на протухший, и на удалённый файл —
        # для менеджера это одно и то же: файла больше нет.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл недоступен в Telegram",
        )
    if not meta.ok:
        _telegram_unavailable(doc_id, resident_id, meta.describe())
    file_path = meta.result.get("file_path") if isinstance(meta.result, dict) else None
    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл недоступен в Telegram",
        )

    # Буфер ДО заголовков: обрыв стрима после начала передачи дал бы
    # обрезанный файл с кодом 200 вместо честного 413.
    try:
        body = await telegram_send.download_file(
            file_path, max_bytes=_TG_FILE_LIMIT, timeout=_TIMEOUT)
    except telegram_send.TelegramFileTooLarge:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Файл больше лимита Telegram (20 МБ)",
        ) from None
    except telegram_send.TelegramUnavailable as e:
        _telegram_unavailable(doc_id, resident_id, str(e))

    content_type = _sniff_document_mime(body)
    if content_type is None:
        logger.warning("Документ %s жителя %s: неподдержанный тип содержимого",
                       doc_id, resident_id)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Неподдерживаемый тип файла",
        )

    inline = content_type in _INLINE_TYPES
    return Response(
        content=body,
        media_type=content_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f"{'inline' if inline else 'attachment'}; "
                                   f'filename="document-{doc_id}"',
            # Приватный кэш на 5 минут: менеджер листает карточку туда-сюда, а
            # `file_path` из Telegram живёт около часа — дольше держать нечего.
            "Cache-Control": "private, max-age=300",
        },
    )
