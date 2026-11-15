"""Отключения, которые объявляет сантехник на смене (TWA: обычный и простой режим).

Один путь для обоих экранов: ``announce`` создаёт запись ``notices``
(``source=staff``, адресована домам, опубликована и сразу в очереди рассылки —
жители домов и менеджеры получают сообщение), ``close`` закрывает её и ставит
в ту же очередь короткую новость «включили».

Кто может объявить: сантехник (специализация ``plumber``) на
активной смене — тот же предикат смены, что у пула заявок. Закрыть может автор
(даже после смены — бот спрашивает «включили?» при её завершении) или любой
сантехник на смене (сменщик).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.news_item import BROADCAST_NONE, BROADCAST_PENDING
from uk_management_bot.database.models.notice import (
    NOTICE_KIND_NEWS,
    NOTICE_KIND_OUTAGE,
    NOTICE_SCOPE_BUILDINGS,
    NOTICE_SOURCE_STAFF,
    NOTICE_STATUS_CLOSED,
    NOTICE_STATUS_PUBLISHED,
    Notice,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.utils.business_time import business_day_window, business_today
from uk_management_bot.utils.datetime_utils import utc_now
from uk_management_bot.utils.shifts import is_on_shift_now_async
from uk_management_bot.utils.specializations import parse_specializations

# Что сантехник объявляет сам; электричество и газ — менеджер из веба.
RESOURCES = ("water", "heating")
# Только сантехник (решение владельца 2026-11-15): специалист по отоплению не объявляет.
PLUMBER_SPECIALIZATIONS = frozenset({"plumber"})
# «На сколько»: часы, до конца дня или «не знаю» (запись висит, пока не закроют).
DURATIONS = {"1h": 1, "2h": 2, "4h": 4, "day": None, "unknown": None}
MAX_BUILDINGS = 30
TITLE_MAX = 200
# Сколько новость «включили» остаётся на витрине.
RESTORED_SHOWN = timedelta(hours=6)

_OFF = {"water": ("Отключена вода", "Suv o'chirildi"), "heating": ("Отключено отопление", "Isitish o'chirildi")}
_ON = {"water": ("Воду включили", "Suv yoqildi"), "heating": ("Отопление включили", "Isitish yoqildi")}
_UNKNOWN_END = ("Время включения сообщим дополнительно.", "Yoqilish vaqti haqida qo'shimcha xabar beramiz.")

# Код отказа → HTTP-статус (роутер).
REFUSAL_STATUS = {
    "not_plumber": 403, "no_active_shift": 403, "not_yours": 403,
    "not_found": 404, "not_open": 409, "already_open": 409,
    "bad_resource": 422, "bad_duration": 422, "bad_buildings": 422,
}


class OutageRefused(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def refusal(db: AsyncSession, user: User, now: Optional[datetime] = None) -> Optional[str]:
    """Почему пользователь не может объявить отключение; None — может."""
    # Статус — здесь, а не в каталоге: гейт роутера бота (ActionGate) его не проверяет.
    if user.status != "approved" or not (parse_specializations(user) & PLUMBER_SPECIALIZATIONS):
        return "not_plumber"
    if not await is_on_shift_now_async(db, user.id, now):
        return "no_active_shift"
    return None


def _title(label: str, place: str) -> str:
    return f"{label} — {place}"[:TITLE_MAX]


async def _place(db: AsyncSession, building_ids: list[int]) -> str:
    """Адреса домов через запятую, в порядке справочника; не все нашлись — отказ."""
    rows = (await db.execute(
        select(Building.id, Building.address)
        .where(Building.id.in_(building_ids), Building.is_active.is_(True)).order_by(Building.address)
    )).all()
    if len(rows) != len(set(building_ids)):
        raise OutageRefused("bad_buildings")
    return ", ".join(address for _, address in rows)


def _ends_at(duration: str, now: datetime) -> Optional[datetime]:
    if duration not in DURATIONS:
        raise OutageRefused("bad_duration")
    if duration == "day":
        return business_day_window(business_today(now))[1]
    hours = DURATIONS[duration]
    return now + timedelta(hours=hours) if hours else None


def _open_clause():
    return (Notice.source == NOTICE_SOURCE_STAFF, Notice.kind == NOTICE_KIND_OUTAGE,
            Notice.status == NOTICE_STATUS_PUBLISHED)


async def announce(db: AsyncSession, user: User, *, resource: str, building_ids: list[int],
                   duration: str, now: Optional[datetime] = None) -> Notice:
    now = now or utc_now()
    code = await refusal(db, user, now)
    if code:
        raise OutageRefused(code)
    if resource not in RESOURCES:
        raise OutageRefused("bad_resource")
    ids = sorted({int(i) for i in building_ids})
    if not ids or len(ids) > MAX_BUILDINGS:
        raise OutageRefused("bad_buildings")
    ends_at = _ends_at(duration, now)
    place = await _place(db, ids)
    # Двойное нажатие и «объявил коллега»: то же отключение по тому же дому уже идёт.
    for other in (await db.execute(select(Notice).where(*_open_clause(), Notice.resource == resource))).scalars():
        if set(other.scope_ids or []) & set(ids):
            raise OutageRefused("already_open")
    unknown = duration == "unknown"
    notice = Notice(
        kind=NOTICE_KIND_OUTAGE, resource=resource, source=NOTICE_SOURCE_STAFF,
        title_ru=_title(_OFF[resource][0], place), title_uz=_title(_OFF[resource][1], place),
        text_ru=_UNKNOWN_END[0] if unknown else "", text_uz=_UNKNOWN_END[1] if unknown else "",
        important=True, status=NOTICE_STATUS_PUBLISHED, publish_at=now, starts_at=now, ends_at=ends_at,
        scope=NOTICE_SCOPE_BUILDINGS, scope_ids=ids, broadcast_status=BROADCAST_PENDING, created_by=user.id,
    )
    db.add(notice)
    await db.flush()
    _audit(db, user, "outage_announced", notice, duration=duration)
    await db.commit()
    await db.refresh(notice)
    return notice


async def close(db: AsyncSession, user: User, notice_id: int, now: Optional[datetime] = None) -> Notice:
    """«Включили»: запись закрыта, жителям тех же домов — короткая новость."""
    now = now or utc_now()
    notice = await db.get(Notice, notice_id)
    if notice is None or notice.source != NOTICE_SOURCE_STAFF or notice.kind != NOTICE_KIND_OUTAGE:
        raise OutageRefused("not_found")
    if notice.status != NOTICE_STATUS_PUBLISHED:
        raise OutageRefused("not_open")
    if notice.created_by != user.id and await refusal(db, user, now):
        raise OutageRefused("not_yours")
    notice.status, notice.closed_at, notice.closed_by = NOTICE_STATUS_CLOSED, now, user.id
    if notice.broadcast_status == BROADCAST_PENDING:
        notice.broadcast_status = BROADCAST_NONE  # закрыли раньше, чем ушло «отключили»
    ru, uz = _ON.get(notice.resource or "", _ON["water"])
    place_ru = notice.title_ru.partition(" — ")[2]
    db.add(Notice(
        kind=NOTICE_KIND_NEWS, source=NOTICE_SOURCE_STAFF,
        title_ru=_title(ru, place_ru), title_uz=_title(uz, place_ru),
        status=NOTICE_STATUS_PUBLISHED, publish_at=now, expires_at=now + RESTORED_SHOWN,
        scope=notice.scope, scope_ids=list(notice.scope_ids or []),
        broadcast_status=BROADCAST_PENDING, created_by=user.id,
    ))
    _audit(db, user, "outage_closed", notice)
    await db.commit()
    await db.refresh(notice)
    return notice


def _audit(db: AsyncSession, user: User, action: str, notice: Notice, **extra) -> None:
    db.add(AuditLog(user_id=user.id, telegram_user_id=user.telegram_id, action=action, details={
        "notice_id": notice.id, "resource": notice.resource, "building_ids": list(notice.scope_ids or []), **extra}))


async def open_outages(db: AsyncSession, user: User, *, allowed: bool) -> list[Notice]:
    """Незакрытые отключения: сантехнику на смене — все, остальным — свои."""
    stmt = select(Notice).where(*_open_clause()).order_by(Notice.id.desc())
    if not allowed:
        stmt = stmt.where(Notice.created_by == user.id)
    return list((await db.execute(stmt)).scalars().all())


async def options(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    """Всё, что нужно экрану: можно ли объявить, справочник домов, идущие отключения."""
    reason = await refusal(db, user, now)
    yards: list[dict] = []
    if reason is None:
        rows = (await db.execute(
            select(Yard.id, Yard.name, Building.id, Building.address)
            .join(Building, Building.yard_id == Yard.id)
            .where(Yard.is_active.is_(True), Building.is_active.is_(True))
            .order_by(Yard.name, Building.address)
        )).all()
        for yard_id, yard_name, building_id, address in rows:
            if not yards or yards[-1]["id"] != yard_id:
                yards.append({"id": yard_id, "name": yard_name, "buildings": []})
            yards[-1]["buildings"].append({"id": building_id, "address": address})
    return {
        "allowed": reason is None, "reason": reason, "resources": list(RESOURCES),
        "durations": list(DURATIONS), "yards": yards,
        "open": await open_outages(db, user, allowed=reason is None),
    }


# --- Напоминания автору (бот: конец смены и истёкший срок) — sync, под run_db ---

@dataclass(frozen=True)
class OpenOutage:
    notice_id: int
    telegram_id: int
    language: str
    title_ru: str
    title_uz: str

    def title(self) -> str:
        return (self.title_uz if self.language == "uz" else "") or self.title_ru


def _open_sync(db: Session, *conditions) -> list[OpenOutage]:
    rows = db.execute(
        select(Notice.id, User.telegram_id, User.language, Notice.title_ru, Notice.title_uz)
        .join(User, User.id == Notice.created_by)
        .where(*_open_clause(), User.telegram_id.is_not(None), *conditions).order_by(Notice.id)
    ).all()
    return [OpenOutage(int(i), int(tg), lang or "ru", ru, uz) for i, tg, lang, ru, uz in rows]


def open_by_author_sync(db: Session, user_id: int) -> list[OpenOutage]:
    return _open_sync(db, Notice.created_by == user_id)


def overdue_sync(db: Session, now: datetime, window: timedelta) -> list[OpenOutage]:
    """Срок вышел за последний ``window``, а запись не закрыта.

    ponytail: метки «уже напомнили» нет — напоминание одно, когда срок попадает
    в окно тика; пропущенный тик = пропущенное напоминание. Нужны повторы —
    колонка reminded_at.
    """
    return _open_sync(db, Notice.ends_at > now - window, Notice.ends_at <= now)
