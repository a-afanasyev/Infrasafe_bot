"""IDOR/BOLA-матрица UK API (ревью 2026-11-07, docs/audit/idor-review-2026-11-07.md).

Каждый маршрут с id объекта, открытый жителю/исполнителю/инспектору (класс b),
и тикет-маршруты (класс d) — пара проверок: пользователь A на объекте B → 403/404,
свой объект → 2xx. Маршруты, у которых такая пара уже есть в профильных тестах,
сюда не дублируются — их перечисляет `IDOR_COVERAGE`, а ратчет ниже требует,
чтобы каждый не-менеджерский маршрут с path-параметром был в реестре.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi.routing import APIRoute, APIWebSocketRoute

import uk_management_bot.api.requests.executor_actions as executor_actions
import uk_management_bot.api.requests.router as req_router
import uk_management_bot.api.routes.media_proxy as media_proxy
import uk_management_bot.utils.constants as C
from uk_management_bot.api.auth.service import create_access_token, encode_jwt
from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.api.registration.tickets import create_registration_ticket
from uk_management_bot.authz import store
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.yard import Yard

RA = "261107-001"   # заявка жителя A в работе у исполнителя E1
RN = "261107-002"   # новая заявка жителя A (отмена — workflow-ветка PATCH)
RB = "261107-003"   # заявка жителя B

A, B, E1, E2, INSP = 101, 102, 111, 112, 121


def _user(uid: int, roles: str) -> User:
    return User(id=uid, telegram_id=70000 + uid, first_name=f"U{uid}", last_name="Т",
                roles=roles, active_role=roles.split('"')[1], status="approved")


@pytest_asyncio.fixture
async def world(db_session, manager_user, db_session_factory, monkeypatch):
    yard = Yard(name="Двор", is_active=True)
    db_session.add(yard)
    await db_session.flush()
    b1 = Building(address="Дом 1", yard_id=yard.id, is_active=True)
    b2 = Building(address="Дом 2", yard_id=yard.id, is_active=True)
    db_session.add_all([b1, b2])
    await db_session.flush()
    apt1 = Apartment(building_id=b1.id, apartment_number="1", is_active=True)
    apt2 = Apartment(building_id=b2.id, apartment_number="2", is_active=True)
    db_session.add_all([apt1, apt2])
    await db_session.flush()
    db_session.add_all([
        _user(A, '["applicant"]'), _user(B, '["applicant"]'),
        _user(E1, '["executor"]'), _user(E2, '["executor"]'), _user(INSP, '["inspector"]'),
    ])
    await db_session.flush()
    db_session.add_all([
        UserApartment(user_id=A, apartment_id=apt1.id, status="approved"),
        UserApartment(user_id=B, apartment_id=apt2.id, status="approved"),
        Request(request_number=RA, user_id=A, category="plumbing", description="течёт",
                status=C.REQUEST_STATUS_IN_PROGRESS, urgency="low", executor_id=E1,
                assignment_type="individual", apartment_id=apt1.id),
        Request(request_number=RN, user_id=A, category="plumbing", description="новая",
                status=C.REQUEST_STATUS_NEW, urgency="low", apartment_id=apt1.id),
        Request(request_number=RB, user_id=B, category="plumbing", description="чужая",
                status=C.REQUEST_STATUS_NEW, urgency="low", apartment_id=apt2.id),
    ])
    shift = Shift(user_id=E1, start_time=datetime.now(timezone.utc), status="active")
    db_session.add(shift)
    await db_session.flush()
    transfer = ShiftTransfer(shift_id=shift.id, from_executor_id=E2, to_executor_id=E1,
                             assigned_by=manager_user.id, status="assigned", reason="illness")
    db_session.add(transfer)
    await db_session.commit()

    # Workflow-ветка PATCH и сервисы исполнителя открывают свои сессии.
    monkeypatch.setattr(req_router, "AsyncSessionLocal", db_session_factory)
    monkeypatch.setattr(req_router, "publish_request_event", AsyncMock())
    monkeypatch.setattr(req_router, "dispatch_notify_intents_detached", AsyncMock())
    monkeypatch.setattr(executor_actions, "notify_managers_problem_detached", AsyncMock())
    return {"b1": b1.id, "b2": b2.id, "shift": shift.id, "transfer": transfer.id}


@pytest.fixture
def act_as(client, db_session_factory, world):
    async def _switch(uid: int):
        async with db_session_factory() as s:
            user = await s.get(User, uid)
        app.dependency_overrides[get_current_user] = lambda: user
        return client
    return _switch


# ── Заявка: карточка, комментарии, правка, отмена ───────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,expected", [(B, 403), (E2, 403), (INSP, 403), (A, 200), (E1, 200)])
async def test_request_card(act_as, uid, expected):
    r = await (await act_as(uid)).get(f"/api/v2/requests/{RA}")
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,expected", [(B, 403), (E2, 403), (A, 200), (E1, 200)])
async def test_request_comments_read(act_as, uid, expected):
    r = await (await act_as(uid)).get(f"/api/v2/requests/{RA}/comments")
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,expected", [(B, 403), (E2, 403), (A, 201)])
async def test_request_comments_write(act_as, uid, expected):
    r = await (await act_as(uid)).post(f"/api/v2/requests/{RA}/comments", json={"text": "вопрос"})
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,expected", [(E2, 403), (E1, 200)])
async def test_request_edit_executor_fields(act_as, uid, expected):
    r = await (await act_as(uid)).patch(f"/api/v2/requests/{RA}", json={"completion_report": "сделано"})
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_request_edit_foreign_applicant_is_403(act_as):
    r = await (await act_as(B)).patch(f"/api/v2/requests/{RA}", json={"rating": 5})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,allowed", [(B, False), (A, True)])
async def test_request_cancel_workflow(act_as, db_session_factory, uid, allowed):
    r = await (await act_as(uid)).patch(
        f"/api/v2/requests/{RN}", json={"status": C.REQUEST_STATUS_CANCELLED})
    assert (r.status_code == 200) is allowed, r.text
    async with db_session_factory() as s:
        status = (await s.get(Request, RN)).status
    assert (status == C.REQUEST_STATUS_CANCELLED) is allowed


@pytest.mark.asyncio
async def test_request_edit_role_granted_update_cannot_edit_foreign(act_as, monkeypatch):
    """Действие «Редактировать заявку (бизнес-проверки внутри)» роли без
    исполнения/авторства — не право менеджера на любую заявку.

    Правка ролей в админке переопределяет каталог; edit-ветка PATCH раньше
    считала «не исполнитель и не автор» менеджером и пускала инспектора
    править заметки чужой заявки.
    """
    snapshot = store.Snapshot(version=2, overrides={("inspector", "requests.update"): True},
                              roles=frozenset({"inspector"}))
    monkeypatch.setattr(store, "current_snapshot", lambda: snapshot)
    r = await (await act_as(INSP)).patch(f"/api/v2/requests/{RB}", json={"notes": "чужое"})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,expected", [(E2, 403), (E1, 201)])
async def test_request_problem(act_as, uid, expected):
    r = await (await act_as(uid)).post(f"/api/v2/requests/{RA}/problem", json={"template": "no_material"})
    assert r.status_code == expected, r.text


# ── Медиа заявки через прокси ────────────────────────────────────────────


class _Upstream:
    status_code = 200
    headers = {"content-type": "image/jpeg"}

    async def aiter_bytes(self):
        yield b"\xff\xd8bytes"

    async def aclose(self):
        return None


@pytest.fixture
def media_upstream(monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_SERVICE_URL", "http://media.test")
    calls = []

    async def _get(client, url, **kw):
        calls.append(url)
        payload = {"request_number": RA} if url.endswith("/api/v1/media/7") else []
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    async def _stream(client, url, **kw):
        calls.append(url)
        return _Upstream()

    monkeypatch.setattr(media_proxy, "get_with_retries", _get)
    monkeypatch.setattr(media_proxy, "stream_with_retries", _stream)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,expected", [(B, 403), (E2, 403), (A, 200)])
async def test_media_list(act_as, media_upstream, uid, expected):
    r = await (await act_as(uid)).get(f"/api/v2/media/request/{RA}")
    assert r.status_code == expected, r.text
    # отказ — до похода в media-service
    assert bool(media_upstream) is (expected == 200)


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,expected", [(B, 403), (E2, 403), (A, 200), (E1, 200)])
async def test_media_file(act_as, media_upstream, uid, expected):
    r = await (await act_as(uid)).get("/api/v2/media/7/file")
    assert r.status_code == expected, r.text
    assert any(u.endswith("/7/file") for u in media_upstream) is (expected == 200)


@pytest.mark.asyncio
async def test_media_upload_to_foreign_request_is_403(act_as, monkeypatch):
    forward = AsyncMock()
    monkeypatch.setattr(media_proxy, "_forward_upload", forward)
    monkeypatch.setattr(settings, "MEDIA_SERVICE_URL", "http://media.test")
    r = await (await act_as(B)).post(
        "/api/v2/media/upload", data={"request_number": RA},
        files={"file": ("a.jpg", b"\xff\xd8\xff\xe0" + b"0" * 64, "image/jpeg")})
    assert r.status_code == 403, r.text
    forward.assert_not_awaited()


# ── Смены исполнителя ────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,expected", [(E2, 403), (E1, 200)])
async def test_executor_shift_end(act_as, world, monkeypatch, uid, expected):
    import uk_management_bot.api.shifts.executor_router as ex_router
    monkeypatch.setattr(ex_router, "_notify_shift", AsyncMock())
    monkeypatch.setattr(ex_router, "_remind_open_tasks", AsyncMock())
    r = await (await act_as(uid)).post(f"/api/v2/executor/shifts/{world['shift']}/end")
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,expected", [(E2, 403), (E1, 200)])
async def test_executor_transfer_respond(act_as, world, monkeypatch, uid, expected):
    import uk_management_bot.api.shifts.executor_router as ex_router
    monkeypatch.setattr(ex_router, "publish_shift_event", AsyncMock(), raising=False)
    monkeypatch.setattr(ex_router, "_notify_many", AsyncMock(), raising=False)
    r = await (await act_as(uid)).post(
        f"/api/v2/executor/shifts/transfers/{world['transfer']}/respond", json={"action": "reject"})
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_foreign_transfer_status_is_not_disclosed(act_as, world, db_session_factory):
    """Чужой исполнитель не различает статусы чужой передачи: на любой — «не ваша»."""
    async with db_session_factory() as s:
        (await s.get(ShiftTransfer, world["transfer"])).status = "completed"
        await s.commit()
    r = await (await act_as(E2)).post(
        f"/api/v2/executor/shifts/transfers/{world['transfer']}/respond", json={"action": "accept"})
    assert (r.status_code, r.json()["detail"]) == (403, "not_your_transfer"), r.text


# ── Лифты дома при подаче заявки ─────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("building,expected", [("b2", 403), ("b1", 200)])
async def test_elevators_for_building(act_as, world, monkeypatch, building, expected):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)
    r = await (await act_as(A)).get(f"/api/v2/elevators/for-building/{world[building]}")
    assert r.status_code == expected, r.text


# ── Класс d: тикет регистрации ───────────────────────────────────────────


def _reg_get(client, token: str | None, path: str):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get(f"/api/v2/registration{path}", headers=headers)


@pytest.mark.asyncio
async def test_registration_cascade_requires_ticket(client, world):
    path = f"/buildings/{world['b1']}/apartments"
    assert (await _reg_get(client, None, path)).status_code == 401
    # access-токен не тикет регистрации (нет purpose=register)
    assert (await _reg_get(client, create_access_token(A, ["applicant"]), path)).status_code == 401
    expired = encode_jwt({"sub": "70101", "purpose": "register", "iss": "uk-management",
                          "exp": datetime.now(timezone.utc) - timedelta(seconds=1)})
    assert (await _reg_get(client, expired, path)).status_code == 401
    assert (await _reg_get(client, create_registration_ticket(70101), path)).status_code == 200


@pytest.mark.asyncio
async def test_registration_ticket_is_not_an_access_token(client, world):
    """Тикет (sub=telegram_id) не открывает API под видом users.id."""
    app.dependency_overrides.pop(get_current_user, None)
    ticket = create_registration_ticket(A)  # sub совпадает с users.id жителя A
    r = await client.get(f"/api/v2/requests/{RA}", headers={"Authorization": f"Bearer {ticket}"})
    assert r.status_code == 401, r.text


# ── Ратчет реестра ───────────────────────────────────────────────────────

#: Маршрут → где закреплена пара «чужой → отказ / свой → успех». Ключ —
#: (метод, путь). Значение — тест этого файла или профильный тест.
IDOR_COVERAGE: dict[tuple[str, str], str] = {
    ("GET", "/api/v2/requests/{request_number}"): "test_request_card",
    ("PATCH", "/api/v2/requests/{request_number}"):
        "test_request_edit_executor_fields + test_request_edit_foreign_applicant_is_403 + "
        "test_request_cancel_workflow + test_request_edit_role_granted_update_cannot_edit_foreign",
    ("GET", "/api/v2/requests/{request_number}/comments"): "test_request_comments_read",
    ("POST", "/api/v2/requests/{request_number}/comments"): "test_request_comments_write",
    ("POST", "/api/v2/requests/{request_number}/problem"): "test_request_problem",
    ("POST", "/api/v2/requests/{request_number}/claim"):
        "tests/api/test_request_claim.py::test_taken_request_is_403_for_foreign_specialization",
    ("POST", "/api/v2/requests/{request_number}/complete"):
        "tests/api/test_request_complete_with_photo.py::test_not_my_request_is_403_without_upload",
    ("POST", "/api/v2/requests/{request_number}/before-photo"):
        "tests/api/test_request_before_photo.py::test_not_my_request_is_403",
    ("GET", "/api/v2/media/request/{request_number}"): "test_media_list",
    ("GET", "/api/v2/media/{media_id}/file"): "test_media_file",
    ("POST", "/api/v2/executor/shifts/{shift_id}/end"): "test_executor_shift_end",
    ("POST", "/api/v2/executor/shifts/transfers/{transfer_id}/respond"):
        "test_executor_transfer_respond + test_foreign_transfer_status_is_not_disclosed",
    ("GET", "/api/v2/elevators/for-building/{building_id}"): "test_elevators_for_building",
    ("GET", "/api/v2/registration/yards/{yard_id}/buildings"): "test_registration_cascade_requires_ticket",
    ("GET", "/api/v2/registration/buildings/{building_id}/apartments"):
        "test_registration_cascade_requires_ticket",
    ("GET", "/api/v2/public/work-reports/{report_id}"):
        "tests/api/test_work_reports_public.py::test_feed_only_published_visible",
    ("GET", "/api/v2/public/work-reports/{report_id}/media/{media_id}"):
        "tests/api/test_work_reports_public.py::test_media_404_cross_report_media_id_idor",
}

#: Действия, которые дают только персонал с доступом ко всем объектам раздела
#: (класс a: вертикальной проверки достаточно), и осознанно широкие действия.
STAFF_WIDE_ACTIONS = frozenset({
    "addresses.manage", "residents.manage", "staff.manage", "shifts.manage",
    "work_reports.moderate", "materials.manage", "requests.stats", "elevators.manage",
    "payments.manage", "board.configure", "rbac.manage", "rbac.view", "feedback.manage",
    "group_intake.manage", "requests.manage", "requests.engineering",
    # A10-INT-10 (WONTFIX, решение владельца): исполнитель/инженер видят реестр
    # лифтов и их заявки целиком; инспектор — любой активный дом (обход).
    "elevators.read", "addresses.read",
})


def _actions_of(route) -> set[str]:
    out: set[str] = set()

    def walk(dep):
        for d in dep.dependencies:
            name = getattr(d.call, "__qualname__", "")
            if name.startswith("require_action["):
                out.add(name[len("require_action["):-1])
            walk(d)
    walk(route.dependant)
    return out


def test_every_object_route_outside_staff_scope_is_covered():
    """Новый маршрут с id объекта, открытый не только персоналу, без записи в
    реестре — красный: сначала пара тестов «чужой/свой», потом запись."""
    uncovered = []
    for route in app.routes:
        if not isinstance(route, (APIRoute, APIWebSocketRoute)) or "{" not in route.path:
            continue
        if _actions_of(route) & STAFF_WIDE_ACTIONS:
            continue
        for method in sorted(getattr(route, "methods", None) or {"WS"}):
            if (method, route.path) not in IDOR_COVERAGE:
                uncovered.append((method, route.path))
    assert uncovered == [], uncovered


def test_registry_has_no_stale_entries():
    live = {(m, r.path) for r in app.routes if isinstance(r, APIRoute) for m in r.methods}
    assert set(IDOR_COVERAGE) <= live, set(IDOR_COVERAGE) - live


def test_registry_points_to_existing_tests():
    from pathlib import Path

    here = inspect.getsource(inspect.getmodule(test_registry_has_no_stale_entries))
    root = Path(__file__).resolve().parents[2]
    for ref in IDOR_COVERAGE.values():
        for part in ref.split(" + "):
            if "::" in part:
                path, name = part.split("::")
                assert f"def {name}(" in (root / path).read_text(encoding="utf-8"), part
            else:
                assert f"def {part}(" in here, part
