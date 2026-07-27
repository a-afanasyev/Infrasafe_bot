"""PENT-F17 — контракт публичного health-роута и запрет ложно-зелёной пробы.

Пункт был сформулирован как «`/uk/api/health` → 404, мониторинг может не
заметить отказ API». Разбор на живом profk 2026-07-26 показал, что беда шире и
конкретнее «неправильного URL»:

* `/uk/api/health` действительно 404 — но не из-за приложения: путь не входит в
  prefix-allowlist edge'а (SEC-22), поэтому edge возвращает свою HTML-страницу,
  не доходя до FastAPI. Это правится одной строкой в конфиге владельца, см.
  `docs/audit/2026-07-26-pent-f17-owner-checklist.md`;
* `/uk/health` отдавал **200 text/html** — SPA-fallback фронт-nginx. Любой
  мониторинг «по очевидному URL» был бы зелёным при мёртвом API, потому что
  статику nginx отдаёт независимо от него. Закрыто `location = /health` с 404;
* внешняя проба «management-api жив» в Uptime Kuma смотрела на
  `https://profk.uz/uk/api/v1/` с допуском 200-499, полагаясь на «живой апстрим
  ответит 404». Но на этот путь **404 отдаёт сам edge** (allowlist), апстрима
  запрос не касается — проверка зелена и при мёртвом API. Доказано разницей
  ответов: `/uk/api/v1/` → `text/html` от nginx, `/uk/api/v2/requests/__nope__`
  → `application/json` от FastAPI.

Тесты ниже держат две вещи, которые можно держать из репозитория: тело/тип
ответа приложения и отсутствие SPA-fallback'а на `/health` во фронт-nginx.
"""
import re
from pathlib import Path

import pytest

NGINX_CONF = Path(__file__).resolve().parents[2] / "frontend" / "nginx.conf"


@pytest.mark.asyncio
async def test_api_health_is_json_ok(client):
    """Канон публичного health: 200, JSON, ровно `{"ok": true}`."""
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_api_health_body_carries_no_spa_markers(client):
    """Ответ не должен выглядеть как страница: именно по HTML-признакам
    мониторинг и не отличал SPA-заглушку от живого API."""
    lowered = (await client.get("/api/health")).text.lower()
    for marker in ("<!doctype", "<html", "<head", "index.html", "data-brand"):
        assert marker not in lowered, f"HTML-маркер {marker!r} в теле health-ответа"


@pytest.mark.asyncio
async def test_internal_health_stays_stable_for_docker_probe(client):
    """`/health` (без `/api`) — внутренняя проба Dockerfile.api/compose.

    Её тело менять нельзя не из вкуса: blackbox-проба обсервабилити-слоя на
    profk бьёт прямо в `http://uk-management-api:8080/health`, и это
    единственный слой, который сегодня честно видит смерть API.
    """
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy", "service": "api"}


def test_frontend_nginx_does_not_serve_spa_on_health():
    """Фронт-nginx обязан отвечать на `/health` 404, а не index.html.

    Гейт конфигурации, а не приложения: без него правка `nginx.conf` вернёт
    SPA-fallback на `/health` и ложно-зелёная проба воскреснет незаметно.
    """
    conf = NGINX_CONF.read_text(encoding="utf-8")
    block = re.search(
        r"location\s*=\s*/health\s*\{(?P<body>[^}]*)\}", conf, re.S
    )
    assert block, "в frontend/nginx.conf нет `location = /health` (PENT-F17)"
    assert re.search(r"return\s+404\s*;", block.group("body")), (
        "`location = /health` есть, но не возвращает 404 — проба снова может "
        "получить SPA-страницу"
    )
