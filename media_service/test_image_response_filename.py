"""Выдача файла с не-ASCII именем (например, «Снимок экрана …».png с macOS).

HTTP-заголовки — latin-1: сырое кириллическое имя в Content-Disposition роняло
Response в UnicodeEncodeError, и `GET /media/{id}/file` отвечал 500 — первая же
загрузка скриншота с Mac через дашборд ломала превью фотоотчёта. Канон
RFC 6266/5987: ASCII-фолбэк в filename=, полное имя — в filename*=UTF-8''.
"""
from app.api.v1.media import _image_response

# Однопиксельный JPEG-префикс — _sniff_image_mime хватает магических байт.
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 8


def _meta(filename):
    return {"original_filename": filename, "mime_type": "image/jpeg"}


def _disposition(resp):
    return resp.headers["content-disposition"]


def test_non_ascii_filename_does_not_crash_and_uses_rfc5987():
    resp = _image_response(JPEG_BYTES, _meta("Снимок экрана — 2026-08-10.png"), "image/jpeg")
    disposition = _disposition(resp)
    # Заголовок построен (нет UnicodeEncodeError) и несёт обе формы имени.
    assert 'filename="' in disposition
    assert "filename*=UTF-8''" in disposition
    assert "%D0%A1%D0%BD%D0%B8%D0%BC%D0%BE%D0%BA" in disposition  # «Снимок»
    # Starlette уже сериализовал заголовки в latin-1 — сам факт наличия
    # resp.raw_headers означает, что кодирование прошло.
    assert resp.raw_headers


def test_fully_non_ascii_filename_falls_back_to_file():
    resp = _image_response(JPEG_BYTES, _meta("скриншот.—"), "image/jpeg")
    assert 'filename="file"' in _disposition(resp)


def test_ascii_filename_unchanged():
    resp = _image_response(JPEG_BYTES, _meta("verify.jpg"), "image/jpeg")
    disposition = _disposition(resp)
    assert disposition.startswith('inline; filename="verify.jpg"')
    assert "filename*" not in disposition


def test_missing_filename_defaults_to_file():
    resp = _image_response(JPEG_BYTES, _meta(None), "image/jpeg")
    assert 'filename="file"' in _disposition(resp)
