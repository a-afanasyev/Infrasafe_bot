"""A9-P3-13 / A9-P2-11 — edit-ветка PATCH заявки и вход комментариев.

* ``{"rating"}`` без статуса у жителя — 422 «только вместе с приёмкой»
  (раньше ``getattr(req, "rating")`` → AttributeError → 500: у модели нет поля);
* терминальный гард на ВСЕ поля edit-ветки (раньше — только urgency):
  исполнитель правил отчёт/материалы закрытой заявки, менеджер — заметки;
* правка в edit-ветке пишет строку ``audit_logs`` (раньше — прямой setattr без следа);
* ответы PATCH (edit, workflow, смена категории) несут поля лифта — как GET;
* ``POST …/comments``: ``media_files`` и лишние ключи — 422, длинный текст — 422.
"""
from datetime import date
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select

import uk_management_bot.api.requests.router as req_router
import uk_management_bot.utils.constants as C
from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_comment import RequestComment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.category_change import CategoryChangeResult
from uk_management_bot.services.elevator_service import generate_public_code

PATCH_URL = "/api/v2/requests/{number}"
NUMBER = "260923-001"


@pytest_asyncio.fixture
async def executor_user(db_session):
    u = User(telegram_id=779001, username="exec", first_name="Exec", last_name="T",
             roles='["executor"]', status="approved")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def applicant_user(db_session):
    u = User(telegram_id=779002, username="appl", first_name="Appl", last_name="T",
             roles='["applicant"]', status="approved")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture(autouse=True)
def _no_realtime(monkeypatch):
    monkeypatch.setattr(req_router, "publish_request_event", AsyncMock())


def _act_as(user):
    app.dependency_overrides[get_current_user] = lambda: user


async def _seed(db, *, owner_id, status="В работе", executor_id=None, elevator_id=None,
                category="electricity", notes=None):
    db.add(Request(request_number=NUMBER, user_id=owner_id, category=category,
                   description="desc", status=status, urgency="low", notes=notes,
                   executor_id=executor_id, elevator_id=elevator_id,
                   elevator_operational=False if elevator_id else None))
    await db.commit()


async def _elevator(db) -> Elevator:
    yard = Yard(name="Двор", is_active=True)
    db.add(yard)
    await db.flush()
    building = Building(address="ул. Лифтовая 3", yard_id=yard.id, is_active=True,
                        entrance_count=1, floor_count=9)
    db.add(building)
    await db.flush()
    elevator = Elevator(
        building_id=building.id, entrance_number=1, elevator_number=1,
        passport_number="P-1", manufacturer="OTIS", serial_number="S-1",
        public_code=generate_public_code(), is_commissioned=True,
        commissioned_at=date(2020, 1, 1), current_status="working",
    )
    db.add(elevator)
    await db.commit()
    return elevator


async def _row(db) -> Request:
    db.expire_all()
    return (await db.execute(
        select(Request).where(Request.request_number == NUMBER))).scalar_one()


# ── rating без статуса ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_applicant_rating_without_status_is_422_not_500(client, db_session, applicant_user):
    await _seed(db_session, owner_id=applicant_user.id, status="Исполнено")
    _act_as(applicant_user)

    r = await client.patch(PATCH_URL.format(number=NUMBER), json={"rating": 5})

    assert r.status_code == 422, r.text
    assert "rating" in r.json()["detail"]


# ── Терминальный гард на все поля ──────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("term", [C.REQUEST_STATUS_APPROVED, C.REQUEST_STATUS_CANCELLED])
@pytest.mark.parametrize("field", ["completion_report", "requested_materials", "notes"])
async def test_executor_cannot_edit_finalized_request(
    client, db_session, applicant_user, executor_user, term, field,
):
    await _seed(db_session, owner_id=applicant_user.id, status=term,
                executor_id=executor_user.id)
    _act_as(executor_user)

    r = await client.patch(PATCH_URL.format(number=NUMBER), json={field: "правка задним числом"})

    assert r.status_code == 422, r.text
    assert getattr(await _row(db_session), field) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("term", [C.REQUEST_STATUS_APPROVED, C.REQUEST_STATUS_CANCELLED])
async def test_manager_cannot_edit_notes_of_finalized_request(client, db_session, applicant_user, term):
    await _seed(db_session, owner_id=applicant_user.id, status=term)

    r = await client.patch(PATCH_URL.format(number=NUMBER), json={"notes": "новое"})

    assert r.status_code == 422, r.text
    assert (await db_session.execute(select(AuditLog))).scalars().all() == []


