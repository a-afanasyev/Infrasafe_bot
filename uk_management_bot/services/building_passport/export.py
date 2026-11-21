"""Выгрузка паспорта дома в XLSX.

Строится из **переданных** схемы, эталона формы и значений, а не из текущих
модулей: подписанная редакция печатается по своей копии схемы и эталона и не
меняется после правки формы.

Листы:

* «Форма №3824» — строки оригинала по порядку и дословно; значение — в колонке
  «Қиймати». Шапка УК и место подписи — вне тела формы;
* «Дополнение УК» — пункты и варианты, которых в форме нет;
* «Разбивка» — полные строки окон, дверей и труб (в форме они свёрнуты).

Текст от людей пишется через ``_put`` / ``clean_text`` отчёта аналитики: строка
с «=» остаётся текстом, управляющие символы убираются.
"""
from __future__ import annotations

import io
from typing import Any, Iterable, Mapping, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.worksheet import Worksheet

from uk_management_bot.services.request_analytics.official_xlsx import (
    HEADER_FILL,
    HEADER_FONT,
    SECTION_FONT,
    WRAP,
    _print_setup,
    _put,
    _widths,
    clean_text,
)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DASH = "—"
MARK = "✓"
ABSENT_CELL = "мавжуд эмас"  # строка формы «отсутствует»
OPENING_GROUPS = ("windows", "doors")
#: Число печатается в строке варианта, выбранного в другом пункте: в форме 5.7
#: толщина пишется в скобках у выбранного материала, отдельной строки нет.
ROW_FOLLOWS = {"roof_insulation_thickness": "roof_insulation"}
BOLD = Font(bold=True)
ITALIC = Font(italic=True)

LABELS = {
    "ru": {"form": "Форма №3824", "extra": "Дополнение УК", "rows": "Разбивка", "summary": "Сводная",
           "draft": "ЧЕРНОВИК — паспорт не подписан", "revision": "Редакция №{no}", "organization": "Организация",
           "address": "Адрес", "inspection_date": "Дата осмотра", "responsible_name": "Ответственный",
           "note": "Примечание", "signature": "Подпись ответственного: ____________________   Дата: ____________",
           "item": "Пункт", "value": "Значение", "house": "Дом", "status": "Статус",
           "off_form": "шу жумладан шаклдан ташқари турлар: {count} дона, {area} м2 — «{sheet}» варағига қаранг",
           "extra_note": "Сведения, которых нет в форме №3824; ведутся управляющей компанией."},
    "uz": {"form": "3824-shakl", "extra": "UK qo'shimchasi", "rows": "Tafsilot", "summary": "Yig'ma",
           "draft": "QORALAMA — pasport imzolanmagan", "revision": "{no}-tahrir", "organization": "Tashkilot",
           "address": "Manzil", "inspection_date": "Ko'rik sanasi", "responsible_name": "Mas'ul",
           "note": "Izoh", "signature": "Mas'ul shaxs imzosi: ____________________   Sana: ____________",
           "item": "Band", "value": "Qiymat", "house": "Uy", "status": "Holat",
           "off_form": "шу жумладан шаклдан ташқари турлар: {count} дона, {area} м2 — «{sheet}» варағига қаранг",
           "extra_note": "3824-shaklda yo'q ma'lumotlar; boshqaruv kompaniyasi yuritadi."},
}


