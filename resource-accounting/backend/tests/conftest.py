import os
import tempfile

os.environ.setdefault("RESOURCE_DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ.setdefault("RESOURCE_DEV_AUTH_ENABLED", "true")
os.environ.setdefault("RESOURCE_SERVICE_TOKEN", "test-service-token")

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Tenant


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add(Tenant(code="uk", name="УК"))
        db.commit()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def db():
    session = SessionLocal()
    yield session
    session.close()


def login(client: TestClient, role: str, external_id: str | None = None) -> TestClient:
    resp = client.post(
        "/v1/auth/dev-login",
        json={
            "external_user_id": external_id or f"user-{role}",
            "display_name": f"Test {role}",
            "role": role,
        },
    )
    assert resp.status_code == 200, resp.text
    return client


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def admin(client):
    return login(client, "resource_admin")


@pytest.fixture()
def operator():
    return login(TestClient(app), "resource_operator")


@pytest.fixture()
def reviewer():
    return login(TestClient(app), "resource_reviewer")


@pytest.fixture()
def viewer():
    return login(TestClient(app), "resource_viewer")


def make_object(admin: TestClient, name: str, **kwargs) -> dict:
    resp = admin.post("/v1/objects", json={"name": name, **kwargs})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def make_meter(admin: TestClient, number: str, object_id: str, **kwargs) -> dict:
    payload = {
        "meter_number": number,
        "name": f"Счётчик {number}",
        "resource_type": "electricity",
        "unit": "kWh",
        "description": "Тестовый прибор",
        "install_location": "Щитовая",
        "primary_object_id": object_id,
    }
    payload.update(kwargs)
    resp = admin.post("/v1/meters", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def make_period(client: TestClient, month: str) -> dict:
    resp = client.post("/v1/periods", json={"month": month})
    assert resp.status_code in (201, 409), resp.text
    if resp.status_code == 409:
        periods = client.get("/v1/periods").json()["data"]
        return next(p for p in periods if p["month"] == month)
    return resp.json()["data"]
