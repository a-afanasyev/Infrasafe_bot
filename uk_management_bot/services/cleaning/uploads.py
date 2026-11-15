"""Загрузка фото уборки: одна операция = один ключ, исход сохраняется.

Порядок (раздел 3 плана):

* всегда — валидация байтов, отпечаток присланного, поиск по ключу со сверкой
  владельца, задания, слота и содержимого; сохранённый исход возвращается как
  есть, срок и статус при повторе не проверяются;
* **А** приём: короткая транзакция под блокировкой задания, фиксирует
  ``received_at`` и вид операции (обычная / позднее доказательство), пишет
  ``pending`` с арендой либо сохранённый отказ;
* **Б** отправка в медиа-сервис без блокировок;
* **В** финализация: задание блокируется заново, строка закрывается условным
  обновлением по своей аренде, исход определяется по состоянию на этот момент.

Тяжёлая работа с изображением выполняется вне транзакций.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional, Union

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.cleaning import CleaningDay, CleaningPhoto, CleaningTask
from uk_management_bot.services.cleaning import acceptance, images
from uk_management_bot.services.cleaning.rules import rules_for
from uk_management_bot.services.cleaning.transitions import log_event, move
from uk_management_bot.services.executor_completion import (
    CompletionRefused,
    parse_idempotency_key,
    upload_executor_photo,
    validate_completion_photo,
)
from uk_management_bot.utils.business_time import fmt_datetime
from uk_management_bot.utils.datetime_utils import as_utc, utc_now

logger = logging.getLogger(__name__)

CATEGORY = "cleaning_photo"
LEASE = timedelta(minutes=2)
SLOT_RE = re.compile(r"floor:[1-9][0-9]{0,2}|point:[a-z_]{1,30}")
_OPEN = ("planned", "in_progress")                 # обычная операция
_LATE_OK = _OPEN + ("missed", "expired")           # позднее доказательство
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

MediaUpload = Callable[[int, int, bytes, str], Awaitable[int]]
MediaDelete = Callable[[int], Awaitable[None]]


class UploadRefused(Exception):
    """Отказ без сохранённой строки: код + HTTP-статус (4xx окончательный, 409/503 — повторить)."""

    def __init__(self, code: str, http_status: int):
        super().__init__(code)
        self.code, self.http_status = code, http_status


class MediaFailure(Exception):
    """Сбой медиа-сервиса: ``media_unavailable`` (временный) или ``media_rejected``."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class UploadResult:
    photo_id: int
    outcome: str                  # activated / superseded / evidence / refused
    refusal_code: Optional[str]
    media_id: Optional[int]
    replay: bool = False


@dataclass(frozen=True)
class _Claim:
    photo_id: int
    token: str
    stamp: str


def _result(photo: CleaningPhoto, *, replay: bool = False) -> UploadResult:
    return UploadResult(photo.id, photo.outcome, photo.refusal_code, photo.media_id, replay)


