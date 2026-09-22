"""A9-P3-3: commit_token импорта — срочный и привязан к {user, tenant, month}.
A9-P2-13: preview не выполняет разбор файла и SQL в event loop."""

import asyncio
import threading
import time
import uuid
from types import SimpleNamespace

import pytest
from itsdangerous import TimestampSigner
from sqlalchemy import delete, select

from app.api import imports as imports_api
from app.db import SessionLocal
from app.models import Reading, ReadingRevision, ReportingPeriod, User
from tests.conftest import login, make_meter, make_object, make_period
from tests.test_imports import _preview

# Все периоды модуля — в 2041 году; после каждого теста они удаляются.
_MONTH_PREFIX = "2041-"


@pytest.fixture(autouse=True)
def _drop_module_periods():
    """Сьют делит одну БД и тенант: открытые периоды, оставленные здесь, попадали
    в lock_periods_from чужих тестов (test_period_concurrency_pg на PG ждёт
    ровно [feb, mar]). Убираем свои периоды вместе с показаниями."""
    yield
    with SessionLocal() as db:
        period_ids = select(ReportingPeriod.id).where(ReportingPeriod.month.startswith(_MONTH_PREFIX))
        reading_ids = select(Reading.id).where(Reading.reporting_period_id.in_(period_ids))
        db.execute(delete(ReadingRevision).where(ReadingRevision.reading_id.in_(reading_ids)))
        db.execute(delete(Reading).where(Reading.reporting_period_id.in_(period_ids)))
        db.execute(delete(ReportingPeriod).where(ReportingPeriod.month.startswith(_MONTH_PREFIX)))
        db.commit()


def _csv(number: str, month: str) -> bytes:
    return f"meter_number;period;reading_value;read_at;note\n{number};{month};10;;\n".encode()


def _user(external_id: str) -> User:
    with SessionLocal() as db:
        return db.execute(select(User).where(User.external_id == external_id)).scalar_one()


def _commit(client, month: str, token: str):
    return client.post("/v1/imports/readings/commit", json={"month": month, "commit_token": token})


def _rows(number: str, month: str) -> list[dict]:
    return [{"meter_number": number, "period": month, "reading_value": "10", "read_at": "", "note": ""}]


def test_expired_token_rejected(admin, monkeypatch):
    obj = make_object(admin, "A9P33-exp")
    make_meter(admin, "A9P33-EXP", obj["id"])
    make_period(admin, "2041-01")
    user = _user("user-resource_admin")
    stale = int(time.time()) - imports_api.COMMIT_TOKEN_MAX_AGE_SECONDS - 60
    monkeypatch.setattr(TimestampSigner, "get_timestamp", lambda self: stale)
    token = imports_api.issue_commit_token(user, "2041-01", _rows("A9P33-EXP", "2041-01"))
    monkeypatch.undo()

    resp = _commit(admin, "2041-01", token)
    assert resp.status_code == 400, resp.text
    assert "устарел" in resp.json()["error"]["message"]


def test_token_of_other_user_rejected(admin):
    obj = make_object(admin, "A9P33-usr")
    make_meter(admin, "A9P33-USR", obj["id"])
    make_period(admin, "2041-02")
    other = login(admin.__class__(admin.app), "resource_operator", "a9p33-other-operator")
    data = _preview(other, "2041-02", "r.csv", _csv("A9P33-USR", "2041-02")).json()["data"]
    assert data["valid"] == 1

    resp = _commit(admin, "2041-02", data["commit_token"])
    assert resp.status_code == 400, resp.text
    # владелец токена по-прежнему может его применить
    assert _commit(other, "2041-02", data["commit_token"]).status_code == 200


def test_token_of_other_tenant_rejected(admin):
    make_period(admin, "2041-03")
    user = _user("user-resource_admin")
    foreign = SimpleNamespace(id=user.id, tenant_id=uuid.uuid4())
    token = imports_api.issue_commit_token(foreign, "2041-03", _rows("X", "2041-03"))

    resp = _commit(admin, "2041-03", token)
    assert resp.status_code == 400, resp.text


def test_token_of_other_month_rejected(admin):
    obj = make_object(admin, "A9P33-mon")
    make_meter(admin, "A9P33-MON", obj["id"])
    make_period(admin, "2041-04")
    make_period(admin, "2041-05")
    data = _preview(admin, "2041-04", "r.csv", _csv("A9P33-MON", "2041-04")).json()["data"]

    resp = _commit(admin, "2041-05", data["commit_token"])
    assert resp.status_code == 400, resp.text


def test_legacy_unbound_token_rejected(admin):
    """Подписанный токен старого формата (голый список строк) больше не принимается."""
    make_period(admin, "2041-06")
    legacy = imports_api._commit_serializer().dumps(_rows("X", "2041-06"))
    assert _commit(admin, "2041-06", legacy).status_code == 400


def test_preview_parsing_runs_outside_event_loop(admin, monkeypatch):
    make_period(admin, "2041-07")
    seen: dict = {}
    real_parse = imports_api.parse_file

    def spy(filename, content):
        try:
            asyncio.get_running_loop()
            seen["in_loop"] = True
        except RuntimeError:
            seen["in_loop"] = False
        seen["thread"] = threading.current_thread().name
        return real_parse(filename, content)

    monkeypatch.setattr(imports_api, "parse_file", spy)
    resp = _preview(admin, "2041-07", "r.csv", _csv("NOPE", "2041-07"))
    assert resp.status_code == 200, resp.text
    assert seen["in_loop"] is False, seen


def test_preview_rejects_oversized_file(admin):
    make_period(admin, "2041-08")
    resp = _preview(admin, "2041-08", "big.csv", b"x" * (imports_api.MAX_UPLOAD_BYTES + 1))
    assert resp.status_code == 400
    assert "5 МБ" in resp.json()["error"]["message"]
