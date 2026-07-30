"""AUD6-P2-17: ключ rate-limit = реальный клиентский IP за edge-nginx.

Порт канона ``uk_management_bot/api/rate_limit_keys.py`` (PENT-F11/AUD3-35).
Сервис живёт за edge-прокси: TCP-peer для всех клиентов один (nginx), поэтому
дефолтный ``get_remote_address`` превращает per-IP лимиты (в т.ч. 10/minute на
вход) в ОДИН глобальный бакет — десяток контролёров блокирует вход всем.

``X-Real-IP`` ставит наш nginx (``proxy_set_header`` перезаписывает клиентское
значение). Если задан allowlist ``RESOURCE_RATE_LIMIT_TRUSTED_PROXIES``
(IP/CIDR через запятую), заголовок принимается ТОЛЬКО от перечисленных peer'ов
— подделка с прямого коннекта не обходит лимит. Пустой allowlist сохраняет
доверие к заголовку как есть (задокументированный инвариант: edge — един-
ственный ingress). ``X-Forwarded-For`` сознательно не используется: nginx
дописывает в него, левая запись — под контролем клиента.
"""

import ipaddress
import logging
from functools import lru_cache

from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def _trusted_networks() -> tuple[ipaddress._BaseNetwork, ...]:
    networks: list[ipaddress._BaseNetwork] = []
    for item in get_settings().rate_limit_trusted_proxies.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            # Опечатка не должна ронять сервис, но и молчать нельзя: молча
            # «недоверенный» прокси = внезапная смена бакетов на peer-IP.
            logger.error(
                "RESOURCE_RATE_LIMIT_TRUSTED_PROXIES: запись %r не IP/CIDR — игнорируется",
                item,
            )
    return tuple(networks)


def _is_trusted_peer(peer: str | None) -> bool:
    if peer is None:
        return False
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(address in network for network in _trusted_networks())


def client_ip_key(request: Request) -> str:
    real_ip = request.headers.get("X-Real-IP")
    if real_ip and real_ip.strip():
        peer = request.client.host if request.client else None
        if not _trusted_networks() or _is_trusted_peer(peer):
            return real_ip.strip()
    return get_remote_address(request)
