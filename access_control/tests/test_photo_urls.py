"""Короткоживущие signed-URL для фото (§11): подпись/верификация.

Юнит-тесты чистых крипто-функций ``sign``/``verify`` (без БД). Секрет —
``ACCESS_PHOTO_URL_SECRET`` (conftest задаёт синтетический через ``setdefault``,
как H2/M1 device-auth/snapshot seed). Подпись HMAC-SHA256 покрывает
``event_id+kind+exp``; проверка — подпись (``compare_digest``) и срок (``exp``).
"""
from __future__ import annotations

import time

import pytest

from access_control.services import photo_urls as pu


def test_sign_returns_signed_path_to_photos_endpoint() -> None:
    url = pu.sign(123, "plate", ttl_seconds=300)
    assert url.startswith("/api/v1/access/photos/plate/123")
    assert "sig=" in url
    assert "exp=" in url


def test_sign_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError):
        pu.sign(1, "selfie", ttl_seconds=300)


def test_verify_valid_signature_roundtrip() -> None:
    exp = int(time.time()) + 300
    sig = pu.compute_sig(123, "plate", exp)
    # Не бросает → валидно.
    pu.verify(123, "plate", exp, sig)


def test_verify_expired_raises_expired() -> None:
    past = int(time.time()) - 1
    sig = pu.compute_sig(7, "overview", past)
    with pytest.raises(pu.PhotoUrlExpired):
        pu.verify(7, "overview", past, sig)


def test_verify_tampered_signature_raises_invalid() -> None:
    exp = int(time.time()) + 300
    sig = pu.compute_sig(7, "plate", exp)
    with pytest.raises(pu.PhotoUrlInvalid):
        pu.verify(7, "plate", exp, sig + "00")


def test_verify_tampered_event_id_raises_invalid() -> None:
    """Подпись привязана к event_id — нельзя переиспользовать на другое событие."""
    exp = int(time.time()) + 300
    sig = pu.compute_sig(7, "plate", exp)
    with pytest.raises(pu.PhotoUrlInvalid):
        pu.verify(8, "plate", exp, sig)


def test_verify_tampered_kind_raises_invalid() -> None:
    exp = int(time.time()) + 300
    sig = pu.compute_sig(7, "plate", exp)
    with pytest.raises(pu.PhotoUrlInvalid):
        pu.verify(7, "overview", exp, sig)


def test_verify_tampered_exp_raises_invalid() -> None:
    """exp входит в подпись — продление срока инвалидирует подпись (не 410, а 403)."""
    exp = int(time.time()) + 300
    sig = pu.compute_sig(7, "plate", exp)
    with pytest.raises(pu.PhotoUrlInvalid):
        pu.verify(7, "plate", exp + 10_000, sig)


def test_sign_then_parse_verify_full_url() -> None:
    """Из подписанного URL извлекаются exp/sig, которые проходят verify."""
    from urllib.parse import parse_qs, urlsplit

    url = pu.sign(55, "overview", ttl_seconds=300)
    q = parse_qs(urlsplit(url).query)
    exp = int(q["exp"][0])
    sig = q["sig"][0]
    pu.verify(55, "overview", exp, sig)
