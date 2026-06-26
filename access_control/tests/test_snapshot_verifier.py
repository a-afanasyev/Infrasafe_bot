"""Критерий приёмки §15.18: edge-верификатор snapshot одним pinned public key (§8.2).

Edge отклоняет snapshot с неизвестным ``key_id`` / неверной подписью / истёкшим
сроком / недопустимым clock-drift и НИКОГДА не открывает шлагбаум по snapshot в
``fail_closed`` (reject-only). Монотонная защита от скачка системных часов.

Юнит-тесты без БД: backend-подпись (snapshot_signing) + edge-проверка
(snapshot_verifier).
"""
from __future__ import annotations

import datetime as dt

from access_control.edge.snapshot_verifier import (
    MAX_CLOCK_DRIFT_SECONDS,
    SnapshotVerifier,
    verify_snapshot,
)
from access_control.services.snapshot_signing import (
    build_snapshot,
    current_key_id,
    public_key_bytes,
    sign_snapshot,
)


def _signed_snapshot(**kw) -> dict:
    snap = build_snapshot(controller_uid="ctrl-1", zone_id=1, **kw)
    return sign_snapshot(snap).data


def _pinned() -> tuple[str, bytes]:
    return current_key_id(), public_key_bytes()


def test_valid_snapshot_accepted_but_entry_not_allowed() -> None:
    """Валидный snapshot принят, но в fail_closed въезд НЕ открывается (reject-only)."""
    snap = _signed_snapshot()
    key_id, pub = _pinned()
    result = verify_snapshot(snap, pinned_key_id=key_id, pinned_public_key=pub)
    assert result.accepted is True
    assert result.entry_allowed is False
    assert result.state == "fail_closed"


def test_unknown_key_id_rejected() -> None:
    snap = _signed_snapshot()
    _, pub = _pinned()
    result = verify_snapshot(
        snap, pinned_key_id="some-other-key-id", pinned_public_key=pub
    )
    assert result.accepted is False
    assert result.reason == "unknown_key_id"
    assert result.entry_allowed is False


def test_bad_signature_rejected() -> None:
    snap = _signed_snapshot()
    snap["signature"] = "00" * 64  # подменённая подпись
    key_id, pub = _pinned()
    result = verify_snapshot(snap, pinned_key_id=key_id, pinned_public_key=pub)
    assert result.accepted is False
    assert result.reason == "bad_signature"


def test_expired_snapshot_rejected() -> None:
    """expires_at в прошлом (по стенным часам) → reject (§8.2: возраст ≤ 15 мин)."""
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=30)
    snap = _signed_snapshot(now=past)
    key_id, pub = _pinned()
    result = verify_snapshot(snap, pinned_key_id=key_id, pinned_public_key=pub)
    assert result.accepted is False
    assert result.reason == "expired"


def test_clock_drift_exceeded_rejected() -> None:
    """Недопустимый дрейф часов edge (>30c) → reject (§8.2)."""
    snap = _signed_snapshot()
    key_id, pub = _pinned()
    result = verify_snapshot(
        snap,
        pinned_key_id=key_id,
        pinned_public_key=pub,
        clock_drift_seconds=MAX_CLOCK_DRIFT_SECONDS + 5,
    )
    assert result.accepted is False
    assert result.reason == "clock_drift_exceeded"


def test_monotonic_protection_against_clock_rollback() -> None:
    """Перевод стенных часов назад не «омолаживает» snapshot: монотонный возраст."""
    snap = _signed_snapshot()
    key_id, pub = _pinned()
    verifier = SnapshotVerifier(key_id, pub, max_age_seconds=900)
    # accept фиксирует момент получения; recheck с монотонным временем далеко в будущем.
    accept = verifier.accept(snap)
    assert accept.accepted is True
    import time

    far_future_mono = time.monotonic() + 100000  # монотонно прошло > max_age
    rechecked = verifier.recheck(snap, now_monotonic=far_future_mono)
    assert rechecked.accepted is False
    assert rechecked.reason == "monotonic_expired"


def test_fail_closed_never_opens_even_when_valid() -> None:
    """Главный инвариант §15.18: даже валидный snapshot не открывает въезд offline."""
    snap = _signed_snapshot()
    key_id, pub = _pinned()
    verifier = SnapshotVerifier(key_id, pub)
    result = verifier.accept(snap)
    assert result.accepted is True
    assert result.entry_allowed is False


# --- Порт guards из B (edge/snapshot.py): reject-only усиление (§8.2) ---


def test_offline_mode_not_fail_closed_rejected() -> None:
    """Пилотный snapshot обязан быть fail_closed (§8.2): иной offline_mode → reject."""
    snap = _signed_snapshot(offline_mode="cached_permanent_only")
    key_id, pub = _pinned()
    result = verify_snapshot(snap, pinned_key_id=key_id, pinned_public_key=pub)
    assert result.accepted is False
    assert result.reason == "offline_mode_forbidden"


def test_grant_fields_forbidden_rejected() -> None:
    """fail_closed snapshot НЕ должен содержать разрешающий список (§8.2)."""
    snap = build_snapshot(controller_uid="ctrl-1", zone_id=1)
    snap["vehicles"] = ["01A111AA"]  # запрещённое grant-поле (до подписи)
    signed = sign_snapshot(snap).data
    key_id, pub = _pinned()
    result = verify_snapshot(signed, pinned_key_id=key_id, pinned_public_key=pub)
    assert result.accepted is False
    assert result.reason == "grant_fields_forbidden"


def test_snapshot_lifetime_too_long_rejected() -> None:
    """Заявленный lifetime > 15 мин → reject (§8.2 max age), даже если ещё не истёк."""
    snap = _signed_snapshot(ttl_seconds=30 * 60)  # 30 минут
    key_id, pub = _pinned()
    result = verify_snapshot(snap, pinned_key_id=key_id, pinned_public_key=pub)
    assert result.accepted is False
    assert result.reason == "lifetime_too_long"


def test_snapshot_issued_in_future_rejected() -> None:
    """issued_at существенно в будущем (>5c) → reject (§8.2 защита от скачка часов)."""
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=60)
    snap = _signed_snapshot(now=future)
    key_id, pub = _pinned()
    result = verify_snapshot(snap, pinned_key_id=key_id, pinned_public_key=pub)
    assert result.accepted is False
    assert result.reason == "issued_in_future"
