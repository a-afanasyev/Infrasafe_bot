"""Рейт-лимиты раздела «Жители».

Конвенция проекта — лимит объявляется НА МАРШРУТЕ (`@limiter.limit`), общего
`default_limits` у лимитера нет. 26 маршрутов в других доменах его несут, а
все 11 маршрутов «Жителей» уехали в прод без единого — находка аудита
2026-07-29.

Что именно это чинит (и чего НЕ чинит):

* **Не** защиту от неаутентифицированного флуда: auth-зависимости FastAPI
  выполняются ДО лимитера, поэтому 401-трафик до счётчика не доходит вовсе.
* Защиту от злоупотребления **авторизованной** сессией менеджера: прокси
  документов ходит во внешний Telegram и буферизует до 20 МБ в память на
  запрос, а approve/reject/request-documents на каждый вызов отправляют
  жителю сообщение в Telegram — то есть чужой чат можно завалить.

IP берётся из `X-Real-IP` (`client_ip_key`), поэтому каждый тест крутит свой
октет из TEST-NET-3: в dev-контейнере счётчик живёт в Redis и переживает
перезапуск сьюта.
"""
import time

import pytest

BASE = "/api/v2/residents"


def _ip(salt: int = 0) -> dict:
    base = (time.monotonic_ns() >> 4) & 0xFF
    octet = (base + salt) % 256
    if octet in (0, 255):
        octet = 1
    return {"X-Real-IP": f"203.0.113.{octet}"}


@pytest.mark.asyncio
class TestReadLimits:

    async def test_list_capped_at_60_per_minute(self, client):
        headers = _ip(0)
        for i in range(60):
            r = await client.get(BASE, headers=headers)
            assert r.status_code == 200, f"вызов {i+1}: {r.status_code} {r.text}"

        r = await client.get(BASE, headers=headers)
        assert r.status_code == 429, r.text

    async def test_stats_has_its_own_bucket(self, client):
        """У каждого маршрута свой счётчик: исчерпанный список не должен
        закрывать статистику — иначе один тяжёлый экран гасит весь раздел."""
        headers = _ip(60)
        for _ in range(60):
            await client.get(BASE, headers=headers)

        r = await client.get(f"{BASE}/stats", headers=headers)
        assert r.status_code == 200, r.text


@pytest.mark.asyncio
class TestDocumentProxyLimit:

    async def test_file_proxy_capped_at_30_per_minute(self, client):
        """Самый дорогой маршрут раздела: внешний запрос + буфер до 20 МБ.

        Ответ здесь 404 (жителя нет) — для лимитера это неважно: он считает
        обращения, а не успехи. Важно, что 31-й даёт именно 429.
        """
        headers = _ip(120)
        for i in range(30):
            r = await client.get(f"{BASE}/999999/documents/1/file", headers=headers)
            assert r.status_code != 429, f"вызов {i+1} упёрся в лимит раньше срока"

        r = await client.get(f"{BASE}/999999/documents/1/file", headers=headers)
        assert r.status_code == 429, r.text


@pytest.mark.asyncio
class TestMutationLimits:

    async def test_approve_capped_at_30_per_minute(self, client):
        headers = _ip(180)
        for i in range(30):
            r = await client.post(f"{BASE}/999999/approve", json={}, headers=headers)
            assert r.status_code != 429, f"вызов {i+1} упёрся в лимит раньше срока"

        r = await client.post(f"{BASE}/999999/approve", json={}, headers=headers)
        assert r.status_code == 429, r.text

    async def test_request_documents_capped_at_20_per_minute(self, client):
        """Порождает сообщение в Telegram жителю — лимит строже прочих мутаций."""
        headers = _ip(240)
        body = {"document_types": ["passport"], "comment": "нужен паспорт"}
        for i in range(20):
            r = await client.post(
                f"{BASE}/999999/verification/request-documents", json=body, headers=headers,
            )
            assert r.status_code != 429, f"вызов {i+1} упёрся в лимит раньше срока"

        r = await client.post(
            f"{BASE}/999999/verification/request-documents", json=body, headers=headers,
        )
        assert r.status_code == 429, r.text


@pytest.mark.asyncio
async def test_limits_are_per_ip(client):
    """Лимит на IP, а не глобальный: один менеджер не должен ронять раздел
    для остальных."""
    base = (time.monotonic_ns() >> 4) & 0xFF
    octet_a = base % 250 + 2
    octet_b = octet_a + 1 if octet_a < 251 else 2
    ip_a = {"X-Real-IP": f"203.0.113.{octet_a}"}
    ip_b = {"X-Real-IP": f"203.0.113.{octet_b}"}
    assert ip_a["X-Real-IP"] != ip_b["X-Real-IP"]

    for _ in range(60):
        await client.get(BASE, headers=ip_a)

    r = await client.get(BASE, headers=ip_b)
    assert r.status_code == 200, r.text
