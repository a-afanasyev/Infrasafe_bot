"""П10 / PENT-F11 + AUD3-35 — доверенные прокси задаются подсетью, а не списком IP.

`X-Real-IP` — это ключ rate-limit-бакета. Доверять ему можно только если TCP-peer
и есть наш edge. Механизм allowlist в коде был, но сравнивал СТРОКИ на точное
совпадение, а адрес edge не статичен — ровно поэтому `FORWARDED_ALLOW_IPS`
(PENT-F03) задан подсетью. Строка `172.19.0.0/16` в такой набор не сматчилась бы
никогда: allowlist выглядел бы настроенным и молча не работал.

Проверяется наблюдаемое следствие — какой ключ бакета получится, а не форма
хранения allowlist.
"""
from __future__ import annotations

import importlib

import pytest

MODULE = "uk_management_bot.api.rate_limit_keys"

EDGE_IP = "172.19.0.7"
OTHER_IP = "10.9.9.9"
CLIENT_IP = "203.0.113.5"


def _reload_with(monkeypatch, trusted: str | None):
    """Перечитать модуль с заданным allowlist (он читается на импорте)."""
    if trusted is None:
        monkeypatch.delenv("RATE_LIMIT_TRUSTED_PROXIES", raising=False)
    else:
        monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXIES", trusted)
    module = importlib.import_module(MODULE)
    return importlib.reload(module)


class _Request:
    """Минимальный дубль starlette-запроса: только peer и заголовки."""

    def __init__(self, peer: str | None, real_ip: str | None = CLIENT_IP):
        self.client = type("C", (), {"host": peer})() if peer else None
        self.headers = {"X-Real-IP": real_ip} if real_ip else {}


@pytest.fixture(autouse=True)
def restore_module():
    yield
    importlib.reload(importlib.import_module(MODULE))


class TestSubnetAllowlist:
    def test_peer_inside_the_subnet_is_trusted(self, monkeypatch):
        """Суть пункта: подсеть должна МАТЧИТЬСЯ, а не быть мёртвой строкой."""
        keys = _reload_with(monkeypatch, "172.19.0.0/16")

        assert keys.client_ip_key(_Request(EDGE_IP)) == CLIENT_IP

    def test_peer_outside_the_subnet_falls_back_to_the_tcp_peer(self, monkeypatch):
        """Подделанный `X-Real-IP` от чужого контейнера не должен менять бакет."""
        keys = _reload_with(monkeypatch, "172.19.0.0/16")

        assert keys.client_ip_key(_Request(OTHER_IP)) == OTHER_IP

    def test_single_address_still_works(self, monkeypatch):
        """Одиночный IP — частный случай сети (/32), прежняя запись не ломается."""
        keys = _reload_with(monkeypatch, EDGE_IP)

        assert keys.client_ip_key(_Request(EDGE_IP)) == CLIENT_IP
        assert keys.client_ip_key(_Request(OTHER_IP)) == OTHER_IP

    def test_mixed_list_of_addresses_and_subnets(self, monkeypatch):
        keys = _reload_with(monkeypatch, f"{OTHER_IP}, 172.19.0.0/16")

        assert keys.client_ip_key(_Request(EDGE_IP)) == CLIENT_IP
        assert keys.client_ip_key(_Request(OTHER_IP)) == CLIENT_IP
        assert keys.client_ip_key(_Request("192.0.2.1")) == "192.0.2.1"

    def test_garbage_entry_is_dropped_and_does_not_break_startup(self, monkeypatch):
        """Опечатка не должна ронять API — но и не должна «доверять всем»."""
        keys = _reload_with(monkeypatch, "not-an-ip, 172.19.0.0/16")

        assert keys.client_ip_key(_Request(EDGE_IP)) == CLIENT_IP
        assert keys.client_ip_key(_Request(OTHER_IP)) == OTHER_IP


class TestBackwardCompatibility:
    def test_unset_allowlist_keeps_the_documented_behaviour(self, monkeypatch):
        """Без переменной поведение прежнее: заголовок edge принимается.

        Это осознанный инвариант (nginx перезаписывает заголовок, api не
        публикует host-порт), а не забытая ветка — менять его в рамках этого
        пункта нельзя.
        """
        keys = _reload_with(monkeypatch, None)

        assert keys.client_ip_key(_Request(OTHER_IP)) == CLIENT_IP

    def test_without_the_header_the_peer_is_the_bucket(self, monkeypatch):
        keys = _reload_with(monkeypatch, "172.19.0.0/16")

        assert keys.client_ip_key(_Request(EDGE_IP, real_ip=None)) == EDGE_IP
