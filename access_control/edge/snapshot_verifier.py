"""Edge-сторона: проверка offline-snapshot ОДНИМ pinned public key (§8.2, §15.18).

Reject-only пилот: edge принимает snapshot только при совпадении ``key_id``,
верной подписи, неистёкшем сроке и допустимом clock-drift. Но даже валидный
snapshot в ``fail_closed`` НЕ открывает въезд (§8.2: «даже валидный snapshot не
может разрешить offline-въезд»). Любой провал (неизвестный key_id / неверная
подпись / истёкший / недопустимый дрейф) → reject + переход в ``fail_closed``.

Защита от скачка системных часов (§8.2): срок ограничивается также МОНОТОННЫМ
временем с момента получения snapshot — перевод стенных часов назад не «омолодит»
истёкший snapshot.
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass

from access_control.services.snapshot_signing import (
    SNAPSHOT_TTL_SECONDS,
    verify_signature,
)

# Допустимый дрейф часов edge для проверки срока (§8: >30c → fail_closed).
MAX_CLOCK_DRIFT_SECONDS = 30

FAIL_CLOSED = "fail_closed"


@dataclass(frozen=True)
class VerifyResult:
    """Итог проверки snapshot на edge (§8.2).

    ``accepted`` — snapshot структурно валиден (key/подпись/срок/дрейф). ``state`` —
    режим edge после проверки (всегда ``fail_closed`` в пилоте). ``entry_allowed`` —
    можно ли открыть въезд: в ``fail_closed`` ВСЕГДА False (reject-only).
    """

    accepted: bool
    entry_allowed: bool
    state: str
    reason: str | None


def _parse_dt(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def verify_snapshot(
    snapshot: dict,
    *,
    pinned_key_id: str,
    pinned_public_key: bytes,
    expected_controller_uid: str | None = None,
    now: dt.datetime | None = None,
    received_monotonic: float | None = None,
    now_monotonic: float | None = None,
    max_age_seconds: int = SNAPSHOT_TTL_SECONDS,
    clock_drift_seconds: float = 0.0,
    max_clock_drift_seconds: int = MAX_CLOCK_DRIFT_SECONDS,
) -> VerifyResult:
    """Проверить snapshot одним pinned ключом (§8.2). Reject-only: въезд не открывает.

    Любой негативный исход → ``accepted=False`` + ``state=fail_closed``. Позитивный
    исход → ``accepted=True``, но ``entry_allowed=False`` (fail_closed пилот).
    """
    wall_now = now or dt.datetime.now(dt.timezone.utc)

    def _reject(reason: str) -> VerifyResult:
        return VerifyResult(False, False, FAIL_CLOSED, reason)

    # 1) Недопустимый clock-drift (§8: >30c → fail_closed, ещё до доверия сроку).
    if abs(clock_drift_seconds) > max_clock_drift_seconds:
        return _reject("clock_drift_exceeded")

    # 2) key_id обязан совпасть с единственным pinned (§8.2).
    if snapshot.get("key_id") != pinned_key_id:
        return _reject("unknown_key_id")

    # 3) Подпись Ed25519 pinned публичным ключом.
    if not verify_signature(snapshot, pinned_public_key):
        return _reject("bad_signature")

    # 3.5) Scope: snapshot должен быть выписан ИМЕННО на свой контроллер (H1, §8.2,
    # §9.1). Проверяется ТОЛЬКО после валидной подписи — иначе доверять полю нельзя.
    # Верификатор инициализируется UID своего контроллера; валидный snapshot чужого
    # контроллера (например, перехваченный/переадресованный) → reject.
    if (
        expected_controller_uid is not None
        and snapshot.get("controller_uid") != expected_controller_uid
    ):
        return _reject("controller_uid_mismatch")

    # 4) Срок по СТЕННЫМ часам (§8.2: возраст ≤ 15 мин).
    expires_at = _parse_dt(snapshot.get("expires_at"))
    if expires_at is None or wall_now >= expires_at:
        return _reject("expired")

    # 5) Монотонная защита от скачка часов (§8.2): возраст с момента получения.
    if received_monotonic is not None:
        mono = now_monotonic if now_monotonic is not None else time.monotonic()
        if (mono - received_monotonic) > max_age_seconds:
            return _reject("monotonic_expired")

    # Валиден — но в fail_closed въезд всё равно НЕ открывается (reject-only).
    return VerifyResult(True, False, FAIL_CLOSED, None)


class SnapshotVerifier:
    """Stateful обёртка edge: хранит pinned ключ и момент получения (монотонно).

    Один pinned (``key_id`` + публичный ключ) — модель пилота (§8.2). ``accept``
    фиксирует монотонный момент получения для последующей защиты от скачка часов.
    """

    def __init__(
        self,
        pinned_key_id: str,
        pinned_public_key: bytes,
        *,
        expected_controller_uid: str | None = None,
        offline_mode: str = FAIL_CLOSED,
        max_age_seconds: int = SNAPSHOT_TTL_SECONDS,
        max_clock_drift_seconds: int = MAX_CLOCK_DRIFT_SECONDS,
    ) -> None:
        self._key_id = pinned_key_id
        self._public_key = pinned_public_key
        # UID собственного контроллера: snapshot чужого контроллера отвергается (H1).
        self._expected_controller_uid = expected_controller_uid
        self._offline_mode = offline_mode
        self._max_age = max_age_seconds
        self._max_drift = max_clock_drift_seconds
        self._received_monotonic: float | None = None

    def accept(
        self,
        snapshot: dict,
        *,
        now: dt.datetime | None = None,
        clock_drift_seconds: float = 0.0,
    ) -> VerifyResult:
        """Принять snapshot: зафиксировать момент получения и проверить (§8.2)."""
        self._received_monotonic = time.monotonic()
        return verify_snapshot(
            snapshot,
            pinned_key_id=self._key_id,
            pinned_public_key=self._public_key,
            expected_controller_uid=self._expected_controller_uid,
            now=now,
            received_monotonic=self._received_monotonic,
            max_age_seconds=self._max_age,
            clock_drift_seconds=clock_drift_seconds,
            max_clock_drift_seconds=self._max_drift,
        )

    def recheck(
        self,
        snapshot: dict,
        *,
        now: dt.datetime | None = None,
        now_monotonic: float | None = None,
        clock_drift_seconds: float = 0.0,
    ) -> VerifyResult:
        """Перепроверить ранее принятый snapshot (срок/монотонность/дрейф, §8.2)."""
        return verify_snapshot(
            snapshot,
            pinned_key_id=self._key_id,
            pinned_public_key=self._public_key,
            expected_controller_uid=self._expected_controller_uid,
            now=now,
            received_monotonic=self._received_monotonic,
            now_monotonic=now_monotonic,
            max_age_seconds=self._max_age,
            clock_drift_seconds=clock_drift_seconds,
            max_clock_drift_seconds=self._max_drift,
        )
