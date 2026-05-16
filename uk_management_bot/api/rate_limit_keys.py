"""Rate-limit key function — side-effect-free.

Kept separate from ``rate_limit.py`` on purpose: that module builds a
module-level ``limiter`` (possibly Redis-backed) at import time. The web app
(``web/limiter.py``) only needs the key function and must not trigger
construction of the API limiter just by importing it.
"""
from slowapi.util import get_remote_address
from starlette.requests import Request


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

    In local dev there is no nginx and the header is absent — fall back to
    ``get_remote_address``, which is the real client there.
    """
    real_ip = request.headers.get("X-Real-IP")
    if real_ip and real_ip.strip():
        return real_ip.strip()
    return get_remote_address(request)