@pytest.mark.asyncio
async def test_executor_edits_active_request(client, db_session, applicant_user, executor_user):
    """Контрольный: активная заявка по-прежнему правится исполнителем."""
    await _seed(db_session, owner_id=applicant_user.id, executor_id=executor_user.id)
    _act_as(executor_user)

    r = await client.patch(PATCH_URL.format(number=NUMBER), json={"completion_report": "готово"})

    assert r.status_code == 200, r.text
    assert (await _row(db_session)).completion_report == "готово"


# ── Аудит правок ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_manager_edit_writes_audit(client, db_session, manager_user, applicant_user):
    await _seed(db_session, owner_id=applicant_user.id)

    r = await client.patch(PATCH_URL.format(number=NUMBER),
                           json={"urgency": "high", "notes": "заметка"})

    assert r.status_code == 200, r.text
    logs = (await db_session.execute(select(AuditLog))).scalars().all()
    assert len(logs) == 1
    log = logs[0]
    assert log.action == "request_fields_edited"
    assert log.user_id == manager_user.id
    assert log.details["request_number"] == NUMBER
    assert log.details["fields"]["urgency"] == {"old": "low", "new": "high"}
    assert log.details["fields"]["notes"] == {"old": None, "new": "заметка"}


@pytest.mark.asyncio
async def test_no_op_edit_writes_no_audit(client, db_session, applicant_user):
    await _seed(db_session, owner_id=applicant_user.id)

    r = await client.patch(PATCH_URL.format(number=NUMBER), json={"urgency": "low"})

    assert r.status_code == 200, r.text
    assert (await db_session.execute(select(AuditLog))).scalars().all() == []


