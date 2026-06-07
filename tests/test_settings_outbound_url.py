"""SEC-063 — outbound InfraSafe URLs must be safe http(s) targets.

`_require_safe_outbound_url` is the validator wired into Settings'
production-only startup block for INFRASAFE_WEBHOOK_URL (signed webhook target +
buildings metrics) and INFRASAFE_REQUESTS_INVENTORY_URL (reconciliation poll).
A bad value would otherwise silently redirect HMAC-signed payloads to an
arbitrary or eavesdroppable host. Plaintext http is tolerated only for
local/internal hosts (dev & test stubs run DEBUG=false with an http
host.docker.internal target). We unit-test the validator directly — reloading
Settings would mutate a process-global singleton shared by the full suite.
"""
import pytest

from uk_management_bot.config.settings import _require_safe_outbound_url


def test_empty_url_is_allowed():
    # Integration simply unconfigured — must not raise.
    _require_safe_outbound_url("INFRASAFE_WEBHOOK_URL", "")


@pytest.mark.parametrize(
    "url",
    [
        "https://infrasafe.uz",
        "https://infrasafe.uz/api/webhooks",
        "https://infrasafe.aisolutions.uz:8443/hook",
        # plaintext http allowed for local / internal targets (dev/test stubs)
        "http://host.docker.internal:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://10.0.0.5/hook",
        "http://media-service.internal/api",
    ],
)
def test_valid_urls_pass(url):
    _require_safe_outbound_url("INFRASAFE_WEBHOOK_URL", url)


@pytest.mark.parametrize(
    "url",
    [
        "http://infrasafe.uz",          # plaintext to PUBLIC host
        "http://evil.example.com/hook",  # plaintext to public host
        "ftp://infrasafe.uz",           # wrong scheme
        "infrasafe.uz",                 # scheme-less (host parsed as path)
        "https:///api/webhooks",        # no host
        "//infrasafe.uz/hook",          # scheme-less protocol-relative
        "javascript:alert(1)",          # non-network scheme
    ],
)
def test_invalid_urls_raise(url):
    with pytest.raises(ValueError):
        _require_safe_outbound_url("INFRASAFE_WEBHOOK_URL", url)


def test_error_names_the_setting():
    with pytest.raises(ValueError, match="INFRASAFE_REQUESTS_INVENTORY_URL"):
        _require_safe_outbound_url("INFRASAFE_REQUESTS_INVENTORY_URL", "http://evil.example.com")
