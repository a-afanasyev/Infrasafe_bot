"""AUD6-P2-06 / AUD6-P2-17: пул соединений и ключ rate-limit за прокси."""

from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.core import ratelimit_key
from app.db import _engine_kwargs

# --- AUD6-P2-06: размер пула -------------------------------------------------


def test_engine_kwargs_postgres_pool_is_explicit():
    s = SimpleNamespace(
        database_url="postgresql+psycopg2://u:p@h:5432/db", db_pool_size=15, db_max_overflow=25
    )
    kw = _engine_kwargs(s)
    assert kw["pool_size"] == 15
    assert kw["max_overflow"] == 25
    assert kw["pool_pre_ping"] is True


def test_engine_kwargs_sqlite_has_no_pool_args():
    s = SimpleNamespace(database_url="sqlite:///x.db")
    kw = _engine_kwargs(s)
    assert "pool_size" not in kw and "max_overflow" not in kw


# --- AUD6-P2-17: client_ip_key ----------------------------------------------


def _req(headers: dict | None = None, peer: str | None = "10.0.0.9") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": (peer, 1234) if peer else None,
    }
    return Request(scope)


@pytest.fixture
def trusted(monkeypatch):
    """Подменяет allowlist и чистит lru_cache до и после."""

    def _set(raw: str) -> None:
        monkeypatch.setattr(
            ratelimit_key, "get_settings",
            lambda: SimpleNamespace(rate_limit_trusted_proxies=raw),
        )
        ratelimit_key._trusted_networks.cache_clear()

    yield _set
    ratelimit_key._trusted_networks.cache_clear()


def test_no_allowlist_header_is_honored(trusted):
    trusted("")
    assert ratelimit_key.client_ip_key(_req({"X-Real-IP": "1.2.3.4"})) == "1.2.3.4"


def test_no_header_falls_back_to_peer(trusted):
    trusted("")
    assert ratelimit_key.client_ip_key(_req()) == "10.0.0.9"


def test_trusted_peer_header_honored(trusted):
    trusted("10.0.0.0/24")
    assert ratelimit_key.client_ip_key(_req({"X-Real-IP": "1.2.3.4"})) == "1.2.3.4"


def test_untrusted_peer_header_ignored(trusted):
    """Подделанный X-Real-IP с прямого коннекта не обходит per-IP лимит."""
    trusted("172.19.0.0/16")
    assert ratelimit_key.client_ip_key(_req({"X-Real-IP": "1.2.3.4"})) == "10.0.0.9"


def test_garbage_allowlist_entry_ignored_rest_works(trusted):
    trusted("не-адрес, 10.0.0.0/24")
    assert ratelimit_key.client_ip_key(_req({"X-Real-IP": "1.2.3.4"})) == "1.2.3.4"
