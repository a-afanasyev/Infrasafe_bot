"""AUD8-SEC-03: ILIKE-паттерн по номеру экранирует %/_; фото без media:// → 404."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from access_control.api.registry import _photo_media_id, _plate_pat


def test_plate_pattern_escapes_like_metachars() -> None:
    assert _plate_pat("%") == r"%\%%"
    assert _plate_pat("a_b") == r"%A\_B%"
    assert _plate_pat(" 01a\\ ") == r"%01A\\%"


def test_plate_pattern_plain_contains() -> None:
    assert _plate_pat("01a123") == "%01A123%"


def test_photo_media_id_accepts_only_media_scheme() -> None:
    assert _photo_media_id("media://42") == "42"
    with pytest.raises(HTTPException) as exc:
        _photo_media_id("https://storage.example/photo.jpg")
    assert exc.value.status_code == 404
