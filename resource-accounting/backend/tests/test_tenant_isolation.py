"""IDOR между тенантами (ревью 2026-11-07, docs/audit/idor-review-2026-11-07.md).

Каждый маршрут с id объекта: пользователь чужого тенанта → 404 (как «нет такого»),
свой тенант → 200. Сьют делит дефолтный тенант «uk»; второй заводится здесь.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.security import create_session_token
from app.main import app
from app.models import Tenant, User
from tests.conftest import make_meter, make_object, make_period

MONTH = "2031-03"


@pytest.fixture()
def outsider(db):
    tenant = db.query(Tenant).filter(Tenant.code == "other").one_or_none()
    if tenant is None:
        tenant = Tenant(code="other", name="Чужая УК")
        db.add(tenant)
        db.flush()
    user = User(tenant_id=tenant.id, external_id="other-admin", display_name="Чужой",
                role="resource_admin")
    db.add(user)
    db.commit()
    client = TestClient(app)
    client.cookies.set(get_settings().session_cookie_name, create_session_token(str(user.id)))
    yield client
    db.delete(user)
    db.commit()


@pytest.fixture()
def owned(admin):
    obj = make_object(admin, "Изоляция: дом")
    meter = make_meter(admin, f"ISO-{uuid.uuid4().hex[:8]}", obj["id"])
    make_period(admin, MONTH)
    reading = admin.put(f"/v1/meters/{meter['id']}/readings/{MONTH}", json={"value": "10"})
    assert reading.status_code == 200, reading.text
    return {"object": obj["id"], "meter": meter["id"], "reading": reading.json()["data"]["id"]}


@pytest.mark.parametrize("method,path,body", [
    ("get", "/v1/objects/{object}", None),
    ("patch", "/v1/objects/{object}", {"name": "взлом"}),
    ("post", "/v1/objects/{object}/archive", None),
    ("get", "/v1/meters/{meter}", None),
    ("patch", "/v1/meters/{meter}", {"name": "взлом"}),
    ("post", "/v1/meters/{meter}/archive", None),
    ("get", "/v1/analytics/meters/{meter}", None),
    ("put", "/v1/meters/{meter}/readings/" + MONTH, {"value": "999"}),
    ("post", "/v1/readings/{reading}/corrections",
     {"new_value": "999", "reason": "взлом", "kind": "correction"}),
])
def test_foreign_tenant_gets_404_owner_gets_through(owned, outsider, admin, method, path, body):
    url = path.format(**owned)
    kwargs = {"json": body} if body is not None else {}
    foreign = getattr(outsider, method)(url, **kwargs)
    assert foreign.status_code == 404, foreign.text
    # свой тенант до объекта доходит (бизнес-отказ возможен, «не найдено» — нет)
    if method == "get":
        assert getattr(admin, method)(url).status_code == 200


def test_foreign_tenant_lists_do_not_leak(owned, outsider):
    for url in ("/v1/objects", "/v1/meters"):
        resp = outsider.get(url)
        assert resp.status_code == 200, resp.text
        ids = {row["id"] for row in resp.json()["data"]["items"]} if isinstance(
            resp.json()["data"], dict) else {row["id"] for row in resp.json()["data"]}
        assert not ids & {owned["object"], owned["meter"]}


@pytest.mark.parametrize("collection", ["object-types", "tags", "providers"])
def test_foreign_tenant_cannot_patch_catalog(admin, outsider, collection):
    created = admin.post(f"/v1/{collection}", json={"name": f"iso-{uuid.uuid4().hex[:8]}"})
    assert created.status_code == 201, created.text
    url = f"/v1/{collection}/{created.json()['data']['id']}"
    assert outsider.patch(url, json={"name": "взлом"}).status_code == 404
    assert admin.patch(url, json={"name": f"iso-{uuid.uuid4().hex[:8]}"}).status_code == 200
