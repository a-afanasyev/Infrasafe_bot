"""Выгрузка паспорта дома: лист формы против эталона, свёртка строк, типы вне формы, защита текста."""
import copy
import io

from openpyxl import load_workbook

from uk_management_bot.services.building_passport import export, schema, validation

SCHEMA, FORM = schema.public_schema(), schema.etalon()


def _book(values=None, *, unknown=None, absent=(), revision_no=None, form=FORM, meta=None, lang="ru"):
    values = validation.with_computed(values or {})
    body = export.render(schema=SCHEMA, form=form, values=values, unknown=unknown or {}, absent=absent,
                         meta=meta or {"inspection_date": "2026-11-20", "responsible_name": "Иванов", "note": None},
                         address="д. 12", revision_no=revision_no, organization="УК Тест", lang=lang)
    return load_workbook(io.BytesIO(body))


def _form_rows(book) -> list[tuple]:
    """Строки тела формы: от шапки таблицы до блока подписи."""
    rows = [tuple("" if c is None else c for c in r) for r in book.worksheets[0].iter_rows(values_only=True)]
    start = next(i for i, r in enumerate(rows) if r[0] == "Т/р")
    return rows[start:start + len(FORM["rows"])]


def _value(book, no: str, row: int = 1) -> str:
    etalon = [r for r in FORM["rows"]]
    index = next(i for i, r in enumerate(etalon) if r.get("no") == no and r.get("row") == row)
    return _form_rows(book)[index][3]


def test_form_sheet_repeats_the_original_row_by_row():
    rows = _form_rows(_book())
    assert len(rows) == len(FORM["rows"]) == 252
    for got, line in zip(rows, FORM["rows"]):
        if line["kind"] == "header":
            assert list(got) == line["cells"]
        elif line["kind"] in ("section", "subheading"):
            assert got[0].endswith(line["title"]) and got[1:] == ("", "", "")
        else:
            first = line["kind"] == "item"
            assert got[0] == (line["no"] if first else "")
            assert got[1] == (line.get("title", "") if first else "")
            assert got[2] == " / ".join(c for c in line["cells"] if c)  # единицы и подписи — дословно


def test_sheets_head_draft_mark_and_signature_place():
    book = _book()
    assert book.sheetnames == ["Форма №3824", "Дополнение УК", "Разбивка"]
    cells = [c for r in book.worksheets[0].iter_rows(values_only=True) for c in r if c]
    assert cells[0].startswith("ЧЕРНОВИК") and "УК Тест" in cells and "д. 12" in cells and "Иванов" in cells
    assert any(str(c).startswith("Подпись ответственного") for c in cells)
    assert FORM["title"] in cells
    signed = [c for r in _book(revision_no=2).worksheets[0].iter_rows(values_only=True) for c in r if c]
    assert signed[0] == "Редакция №2"


def test_plain_values_choices_unknown_and_absent():
    book = _book({"floors": 9, "cadastre_no": "10:08:01", "heritage": "no", "management": "hoa",
                  "lifts_passenger": 0, "lifts_cargo": 0, "attic_type": "none"},
                 unknown={"built_year": "нет документов"}, absent=["doors"])
    assert _value(book, "2.10") == "9" and _value(book, "1.2") == "10:08:01"
    assert _value(book, "1.5") == "берилмаган"
    assert _value(book, "2.12", 2) == "Уй-жой мулкдорлари ширкати" and _value(book, "2.12", 1) == ""
    assert _value(book, "1.3") == "—", "«нет данных» печатается прочерком"
    assert _value(book, "2.16", 3) == "✓", "лифтов нет — строка «мавжуд эмас»"
    assert _value(book, "2.20", 3) == "✓", "дверей нет в доме"
    assert _value(book, "5.9") == "йўқ"


def test_pipes_fold_into_one_row_per_material_with_diameters_listed():
    pipe = {"run": "horizontal", "material": "steel"}
    book = _book({"heating_type": "central", "heating_pipes": [
        {**pipe, "diameter": 32, "length": 100, "ok_length": 80, "bad_length": 20},
        {**pipe, "diameter": 50, "length": 40.5, "ok_length": 40.5, "bad_length": 0},
        {**pipe, "diameter": 25, "length": 10, "ok_length": 0, "bad_length": 10},
        {"run": "riser", "material": "pp", "diameter": 20, "length": 7, "ok_length": 7, "bad_length": 0}]})
    assert [_value(book, "6.4", n) for n in (1, 2, 3, 4)] == ["25, 32, 50", "150.5", "120.5", "30"]
    assert [_value(book, "6.7", n) for n in (1, 2)] == ["20", "7"]
    assert _value(book, "6.5") == "" and _value(book, "6.6") == ""
    assert len([r for r in book["Разбивка"].iter_rows(values_only=True) if r[0] == "горизонтальные"]) == 3


