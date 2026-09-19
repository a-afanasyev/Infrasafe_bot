"""AUD8-SEC-04: XLSX-импорт ограничивает распакованный размер и число записей."""
from __future__ import annotations

import io
import zipfile

import pytest

from app.core.errors import ApiError
from app.services.imports import _assert_xlsx_bounds, parse_file


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_unpacked_size_cap_uses_actual_bytes_not_header() -> None:
    content = _zip({"xl/worksheets/sheet1.xml": b"0" * (2 * 1024 * 1024)})
    assert len(content) < 64 * 1024  # хорошо сжимается — заявленный размер не важен
    with pytest.raises(ValueError):
        _assert_xlsx_bounds(content, max_unpacked=1024 * 1024)
    _assert_xlsx_bounds(content, max_unpacked=4 * 1024 * 1024)  # в лимите — тихо


def test_entry_count_cap() -> None:
    content = _zip({f"m{i}.xml": b"x" for i in range(5)})
    with pytest.raises(ValueError):
        _assert_xlsx_bounds(content, max_entries=4)
    _assert_xlsx_bounds(content, max_entries=5)


def test_parse_file_rejects_bomb_before_workbook_load(monkeypatch) -> None:
    from app.services import imports as mod

    monkeypatch.setattr(mod, "XLSX_MAX_UNPACKED_BYTES", 1024 * 1024)
    content = _zip({"xl/worksheets/sheet1.xml": b"0" * (2 * 1024 * 1024)})
    with pytest.raises(ApiError) as exc:
        parse_file("bomb.xlsx", content)
    assert exc.value.status_code == 400
