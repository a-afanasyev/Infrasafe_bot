"""PR2b — PATCH /api/v2/requests/{number} workflow-ветка.

Покрывает:
  * транспортный маппер `_build_workflow_payload` (schema-contract: deprecated/сырые
    поля схемы маршрутизируются в payload движка, не теряются и не дропаются);
  * HTTP-контракт workflow-ветки (mock run_command_async): exception→код,
    deprecated manager_confirmed→target Исполнено, combine status+urgency → 422,
    happy-path (realtime + свежая карточка).

run_command_async здесь мокается: его транзакционная логика проверяется в
tests/services/test_workflow_runner.py (sync) + parity-тест (postgres). Здесь —
только адаптер: маппинг полей, маршрутизация, коды ошибок.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
import uk_management_bot.api.requests.router as req_router
from uk_management_bot.api.requests.router import _build_workflow_payload
from uk_management_bot.services.workflow_runner import CommandOutcome, RequestNotFound
from uk_management_bot.utils.request_workflow import (
    RequestState, EventIntent,
    NotAuthorized, InvalidTransition, RepeatRejected, PayloadInvalid,
)
import uk_management_bot.utils.constants as C

PATCH_URL = "/api/v2/requests/{number}"


# ═══════════════════════════ Маппер (pure, schema-contract) ═══════════════════════════

class TestBuildWorkflowPayload:
    def test_purchase_materials_optional(self):
        assert _build_workflow_payload(C.REQUEST_STATUS_PURCHASE, {}) == {}
        assert _build_workflow_payload(
            C.REQUEST_STATUS_PURCHASE, {"requested_materials": "трубы"}
        ) == {"requested_materials": "трубы"}

    def test_clarification_notes_to_question(self):
        # дашборд кладёт текст в `notes` → движок ждёт `question` (+ append в notes-поле)
        out = _build_workflow_payload(C.REQUEST_STATUS_CLARIFICATION, {"notes": "адрес?"})
        assert out == {"question": "адрес?", "notes": "\n\nадрес?"}

    def test_executed_completion_report(self):
        assert _build_workflow_payload(
            C.REQUEST_STATUS_EXECUTED, {"completion_report": "готово"}
        ) == {"completion_report": "готово"}

    def test_completed_confirmation_notes_renamed(self):
        # deprecated manager_confirmation_notes → confirmation_notes; manager_confirmed дропается
        out = _build_workflow_payload(
            C.REQUEST_STATUS_COMPLETED,
            {"manager_confirmed": True, "manager_confirmation_notes": "ок"},
        )
        assert out == {"confirmation_notes": "ок"}

    def test_approved_owner_rating(self):
        assert _build_workflow_payload(
            C.REQUEST_STATUS_APPROVED, {"rating": 5}
        ) == {"rating": 5}

    def test_approved_manager_force_notes(self):
        assert _build_workflow_payload(
            C.REQUEST_STATUS_APPROVED, {"manager_confirmation_notes": "за жителя"}
        ) == {"confirmation_notes": "за жителя"}

    def test_in_progress_assign_executor(self):
        assert _build_workflow_payload(
            C.REQUEST_STATUS_IN_PROGRESS, {"executor_id": 7}
        ) == {"executor_id": 7}

    def test_in_progress_return_reason_renamed(self):
        # return_reason → reason (MANAGER_RETURN_TO_WORK)
        assert _build_workflow_payload(
            C.REQUEST_STATUS_IN_PROGRESS, {"return_reason": "переделать"}
        ) == {"reason": "переделать"}

    def test_cancel_reason_optional(self):
        assert _build_workflow_payload(C.REQUEST_STATUS_CANCELLED, {}) == {}
        assert _build_workflow_payload(
            C.REQUEST_STATUS_CANCELLED, {"return_reason": "дубль"}
        ) == {"reason": "дубль"}


# ═══════════════════════════ HTTP-контракт (mock run_command) ═══════════════════════════

def _outcome(old_status, new_status, public_status, *, intents=()):
    st = RequestState(request_number="260101-001", user_id=2, status=new_status,
                      manager_confirmed=False, is_returned=False,
                      apartment_id=None, executor_id=None)
    old = RequestState(request_number="260101-001", user_id=2, status=old_status,
                       manager_confirmed=False, is_returned=False,
                       apartment_id=None, executor_id=None)
    return CommandOutcome(
        request_number="260101-001", no_op=False, old_state=old, new_state=st,
        old_status=old_status, new_status=new_status,
        new_canon_status=new_status, public_status=public_status,
        post_commit_intents=intents,
    )


async def _seed(db, *, owner_id, status="В работе", number="260101-001"):
    db.add(Request(request_number=number, user_id=owner_id, category="electricity",
                   description="d", status=status, urgency="low"))
    await db.commit()


@pytest.fixture
def _capture(monkeypatch):
    events = []

    async def fake_publish(event_type, data):
        events.append((event_type, data))

    monkeypatch.setattr(req_router, "publish_request_event", fake_publish)
    return events


@pytest.mark.asyncio
async def test_workflow_success_publishes_realtime_and_returns_card(
    client, db_session, manager_user, applicant_user, _capture, monkeypatch
):
    await _seed(db_session, owner_id=applicant_user.id, status="В работе")
    intent = EventIntent("realtime", {"request_number": "260101-001", "status": "Выполнена"})
    mock = AsyncMock(return_value=_outcome("В работе", "Выполнена", "Выполнена", intents=(intent,)))
    monkeypatch.setattr(req_router, "run_command_async", mock)

    r = await client.patch(PATCH_URL.format(number="260101-001"),
                           json={"status": "Выполнена", "completion_report": "готово"})
    assert r.status_code == 200, r.text
    # маппер собрал payload и передал в run_command как LegacyStatusIntent
    assert mock.await_count == 1
    sent_intent = mock.await_args.args[3]
    assert sent_intent.target_status == "Выполнена"
    assert sent_intent.payload == {"completion_report": "готово"}
    # realtime опубликован
    assert any(e[0] == "request.status_changed" for e in _capture)


@pytest.mark.asyncio
async def test_deprecated_manager_confirmed_routes_to_completed(
    client, db_session, applicant_user, monkeypatch
):
    await _seed(db_session, owner_id=applicant_user.id, status="Выполнена")
    mock = AsyncMock(return_value=_outcome("Выполнена", "Исполнено", "Исполнено"))
    monkeypatch.setattr(req_router, "run_command_async", mock)

    # старый клиент: только manager_confirmed:true, без status
    r = await client.patch(PATCH_URL.format(number="260101-001"),
                           json={"manager_confirmed": True, "manager_confirmation_notes": "ок"})
    assert r.status_code == 200, r.text
    sent_intent = mock.await_args.args[3]
    assert sent_intent.target_status == C.REQUEST_STATUS_COMPLETED
    assert sent_intent.payload == {"confirmation_notes": "ок"}


@pytest.mark.asyncio
async def test_executor_id_only_patch_routes_to_manager_assign(
    client, db_session, manager_user, applicant_user, monkeypatch
):
    """FEAT-группы: PATCH {executor_id} без status → канонический MANAGER_ASSIGN
    {executor_id} (а не прямой setattr executor_id в обход workflow)."""
    from uk_management_bot.utils.request_workflow import Action
    await _seed(db_session, owner_id=applicant_user.id, status="Новая")
    mock = AsyncMock(return_value=_outcome("Новая", "В работе", "В работе"))
    monkeypatch.setattr(req_router, "run_command_async", mock)

    r = await client.patch(PATCH_URL.format(number="260101-001"),
                           json={"executor_id": 7})
    assert r.status_code == 200, r.text
    sent = mock.await_args.args[3]
    assert sent.action == Action.MANAGER_ASSIGN
    assert dict(sent.payload) == {"executor_id": 7}


@pytest.mark.asyncio
async def test_assign_to_duty_routes_to_manager_assign_group(
    client, db_session, manager_user, applicant_user, monkeypatch
):
    """FEAT-группы (followup #2): дашборд «Назначить дежурному» (status=В работе +
    assign_to_duty) → MANAGER_ASSIGN {group: spec}, спец резолвится сервером по
    категории заявки (CATEGORY_TO_SPECIALIZATION[electricity]=electrician)."""
    from uk_management_bot.utils.request_workflow import Action
    await _seed(db_session, owner_id=applicant_user.id, status="Новая")  # category=electricity
    mock = AsyncMock(return_value=_outcome("Новая", "В работе", "В работе"))
    monkeypatch.setattr(req_router, "run_command_async", mock)

    r = await client.patch(PATCH_URL.format(number="260101-001"),
                           json={"status": "В работе", "assign_to_duty": True})
    assert r.status_code == 200, r.text
    sent = mock.await_args.args[3]
    assert sent.action == Action.MANAGER_ASSIGN
    assert dict(sent.payload) == {"group": "electrician"}


@pytest.mark.asyncio
@pytest.mark.parametrize("exc,code", [
    (NotAuthorized("x"), 403),
    (InvalidTransition("x"), 422),
    (RepeatRejected("x"), 422),
    (PayloadInvalid("x"), 422),
    (RequestNotFound("260101-001"), 404),
])
async def test_workflow_exception_maps_to_http(
    client, db_session, applicant_user, monkeypatch, exc, code
):
    await _seed(db_session, owner_id=applicant_user.id)
    monkeypatch.setattr(req_router, "run_command_async", AsyncMock(side_effect=exc))
    r = await client.patch(PATCH_URL.format(number="260101-001"), json={"status": "Выполнена"})
    assert r.status_code == code, r.text


@pytest.mark.asyncio
async def test_combine_status_and_urgency_rejected(client, db_session, applicant_user, monkeypatch):
    # combine не должен даже доходить до run_command
    mock = AsyncMock()
    monkeypatch.setattr(req_router, "run_command_async", mock)
    await _seed(db_session, owner_id=applicant_user.id)
    r = await client.patch(PATCH_URL.format(number="260101-001"),
                           json={"status": "Выполнена", "urgency": "high"})
    assert r.status_code == 422
    assert mock.await_count == 0


@pytest_asyncio.fixture
async def applicant_user(db_session):
    u = User(telegram_id=777002, username="appl", first_name="A", last_name="B",
             roles='["applicant"]', status="approved")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u
