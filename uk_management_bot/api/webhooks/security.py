"""HMAC-SHA256 verification for inbound webhooks (InfraSafe → UK).

Mirrors the outbound signing scheme in services/webhook_sender.py:sign_payload —
header `x-webhook-signature: t=<unix>,v1=<hmac_hex>`, signature computed over
`f"{t}." + raw_body`. The InfraSafe sender (ukApiClient.js) must sign identically.
"""
import hashlib
import hmac
import logging
import time

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SEC = 300


def verify_signature(
    raw_body: bytes,
    header: str | None,
    secrets: list[str],
    window_sec: int = DEFAULT_WINDOW_SEC,
) -> tuple[bool, str]:
    """Verify the `x-webhook-signature` header against the raw request body.

    Returns (ok, reason). reason ∈ {'', 'no_header', 'bad_format', 'stale',
    'no_match'}. `secrets` is tried in order (dual-secret rotation: primary +
    next); empty entries are skipped. Comparison is constant-time.
    """
    if not header:
        return False, "no_header"
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = parts["t"]
        sig = parts["v1"]
        ts_int = int(ts)
    except (ValueError, KeyError):
        return False, "bad_format"

    if abs(int(time.time()) - ts_int) > window_sec:
        return False, "stale"

    message = f"{ts}.".encode() + raw_body
    for secret in secrets:
        if not secret:
            continue
        expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, sig):
            return True, ""
    return False, "no_match"