# ── Карточка ответа несёт лифт ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_edit_response_card_carries_elevator(client, db_session, applicant_user):
    elevator = await _elevator(db_session)
    await _seed(db_session, owner_id=applicant_user.id, elevator_id=elevator.id,
                category="elevator")

    r = await client.patch(PATCH_URL.format(number=NUMBER), json={"urgency": "high"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["elevator_id"] == elevator.id
    assert body["elevator_status"] == "working"
    assert "ул. Лифтовая 3" in body["elevator_label"]


@pytest.mark.asyncio
async def test_edit_response_card_carries_executor_name(
    client, db_session, applicant_user, executor_user,
):
    """Как у GET: edit-ветка раньше отдавала executor_name=null."""
    await _seed(db_session, owner_id=applicant_user.id, executor_id=executor_user.id)

    r = await client.patch(PATCH_URL.format(number=NUMBER), json={"urgency": "high"})

    assert r.status_code == 200, r.text
    assert r.json()["executor_name"]


@pytest.mark.asyncio
async def test_workflow_response_card_carries_elevator(
    client, db_session, applicant_user, monkeypatch,
):
    from types import SimpleNamespace

    elevator = await _elevator(db_session)
    await _seed(db_session, owner_id=applicant_user.id, elevator_id=elevator.id,
                category="elevator")
    outcome = SimpleNamespace(post_commit_intents=(), old_state=None, new_state=None)
    monkeypatch.setattr(req_router, "run_command_async", AsyncMock(return_value=outcome))
    monkeypatch.setattr(req_router, "dispatch_notify_intents_detached", AsyncMock())

    r = await client.patch(PATCH_URL.format(number=NUMBER),
                           json={"status": "Выполнена", "completion_report": "готово"})

    assert r.status_code == 200, r.text
    assert r.json()["elevator_status"] == "working"


@pytest.mark.asyncio
async def test_category_change_response_card_carries_elevator(
    client, db_session, applicant_user, monkeypatch,
):
    elevator = await _elevator(db_session)
    await _seed(db_session, owner_id=applicant_user.id, elevator_id=elevator.id,
                category="elevator")
    result = CategoryChangeResult(
        request_number=NUMBER, no_op=True, old_category="elevator", new_category="elevator",
        old_specialization=None, new_specialization=None, specialization_changed=False,
        dispatch=None, status="В работе", executor_id=None,
        executor_spec_mismatch=False, can_reassign=False, post_commit_intents=(),
    )
    monkeypatch.setattr(req_router, "change_category_async", AsyncMock(return_value=result))

    r = await client.patch(f"/api/v2/requests/{NUMBER}/category", json={"category": "elevator"})

    assert r.status_code == 200, r.text
    assert r.json()["request"]["elevator_status"] == "working"


# ── Комментарии: вход ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_comment_with_media_files_rejected(client, db_session, applicant_user):
    await _seed(db_session, owner_id=applicant_user.id)

    r = await client.post(f"/api/v2/requests/{NUMBER}/comments",
                          json={"text": "фото", "media_files": ["https://evil.example/x.jpg"]})

    assert r.status_code == 422, r.text
    assert (await db_session.execute(select(RequestComment))).scalars().all() == []


@pytest.mark.asyncio
async def test_comment_too_long_rejected(client, db_session, applicant_user):
    await _seed(db_session, owner_id=applicant_user.id)

    r = await client.post(f"/api/v2/requests/{NUMBER}/comments",
                          json={"text": "я" * (C.MAX_DESCRIPTION_LENGTH + 1)})

    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_comment_plain_still_created(client, db_session, applicant_user):
    """Контрольный: тело, которым ходят дашборд и TWA, проходит."""
    await _seed(db_session, owner_id=applicant_user.id)

    r = await client.post(f"/api/v2/requests/{NUMBER}/comments",
                          json={"text": "ок", "is_internal": True})

    assert r.status_code == 201, r.text


def test_create_schemas_have_no_media_files():
    """Create-схемы поле больше не знают: строка не может доехать до answer_photo."""
    from uk_management_bot.api.requests.schemas import (
        CreateInspectorRequestBody,
        CreateRequestBody,
    )

    assert "media_files" not in CreateRequestBody.model_fields
    assert "media_files" not in CreateInspectorRequestBody.model_fields


# ── Лимиты длины текстовых полей (сек-ревью a507ce4d, MEDIUM) ─────────────
# Канон — MAX_DESCRIPTION_LENGTH (2000): им же бот ограничивает описание;
# у фронта/TWA своего лимита на эти поля нет.

_LIMIT = C.MAX_DESCRIPTION_LENGTH
_PATCH_TEXT_FIELDS = [
    "notes", "completion_report", "requested_materials",
    "return_reason", "manager_confirmation_notes",
]


@pytest.mark.parametrize("field", _PATCH_TEXT_FIELDS)
def test_patch_text_fields_limited(field):
    from pydantic import ValidationError

    from uk_management_bot.api.requests.schemas import UpdateRequestBody

    assert getattr(UpdateRequestBody(**{field: "я" * _LIMIT}), field)
    with pytest.raises(ValidationError):
        UpdateRequestBody(**{field: "я" * (_LIMIT + 1)})


@pytest.mark.parametrize("schema_name,address_type", [
    ("CreateRequestBody", "apartment"),
    ("CreateInspectorRequestBody", "building"),
])
def test_create_description_limited(schema_name, address_type):
    from pydantic import ValidationError

    from uk_management_bot.api.requests import schemas

    schema = getattr(schemas, schema_name)
    base = dict(category="electricity", urgency="low",
                address_type=address_type, address_id=1)
    assert schema(**base, description="я" * _LIMIT).description
    with pytest.raises(ValidationError):
        schema(**base, description="я" * (_LIMIT + 1))


@pytest.mark.asyncio
async def test_patch_too_long_notes_is_422_over_http(client, db_session, applicant_user):
    await _seed(db_session, owner_id=applicant_user.id)

    r = await client.patch(PATCH_URL.format(number=NUMBER), json={"notes": "я" * (_LIMIT + 1)})

    assert r.status_code == 422, r.text
    assert (await _row(db_session)).notes is None


# ── Аудит: значения усекаются ─────────────────────────────────────────────


def test_audit_value_truncation():
    from uk_management_bot.api.requests.service import (
        AUDIT_VALUE_MAX_LEN,
        _audit_value,
    )

    assert _audit_value(None) is None
    assert _audit_value("low") == "low"
    exact = "я" * AUDIT_VALUE_MAX_LEN
    assert _audit_value(exact) == exact
    cut = _audit_value("я" * (AUDIT_VALUE_MAX_LEN + 500))
    assert cut.startswith("я" * AUDIT_VALUE_MAX_LEN)
    assert cut.endswith("…[+500]")


@pytest.mark.asyncio
async def test_audit_truncates_long_old_value(client, db_session, applicant_user):
    """Старое значение могло попасть в БД в обход лимитов (бот пишет напрямую) —
    в аудит оно уходит усечённым."""
    from uk_management_bot.api.requests.service import AUDIT_VALUE_MAX_LEN

    await _seed(db_session, owner_id=applicant_user.id, notes="с" * (AUDIT_VALUE_MAX_LEN + 10))

    r = await client.patch(PATCH_URL.format(number=NUMBER), json={"notes": "коротко"})

    assert r.status_code == 200, r.text
    log = (await db_session.execute(select(AuditLog))).scalar_one()
    assert log.details["fields"]["notes"]["old"] == "с" * AUDIT_VALUE_MAX_LEN + "…[+10]"
    assert log.details["fields"]["notes"]["new"] == "коротко"


def test_manager_edit_fields_match_patch_schema():
    """Мёртвых ключей в белом списке менеджера нет: каждое поле пропускает схема."""
    from uk_management_bot.api.requests.schemas import UpdateRequestBody

    assert req_router._MANAGER_EDIT_FIELDS <= set(UpdateRequestBody.model_fields)
    assert req_router._EXECUTOR_EDIT_FIELDS <= set(UpdateRequestBody.model_fields)
