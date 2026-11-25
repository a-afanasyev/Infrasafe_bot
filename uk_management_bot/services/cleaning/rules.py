"""Настройки модуля «Уборка»: версии append-only, значение на дату.

Правка настроек создаёт новую строку ``cleaning_rules``; на бизнес-дату действует
последняя версия, созданная ДО начала этой даты. Поэтому смена времени конца
дня (и любого порога) вступает в силу с завтра и не обрывает идущий день.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.cleaning import CleaningRules
from uk_management_bot.utils.business_time import business_day_window, business_wall_clock

DEFAULTS: Mapping[str, Any] = MappingProxyType({
    "day_end_time": "23:59",          # конец дня уборки, время бизнес-зоны (задаёт менеджер)
    "close_grace_minutes": 5,         # закрытие дня не раньше, чем через столько после конца
    "late_window_hours": 24,          # сколько после конца дня принимаются поздние доказательства
    "session_ttl_minutes": 120,       # окно уровня доверия `live` от первого открытия задания
    "allow_deferred_auto": False,     # допускать ли `deferred` к автоприёмке
    "backfill_days": 3,               # глубина догенерации пропущенных дней
    "floors_norm_per_day": 40,        # норма нагрузки на уборщицу
    "area_norm_m2_per_day": 0,        # норма в м² мест общего пользования (0 — перегрузка по этажам)
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
    "floors_norm_per_day": 1000, "area_norm_m2_per_day": 100000, "sample_every": 1000, "probation_days": 365,
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


async def save(db: AsyncSession, patch: Mapping[str, Any], *, actor_id: Optional[int]) -> Rules:
    """Новая версия настроек = последняя + правка; действует с завтрашней бизнес-даты."""
    data = {**(await latest(db)).data, **_validated(patch)}
    row = CleaningRules(data=data, created_by=actor_id)
    db.add(row)
    await db.flush()
    return Rules(version=row.id, data=MappingProxyType(data))
