"""ARCH-137 фаза A: поведенческие тесты на классы дефектов наивного времени.

AST-гейт (`tests/services/test_shift_tz_inventory.py`) держит инвентарь; здесь —
поведение трёх точечных исправлений, которые гейт сам по себе не проверяет:

  * A2 — `_format_duration_hm`: арифметика в Python между значением из БД
    (aware на Postgres, naive на sqlite) и «сейчас». До фикса aware-start при
    `end_time=None` давал `TypeError: can't subtract offset-naive and
    offset-aware datetimes` — реальный прод-кейс (Postgres отдаёт aware).
  * A3 — TTL инвайта: `.timestamp()` у наивного datetime трактуется по зоне
    процесса, то есть срок жизни инвайта уезжал бы на смещение при смене `TZ`.
    Инвариант: expires_at ≈ time.time() + hours*3600 при ЛЮБОЙ зоне процесса.
  * `as_utc` — нормализатор: naive трактуется как UTC (правило business_time),
    aware конвертируется без сдвига инстанта.
"""

import base64
import json
import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from uk_management_bot.services.notification_service import _format_duration_hm
from uk_management_bot.utils.datetime_utils import as_utc, utc_now


# ── as_utc ───────────────────────────────────────────────────────────────────

def test_as_utc_tags_naive_as_utc():
    naive = datetime(2026, 8, 4, 12, 0, 0)
    out = as_utc(naive)
    assert out.tzinfo is timezone.utc
    assert (out.year, out.hour) == (2026, 12)  # стена не сдвинулась


def test_as_utc_converts_aware_without_shifting_instant():
    plus5 = timezone(timedelta(hours=5))
    aware = datetime(2026, 8, 4, 12, 0, 0, tzinfo=plus5)
    out = as_utc(aware)
    assert out.tzinfo is timezone.utc
    assert out == aware  # тот же инстант
    assert out.hour == 7


# ── A2: _format_duration_hm ─────────────────────────────────────────────────

def test_duration_aware_start_and_open_end_does_not_raise():
    """Постгрес-кейс: aware start_time из БД, end_time ещё не установлен."""
    start = utc_now() - timedelta(hours=2, minutes=30)
    hours, minutes = _format_duration_hm(start, None)
    assert (hours, minutes) == (2, 30)


def test_duration_naive_start_aware_end_mixed():
    """sqlite-кейс: naive из БД против aware `now` — нормализуются обе стороны."""
    end = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc)
    start_naive = datetime(2026, 8, 4, 8, 45)  # трактуется как UTC
    assert _format_duration_hm(start_naive, end) == (1, 15)


def test_duration_negative_clamped_to_zero():
    start = utc_now() + timedelta(hours=1)
    assert _format_duration_hm(start, None) == (0, 0)


# ── A3: TTL инвайта не зависит от зоны процесса ─────────────────────────────

def _decode_invite_payload(token: str) -> dict:
    """Токен = `invite_v1:{payload_b64}.{signature}`; payload — urlsafe base64."""
    payload_b64 = token.split(":", 1)[1].rsplit(".", 1)[0]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


@pytest.mark.parametrize("tz", ["UTC", "Asia/Tashkent", "Pacific/Kiritimati"])
def test_invite_ttl_is_process_tz_independent(tz, monkeypatch):
    """expires_at — эпоха; time.time() зоны не имеет, значит и payload не должен.

    До фикса naive `utcnow().timestamp()` при `TZ=Pacific/Kiritimati` (+14, без
    DST) укорачивал жизнь инвайта на 14 часов.
    """
    monkeypatch.setenv("TZ", tz)
    time.tzset()
    try:
        with patch("uk_management_bot.services.invite_service.settings") as mock_settings:
            mock_settings.INVITE_SECRET = "test-secret-arch137-ttl-invariant"
            from uk_management_bot.services.invite_service import InviteService

            service = InviteService(MagicMock())
            token = service.generate_invite(role="manager", created_by=1, hours=24)
        payload = _decode_invite_payload(token)
        drift = payload["expires_at"] - (time.time() + 24 * 3600)
        assert abs(drift) < 60, f"TTL уехал на {drift:.0f}s при TZ={tz}"
    finally:
        os.environ.pop("TZ", None)
        time.tzset()
