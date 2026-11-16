"""Чистые функции плана уборки: разбор, задание на день, покрытие этажей, выбор версии."""
from datetime import date

import pytest

from uk_management_bot.services.cleaning.planning import (
    PlanItem,
    PlanError,
    Validity,
    effective,
    floor_coverage,
    parse_items,
    task_for,
)

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)

# Дом 12 из раскадровки: 3 подъезда, 9 этажей.
RAW = [
    {"work_kind": "wet", "weekdays": [MON, THU], "floor_from": 1, "floor_to": 5},
    {"work_kind": "wet", "weekdays": [TUE, FRI], "floor_from": 6, "floor_to": 9},
    {"work_kind": "dry", "weekdays": [WED, SAT], "floor_from": 1, "floor_to": 1},
    {"work_kind": "elevator", "weekdays": [MON, TUE, WED, THU, FRI, SAT], "entrances": [1, 3]},
]


def _items():
    return parse_items(RAW, floor_count=9, entrance_count=3)


def test_task_lists_floor_range_of_the_day_and_elevator_point():
    task = task_for(_items(), (), entrance=1, weekday=TUE)
    assert task.works == ("wet", "elevator")
    assert task.slots == ("floor:6", "floor:7", "floor:8", "floor:9", "point:elevator")


def test_basement_and_parking_are_point_works_with_own_days():
    items = parse_items([
        {"work_kind": "wet", "weekdays": [MON]},
        {"work_kind": "basement", "weekdays": [MON, THU]},
        {"work_kind": "parking", "weekdays": [THU], "entrances": [2]},
    ], floor_count=2, entrance_count=2)
    assert task_for(items, (), entrance=1, weekday=MON).slots == ("floor:1", "floor:2", "point:basement")
    assert task_for(items, (), entrance=1, weekday=THU).slots == ("point:basement",)
    both = task_for(items, (), entrance=2, weekday=THU)
    assert (both.works, both.slots) == (("basement", "parking"), ("point:basement", "point:parking"))


def test_entrance_without_elevator_work_gets_only_floors():
    task = task_for(_items(), (), entrance=2, weekday=MON)
    assert task.works == ("wet",)
    assert task.slots == ("floor:1", "floor:2", "floor:3", "floor:4", "floor:5")


def test_no_work_on_the_day_means_no_task():
    assert task_for(_items(), (), entrance=2, weekday=SUN) is None


def test_all_floors_when_range_omitted_and_overlapping_items_do_not_duplicate():
    items = parse_items(
        [{"work_kind": "wet", "weekdays": [MON]}, {"work_kind": "dry", "weekdays": [MON], "floor_from": 1, "floor_to": 2}],
        floor_count=3, entrance_count=1,
    )
    task = task_for(items, (), entrance=1, weekday=MON)
    assert task.works == ("wet", "dry")
    assert task.slots == ("floor:1", "floor:2", "floor:3")


def test_extra_points_are_added_to_every_task():
    task = task_for(_items(), ("entrance",), entrance=2, weekday=WED)
    assert task.slots == ("floor:1", "point:entrance")


def test_coverage_counts_times_per_week_per_floor():
    assert floor_coverage(_items(), "wet", floor_count=9) == {f: 2 for f in range(1, 10)}
    dry = floor_coverage(_items(), "dry", floor_count=9)
    assert dry[1] == 2 and all(dry[f] == 0 for f in range(2, 10))


def test_coverage_takes_worst_entrance():
    only_first = [PlanItem("wet", frozenset({1, 4}), frozenset({1}), tuple(range(1, 10)))]
    assert floor_coverage(only_first, "wet", floor_count=9, entrance_count=1)[5] == 2
    assert set(floor_coverage(only_first, "wet", floor_count=9, entrance_count=2).values()) == {0}


@pytest.mark.parametrize("raw, code", [
    ([{"work_kind": "polish", "weekdays": [MON]}], "bad_work_kind"),
    ([{"work_kind": "wet", "weekdays": []}], "bad_weekdays"),
    ([{"work_kind": "wet", "weekdays": [7]}], "bad_weekdays"),
    ([{"work_kind": "wet", "weekdays": [MON], "floor_from": 3, "floor_to": 2}], "bad_floors"),
    ([{"work_kind": "wet", "weekdays": [MON], "floor_from": 1, "floor_to": 10}], "bad_floors"),
    ([{"work_kind": "wet", "weekdays": [MON], "floor_from": 2}], "bad_floors"),
    ([{"work_kind": "wet", "weekdays": [MON], "entrances": [4]}], "bad_entrances"),
    ([{"work_kind": "wet", "weekdays": [MON], "entrances": []}], "bad_entrances"),
    ([{"work_kind": "elevator", "weekdays": [MON], "floor_from": 1, "floor_to": 2}], "bad_floors"),
    ("nope", "bad_items"),
])
def test_invalid_plan_is_rejected_with_code(raw, code):
    with pytest.raises(PlanError) as exc:
        parse_items(raw, floor_count=9, entrance_count=3)
    assert exc.value.code == code


def test_effective_picks_the_version_valid_on_that_date():
    old = Validity(id=1, valid_from=date(2026, 11, 1), valid_to=date(2026, 11, 17))
    new = Validity(id=2, valid_from=date(2026, 11, 18), valid_to=None)
    assert effective([old, new], date(2026, 11, 17)).id == 1
    assert effective([old, new], date(2026, 11, 18)).id == 2
    assert effective([old, new], date(2026, 10, 31)) is None


def test_first_floor_is_shot_as_three_points(cleaning_first_floor_points):
    from uk_management_bot.services.cleaning.planning import shooting_slots

    assert cleaning_first_floor_points == ("point:entry1", "point:entry2", "point:lift_hall")
    slots = ("floor:1", "floor:2", "floor:3", "point:elevator")
    assert shooting_slots(slots, cleaning_first_floor_points) == (
        "point:entry1", "point:entry2", "point:lift_hall", "floor:2", "floor:3", "point:elevator")
    # первый этаж сегодня не моется — точек первого этажа нет
    assert shooting_slots(("floor:2", "floor:3"), cleaning_first_floor_points) == ("floor:2", "floor:3")
    # правило выключено — прежний один кадр
    assert shooting_slots(slots, ()) == slots
