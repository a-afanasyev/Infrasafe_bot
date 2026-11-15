"""План уборки дома: разбор, задание подъезда на день, покрытие этажей, выбор версии.

Только чистые функции — без БД и времени. Версия плана хранит ``items`` как JSON;
здесь он проверяется и превращается в задание: какие работы и какие точки съёмки
(``floor:N`` на каждый этаж отрезка, ``point:*`` для работ без этажей и доп. точек).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Protocol, Sequence, TypeVar

# Работы по этажам и работы «в одной точке» (этажи не выбираются).
FLOOR_WORKS = ("wet", "dry")
POINT_WORKS = {"elevator": "point:elevator"}
WORK_KINDS = FLOOR_WORKS + tuple(POINT_WORKS)
WEEKDAYS = range(7)  # 0 = понедельник, как date.weekday()


class PlanError(ValueError):
    """План не прошёл проверку; ``code`` — машинный код для ответа API."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class PlanItem:
    work_kind: str
    weekdays: frozenset[int]
    entrances: Optional[frozenset[int]]  # None — все подъезды
    floors: tuple[int, ...]  # пусто у работ без этажей


@dataclass(frozen=True)
class DayTask:
    works: tuple[str, ...]
    slots: tuple[str, ...]


def _ints(value: object) -> Optional[list[int]]:
    if not isinstance(value, list) or not all(type(v) is int for v in value):
        return None
    return value


def _floors(raw: dict, kind: str, floor_count: int) -> tuple[int, ...]:
    lo, hi = raw.get("floor_from"), raw.get("floor_to")
    if kind in POINT_WORKS:
        if lo is not None or hi is not None:
            raise PlanError("bad_floors")
        return ()
    if lo is None and hi is None:
        return tuple(range(1, floor_count + 1))
    if type(lo) is not int or type(hi) is not int or not 1 <= lo <= hi <= floor_count:
        raise PlanError("bad_floors")
    return tuple(range(lo, hi + 1))


def _parse_item(raw: object, floor_count: int, entrance_count: int) -> PlanItem:
    if not isinstance(raw, dict):
        raise PlanError("bad_items")
    kind = raw.get("work_kind")
    if kind not in WORK_KINDS:
        raise PlanError("bad_work_kind")
    weekdays = _ints(raw.get("weekdays"))
    if not weekdays or any(d not in WEEKDAYS for d in weekdays):
        raise PlanError("bad_weekdays")
    entrances = raw.get("entrances")
    if entrances is not None:
        entrances = _ints(entrances)
        if not entrances or any(not 1 <= e <= entrance_count for e in entrances):
            raise PlanError("bad_entrances")
    return PlanItem(
        work_kind=kind,
        weekdays=frozenset(weekdays),
        entrances=None if entrances is None else frozenset(entrances),
        floors=_floors(raw, kind, floor_count),
    )


def parse_items(raw: object, *, floor_count: int, entrance_count: int) -> tuple[PlanItem, ...]:
    """JSON версии плана → проверенные пункты; иначе ``PlanError``."""
    if not isinstance(raw, list):
        raise PlanError("bad_items")
    return tuple(_parse_item(item, floor_count, entrance_count) for item in raw)


def _applies(item: PlanItem, entrance: int, weekday: int) -> bool:
    return weekday in item.weekdays and (item.entrances is None or entrance in item.entrances)


def task_for(items: Sequence[PlanItem], extra_points: Iterable[str], *,
             entrance: int, weekday: int) -> Optional[DayTask]:
    """Задание подъезда на день недели; None — работ по плану нет."""
    todays = [i for i in items if _applies(i, entrance, weekday)]
    if not todays:
        return None
    works = tuple(dict.fromkeys(i.work_kind for i in todays))
    floors = sorted({f for i in todays for f in i.floors})
    points = dict.fromkeys(
        [POINT_WORKS[i.work_kind] for i in todays if i.work_kind in POINT_WORKS]
        + [f"point:{p}" for p in extra_points]
    )
    return DayTask(works=works, slots=tuple(f"floor:{f}" for f in floors) + tuple(points))


def floor_coverage(items: Sequence[PlanItem], work_kind: str, *, floor_count: int,
                   entrance_count: int = 1) -> dict[int, int]:
    """Сколько раз в неделю работа проходит по каждому этажу (0 — пропуск).

    По худшему подъезду: строка «только подъезд 1» не закрывает этажи подъезда 2.
    """
    per_entrance = []
    for entrance in range(1, entrance_count + 1):
        counts = dict.fromkeys(range(1, floor_count + 1), 0)
        for item in items:
            if item.work_kind == work_kind and (item.entrances is None or entrance in item.entrances):
                for floor in item.floors:
                    counts[floor] += len(item.weekdays)
        per_entrance.append(counts)
    return {floor: min(c[floor] for c in per_entrance) for floor in range(1, floor_count + 1)}


class _Dated(Protocol):
    valid_from: date
    valid_to: Optional[date]


@dataclass(frozen=True)
class Validity:
    """Период действия версии/назначения (для тестов и лёгких выборок)."""

    id: int
    valid_from: date
    valid_to: Optional[date]


T = TypeVar("T", bound=_Dated)


def effective(rows: Iterable[T], day: date) -> Optional[T]:
    """Строка, действовавшая на дату: ``valid_from <= day <= valid_to`` (или без конца)."""
    for row in rows:
        if row.valid_from <= day and (row.valid_to is None or day <= row.valid_to):
            return row
    return None
