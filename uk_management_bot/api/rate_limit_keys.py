"""Rate-limit key function — side-effect-free.

Kept separate from ``rate_limit.py`` on purpose: that module builds a
module-level ``limiter`` (possibly Redis-backed) at import time. The web app
(``web/limiter.py``) only needs the key function and must not trigger
construction of the API limiter just by importing it.
"""
import os

from slowapi.util import get_remote_address
from starlette.requests import Request

# Defense in depth: ``X-Real-IP`` is only trustworthy when set by our own
# nginx upstream. If operators provide an allowlist of trusted-proxy peer IPs
# (comma-separated ``RATE_LIMIT_TRUSTED_PROXIES``), the header is honored ONLY
# when the TCP peer is one of them; from any other peer (e.g. the api
# container accidentally exposed directly) the header is ignored and we bucket
# by the real TCP peer instead, so a forged ``X-Real-IP`` cannot evade the
# per-IP limit. When the allowlist is unset the original behavior is preserved
# (the documented invariant is that nginx overwrites the header and the api
# container exposes no host port).
_TRUSTED_PROXIES = frozenset(
    p.strip()
    for p in os.getenv("RATE_LIMIT_TRUSTED_PROXIES", "").split(",")
    if p.strip()
)


def client_ip_key(request: Request) -> str:
    """Rate-limit bucket key = the real client IP.

    Behind nginx the TCP peer is the nginx container, so slowapi's default
    ``get_remote_address`` (``request.client.host``) collapses every client
    into one bucket. nginx sets ``X-Real-IP`` via ``proxy_set_header`` which
    *replaces* any client-supplied value, so it is the trustworthy real IP
    (the api container exposes no host port in prod — nginx is the only
    ingress, so the header cannot be forged).

    ``X-Forwarded-For`` is deliberately NOT used: nginx appends to it
    (``$proxy_add_x_forwarded_for``), so its leftmost entry is attacker-
    controlled.

    If ``RATE_LIMIT_TRUSTED_PROXIES`` is set, ``X-Real-IP`` is trusted only
    when the TCP peer is one of the listed upstreams; otherwise the header is
    ignored and the peer IP is used, so a forged header cannot bypass the
    limit even if the api is reachable without nginx in front.

    In local dev there is no nginx and the header is absent — fall back to
    ``get_remote_address``, which is the real client there.
    """
    real_ip = request.headers.get("X-Real-IP")
    if real_ip and real_ip.strip():
        peer = request.client.host if request.client else None
        if not _TRUSTED_PROXIES or (peer is not None and peer in _TRUSTED_PROXIES):
            return real_ip.strip()
    return get_remote_address(request)
