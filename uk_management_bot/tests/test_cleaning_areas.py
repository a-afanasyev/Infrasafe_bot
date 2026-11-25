"""Площади мест общего пользования и нагрузка подъезда в м²."""
import pytest

from uk_management_bot.services.cleaning.areas import (
    AreasError,
    for_entrance,
    m2_per_weekday,
    parse_areas,
    slot_area,
)
from uk_management_bot.services.cleaning.planning import parse_items

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)

AREAS = {"entrances": {
    "*": {"typical": 20, "floors": {"1": 50, "-1": 70, "5": 25.5}, "points": {"fire_stairs": 30, "elevator": 2.5}},
    "2": {"typical": 40, "points": {"fire_stairs": 60}},
}}


def _areas(raw=AREAS):
    return parse_areas(raw, floor_count=5, entrance_count=2)


def test_entrance_overrides_all_by_field_and_key():
    one, two = for_entrance(_areas(), 1), for_entrance(_areas(), 2)
    assert (one.typical, dict(one.floors), dict(one.points)) == (
        20, {1: 50, -1: 70, 5: 25.5}, {"fire_stairs": 30, "elevator": 2.5})
    assert (two.typical, dict(two.floors), dict(two.points)) == (
        40, {1: 50, -1: 70, 5: 25.5}, {"fire_stairs": 60, "elevator": 2.5})


def test_slot_area_uses_special_floor_typical_and_points():
    one = for_entrance(_areas(), 1)
    assert [slot_area(one, s) for s in ("floor:1", "floor:-1", "floor:3", "floor:5", "point:fire_stairs",
                                        "point:parking")] == [50, 70, 20, 25.5, 30, None]


def test_m2_counts_floor_once_a_day_and_adds_points():
    items = parse_items([
        {"work_kind": "wet", "weekdays": [MON], "floor_from": -1, "floor_to": 5},
        {"work_kind": "dry", "weekdays": [MON], "floor_from": 1, "floor_to": 2},
        {"work_kind": "fire_stairs", "weekdays": [MON, TUE], "entrances": [2]},
    ], floor_count=5, entrance_count=2)
    one = m2_per_weekday(items, _areas(), entrance=1)
    assert one[MON] == 70 + 50 + 20 * 3 + 25.5 and one[TUE:] == [0] * 6
    two = m2_per_weekday(items, _areas(), entrance=2)
    assert two[MON] == 70 + 50 + 40 * 3 + 25.5 + 60 and two[TUE] == 60


def test_no_typical_or_missing_point_area_means_unknown():
    items = parse_items([{"work_kind": "wet", "weekdays": [MON]},
                         {"work_kind": "parking", "weekdays": [TUE]}], floor_count=5, entrance_count=2)
    assert m2_per_weekday(items, parse_areas(None, floor_count=5, entrance_count=2), entrance=1) is None
    assert m2_per_weekday(items, _areas(), entrance=1) is None  # у парковки нет площади


@pytest.mark.parametrize("raw", [
    [],
    {"entrances": []},
    {"entrances": {"3": {"typical": 1}}},
    {"entrances": {"x": {"typical": 1}}},
    {"entrances": {"02": {"typical": 1}}},
    {"entrances": {"*": {"typical": -1}}},
    {"entrances": {"*": {"typical": 10001}}},
    {"entrances": {"*": {"typical": True}}},
    {"entrances": {"*": {"typical": "20"}}},
    {"entrances": {"*": {"floors": {"0": 1}}}},
    {"entrances": {"*": {"floors": {"6": 1}}}},
    {"entrances": {"*": {"floors": {"-2": 1}}}},
    {"entrances": {"*": {"floors": {"01": 1}}}},
    {"entrances": {"*": {"floors": {" 1": 1}}}},
    {"entrances": {"*": {"floors": {"1_0": 1}}}},
    {"entrances": {"*": {"floors": {"+1": 1}}}},
    {"entrances": {"²": {"typical": 1}}},
    {"entrances": {"*": {"points": {"wet": 1}}}},
    {"entrances": {"*": {"area": 1}}},
    {"other": {}},
])
def test_bad_areas_are_rejected(raw):
    with pytest.raises(AreasError):
        _areas(raw)
