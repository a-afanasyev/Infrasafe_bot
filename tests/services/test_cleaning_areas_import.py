"""Разбор CSV площадей (dbops/cleaning_areas_import.py) и оценка м² дома."""
import csv
import io

import pytest

from uk_management_bot.dbops import cleaning_areas_import as mod
from uk_management_bot.services.cleaning.areas import parse_areas

HEAD = ("building_id;адрес;подъезд;typical_m2;floor1_m2;basement_m2;особые_этажи;"
        "fire_stairs_m2;parking_exit_m2;elevator_cab_m2;источник;уверенность;примечание\n")


def _rows(body: str):
    return csv.DictReader(io.StringIO(HEAD + body), delimiter=";")


def test_rows_become_areas_per_building():
    areas = mod.areas_from_rows(_rows(
        "12;1G;*;28,4;62;;16:31.0 9:30,5;36;18;2.6;БТИ;высокая;\n"
        "12;1G;3;41;;;;;;;обмер;средняя;угловая\n"
        "13;1H;*;20;;;;;;;БТИ;высокая;\n"))
    assert areas == {
        12: {"entrances": {
            "*": {"typical": 28.4, "floors": {"16": 31.0, "9": 30.5, "1": 62.0},
                  "points": {"fire_stairs": 36.0, "parking": 18.0, "elevator": 2.6}},
            "3": {"typical": 41.0}}},
        13: {"entrances": {"*": {"typical": 20.0}}},
    }


@pytest.mark.parametrize("body", [
    "x;1G;*;28;;;;;;;;;\n",
    "12;1G;*;много;;;;;;;;;\n",
    "12;1G;*;28;;;16=31;;;;;;\n",
    "12;1G;*;28;;;;;;;;;\n12;1G;*;29;;;;;;;;;\n",
    "12;1G;3;;;;;;;;;;\n12;1G;3;29;;;;;;;;;\n",   # дубль после пустой строки
    "12;1G;*;28;62;;1:60;;;;;;\n",                # 1-й этаж дважды
    "١٢;1G;*;28;;;;;;;;;\n",                      # не-ASCII цифры
])
def test_bad_rows_are_rejected(body):
    with pytest.raises(mod.RowError):
        mod.areas_from_rows(_rows(body))


def test_zero_typical_is_kept():
    assert mod.areas_from_rows(_rows("12;1G;*;0;;;;;;;;;\n")) == {12: {"entrances": {"*": {"typical": 0.0}}}}


def test_estimate_sums_all_floors_basement_and_points():
    parsed = parse_areas({"entrances": {"*": {"typical": 20, "floors": {"1": 50, "-1": 70},
                                              "points": {"fire_stairs": 30}},
                                        "2": {"typical": 40}}}, floor_count=3, entrance_count=2)
    one = 50 + 20 * 2 + 70 + 30
    two = 50 + 40 * 2 + 70 + 30
    assert mod.estimate_m2(parsed, floor_count=3, entrance_count=2) == one + two
