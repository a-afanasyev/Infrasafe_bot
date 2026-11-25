"""Загрузка площадей мест общего пользования домов (нагрузка уборщиц в м²) из CSV.

CSV — от агента по сбору площадей (формат в docs/CLEANING_MODULE.md, «Нагрузка в м²»):
UTF-8, разделитель «;», десятичная точка или запятая. Колонки:
  building_id;адрес;подъезд;typical_m2;floor1_m2;basement_m2;особые_этажи;
  fire_stairs_m2;parking_exit_m2;elevator_cab_m2;источник;уверенность;примечание
подъезд «*» — все подъезды дома, номер — только отличающиеся поля этого подъезда;
особые_этажи — через пробел: «16:31 30:28.5» («;» занят разделителем CSV).

Без ``--apply`` — сухой прогон: по каждому дому подъезды, оценка м² МОП всего дома и
сравнение с паспортом (п. 2.3 «Площадь общего пользования»; расхождение >25% помечено).
С ``--apply`` пишет ``cleaning_building_settings.areas`` — всё или ничего: при любой
ошибке строки ничего не записывается. Запись в прод-БД — только с разрешения владельца.

Запуск в api-контейнере (``scripts/`` в образ не попадает — поэтому модуль пакета):
  docker cp areas.csv uk-management-api:/tmp/areas.csv
  docker exec uk-management-api python -m uk_management_bot.dbops.cleaning_areas_import /tmp/areas.csv
  docker exec uk-management-api python -m uk_management_bot.dbops.cleaning_areas_import /tmp/areas.csv --apply
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from typing import Iterable, Mapping

from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.building_passport import BuildingPassport
from uk_management_bot.database.models.cleaning import CleaningBuildingSettings
from uk_management_bot.services.cleaning.areas import AreasError, for_entrance, parse_areas, slot_area

POINT_COLUMNS = {"fire_stairs_m2": "fire_stairs", "parking_exit_m2": "parking", "elevator_cab_m2": "elevator"}
PASSPORT_GAP = 0.25


class RowError(ValueError):
    pass


def _num(text: str, where: str) -> float | None:
    text = (text or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        raise RowError(f"{where}: не число «{text}»") from None


def _special(text: str, where: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for part in (text or "").split():  # «;» — разделитель CSV, поэтому этажи через пробел
        floor, sep, m2 = part.partition(":")
        digits = floor.strip().removeprefix("-")
        if not sep or not digits.isascii() or not digits.isdigit():
            raise RowError(f"{where}: особый этаж «{part}», нужно «этаж:м²»")
        out[str(int(floor))] = _num(m2, where)
    return out


def _entrance(row: Mapping[str, str], where: str) -> dict:
    floors = _special(row.get("особые_этажи", ""), where)
    for column, key in (("floor1_m2", "1"), ("basement_m2", "-1")):
        value = _num(row.get(column, ""), where)
        if value is not None:
            if key in floors:
                raise RowError(f"{where}: этаж {key} и в {column}, и в особых этажах")
            floors[key] = value
    points = {key: v for column, key in POINT_COLUMNS.items() if (v := _num(row.get(column, ""), where)) is not None}
    typical = _num(row.get("typical_m2", ""), where)
    out: dict = {} if typical is None else {"typical": typical}  # 0 — тоже значение
    return out | {k: v for k, v in (("floors", floors), ("points", points)) if v}


def areas_from_rows(rows: Iterable[Mapping[str, str]]) -> dict[int, dict]:
    """Строки CSV → ``{building_id: {"entrances": {...}}}``; ``RowError`` на первой плохой."""
    out: dict[int, dict] = defaultdict(lambda: {"entrances": {}})
    seen: set[tuple[int, str]] = set()  # пустая строка подъезда в entrances не попадает — дубль ловим здесь
    for number, row in enumerate(rows, start=2):  # строка 1 — заголовок
        where = f"строка {number}"
        building = (row.get("building_id") or "").strip()
        scope = (row.get("подъезд") or "").strip() or "*"
        if not building.isascii() or not building.isdigit():
            raise RowError(f"{where}: building_id «{building}»")
        entrances = out[int(building)]["entrances"]
        if (int(building), scope) in seen:
            raise RowError(f"{where}: дом {building}, подъезд {scope} уже был")
        seen.add((int(building), scope))
        own = _entrance(row, where)
        if own:
            entrances[scope] = own
    return dict(out)


def estimate_m2(parsed, *, floor_count: int, entrance_count: int) -> float:
    """Оценка м² МОП дома: все этажи 1…N, −1 и точки каждого подъезда (если заданы)."""
    total = 0.0
    for entrance in range(1, entrance_count + 1):
        own = for_entrance(parsed, entrance)
        floors = [f"floor:{f}" for f in range(1, floor_count + 1)] + (["floor:-1"] if -1 in own.floors else [])
        total += sum(slot_area(own, slot) or 0 for slot in floors) + sum(own.points.values())
    return round(total, 1)


def _report(session, by_building: dict[int, dict]) -> tuple[list[str], list[tuple[int, dict]]]:
    errors, ready = [], []
    for building_id, areas in sorted(by_building.items()):
        building = session.get(Building, building_id)
        if building is None:
            errors.append(f"дом {building_id}: нет в справочнике")
            continue
        try:
            parsed = parse_areas(areas, floor_count=building.floor_count, entrance_count=building.entrance_count)
        except AreasError as exc:
            errors.append(f"дом {building_id} ({building.address}): {exc.code}")
            continue
        total = estimate_m2(parsed, floor_count=building.floor_count, entrance_count=building.entrance_count)
        passport = session.query(BuildingPassport).filter_by(building_id=building_id).one_or_none()
        common = (passport.values or {}).get("common_area") if passport is not None else None
        mark = ""
        if isinstance(common, (int, float)) and common > 0:
            gap = abs(total - common) / common
            mark = f" | паспорт {common} м², расхождение {gap:.0%}" + (" ⚠️" if gap > PASSPORT_GAP else "")
        print(f"дом {building_id} ({building.address}): подъезды {', '.join(areas['entrances'])}; "
              f"≈{total} м² МОП{mark}")
        ready.append((building_id, areas))
    return errors, ready


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv_path")
    parser.add_argument("--apply", action="store_true", help="записать (иначе сухой прогон)")
    args = parser.parse_args(argv)
    from uk_management_bot.database.session import SessionLocal  # движок БД — только при запуске

    with open(args.csv_path, encoding="utf-8-sig", newline="") as fh:
        try:
            by_building = areas_from_rows(csv.DictReader(fh, delimiter=";"))
        except RowError as exc:
            print(f"ОШИБКА: {exc}", file=sys.stderr)
            return 1
    with SessionLocal() as session:
        errors, ready = _report(session, by_building)
        for line in errors:
            print(f"ОШИБКА: {line}", file=sys.stderr)
        if errors:
            print("Ничего не записано: исправьте ошибки.", file=sys.stderr)
            return 1
        if not args.apply:
            print(f"Сухой прогон: {len(ready)} домов. Для записи — --apply.")
            return 0
        for building_id, areas in ready:
            row = session.get(CleaningBuildingSettings, building_id)
            if row is None:
                session.add(CleaningBuildingSettings(building_id=building_id, areas=areas))
            else:
                row.areas = areas
        session.commit()
        print(f"Записано: {len(ready)} домов.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
