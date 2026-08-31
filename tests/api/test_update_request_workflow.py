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
    SameExecutor,
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

    def test_returned_keeps_return_reason_name(self):
        """APPLICANT_RETURN ждёт именно `return_reason` — в отличие от ветки
        «В работе», где то же поле переводится в `reason` для
        MANAGER_RETURN_TO_WORK. Ветки для «Возвращена» не было вовсе, из-за чего
        возврат из TWA-приёмки не доходил до движка."""
        assert _build_workflow_payload(
            C.REQUEST_STATUS_RETURNED, {"return_reason": "лифт снова встал"}
        ) == {"return_reason": "лифт снова встал"}

    def test_returned_without_reason_gives_empty_payload(self):
        """Пустой payload → движок сам отвергнет по PAYLOAD_SCHEMAS
        (return_reason обязателен). Маппер молча ничего не подставляет."""
        assert _build_workflow_payload(C.REQUEST_STATUS_RETURNED, {}) == {}

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
async def test_assign_to_duty_assigns_concrete_duty_executor(
    client, db_session, manager_user, applicant_user, monkeypatch
):
    """Дашборд «Назначить дежурному» назначает КОНКРЕТНОГО дежурного.

    Инвариант «В работе ⟺ есть исполнитель» (решение владельца 2026-08-17):
    раньше кнопка ставила MANAGER_ASSIGN {group: spec} и заявка уезжала в
    «В работе» без человека. Спец по-прежнему резолвит сервер по категории
    (CATEGORY_TO_SPECIALIZATION[electricity]=electrician), но дальше идёт подбор
    дежурного — тот же, что у авто-менеджера.
    """
    from uk_management_bot.utils.request_workflow import Action
    await _seed(db_session, owner_id=applicant_user.id, status="Новая")  # category=electricity
    mock = AsyncMock(return_value=_outcome("Новая", "В работе", "В работе"))
    monkeypatch.setattr(req_router, "run_command_async", mock)
    monkeypatch.setattr(
        "uk_management_bot.services.dispatch.pick_duty_executor_id",
        lambda *a, **k: 55,
    )

    r = await client.patch(PATCH_URL.format(number="260101-001"),
                           json={"status": "В работе", "assign_to_duty": True})
    assert r.status_code == 200, r.text
    sent = mock.await_args.args[3]
    assert sent.action == Action.MANAGER_ASSIGN
    assert dict(sent.payload) == {"executor_id": 55}


@pytest.mark.asyncio
async def test_assign_to_duty_excludes_current_executor(
    client, db_session, manager_user, applicant_user, monkeypatch
):
    """Переназначение «дежурному» не смеет резолвить ТЕКУЩЕГО исполнителя.

    Его туда и поставил авто-диспетчер, поэтому без исключения кнопка вернула
    бы того же человека и не сделала бы ничего. Паритет с бот-путём
    (handlers/admin/reassignment._resolve_duty).
    """
    from uk_management_bot.database.models.request import Request as R
    from sqlalchemy import update as sa_update

    await _seed(db_session, owner_id=applicant_user.id, status="В работе")
    await db_session.execute(
        sa_update(R).where(R.request_number == "260101-001").values(executor_id=42))
    await db_session.commit()

    seen = {}

    def _spy(spec, db=None, exclude_user_ids=frozenset(), strict=False):
        seen["exclude"] = exclude_user_ids
        return 55

    monkeypatch.setattr(req_router, "run_command_async",
                        AsyncMock(return_value=_outcome("В работе", "В работе", "В работе")))
    monkeypatch.setattr(
        "uk_management_bot.services.dispatch.pick_duty_executor_id", _spy)

    r = await client.patch(PATCH_URL.format(number="260101-001"),
                           json={"status": "В работе", "assign_to_duty": True})
    assert r.status_code == 200, r.text
    assert seen["exclude"] == frozenset({42}), (
        "текущий исполнитель обязан быть исключён из подбора")