async def _lock_task(db: AsyncSession, task_id: int) -> Optional[CleaningTask]:
    return (await db.execute(
        select(CleaningTask).where(CleaningTask.id == task_id).with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()


def _stamp_text(now: datetime, task_id: int, slot: str, trust: str) -> str:
    return f"{fmt_datetime(now)} | #{task_id} | {slot.replace(':', ' ')} | {trust}"


# ── медиа-сервис по умолчанию ───────────────────────────────────────────────

async def _media_upload(task_id: int, user_id: int, jpeg: bytes, slot: str) -> int:
    try:
        return await upload_executor_photo(
            f"cl-{task_id}", user_id, jpeg, "image/jpeg",
            category=CATEGORY, name_suffix=slot.replace(":", "-"))
    except CompletionRefused as exc:
        # По коду, не по статусу: у окончательного отказа медиа статус тоже 5xx (502).
        raise MediaFailure("media_rejected" if exc.code == "media_rejected" else "media_unavailable") from None


async def _media_delete(media_id: int) -> None:
    from uk_management_bot.integrations import get_media_client

    client = get_media_client()
    if client is None:
        return
    try:
        await client.delete_media(media_id)
    except Exception as exc:  # noqa: BLE001 — лишний файл подберёт чистка
        logger.warning("cleaning: файл %s не удалён: %s", media_id, type(exc).__name__)


# ── сессия задания (уровень доверия live) ───────────────────────────────────

async def open_session(db: AsyncSession, task_id: int, user_id: int, *, now: Optional[datetime] = None) -> None:
    """Зафиксировать первое онлайн-открытие задания; повторное окно не продлевает."""
    now = now or utc_now()
    task = await _lock_task(db, task_id)
    if task is None or task.responsible_id != user_id or task.session_opened_at is not None:
        return
    day = await db.get(CleaningDay, task.work_date)
    if day is not None and now <= as_utc(day.day_end_at):
        task.session_opened_at = now
        await db.flush()


def _trust(task: CleaningTask, now: datetime, ttl_minutes: int, late: bool) -> str:
    if late:
        return "late"
    if task.session_opened_at is None:
        return "offline"
    opened = as_utc(task.session_opened_at)
    return "live" if opened <= now <= opened + timedelta(minutes=ttl_minutes) else "deferred"


# ── шаг 3: повтор или перехват аренды ───────────────────────────────────────

async def _existing(db: AsyncSession, key: str, user_id: int, task_id: int, slot: str,
                    sha: str, now: datetime) -> Union[UploadResult, _Claim, None]:
    photo = (await db.execute(
        select(CleaningPhoto).where(CleaningPhoto.op_key == key).with_for_update()
    )).scalar_one_or_none()
    if photo is None:
        return None
    if photo.uploaded_by != user_id:
        raise UploadRefused("not_found", 404)
    if (photo.task_id, photo.slot, photo.upload_sha256) != (task_id, slot, sha):
        raise UploadRefused("key_reused", 409)
    if photo.state == "done":
        return _result(photo, replay=True)
    if photo.claimed_at is not None and as_utc(photo.claimed_at) > now - LEASE:
        raise UploadRefused("in_progress", 409)
    token = str(uuid.uuid4())
    photo.claim_token, photo.claimed_at = token, now
    await db.flush()
    return _Claim(photo.id, token, _stamp_text(as_utc(photo.received_at), task_id, slot, photo.trust_level or "-"))


# ── фаза А ──────────────────────────────────────────────────────────────────

async def _accept(db: AsyncSession, *, key: str, user_id: int, task_id: int, slot: str, sha: str,
                  decoded: images.Decoded, captured: datetime, now: datetime,
                  system_camera: bool = False) -> Union[UploadResult, _Claim]:
    task = await _lock_task(db, task_id)
    day = await db.get(CleaningDay, task.work_date) if task is not None else None
    if task is None or day is None:
        raise UploadRefused("not_found", 404)
    rules = await rules_for(db, task.work_date)
    end = as_utc(day.day_end_at)
    late = now > end
    photo = CleaningPhoto(
        task_id=task_id, slot=slot, op_key=key, uploaded_by=user_id, upload_sha256=sha,
        pixel_sha256=decoded.pixel_sha256, dhash=decoded.dhash, received_at=now, client_captured_at=captured,
        trust_level=_trust(task, now, int(rules["session_ttl_minutes"]), late),
    )
    if system_camera and photo.trust_level in ("live", "deferred"):
        photo.trust_level = "offline"  # системная камера может пустить в галерею — не «live»

    refusal = None
    if task.responsible_id != user_id:
        refusal = "not_yours"
    elif slot not in (task.slots_required or ()):
        refusal = "bad_slot"
    elif late and now > end + timedelta(hours=int(rules["late_window_hours"])):
        refusal = "too_late"
    elif task.status not in (_LATE_OK if late else _OPEN):
        refusal = "frozen"

    if refusal is not None:
        photo.state, photo.outcome, photo.refusal_code = "done", "refused", refusal
        db.add(photo)
        await db.flush()
        return _result(photo)

    photo.state, photo.claim_token, photo.claimed_at = "pending", str(uuid.uuid4()), now
    db.add(photo)
    await db.flush()
    return _Claim(photo.id, photo.claim_token, _stamp_text(now, task_id, slot, photo.trust_level))


# ── фаза В ──────────────────────────────────────────────────────────────────

def _order(photo: CleaningPhoto) -> tuple[datetime, datetime]:
    """Какой кадр новее: время съёмки, при равенстве — время получения."""
    return as_utc(photo.client_captured_at or photo.received_at), as_utc(photo.received_at)


async def _activate(db: AsyncSession, task: CleaningTask, photo: CleaningPhoto, now: datetime) -> str:
    current = (await db.execute(
        select(CleaningPhoto).where(CleaningPhoto.task_id == task.id, CleaningPhoto.slot == photo.slot,
                                    CleaningPhoto.is_current.is_(True))
    )).scalar_one_or_none()
    if current is not None:
        if _order(current) > _order(photo):
            return "superseded"
        current.is_current = False
        await db.flush()  # освободить частичный уникальный индекс до установки нового
    photo.is_current, photo.activated_at = True, now
    await db.flush()
    if task.status == "planned":
        await move(db, task, "in_progress", kind="first_photo", actor_id=photo.uploaded_by)

    covered = set((await db.execute(
        select(CleaningPhoto.slot).where(CleaningPhoto.task_id == task.id, CleaningPhoto.is_current.is_(True))
    )).scalars())
    if covered >= set(task.slots_required or ()):
        rules = await rules_for(db, task.work_date)
        verdict = await acceptance.evaluate(db, task, rules)
        task.sampled = verdict.sampled
        await move(db, task, "accepted" if verdict.accept else "review", kind="completed",
                   rules_version=rules.version,
                   payload={"reasons": list(verdict.reasons), "sampled": verdict.sampled})
    return "activated"


async def _finalize(db: AsyncSession, claim: _Claim, user_id: int, task_id: int, now: datetime,
                    *, media_id: Optional[int], refusal: Optional[str] = None) -> Optional[UploadResult]:
    """Закрыть операцию по своей аренде; None — аренду перехватили."""
    task = await _lock_task(db, task_id)
    won = await db.execute(
        update(CleaningPhoto)
        .where(CleaningPhoto.id == claim.photo_id, CleaningPhoto.claim_token == claim.token,
               CleaningPhoto.state == "pending")
        .values(state="done", media_id=media_id)
    )
    if won.rowcount == 0 or task is None:
        return None
    photo = await db.get(CleaningPhoto, claim.photo_id, populate_existing=True)

    if refusal is not None:
        photo.outcome, photo.refusal_code = "refused", refusal
    elif photo.trust_level == "late":
        photo.outcome = "evidence"
        log_event(db, task, "late_evidence", actor_id=user_id, payload={"photo_id": photo.id, "slot": photo.slot})
    elif task.status in ("accepted", "review", "rejected"):
        photo.outcome, photo.refusal_code, photo.media_id = "refused", "frozen", None
    elif task.responsible_id != user_id or task.status not in _OPEN:
        photo.outcome = "evidence"
        log_event(db, task, "evidence", actor_id=user_id, payload={"photo_id": photo.id, "slot": photo.slot})
    else:
        photo.outcome = await _activate(db, task, photo, now)
    await db.flush()
    return _result(photo)


# ── вход ────────────────────────────────────────────────────────────────────

async def upload_photo(
    session_factory, *, user_id: int, task_id: int, slot: str, op_key: str, photo_bytes: bytes,
    client_captured_at: Optional[datetime] = None, now: Optional[datetime] = None,
    system_camera: bool = False,
    media_upload: MediaUpload = _media_upload, media_delete: MediaDelete = _media_delete,
) -> UploadResult:
    """Принять фото точки ``slot`` задания; см. докстринг модуля."""
    now = now or utc_now()
    try:
        key = parse_idempotency_key(op_key)
        validate_completion_photo(photo_bytes)
    except CompletionRefused as exc:
        raise UploadRefused(exc.code, exc.http_status) from None
    if SLOT_RE.fullmatch(slot) is None:
        raise UploadRefused("bad_slot", 422)
    sha = hashlib.sha256(photo_bytes).hexdigest()

    async with session_factory() as db:
        claim = await _existing(db, key, user_id, task_id, slot, sha, now)
        await db.commit()
    if isinstance(claim, UploadResult):
        return claim

    try:
        decoded = await asyncio.to_thread(images.decode, photo_bytes)
    except images.BadImage:
        raise UploadRefused("bad_photo", 422) from None

    if claim is None:
        try:
            async with session_factory() as db:
                claim = await _accept(db, key=key, user_id=user_id, task_id=task_id, slot=slot, sha=sha,
                                      decoded=decoded, captured=client_captured_at or now, now=now,
                                      system_camera=system_camera)
                await db.commit()
        except IntegrityError:  # тот же ключ вставлен параллельным запросом
            raise UploadRefused("in_progress", 409) from None
        if isinstance(claim, UploadResult):
            return claim

    media_id, refusal = None, None
    try:
        stamped = await asyncio.to_thread(images.stamp, decoded.jpeg, claim.stamp)
        media_id = await media_upload(task_id, user_id, stamped, slot)
    except MediaFailure as exc:
        if exc.code != "media_rejected":
            await _release(session_factory, claim)
            raise UploadRefused("media_unavailable", 503) from None
        refusal = "bad_photo"

    async with session_factory() as db:
        result = await _finalize(db, claim, user_id, task_id, now, media_id=media_id, refusal=refusal)
        await db.commit()
    if result is not None:
        if media_id is not None and result.media_id is None:  # отказ «заморожено»: файл не нужен
            await media_delete(media_id)
        return result

    # Аренду перехватил другой обработчик: свой файл лишний, исход — его.
    if media_id is not None:
        await media_delete(media_id)
    async with session_factory() as db:
        photo = await db.get(CleaningPhoto, claim.photo_id)
    if photo is not None and photo.state == "done":
        return _result(photo, replay=True)
    raise UploadRefused("in_progress", 409)


async def _release(session_factory, claim: _Claim) -> None:
    """Временный сбой: снять аренду, чтобы повтор не ждал её истечения."""
    async with session_factory() as db:
        await db.execute(
            update(CleaningPhoto)
            .where(CleaningPhoto.id == claim.photo_id, CleaningPhoto.claim_token == claim.token,
                   CleaningPhoto.state == "pending")
            .values(claimed_at=_EPOCH)
        )
        await db.commit()
