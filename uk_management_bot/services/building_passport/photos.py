"""Фото разделов паспорта дома: одна загрузка = один ключ операции.

Упрощённый вариант ``services/cleaning/uploads.py``:

* **приём** — под блокировкой паспорта проверяются статус и лимит на раздел,
  пишется строка ``pending`` с арендой и адресом файла ``media_ref``;
* **отправка** — без блокировок. ``media_ref`` выводится из ключа операции и
  передаётся медиа-сервису вместо номера заявки, поэтому при повторе файл
  сначала ищется: найден — берём его, не найден — загружаем. Так сбой записи в
  БД после загрузки не даёт второго файла;
* **финализация** — паспорт блокируется заново, строка закрывается условным
  обновлением по своей аренде; если паспорт за это время подписали — отказ.

Фото, вошедшее в подписанную редакцию, из медиа-сервиса не удаляется никогда.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.building_passport import (
    BuildingPassport,
    BuildingPassportPhoto,
    BuildingPassportRevision,
)
from uk_management_bot.services.building_passport import schema
from uk_management_bot.services.building_passport import service as svc
from uk_management_bot.services.building_passport.service import Actor, PassportError
from uk_management_bot.services.executor_completion import (
    CompletionRefused,
    parse_idempotency_key,
    upload_executor_photo,
    validate_completion_photo,
)
from uk_management_bot.utils.datetime_utils import as_utc, utc_now

logger = logging.getLogger(__name__)

CATEGORY = "passport_photo"
MAX_PER_SECTION = 20
LEASE = timedelta(minutes=2)  # больше таймаута загрузки в медиа
ABANDON_AFTER = timedelta(days=1)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class MediaUnavailable(Exception):
    """Медиа-сервис не ответил: операцию можно повторить с тем же ключом."""


class MediaRejected(Exception):
    """Медиа-сервис окончательно отверг файл."""


def media_ref(op_key: str) -> str:
    """Адрес файла в медиа: ``bp`` + 18 знаков ключа — ровно 20, предел медиа-сервиса."""
    return "bp" + uuid.UUID(op_key).hex[:18]


# ── медиа-сервис (подменяется в тестах) ─────────────────────────────────────

async def _find(ref: str) -> list[int]:
    from uk_management_bot.integrations import get_media_client

    client = get_media_client()
    if client is None:
        raise MediaUnavailable
    try:
        rows = await client.get_request_media(ref, category=CATEGORY)
    except Exception as exc:  # noqa: BLE001 — вслепую не загружаем
        logger.warning("passport: поиск файла %s не удался: %s", ref, type(exc).__name__)
        raise MediaUnavailable from None
    return sorted(int(row["id"]) for row in rows if row.get("id") is not None)


async def _upload(ref: str, user_id: Optional[int], photo_bytes: bytes, mime: str, section: str) -> int:
    try:
        return await upload_executor_photo(ref, user_id or 0, photo_bytes, mime, category=CATEGORY, name_suffix=section)
    except CompletionRefused as exc:
        raise (MediaRejected if exc.code == "media_rejected" else MediaUnavailable) from None


async def _delete(media_id: int) -> None:
    from uk_management_bot.integrations import get_media_client

    client = get_media_client()
    if client is None:
        return
    try:
        await client.delete_media(media_id)
    except Exception as exc:  # noqa: BLE001 — лишний файл не мешает паспорту
        logger.warning("passport: файл %s не удалён: %s", media_id, type(exc).__name__)


@dataclass(frozen=True)
class Media:
    find: Callable[[str], Awaitable[list[int]]] = _find
    upload: Callable[[str, Optional[int], bytes, str, str], Awaitable[int]] = _upload
    delete: Callable[[int], Awaitable[None]] = _delete


# ── приём ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _Claim:
    photo_id: int
    token: str
    ref: str


def _out(photo: BuildingPassportPhoto, *, replay: bool = False) -> dict:
    return {"id": photo.id, "section": photo.section, "media_id": photo.media_id,
            "uploaded_by_name": photo.uploaded_by_name,
            "uploaded_at": photo.created_at.isoformat() if photo.created_at else None, "replay": replay}


async def _accept(db: AsyncSession, building_id: int, actor: Actor, *, key: str, section: str, sha: str,
                  now: datetime) -> dict | _Claim:
    _, passport = await svc._open(db, building_id)
    passport = await svc._store(db, passport, building_id)
    token = str(uuid.uuid4())
    photo = (await db.execute(select(BuildingPassportPhoto).where(
        BuildingPassportPhoto.op_key == key).with_for_update())).scalar_one_or_none()
    if photo is not None:
        if (photo.passport_id, photo.section, photo.upload_sha256) != (passport.id, section, sha):
            raise PassportError("key_reused", 409)
        if photo.state == "done":
            if photo.removed_at is not None:  # фото уже убрали: ключ отработал, нужен новый
                raise PassportError("key_reused", 409)
            return _out(photo, replay=True)
        if photo.state == "pending" and photo.claimed_at is not None and as_utc(photo.claimed_at) > now - LEASE:
            raise PassportError("in_progress", 409)
    if passport.status == "signed":
        raise PassportError("signed", 409)
    if photo is None:
        taken = (await db.execute(select(func.count(BuildingPassportPhoto.id)).where(
            BuildingPassportPhoto.passport_id == passport.id, BuildingPassportPhoto.section == section,
            BuildingPassportPhoto.removed_at.is_(None),
            BuildingPassportPhoto.state.in_(("pending", "done"))))).scalar_one()
        if taken >= MAX_PER_SECTION:
            raise PassportError("photo_limit", 409, (section,))
        photo = BuildingPassportPhoto(passport_id=passport.id, section=section, op_key=key, media_ref=media_ref(key),
                                      upload_sha256=sha, uploaded_by=actor.user_id, uploaded_by_name=actor.name)
        db.add(photo)
    photo.state, photo.claim_token, photo.claimed_at = "pending", token, now
    await db.flush()
    return _Claim(photo.id, token, photo.media_ref)


async def _release(session_factory, claim: _Claim) -> None:
    """Временный сбой медиа: снять аренду, чтобы повтор не ждал её истечения."""
    async with session_factory() as db:
        await db.execute(update(BuildingPassportPhoto).where(
            BuildingPassportPhoto.id == claim.photo_id, BuildingPassportPhoto.claim_token == claim.token,
            BuildingPassportPhoto.state == "pending").values(claimed_at=_EPOCH))
        await db.commit()


async def _finalize(db: AsyncSession, building_id: int, actor: Actor, claim: _Claim,
                    media_id: Optional[int]) -> Optional[dict]:
    """Закрыть операцию по своей аренде. None — аренду перехватили."""
    passport = await svc.load(db, building_id, for_update=True)
    if passport is None or passport.status == "signed":
        raise PassportError("signed", 409)
    if media_id is None:
        raise PassportError("bad_photo", 422)
    won = await db.execute(update(BuildingPassportPhoto).where(
        BuildingPassportPhoto.id == claim.photo_id, BuildingPassportPhoto.claim_token == claim.token,
        BuildingPassportPhoto.state == "pending").values(state="done", media_id=media_id))
    if won.rowcount == 0:
        return None
    photo = await db.get(BuildingPassportPhoto, claim.photo_id, populate_existing=True)
    passport.version += 1  # подпись требует точной версии: подписывающий увидит новое фото
    svc._log(db, passport, actor, "photo_added", {"section": photo.section, "photo_id": photo.id})
    await db.flush()
    return _out(photo)


async def upload(session_factory, building_id: int, actor: Actor, *, section: str, op_key: str,
                 photo_bytes: bytes, media: Media = Media(), now: Optional[datetime] = None) -> dict:
    """Принять фото раздела. Отказы — ``PassportError``; 503 ``media_unavailable`` и 409
    ``in_progress`` повторяются с тем же ключом."""
    now = now or utc_now()
    try:
        key = parse_idempotency_key(op_key)
        mime = validate_completion_photo(photo_bytes)
    except CompletionRefused as exc:
        raise PassportError(exc.code, exc.http_status) from None
    if section not in {s.key for s in schema.sections()}:
        raise PassportError("bad_section", 422)
    sha = hashlib.sha256(photo_bytes).hexdigest()

    try:
        async with session_factory() as db:
            claim = await _accept(db, building_id, actor, key=key, section=section, sha=sha, now=now)
            await db.commit()
    except IntegrityError:  # тот же ключ вставлен параллельным запросом
        raise PassportError("in_progress", 409) from None
    except PassportError as exc:
        if exc.code != "stale":
            raise
        # Паспорт дома в этот момент создаёт параллельный запрос (первое фото или первая правка).
        raise PassportError("in_progress", 409) from None
    if isinstance(claim, dict):
        return claim

    media_id: Optional[int] = None
    uploaded = False
    try:
        found = await media.find(claim.ref)
        if found:
            media_id = found[0]
            for extra in found[1:]:
                await media.delete(extra)
        else:
            media_id, uploaded = await media.upload(claim.ref, actor.user_id, photo_bytes, mime, section), True
    except MediaUnavailable:
        await _release(session_factory, claim)
        raise PassportError("media_unavailable", 503) from None
    except MediaRejected:
        media_id = None

    try:
        async with session_factory() as db:
            result = await _finalize(db, building_id, actor, claim, media_id)
            await db.commit()
    except PassportError:
        async with session_factory() as db:
            await _finalize_refusal(db, claim)
        if media_id is not None:
            await media.delete(media_id)
        raise
    if result is not None:
        return result

    # Аренду перехватил другой обработчик: исход — его; свой лишний файл убираем.
    async with session_factory() as db:
        photo = await db.get(BuildingPassportPhoto, claim.photo_id)
    if photo is not None and photo.state == "done":
        if uploaded and media_id != photo.media_id:
            await media.delete(media_id)
        return _out(photo, replay=True)
    raise PassportError("in_progress", 409)


async def _finalize_refusal(db: AsyncSession, claim: _Claim) -> None:
    await db.execute(update(BuildingPassportPhoto).where(
        BuildingPassportPhoto.id == claim.photo_id, BuildingPassportPhoto.claim_token == claim.token,
        BuildingPassportPhoto.state == "pending").values(state="refused", media_id=None))
    await db.commit()


# ── чтение и удаление ───────────────────────────────────────────────────────

async def _photo(db: AsyncSession, building_id: int, photo_id: int) -> BuildingPassportPhoto:
    """Готовое фото паспорта именно этого дома; чужой ``photo_id`` — 404."""
    photo = (await db.execute(select(BuildingPassportPhoto).join(BuildingPassport).where(
        BuildingPassportPhoto.id == photo_id, BuildingPassport.building_id == building_id,
        BuildingPassportPhoto.state == "done"))).scalar_one_or_none()
    if photo is None or photo.media_id is None:
        raise PassportError("not_found", 404)
    return photo


async def _in_revision(db: AsyncSession, photo: BuildingPassportPhoto) -> bool:
    revisions = (await db.execute(select(BuildingPassportRevision.photos).where(
        BuildingPassportRevision.passport_id == photo.passport_id))).scalars()
    return any(item.get("id") == photo.id for photos in revisions for item in photos or ())


async def media_id_of(db: AsyncSession, building_id: int, photo_id: int) -> int:
    photo = await _photo(db, building_id, photo_id)
    if photo.removed_at is not None and not await _in_revision(db, photo):
        raise PassportError("not_found", 404)  # убрано и ни в одной редакции не числится
    return photo.media_id


async def remove(db: AsyncSession, building_id: int, photo_id: int, actor: Actor) -> Optional[int]:
    """Убрать фото из рабочего набора. Возвращает ``media_id``, если файл можно
    удалить из медиа (ни одна редакция на него не ссылается), иначе None."""
    _, passport = await svc._open(db, building_id)
    if passport is None:
        raise PassportError("not_found", 404)
    if passport.status == "signed":
        raise PassportError("signed", 409)
    photo = await _photo(db, building_id, photo_id)
    if photo.removed_at is not None:
        raise PassportError("not_found", 404)
    photo.removed_at = utc_now()
    passport.version += 1
    svc._log(db, passport, actor, "photo_removed", {"section": photo.section, "photo_id": photo.id})
    await db.flush()
    return None if await _in_revision(db, photo) else photo.media_id


# ── чистка брошенных загрузок ───────────────────────────────────────────────

async def cleanup(session_factory, *, media: Media = Media(), now: Optional[datetime] = None) -> int:
    """Загрузки, не доведённые до конца за сутки: файлы по ``media_ref`` удаляются,
    строка закрывается как брошенная. Медиа недоступно — строка ждёт следующего прохода."""
    now = now or utc_now()
    async with session_factory() as db:
        stale = (await db.execute(select(BuildingPassportPhoto.id, BuildingPassportPhoto.media_ref).where(
            BuildingPassportPhoto.state == "pending",
            BuildingPassportPhoto.claimed_at < now - ABANDON_AFTER,
            BuildingPassportPhoto.created_at < now - ABANDON_AFTER))).all()
    closed = 0
    for photo_id, ref in stale:
        token = str(uuid.uuid4())
        mine = (BuildingPassportPhoto.id == photo_id, BuildingPassportPhoto.state == "pending")
        async with session_factory() as db:
            # Сначала аренда: повтор загрузки в это время получит in_progress и не
            # подберёт файл, который чистка сейчас удалит.
            taken = await db.execute(update(BuildingPassportPhoto).where(
                *mine, BuildingPassportPhoto.claimed_at < now - ABANDON_AFTER
            ).values(claim_token=token, claimed_at=utc_now()))
            await db.commit()
        if taken.rowcount == 0:
            continue
        state = "abandoned"
        try:
            for media_id in await media.find(ref):
                await media.delete(media_id)
        except MediaUnavailable:
            state = "pending"  # аренду снимаем, строка ждёт следующего прохода
        async with session_factory() as db:
            await db.execute(update(BuildingPassportPhoto).where(
                *mine, BuildingPassportPhoto.claim_token == token).values(state=state, claimed_at=_EPOCH))
            await db.commit()
        closed += state == "abandoned"
    return closed