def _num(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _sum(rows: Iterable[Mapping], key: str) -> Optional[float]:
    parts = [row[key] for row in rows if row.get(key) is not None]
    return round(sum(parts), 3) if parts else None


def _items(schema: Mapping) -> list[dict]:
    return [item for section in schema["sections"] for item in section["items"]]


def _option(field: Mapping, key: Any) -> Optional[dict]:
    return next((o for o in field.get("options") or () if o["key"] == key), None)


def visible_values(schema: Mapping, values: Mapping) -> dict:
    """Значения без скрытых пунктов: зависимый пункт остаётся в данных, когда его
    условие перестало выполняться, но в файл попадать не должен."""
    items = {i["key"]: i for i in _items(schema)}

    def shown(key: str, seen: frozenset = frozenset()) -> bool:
        rule = items[key].get("show_if")
        if not rule:
            return True
        parent, allowed = rule
        return parent in items and parent not in seen and shown(parent, seen | {key}) and values.get(parent) in allowed

    return {k: v for k, v in values.items()
            if (k.removesuffix("_text") if k.removesuffix("_text") in items else k) not in items
            or shown(k.removesuffix("_text") if k.removesuffix("_text") in items else k)}


def _etalon_rows(form: Mapping) -> dict[str, dict[int, list[str]]]:
    out: dict[str, dict[int, list[str]]] = {}
    for row in form["rows"]:
        if row["kind"] in ("item", "row"):
            out.setdefault(row["no"], {})[row["row"]] = row["cells"]
    return out


# ── значения строк формы ────────────────────────────────────────────────────

def _opening_text(rows: list[Mapping]) -> str:
    """Окна или двери одного типа: суммы; размеры — если одинаковы, иначе перечень."""
    count, area = _sum(rows, "count"), _sum(rows, "area")
    sizes = sorted({(r.get("height"), r.get("width")) for r in rows if r.get("height") and r.get("width")})
    if len(sizes) == 1:
        size = f"бўйи {_num(sizes[0][0])} м, эни {_num(sizes[0][1])} м"
    else:
        size = ", ".join(f"{_num(h)}×{_num(w)} м" for h, w in sizes)
    parts = [f"{_num(count)} дона" if count is not None else "", size, f"{_num(area)} м2" if area is not None else ""]
    return "; ".join(p for p in parts if p)


def _fold_openings(group: Mapping, rows: list[Mapping], etalon: Mapping, cells: dict) -> None:
    no = group["form"][0][0]
    types = next(f for f in group["fields"] if f["key"] == "type")
    by_form: dict[str, list[Mapping]] = {}
    for row in rows:
        option = _option(types, row.get("type"))
        if option and option.get("form"):
            by_form.setdefault(option["form"], []).append(row)
    for row_no, texts in etalon.get(no, {}).items():
        if texts and texts[0] in by_form:
            cells[(no, row_no)] = _opening_text(by_form[texts[0]])


def _fold_pipes(group: Mapping, rows: list[Mapping], cells: dict) -> None:
    """Четыре пункта формы: участок × материал; в каждом — Ø, длина, удовл., неудовл."""
    fields = {f["key"]: f for f in group["fields"]}
    runs = [o["key"] for o in fields["run"]["options"]]
    materials = [o["key"] for o in fields["material"]["options"]]
    numbers = [no for no, _ in group["form"]]
    for row_group in {(r.get("run"), r.get("material")) for r in rows}:
        if row_group[0] not in runs or row_group[1] not in materials:
            continue
        no = numbers[runs.index(row_group[0]) * len(materials) + materials.index(row_group[1])]
        mine = [r for r in rows if (r.get("run"), r.get("material")) == row_group]
        diameters = sorted({r["diameter"] for r in mine if r.get("diameter") is not None})
        texts = [", ".join(_num(d) for d in diameters),
                 *(_num(v) if (v := _sum(mine, key)) is not None else "" for key in ("length", "ok_length", "bad_length"))]
        for row_no, text in enumerate(texts, start=1):
            if text:
                cells[(no, row_no)] = text


def _fold_plain(group: Mapping, rows: list[Mapping], cells: dict) -> None:
    """Открытая строка 2.13 (квартиры сверх 7 комнат): перечень в графике формы."""
    no, row_nos = group["form"][0]
    parts = (("rooms", "хона"), ("count", "дона"), ("area", "м2"))
    cells[(no, (row_nos or [1])[0])] = "; ".join(
        ", ".join(f"{_num(row[key])} {unit}" for key, unit in parts if row.get(key) is not None) for row in rows)


def _mark_absent(group: Mapping, etalon: Mapping, cells: dict, *, unknown: bool = False) -> None:
    """Группы нет в доме — строка «мавжуд эмас»; данных нет — прочерк."""
    for no, row_nos in group["form"]:
        rows = etalon.get(no, {})
        absent_row = next((n for n, texts in rows.items() if [t.lower() for t in texts] == [ABSENT_CELL]), None)
        if absent_row is not None and not unknown:
            cells[(no, absent_row)] = MARK
        else:
            cells[(no, (row_nos or [1])[0])] = DASH


def _other_row(rows: Mapping, claimed: list, option: Mapping) -> Optional[int]:
    """Строка формы «другое — указать» для варианта с расшифровкой; None — такой строки нет."""
    return next((n for n in claimed if option.get("form") and option["form"] in rows.get(n, ())), None)


def _field_cell(field: Mapping, values: Mapping, unknown: Mapping, etalon: Mapping, cells: dict,
                items: Mapping) -> None:
    no = field["form_no"]
    rows = etalon.get(no, {})
    claimed = field.get("form_rows") or sorted(rows)
    if not claimed:
        return
    target, text = claimed[0], None
    value = values.get(field["key"])
    if field["key"] in unknown:
        text = DASH
    elif value is None:
        return
    elif field["type"] == "choice":
        option = _option(field, value)
        if option is None:
            return
        if option.get("other"):
            row = _other_row(rows, claimed, option)
            if row is None:
                return  # строки «другое» у пункта нет — вариант уходит на лист «Дополнение УК»
            # Названный вариант каталога печатается своим названием, «другое» — расшифровкой.
            target, text = row, str(values.get(f"{field['key']}_text") or option["uz"])
        elif option.get("form"):
            target = next((n for n in claimed if option["form"] in rows.get(n, ())), claimed[0])
            text = option["form"]
        else:
            return  # вариант вне формы — на листе «Дополнение УК»
    else:
        text = _num(value)
        leader = items.get(ROW_FOLLOWS.get(field["key"], ""))
        if leader is not None:
            option = _option(leader, values.get(leader["key"])) or {}
            target = next((n for n in claimed if option.get("form") in rows.get(n, ())), claimed[0])
            cells[(no, target)] = text  # число занимает место отметки варианта в этой строке
            return
    cells[(no, target)] = f"{cells[(no, target)]} / {text}" if (no, target) in cells else text  # html-raw: ячейка XLSX, не Telegram


def form_cells(schema: Mapping, form: Mapping, values: Mapping, unknown: Mapping, absent: Iterable[str]) -> dict:
    """Что печатать в колонке «Қиймати»: (пункт, строка) → текст."""
    etalon, cells, gone = _etalon_rows(form), {}, set(absent)
    values = visible_values(schema, values)
    items = {i["key"]: i for i in _items(schema)}
    for item in _items(schema):
        if item["kind"] == "field":
            if item.get("form_no"):
                _field_cell(item, values, unknown, etalon, cells, items)
            continue
        rows = values.get(item["key"]) or []
        if not item.get("form"):
            continue
        if item["key"] in gone or item["key"] in unknown:
            _mark_absent(item, etalon, cells, unknown=item["key"] not in gone)
        elif not rows:
            continue
        elif item["key"] in OPENING_GROUPS:
            _fold_openings(item, rows, etalon, cells)
        elif {"run", "material"} <= {f["key"] for f in item["fields"]}:
            _fold_pipes(item, rows, cells)
        else:
            _fold_plain(item, rows, cells)
    if values.get("attic_type") == "none":
        cells[("5.9", 1)] = "йўқ"  # нет чердака — вариант самой строки формы «м (ҳ) / йўқ»
    for no, rows in etalon.items():  # «отсутствует»: числовые строки пункта все нулевые
        absent_row = next((n for n, texts in rows.items() if [t.lower() for t in texts] == [ABSENT_CELL]), None)
        others = [cells.get((no, n)) for n in rows if n != absent_row]
        if absent_row and (no, absent_row) not in cells and all(o == "0" for o in others) and others:
            cells[(no, absent_row)] = MARK
    return cells


def off_form_openings(schema: Mapping, values: Mapping) -> tuple[int, float]:
    """Окна типов, которых нет в форме: они входят в итог 2.19, но не в строки 2.17."""
    group = next((i for i in _items(schema) if i["key"] == "windows"), None)
    if group is None:
        return 0, 0.0
    types = next(f for f in group["fields"] if f["key"] == "type")
    rows = [r for r in values.get("windows") or []
            if not ((_option(types, r.get("type")) or {}).get("form"))]
    return int(_sum(rows, "count") or 0), float(_sum(rows, "area") or 0)


# ── листы ───────────────────────────────────────────────────────────────────

def _text(ws: Worksheet, row: int, col: int, value: Any, **kw) -> None:
    _put(ws, row, col, clean_text(value) if isinstance(value, str) else value, **kw)


def _head(ws: Worksheet, L: Mapping, head: Mapping) -> int:
    row = 1
    _text(ws, row, 1, head["mark"], font=BOLD)
    for key in ("organization", "address", "inspection_date", "responsible_name", "note"):
        if head.get(key):
            row += 1
            _text(ws, row, 1, L[key])
            _text(ws, row, 2, str(head[key]), align=WRAP)
    return row + 2


def _form_sheet(ws: Worksheet, L: Mapping, form: Mapping, cells: Mapping, head: Mapping, note_219: Optional[str]) -> None:
    row = _head(ws, L, head)
    _text(ws, row, 1, form["title"], font=SECTION_FONT, align=Alignment(horizontal="center", wrap_text=True))
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    for line in form["rows"]:
        row += 1
        kind = line["kind"]
        if kind == "header":
            for col, title in enumerate(line["cells"], start=1):
                _text(ws, row, col, title, font=HEADER_FONT, fill=HEADER_FILL, align=WRAP, border=True)
        elif kind in ("section", "subheading"):
            number = f"{line['section']}. " if kind == "section" and line.get("section") else ""
            _text(ws, row, 1, number + line["title"], font=BOLD if kind == "section" else ITALIC, align=WRAP)
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        else:
            first = kind == "item"
            value = cells.get((line["no"], line["row"]), "")
            if line["no"] == "2.19" and note_219:
                value = f"{value}\n{note_219}" if value else note_219
            _text(ws, row, 1, line["no"] if first else "", border=True)
            _text(ws, row, 2, line.get("title", "") if first else "", align=WRAP, border=True)
            _text(ws, row, 3, " / ".join(c for c in line["cells"] if c), align=WRAP, border=True)
            _text(ws, row, 4, value, align=WRAP, border=True)
    _text(ws, row + 2, 1, L["signature"])
    _widths(ws, [8, 52, 34, 34])
    _print_setup(ws)


def _label(field: Mapping, value: Any, values: Mapping, lang: str) -> str:
    option = _option(field, value)
    if option is None:
        return _num(value)
    if option.get("other"):
        return f"{option[lang]}: {values.get(field['key'] + '_text') or ''}"
    return option[lang]


def _extra_sheet(ws: Worksheet, L: Mapping, schema: Mapping, values: Mapping, lang: str) -> None:
    _text(ws, 1, 1, L["extra_note"], font=ITALIC)
    row = 2
    for section in schema["sections"]:
        lines = []
        for item in section["items"]:
            value = values.get(item["key"])
            if item["kind"] == "group":
                types = next((f for f in item["fields"] if f["key"] == "type"), None)
                for line in (value or []) if types else []:
                    if not ((_option(types, line.get("type")) or {}).get("form")):
                        lines.append((item[lang], "; ".join(
                            f"{f[lang]}: {_label(f, line[f['key']], line, lang)}" for f in item["fields"]
                            if line.get(f["key"]) is not None)))
            elif value is not None:
                option = _option(item, value)
                off_form = option is not None and not option.get("form")
                if not item.get("form_no") or off_form:
                    unit = f" {item['unit']}" if item.get("unit") else ""
                    lines.append((item[lang], _label(item, value, values, lang) + unit))
        if lines:
            row += 1
            _text(ws, row, 1, section[lang], font=BOLD)
            for title, value in lines:
                row += 1
                _text(ws, row, 1, title, align=WRAP, border=True)
                _text(ws, row, 2, value, align=WRAP, border=True)
    _widths(ws, [52, 60])
    _print_setup(ws)


def _rows_sheet(ws: Worksheet, schema: Mapping, values: Mapping, lang: str) -> None:
    row = 0
    for group in (i for i in _items(schema) if i["kind"] == "group"):
        lines = values.get(group["key"]) or []
        if not lines:
            continue
        row += 2
        _text(ws, row, 1, group[lang], font=BOLD)
        row += 1
        for col, field in enumerate(group["fields"], start=1):
            unit = f", {field['unit']}" if field.get("unit") else ""
            _text(ws, row, col, field[lang] + unit, font=HEADER_FONT, fill=HEADER_FILL, align=WRAP, border=True)
        for line in lines:
            row += 1
            for col, field in enumerate(group["fields"], start=1):
                value = line.get(field["key"])
                shown = "" if value is None else _label(field, value, line, lang) if field.get("options") else value
                _text(ws, row, col, shown, border=True)
    _widths(ws, [28, 28, 14, 14, 20, 20])
    _print_setup(ws, landscape=True)


def render(*, schema: Mapping, form: Mapping, values: Mapping, unknown: Mapping, absent: Iterable[str],
           meta: Mapping, address: str, revision_no: Optional[int], organization: str = "", lang: str = "ru") -> bytes:
    """Файл паспорта. ``revision_no=None`` — рабочее состояние, с пометкой «черновик»."""
    L = LABELS["uz" if lang == "uz" else "ru"]
    lang = "uz" if lang == "uz" else "ru"
    head = {"mark": L["draft"] if revision_no is None else L["revision"].format(no=revision_no),
            "organization": organization, "address": address, **{k: meta.get(k) for k in
                                                                 ("inspection_date", "responsible_name", "note")}}
    values = visible_values(schema, values)
    count, area = off_form_openings(schema, values)
    note = L["off_form"].format(count=count, area=_num(area), sheet=L["extra"]) if count else None
    book = Workbook()
    ws = book.active
    ws.title = L["form"]
    _form_sheet(ws, L, form, form_cells(schema, form, values, unknown, absent), head, note)
    _extra_sheet(book.create_sheet(L["extra"]), L, schema, values, lang)
    _rows_sheet(book.create_sheet(L["rows"]), schema, values, lang)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def render_summary(schema: Mapping, houses: list[Mapping], lang: str = "ru") -> bytes:
    """Сводная: дом в строке, одиночный пункт в столбце. Общий на несколько домов
    объект стоит только в строке основного дома; итогов нет — проценты не складываются."""
    lang = "uz" if lang == "uz" else "ru"
    L = LABELS[lang]
    fields = [i for i in _items(schema) if i["kind"] == "field"]
    book = Workbook()
    ws = book.active
    ws.title = L["summary"]
    for col, title in enumerate([L["house"], L["status"], *(
            f"{f['form_no'] + ' ' if f.get('form_no') else ''}{f[lang]}" for f in fields)], start=1):
        _text(ws, 1, col, title, font=HEADER_FONT, fill=HEADER_FILL, align=WRAP, border=True)
    for row, house in enumerate(houses, start=2):
        _text(ws, row, 1, house["address"])
        _text(ws, row, 2, house["mark"])
        linked = set(house.get("shared_from") or ())
        shown = visible_values(schema, house["values"])
        for col, field in enumerate(fields, start=3):
            value = shown.get(field["key"])
            if value is None or field.get("share") in linked:
                continue
            _text(ws, row, col, _label(field, value, house["values"], lang) if field.get("options") else value)
    ws.freeze_panes = "C2"
    _widths(ws, [30, 16])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
