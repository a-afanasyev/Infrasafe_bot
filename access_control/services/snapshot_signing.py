"""Подпись offline-snapshot backend'ом (§8.2). Асимметричный ключ — приватный ТОЛЬКО здесь.

Backend формирует подписанный fail_closed-snapshot (§8.2): без разрешающего списка
номеров (пилот). Подпись — Ed25519 (``cryptography``): приватный ключ существует
только на backend, edge поставляется с ОДНИМ pinned public key. Edge проверяет
``key_id``, подпись и срок, но даже валидный snapshot не открывает въезд в
fail_closed (reject-only, проверка — ``edge/snapshot_verifier.py``).

Канонизация перед подписью — детерминированный JSON (sorted keys, без пробелов):
edge и backend обязаны сериализовать одинаково.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# Возраст snapshot для автоматического въезда (§8.2): 15 минут.
SNAPSHOT_TTL_SECONDS = 15 * 60
SNAPSHOT_VERSION = 1

# Сид приватного ключа берётся ТОЛЬКО из окружения (§8.2, §11). Хардкод-дефолта в
# коде нет (H2/M1): отсутствие env → RuntimeError при использовании (не на импорте,
# чтобы сборка/collection не падали). 32 байта seed Ed25519, hex. Тесты задают
# синтетический сид через окружение (см. access_control/tests/conftest.py).
_SIGNING_SEED_ENV = "ACCESS_SNAPSHOT_SIGNING_SEED"


def _signing_seed_hex() -> str:
    seed = os.getenv(_SIGNING_SEED_ENV)
    if not seed:
        raise RuntimeError(
            f"{_SIGNING_SEED_ENV} не задан: приватный сид подписи snapshot обязателен "
            "(§8.2, §11) — дефолтного сида в коде нет."
        )
    return seed


def _private_key() -> Ed25519PrivateKey:
    seed = bytes.fromhex(_signing_seed_hex())
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_key_bytes() -> bytes:
    """Raw-байты публичного ключа backend (для pinned key на edge, §8.2)."""
    return _private_key().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def current_key_id() -> str:
    """``key_id`` текущего signing-ключа: env-override или дериват из публичного ключа.

    Edge сверяет ``key_id`` snapshot со своим pinned (§8.2). Дериват — стабильный
    хэш публичного ключа (первые 16 hex), чтобы ротация сменила id автоматически.
    """
    override = os.getenv("ACCESS_SNAPSHOT_KEY_ID")
    if override:
        return override
    return "pilot-" + hashlib.sha256(public_key_bytes()).hexdigest()[:16]


def public_key_for(key_id: str) -> bytes | None:
    """Публичный ключ по ``key_id`` (для edge-верификатора/тестов). None если неизвестен.

    В пилоте один ключ; trust store/ротация — этап cached_permanent_only (§8.2).
    """
    if key_id == current_key_id():
        return public_key_bytes()
    return None


def canonical_payload(snapshot: dict) -> bytes:
    """Детерминированная сериализация snapshot ДЛЯ подписи (без поля ``signature``)."""
    payload = {k: v for k, v in snapshot.items() if k != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class SignedSnapshot:
    """Подписанный snapshot + его словарное представление (для ответа endpoint'а)."""

    data: dict
    signature_hex: str


def build_snapshot(
    *,
    controller_uid: str,
    zone_id: int | None,
    offline_mode: str = "fail_closed",
    now: dt.datetime | None = None,
    ttl_seconds: int = SNAPSHOT_TTL_SECONDS,
) -> dict:
    """Собрать НЕподписанный fail_closed-snapshot (§8.2) для конкретного контроллера.

    Содержит controller/zone scope, offline_mode, version, issued_at, expires_at,
    key_id. БЕЗ разрешающего списка номеров (fail_closed пилот, §8.2).
    """
    issued = now or dt.datetime.now(dt.timezone.utc)
    expires = issued + dt.timedelta(seconds=ttl_seconds)
    return {
        "controller_uid": controller_uid,
        "zone_id": zone_id,
        "offline_mode": offline_mode,
        "version": SNAPSHOT_VERSION,
        "issued_at": issued.isoformat(),
        "expires_at": expires.isoformat(),
        "key_id": current_key_id(),
    }


def sign_snapshot(snapshot: dict) -> SignedSnapshot:
    """Подписать snapshot приватным Ed25519-ключом backend (§8.2)."""
    signature = _private_key().sign(canonical_payload(snapshot))
    return SignedSnapshot(data={**snapshot, "signature": signature.hex()}, signature_hex=signature.hex())


def verify_signature(snapshot: dict, public_key: bytes) -> bool:
    """Проверить Ed25519-подпись snapshot заданным публичным ключом (для edge/тестов)."""
    sig_hex = snapshot.get("signature")
    if not sig_hex:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            bytes.fromhex(sig_hex), canonical_payload(snapshot)
        )
        return True
    except Exception:  # noqa: BLE001 — невалидная подпись/ключ → reject
        return False
