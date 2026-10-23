"""A10-SAT-08: потолок строк импорта показаний."""
import pytest

from app.services.imports import MAX_IMPORT_ROWS, parse_file

_HEADER = "meter_number;period;reading_value;read_at;note\n"


def test_parse_file_caps_row_count():
    content = (_HEADER + "M-1;2028-01;1;;\n" * (MAX_IMPORT_ROWS + 1)).encode()
    with pytest.raises(Exception, match="Слишком много строк"):
        parse_file("readings.csv", content)


def test_parse_file_accepts_limit():
    content = (_HEADER + "M-1;2028-01;1;;\n" * MAX_IMPORT_ROWS).encode()
    assert len(parse_file("readings.csv", content)) == MAX_IMPORT_ROWS