@pytest.mark.asyncio
async def test_assign_to_duty_409_when_no_duty_executor(
    client, db_session, manager_user, applicant_user, monkeypatch
):
    """Дежурного нет — статус не меняется, менеджер получает внятный отказ.

    Инвариант не даёт молча увести заявку в «В работе» ничьей, поэтому здесь
    честный 409, а не «успешно назначено никому».
    """
    await _seed(db_session, owner_id=applicant_user.id, status="Новая")
    mock = AsyncMock(return_value=_outcome("Новая", "В работе", "В работе"))
    monkeypatch.setattr(req_router, "run_command_async", mock)
    monkeypatch.setattr(
        "uk_management_bot.services.dispatch.pick_duty_executor_id",
        lambda *a, **k: None,
    )

    r = await client.patch(PATCH_URL.format(number="260101-001"),
                           json={"status": "В работе", "assign_to_duty": True})
    assert r.status_code == 409, r.text
    mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("exc,code", [
    (NotAuthorized("x"), 403),
    (InvalidTransition("x"), 422),
    (RepeatRejected("x"), 422),
    (PayloadInvalid("x"), 422),
    (RequestNotFound("260101-001"), 404),
    # BUG-180: гонка «тот же исполнитель» — конфликт состояния, не битый запрос.
    (SameExecutor("x"), 409),
])
async def test_workflow_exception_maps_to_http(
    client, db_session, applicant_user, monkeypatch, exc, code
):
    await _seed(db_session, owner_id=applicant_user.id)
    monkeypatch.setattr(req_router, "run_command_async", AsyncMock(side_effect=exc))
    r = await client.patch(PATCH_URL.format(number="260101-001"), json={"status": "Выполнена"})
    assert r.status_code == code, r.text


@pytest.mark.asyncio
async def test_workflow_concurrent_delete_returns_404_not_500(
    client, db_session, applicant_user, _capture, monkeypatch
):
    """APIFE-9: заявку удалили между коммитом команды и повторным SELECT свежей
    карточки → распаковка None давала TypeError/500. Ожидаем чистый 404."""
    from sqlalchemy import delete

    await _seed(db_session, owner_id=applicant_user.id, status="В работе")

    async def _delete_then_outcome(*_a, **_k):
        # эмулируем конкурентное удаление: команда «прошла», но строки уже нет
        await db_session.execute(delete(Request).where(Request.request_number == "260101-001"))
        await db_session.commit()
        return _outcome("В работе", "Выполнена", "Выполнена")

    monkeypatch.setattr(req_router, "run_command_async", AsyncMock(side_effect=_delete_then_outcome))

    r = await client.patch(PATCH_URL.format(number="260101-001"),
                           json={"status": "Выполнена", "completion_report": "готово"})
    assert r.status_code == 404, r.text


# ═══════════════════════ BUG-181: old-notice с API-пути ═══════════════════════


def _reassign_outcome(*, old_executor, new_executor):
    """Outcome переназначения: исполнитель сменился, статус остался «В работе»."""
    def _state(executor):
        return RequestState(
            request_number="260101-001", user_id=2, status="В работе",
            manager_confirmed=False, is_returned=False,
            apartment_id=None, executor_id=executor)
    return CommandOutcome(
        request_number="260101-001", no_op=False,
        old_state=_state(old_executor), new_state=_state(new_executor),
        old_status="В работе", new_status="В работе",
        new_canon_status="В работе", public_status="В работе",
        post_commit_intents=(),
    )


@pytest.mark.asyncio
async def test_reassign_schedules_notice_to_replaced_executor(
    client, db_session, applicant_user, monkeypatch
):
    """Переназначение с дашборда обязано уведомить СНЯТОГО исполнителя.

    Матрица интентов его не покрывает (получатель — человек из old_state,
    которого в заявке уже нет), поэтому роутер планирует отдельную фоновую
    задачу по факту из outcome: оба executor_id есть и они разные."""
    await _seed(db_session, owner_id=applicant_user.id, status="В работе")
    monkeypatch.setattr(req_router, "run_command_async", AsyncMock(
        return_value=_reassign_outcome(old_executor=42, new_executor=55)))
    spy = AsyncMock(return_value=1)
    monkeypatch.setattr(req_router, "notify_reassigned_away_detached", spy)

    r = await client.patch(PATCH_URL.format(number="260101-001"),
                           json={"executor_id": 55})
    assert r.status_code == 200, r.text
    spy.assert_awaited_once_with("260101-001", 42)


@pytest.mark.asyncio
async def test_primary_assign_does_not_schedule_old_notice(
    client, db_session, applicant_user, monkeypatch
):
    """Первичное назначение (old executor = None): снимать было некого."""
    await _seed(db_session, owner_id=applicant_user.id, status="Новая")
    monkeypatch.setattr(req_router, "run_command_async", AsyncMock(
        return_value=_reassign_outcome(old_executor=None, new_executor=55)))
    spy = AsyncMock(return_value=1)
    monkeypatch.setattr(req_router, "notify_reassigned_away_detached", spy)

    r = await client.patch(PATCH_URL.format(number="260101-001"),
                           json={"executor_id": 55})
    assert r.status_code == 200, r.text
    spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_requests_rejects_negative_offset(client):
    """APIFE-10: offset<0 (и limit<1) раньше уходили в Postgres → 500; теперь 422."""
    r = await client.get("/api/v2/requests?offset=-1")
    assert r.status_code == 422
    r = await client.get("/api/v2/requests?limit=0")
    assert r.status_code == 422


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
