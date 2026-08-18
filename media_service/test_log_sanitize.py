"""E1/E4 — санитизация токена и вывод MIME из байтов (аудит 2026-08-18).

Тесты проверяют ИТОГОВУЮ отформатированную запись (handler.format с exc_info),
а не record.msg: formatException печатает traceback сырьём, и до фикса токен
уходил именно через него.
"""
from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException

from app.core.log_sanitize import (
    TelegramDownloadError,
    TokenSanitizingFilter,
    describe_http_error,
    redact_token,
)
from app.api.v1.media import _derive_content_type

TOKEN_URL = "https://api.telegram.org/bot12345:AAAAAAAAAAAAAAAAAAAAAAAAAAA/getFile"


def _formatted_record(msg, exc=None) -> str:
    logger = logging.getLogger("sanitize-test")
    formatter = logging.Formatter("%(message)s")
    flt = TokenSanitizingFilter()
    record = logger.makeRecord(
        "sanitize-test", logging.ERROR, __file__, 1, msg, (),
        exc_info=None if exc is None else (type(exc), exc, exc.__traceback__),
    )
    assert flt.filter(record)
    return formatter.format(record)


def test_filter_redacts_token_in_message():
    out = _formatted_record(f"Failed: Server error for url '{TOKEN_URL}'")
    assert "12345:AAAA" not in out and "/bot[REDACTED]" in out


def test_filter_redacts_token_in_traceback():
    try:
        raise RuntimeError(f"Server error for url '{TOKEN_URL}'")
    except RuntimeError as e:
        out = _formatted_record("Unexpected error", exc=e)
    assert "12345:AAAA" not in out
    assert "RuntimeError" in out  # traceback сохранён, замаскирован только токен


def test_download_error_str_carries_no_token():
    """str(exc) уходит клиенту в debug-ответе — токена там быть не должно."""
    class _R:  # httpx-подобное исключение с URL в тексте
        status_code = 502
    src = Exception(f"Server error for url '{TOKEN_URL}'")
    src.response = _R()
    sanitized = TelegramDownloadError(f"download_file X: {describe_http_error(src)}")
    assert "12345:AAAA" not in str(sanitized)
    assert "HTTP 502" in str(sanitized)


def test_redact_token_idempotent():
    once = redact_token(TOKEN_URL)
    assert redact_token(once) == once


# ══════════════════════════════════════════════════════════════════════════════
# E4: вывод MIME из байтов
# ══════════════════════════════════════════════════════════════════════════════

JPEG = b"\xFF\xD8\xFF" + b"\x00" * 16
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16
PDFISH = b"%PDF-1.7 ..." + b"\x00" * 16


def test_sniffed_type_wins_over_client_claim():
    assert _derive_content_type(JPEG, "image/png") == "image/jpeg"


def test_spoofed_media_claim_rejected():
    """Заявлен image/jpeg, байты не медиа → отказ, а не доверие клиенту."""
    with pytest.raises(HTTPException) as e:
        _derive_content_type(PDFISH, "image/jpeg")
    assert e.value.status_code == 415


def test_video_rejected_when_images_only():
    with pytest.raises(HTTPException) as e:
        _derive_content_type(MP4, "video/mp4", images_only=True)
    assert e.value.status_code == 415


def test_png_accepted_when_images_only():
    assert _derive_content_type(PNG, "application/octet-stream", images_only=True) == "image/png"


def test_non_media_claim_rejected_because_allowlist_is_media_only():
    """allowed_file_types содержит только image/*+video/* — не-медиа с любым
    заявленным типом отказ (фолбэк-ветка станет живой, если allowlist расширят)."""
    for claim in ("application/pdf", "application/x-evil"):
        with pytest.raises(HTTPException):
            _derive_content_type(PDFISH, claim)
