"""Эталон формы №3824 («Общий технический паспорт многоквартирного дома»).

Файл `services/building_passport/form_3824.json` — дословный текст приложения к
Правилам содержания МКД (lex.uz/ru/docs/8165716). По нему строятся схема
паспорта и печатный лист формы, поэтому случайная правка эталона меняет то,
что УК сдаёт проверяющим. Тест держит состав и отпечаток: изменить эталон
можно только вместе с этим файлом, то есть осознанно.
"""
import hashlib
import json
from pathlib import Path

ETALON = Path(__file__).resolve().parents[1] / "services" / "building_passport" / "form_3824.json"
ROWS_SHA256 = "98a98b8b0f848b43c9315b58ab0687518d81b1f63def52f27b8ebcc16ca4911e"


def _load() -> dict:
    return json.loads(ETALON.read_text(encoding="utf-8"))


def _item_key(no: str) -> tuple[int, int]:
    section, index = no.split(".")
    return int(section), int(index)


def test_etalon_structure_matches_original_form():
    rows = _load()["rows"]

    assert [row["seq"] for row in rows] == list(range(1, len(rows) + 1))
    assert rows[0]["kind"] == "header" and len(rows[0]["cells"]) == 4, "в оригинале четыре колонки"
    assert [row["section"] for row in rows if row["kind"] == "section"] == list(range(1, 14))

    items = [row["no"] for row in rows if row["kind"] == "item"]
    assert len(items) == len(set(items)) == 87
    assert items == sorted(items, key=_item_key), "пункты идут в порядке формы"
    assert all(_item_key(row["no"])[0] == row["section"] for row in rows if row["kind"] in ("item", "row"))
    # Этих номеров нет в самом оригинале — «дыры» в нумерации не ошибка эталона.
    assert "2.18" not in items and "5.6" not in items

    assert sum(row["kind"] == "subheading" for row in rows) == 11, "подзаголовки без номера"
    assert len(rows) == 252


def test_etalon_is_not_edited_by_accident():
    canonical = json.dumps(_load()["rows"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == ROWS_SHA256, (
        "эталон формы изменён: если форма действительно изменилась, обновите отпечаток "
        "и повысьте версию схемы паспорта"
    )