def test_windows_of_one_type_sum_and_list_their_sizes():
    book = _book({"windows": [
        {"type": "plastic", "count": 4, "width": 1.2, "height": 1.5},
        {"type": "plastic", "count": 2, "width": 0.9, "height": 1.5},
        {"type": "wood", "count": 3, "width": 1, "height": 2}]})
    assert _value(book, "2.17", 3) == "6 дона; 1.5×0.9 м, 1.5×1.2 м; 9.9 м2"
    assert _value(book, "2.17", 1) == "3 дона; бўйи 2 м, эни 1 м; 6 м2"


def test_flats_over_seven_rooms_print_in_the_open_row():
    book = _book({"apt_more": [{"rooms": 8, "count": 2, "area": 310.5}, {"rooms": 9, "count": 1, "area": 200}]})
    assert _value(book, "2.13", 8) == "8 хона, 2 дона, 310.5 м2; 9 хона, 1 дона, 200 м2"


def test_off_form_window_type_stays_out_of_2_17_but_counts_in_2_19_with_a_note():
    book = _book({"windows": [
        {"type": "plastic", "count": 4, "width": 1, "height": 1},
        {"type": "glass_blocks", "count": 5, "width": 2, "height": 1}]})
    assert _value(book, "2.17", 3) == "4 дона; бўйи 1 м, эни 1 м; 4 м2"
    assert all("5 дона" not in _value(book, "2.17", n) for n in (1, 2, 3, 4))
    total = _value(book, "2.19")
    assert total.startswith("9 / 14"), "итог — по всем окнам дома"
    assert "шаклдан ташқари турлар: 5 дона, 10 м2" in total and "«Дополнение УК»" in total
    extra = [" ".join(str(c) for c in r if c) for r in book["Дополнение УК"].iter_rows(values_only=True)]
    assert any("стеклоблоки" in line for line in extra)


def test_off_form_fields_go_to_the_supplement_sheet_only():
    off_form = next(f for f in schema.iter_fields() if f.form_no is None and f.type in ("int", "decimal"))
    book = _book({off_form.key: 7})
    extra = [r for r in book["Дополнение УК"].iter_rows(values_only=True) if r[0] == off_form.ru]
    assert len(extra) == 1 and str(extra[0][1]).startswith("7")
    assert all(r[3] == "" for r in _form_rows(book) if r[0] != "Т/р")


def test_text_starting_with_equals_stays_text():
    formula = '=HYPERLINK("http://evil","x")'
    book = _book({"cadastre_no": formula}, meta={"inspection_date": None, "responsible_name": None, "note": formula})
    cells = [c for r in book.worksheets[0].iter_rows() for c in r if c.value == formula]
    assert len(cells) == 2 and all(c.data_type == "s" for c in cells)


def test_revision_prints_by_its_own_copy_of_the_form():
    """Правка эталона после подписания не меняет файл старой редакции."""
    frozen = copy.deepcopy(FORM)
    frozen["rows"][2]["title"] = "СТАРОЕ НАЗВАНИЕ"
    rows = [r for r in _book(form=frozen, revision_no=1).worksheets[0].iter_rows(values_only=True)]
    assert any(r[1] == "СТАРОЕ НАЗВАНИЕ" for r in rows)


def test_summary_puts_a_shared_object_only_in_the_primary_house_row():
    houses = [
        {"address": "д. 1", "mark": "№1", "values": {"plot_area": 500, "green_share": 30, "floors": 9}, "shared_from": {}},
        {"address": "д. 2", "mark": "№2", "values": {"plot_area": 500, "green_share": 30, "floors": 5},
         "shared_from": {"plot": 1}},
    ]
    sheet = load_workbook(io.BytesIO(export.render_summary(SCHEMA, houses))).worksheets[0]
    head = [c.value for c in sheet[1]]
    plot, floors = head.index("1.4 Площадь прилегающего участка"), head.index("2.10 Количество этажей")
    first, second = ([c.value for c in sheet[n]] for n in (2, 3))
    assert (first[0], first[plot], first[floors]) == ("д. 1", 500, 9)
    assert (second[plot], second[floors]) == (None, 5), "участок учтён один раз — у основного дома"
    assert sheet.max_row == 3, "строки итогов нет: проценты не складываются"
