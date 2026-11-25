"""Площади мест общего пользования подъезда — нагрузка уборщиц в м².

Только чистые функции. ``cleaning_building_settings.areas`` хранит
``{"entrances": {"*": {...}, "3": {...}}}``: на подъезд — ``typical`` (м² типового
этажа), ``floors`` (отличающиеся этажи: ``{"1": м², "-1": м²}``) и ``points``
(работы-точки плана: ``{"fire_stairs": м²}``). Подъезд переопределяет ``"*"`` по полю,
``floors``/``points`` — по ключу.

Нагрузка считается по слотам задания (``planning.task_for``): этаж идёт один раз в
день, какая бы работа в нём ни была (решение владельца 2026-11-25). Нет площади хоть
одного слота дня — нагрузка подъезда неизвестна (``None``), а не занижена.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Optional, Sequence

from uk_management_bot.services.cleaning.planning import (
    BASEMENT_FLOOR,
    POINT_WORKS,
    WEEKDAYS,
    PlanItem,
    task_for,
)

ALL_ENTRANCES = "*"
MAX_M2 = 10000
_FIELDS = frozenset({"typical", "floors", "points"})


class AreasError(ValueError):
    """Площади не прошли проверку; ``code`` — машинный код для ответа API."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class EntranceAreas:
    typical: Optional[float] = None
    floors: Mapping[int, float] = field(default_factory=lambda: MappingProxyType({}))
    points: Mapping[str, float] = field(default_factory=lambda: MappingProxyType({}))


Areas = Mapping[str, EntranceAreas]


def _m2(value: object) -> float:
    if type(value) not in (int, float) or not 0 <= value <= MAX_M2:
        raise AreasError("bad_area")
    return float(value)


def _floor(key: str, floor_count: int) -> int:
    try:
        floor = int(key)
    except (TypeError, ValueError):
        raise AreasError("bad_area_floor") from None
    # Только канонический ключ («01», « 1», «1_0» — нет): JSON хранится как пришёл.
    if key != str(floor) or floor == 0 or not BASEMENT_FLOOR <= floor <= floor_count:
        raise AreasError("bad_area_floor")
    return floor


def _mapping(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise AreasError("bad_areas")
    return raw


def _entrance(raw: object, floor_count: int) -> EntranceAreas:
    raw = _mapping(raw)
    if not set(raw) <= _FIELDS:
        raise AreasError("bad_areas")
    points = _mapping(raw.get("points", {}))
    if not set(points) <= set(POINT_WORKS):
        raise AreasError("bad_area_point")
    typical = raw.get("typical")
    return EntranceAreas(
        typical=None if typical is None else _m2(typical),
        floors=MappingProxyType({_floor(k, floor_count): _m2(v)
                                 for k, v in _mapping(raw.get("floors", {})).items()}),
        points=MappingProxyType({k: _m2(v) for k, v in points.items()}),
    )


def _entrance_key(key: object, entrance_count: int) -> str:
    if key == ALL_ENTRANCES:
        return key
    # Только канонический номер: «03» сохранился бы как есть, а подъезд ищется по «3».
    if (not isinstance(key, str) or not key.isascii() or not key.isdigit() or key != str(int(key))
            or not 1 <= int(key) <= entrance_count):
        raise AreasError("bad_area_entrance")
    return key


def parse_areas(raw: object, *, floor_count: int, entrance_count: int) -> Areas:
    """JSON площадей дома → проверенные площади по подъездам; ``None`` — площадей нет."""
    if raw is None:
        return MappingProxyType({})
    raw = _mapping(raw)
    if set(raw) != {"entrances"}:
        raise AreasError("bad_areas")
    return MappingProxyType({
        _entrance_key(key, entrance_count): _entrance(value, floor_count)
        for key, value in _mapping(raw["entrances"]).items()
    })


def for_entrance(areas: Areas, entrance: int) -> EntranceAreas:
    """Площади подъезда: общие ``"*"`` с переопределениями подъезда."""
    base, own = areas.get(ALL_ENTRANCES, EntranceAreas()), areas.get(str(entrance), EntranceAreas())
    return EntranceAreas(
        typical=own.typical if own.typical is not None else base.typical,
        floors=MappingProxyType({**base.floors, **own.floors}),
        points=MappingProxyType({**base.points, **own.points}),
    )


def slot_area(areas: EntranceAreas, slot: str) -> Optional[float]:
    """м² точки съёмки задания; ``None`` — площадь не задана."""
    kind, _, name = slot.partition(":")
    if kind == "floor":
        return areas.floors.get(int(name), areas.typical)
    return areas.points.get(name)


def m2_per_weekday(items: Sequence[PlanItem], areas: Areas, *, entrance: int) -> Optional[list[float]]:
    """м² подъезда на каждый день недели (пн…вс); ``None`` — площадей не хватает."""
    own = for_entrance(areas, entrance)
    if own.typical is None:
        return None
    result = []
    for weekday in WEEKDAYS:
        task = task_for(items, (), entrance=entrance, weekday=weekday)
        day = [slot_area(own, slot) for slot in (task.slots if task else ())]
        if None in day:
            return None
        result.append(round(sum(day), 1))
    return result
