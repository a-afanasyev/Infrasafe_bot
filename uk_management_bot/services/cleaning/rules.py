"""Настройки модуля «Уборка»: версии append-only, значение на дату.

Правка настроек создаёт новую строку ``cleaning_rules``; на бизнес-дату действует
последняя версия, созданная ДО начала этой даты. Поэтому смена любого порога
вступает в силу с завтра и не обрывает идущий день.

Одно исключение — ПРОДЛЕНИЕ конца дня. Если новое ``day_end_time`` позже
сегодняшнего, а день ещё не закрыт, оно применяется сразу (``_extend_today``):
менеджер, который видит, что уборщицы не успевают, продлевает день именно на
сегодня. Сократить идущий день настройкой нельзя — это оборвало бы работу.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.cleaning import CleaningDay, CleaningRules
from uk_management_bot.utils.business_time import business_day_window, business_today, business_wall_clock
from uk_management_bot.utils.datetime_utils import as_utc, utc_now

logger = logging.getLogger(__name__)

DEFAULTS: Mapping[str, Any] = MappingProxyType({
    "day_end_time": "23:59",          # конец дня уборки, время бизнес-зоны (задаёт менеджер)
    "close_grace_minutes": 5,         # закрытие дня не раньше, чем через столько после конца
    "late_window_hours": 24,          # сколько после конца дня принимаются поздние доказательства
    "session_ttl_minutes": 120,       # окно уровня доверия `live` от первого открытия задания
    "allow_deferred_auto": False,     # допускать ли `deferred` к автоприёмке
    "backfill_days": 3,               # глубина догенерации пропущенных дней
    "floors_norm_per_day": 40,        # норма нагрузки на уборщицу
    "sample_every": 10,               # выборочный контроль: 1 из N автопринятых
    "probation_days": 14,             # первые дни новой уборщицы — всё на проверку
    "superseded_retention_days": 7,   # хранение заменённых фото
    "reminder_hours_before_end": 3,   # напоминание уборщице до конца дня
    "similar_days": 30,               # с фото за сколько дней сравнивать кадр (0 — не сравнивать)
    "similar_distance": 2,            # отличие отпечатков, при котором кадр «почти тот же»
    "min_seconds_per_floor": 20,      # быстрее этого между точками — «слишком быстро» (0 — выкл.)
})


@dataclass(frozen=True)
class Rules:
    version: Optional[int]  # None — версий ещё нет, действуют значения по умолчанию
    data: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.data[key]


async def rules_for(db: AsyncSession, day: date) -> Rules:
    """Настройки, действующие на бизнес-дату ``day``."""
    day_start, _ = business_day_window(day)
    row = (await db.execute(
        select(CleaningRules).where(CleaningRules.created_at < day_start)
        .order_by(CleaningRules.id.desc()).limit(1)
    )).scalar_one_or_none()
    stored = row.data if row is not None and isinstance(row.data, dict) else {}
    return Rules(version=row.id if row is not None else None,
                 data=MappingProxyType({**DEFAULTS, **stored}))


def day_end_at(day: date, rules: Rules) -> datetime:
    """Момент конца дня уборки (UTC) по настройке ``day_end_time`` = «ЧЧ:ММ»."""
    hour, minute = (int(part) for part in str(rules["day_end_time"]).split(":"))
    return business_wall_clock(day, hour, minute)


# ── правка настроек ─────────────────────────────────────────────────────────

_TIME_RE = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]")
# Верхние границы числовых настроек (нижняя у всех — 0).
_INT_MAX = {
    "close_grace_minutes": 120, "late_window_hours": 72, "session_ttl_minutes": 720, "backfill_days": 14,
    "floors_norm_per_day": 1000, "sample_every": 1000, "probation_days": 365,
    "superseded_retention_days": 365, "reminder_hours_before_end": 12,
    "similar_days": 365, "similar_distance": 16, "min_seconds_per_floor": 3600,
}


class RulesError(ValueError):
    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


def _validated(patch: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in patch.items():
        if key == "day_end_time":
            ok = isinstance(value, str) and _TIME_RE.fullmatch(value) is not None and value != "00:00"
        elif key == "allow_deferred_auto":
            ok = isinstance(value, bool)
        elif key in _INT_MAX:
            ok = type(value) is int and 0 <= value <= _INT_MAX[key]
        else:
            ok = False
        if not ok:
            raise RulesError(key)
    return dict(patch)


async def latest(db: AsyncSession) -> Rules:
    """Последняя сохранённая версия (то, что видит и правит менеджер)."""
    row = (await db.execute(select(CleaningRules).order_by(CleaningRules.id.desc()).limit(1))).scalar_one_or_none()
    stored = row.data if row is not None and isinstance(row.data, dict) else {}
    return Rules(version=row.id if row is not None else None, data=MappingProxyType({**DEFAULTS, **stored}))


async def _open_today(db: AsyncSession, now: datetime, *, lock: bool = False) -> Optional[CleaningDay]:
    """Сегодняшний день уборки, если он создан и ещё идёт."""
    # populate_existing: без него уже загруженный в сессию день вернулся бы из
    # identity map БЕЗ запроса — то есть без FOR UPDATE и с устаревшим closed_at.
    day = await db.get(CleaningDay, business_today(now), with_for_update=lock, populate_existing=lock)
    return None if day is None or day.skipped or day.closed_at is not None else day


async def today_end_at(db: AsyncSession, *, now: Optional[datetime] = None) -> Optional[datetime]:
    """До какого момента сегодня принимаются фото; None — дня нет или он уже закрыт."""
    day = await _open_today(db, now or utc_now())
    return None if day is None else as_utc(day.day_end_at)


async def _extend_today(db: AsyncSession, data: Mapping[str, Any], now: datetime,
                        actor_id: Optional[int]) -> None:
    """Применить более поздний конец дня к идущему дню (см. докстринг модуля).

    Строка дня берётся под блокировкой — так же её берёт ``days.close_days``,
    поэтому продление и закрытие не пересекаются: либо день продлён и закрытие
    увидит новое время, либо он уже закрыт и остаётся закрытым.
    """
    day = await _open_today(db, now, lock=True)
    if day is None:
        return
    new_end = day_end_at(day.work_date, Rules(version=None, data=data))
    if new_end <= as_utc(day.day_end_at):
        return
    # Версия настроек при повторном сохранении не создаётся, поэтому кто и
    # когда продлил день, остаётся только здесь.
    logger.info("cleaning: конец дня %s продлён с %s до %s (user_id=%s)",
                day.work_date, as_utc(day.day_end_at).isoformat(), new_end.isoformat(), actor_id)
    day.day_end_at = new_end
    # Напоминание «до конца дня N часов» могло уже уйти со старым временем —
    # сбрасываем отметку, чтобы оно ушло заново, с новым.
    day.reminded_at = None
    await db.flush()


async def save(db: AsyncSession, patch: Mapping[str, Any], *, actor_id: Optional[int],
               now: Optional[datetime] = None) -> Rules:
    """Новая версия настроек = последняя + правка; действует с завтрашней бизнес-даты.

    Исключение — продление конца дня, оно применяется и к идущему дню. Правка,
    которая ничего не меняет, версию не создаёт: журнал версий — это журнал
    изменений, а не нажатий «Сохранить».

    Продление проверяется при КАЖДОМ сохранении с ``day_end_time``, даже если
    версия не изменилась: настройку могли сохранить раньше, чем был создан
    сегодняшний день (тогда он создан по вчерашней версии), и повторное нажатие
    «Сохранить» с тем же временем обязано его продлить.
    """
    current = await latest(db)
    data = {**current.data, **_validated(patch)}
    if data == dict(current.data):
        saved = current
    else:
        row = CleaningRules(data=data, created_by=actor_id)
        db.add(row)
        await db.flush()
        saved = Rules(version=row.id, data=MappingProxyType(data))
    if "day_end_time" in patch:
        await _extend_today(db, data, now or utc_now(), actor_id)
    return saved
