"""Короткоживущие signed-URL для фото событий (§11).

Фото номера/обзора — персональные данные (§11): отдаём НЕ сырой storage-URL, а
короткоживущий подписанный URL на capability-эндпоинт ``/api/v1/access/photos``.
URL может загрузить ``<img src>`` (который не умеет слать Authorization); короткий
TTL компенсирует отсутствие Bearer.

Подпись HMAC-SHA256 покрывает ``event_id + kind + exp`` (срок — unix-время). Любая
подмена параметра инвалидирует подпись (``compare_digest``). Секрет берётся ТОЛЬКО
из окружения ``ACCESS_PHOTO_URL_SECRET`` — хардкод-дефолта в коде нет (H2/M1, как
device-auth/snapshot seed): отсутствие env → ``RuntimeError`` при использовании (не
на импорте). Тесты задают синтетический секрет через ``os.environ.setdefault``
(access_control/tests/conftest.py).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time

# Допустимые виды фото (часть подписи и пути).
KINDS = ("plate", "overview")

# Префикс capability-эндпоинта выдачи фото (см. api/registry.py).
PHOTO_PATH_PREFIX = "/api/v1/access/photos"

# TTL signed-URL по умолчанию (§11: короткоживущий). Конфигурируемо.
DEFAULT_PHOTO_URL_TTL_SECONDS = int(os.getenv("ACCESS_PHOTO_URL_TTL_SECONDS", "300"))

# Имя env-секрета подписи. Дефолта в коде нет (H2/M1).
_SECRET_ENV = "ACCESS_PHOTO_URL_SECRET"


class PhotoUrlInvalid(Exception):
    """Подпись не совпала / неизвестный kind → доступ запрещён (403)."""


class PhotoUrlExpired(Exception):
    """Подпись валидна, но срок ``exp`` истёк → ссылка протухла (410)."""


def _secret() -> bytes:
    secret = os.getenv(_SECRET_ENV)
    if not secret:
        raise RuntimeError(
            f"{_SECRET_ENV} не задан: секрет подписи signed-URL фото обязателен "
            "(§11) — дефолтного секрета в коде нет."
        )
    return secret.encode("utf-8")


def _canonical(event_id: int, kind: str, exp: int) -> str:
    """Канонический стринг подписи: event_id\\nkind\\nexp."""
    return f"{int(event_id)}\n{kind}\n{int(exp)}"


def compute_sig(event_id: int, kind: str, exp: int) -> str:
    """HMAC-SHA256(event_id+kind+exp) hex на ``ACCESS_PHOTO_URL_SECRET`` (§11)."""
    if kind not in KINDS:
        raise ValueError(f"неизвестный kind фото: {kind!r} (допустимы {KINDS})")
    return hmac.new(
        _secret(), _canonical(event_id, kind, exp).encode("utf-8"), hashlib.sha256
    ).hexdigest()


def sign(event_id: int, kind: str, ttl_seconds: int = DEFAULT_PHOTO_URL_TTL_SECONDS,
         *, now: int | None = None) -> str:
    """Построить подписанный относительный URL на ``/photos/{kind}/{event_id}`` (§11).

    ``exp = now + ttl`` (unix-время). Возвращает путь с query ``?exp=&sig=`` —
    пригоден для ``<img src>`` и ``RedirectResponse``.
    """
    if kind not in KINDS:
        raise ValueError(f"неизвестный kind фото: {kind!r} (допустимы {KINDS})")
    base = int(time.time()) if now is None else int(now)
    exp = base + int(ttl_seconds)
    sig = compute_sig(event_id, kind, exp)
    return f"{PHOTO_PATH_PREFIX}/{kind}/{int(event_id)}?exp={exp}&sig={sig}"


def verify(event_id: int, kind: str, exp: int, sig: str, *, now: int | None = None) -> None:
    """Проверить подпись и срок signed-URL фото (§11).

    Сначала подпись (подмена любого параметра, включая ``exp``, → ``PhotoUrlInvalid``,
    403), затем срок (валидная, но протухшая → ``PhotoUrlExpired``, 410). Ничего не
    возвращает при успехе.
    """
    if kind not in KINDS:
        raise PhotoUrlInvalid("unknown photo kind")
    try:
        expected = compute_sig(event_id, kind, int(exp))
    except (ValueError, TypeError):
        raise PhotoUrlInvalid("bad signed url params")
    if not hmac.compare_digest(expected, sig or ""):
        raise PhotoUrlInvalid("invalid signature")
    current = int(time.time()) if now is None else int(now)
    if current > int(exp):
        raise PhotoUrlExpired("signed url expired")
