"""POST /api/v2/requests/{number}/claim — взятие заявки из группового пула (TWA).

Дефект: TWA-кнопка «В работу» для «Новой» слала PATCH {status: 'В работе'};
status-based вход намеренно не резолвится в EXECUTOR_CLAIM (planner
`_STATUS_RESOLVE_EXCLUDE`) → 422 «no action maps 'Новая' -> 'В работе'».
Бот берёт заявку явной командой EXECUTOR_CLAIM — эндпоинт делает то же.

Здесь run_command_async НЕ мокается: настоящий канон на aiosqlite, чтобы
проверка предиката `_executor_can_claim` и конверсии group→individual была
реальной, а не сравнением вызова мока.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
import uk_management_bot.api.requests.router as req_router
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
import uk_management_bot.utils.constants as C

NUMBER = "260925-001"
CLAIM_URL = f"/api/v2/requests/{NUMBER}/claim"
PATCH_URL = f"/api/v2/requests/{NUMBER}"


def _executor(uid: int, *, spec: str = "plumber") -> User:
    return User(id=uid, telegram_id=70000 + uid, first_name=f"Exec{uid}",
                roles='["executor"]', active_role="executor",
                status="approved", language="ru", specialization=spec)


def _on_shift(uid: int) -> Shift:
    return Shift(user_id=uid, status="active",
                 start_time=datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc))


@pytest_asyncio.fixture
async def pool(db_session, manager_user, monkeypatch):
    """«Новая» заявка с активным group-назначением на plumber + два дежурных
    сантехника на смене (id 41, 42) и один без смены (id 43)."""
    db_session.add_all([
        _executor(41), _executor(42), _executor(43),
        _on_shift(41), _on_shift(42),
        Request(request_number=NUMBER, user_id=manager_user.id,
                category="plumbing", description="течёт кран",
                status=C.REQUEST_STATUS_NEW, urgency="low"),
        RequestAssignment(request_number=NUMBER, assignment_type="group",
                          group_specialization="plumber", executor_id=None,
                          created_by=manager_user.id, status="active"),
    ])
    await db_session.commit()

    async def noop(*_a, **_k):
        return None

    monkeypatch.setattr(req_router, "publish_request_event", noop)
    monkeypatch.setattr(req_router, "dispatch_notify_intents_detached", noop)
    pool_notify = AsyncMock(return_value=0)
    monkeypatch.setattr(req_router, "notify_group_pool_claimed_detached", pool_notify)
    return pool_notify


@pytest.fixture
def act_as(client, db_session_factory, pool, monkeypatch):
    """Переключить текущего пользователя API и направить canonical-writer
    в тестовую БД."""
    monkeypatch.setattr(req_router, "AsyncSessionLocal", db_session_factory)

    async def _switch(uid: int):
        async with db_session_factory() as s:
            user = await s.get(User, uid)
        app.dependency_overrides[get_current_user] = lambda: user
        return client

    return _switch


async def _request_row(factory):
    async with factory() as s:
        return await s.get(Request, NUMBER)


@pytest.mark.asyncio
async def test_status_patch_cannot_claim_from_pool(act_as):
    """Воспроизведение дефекта: старый путь TWA (PATCH статуса) → 422."""
    client = await act_as(41)
    r = await client.patch(PATCH_URL, json={"status": C.REQUEST_STATUS_IN_PROGRESS})
    assert r.status_code == 422, r.text
    assert "no action maps" in r.json()["detail"]


@pytest.mark.asyncio
async def test_claim_takes_request_into_work(act_as, db_session_factory):
    client = await act_as(41)
    r = await client.post(CLAIM_URL)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["request_number"] == NUMBER
    assert body["status"] == C.REQUEST_STATUS_IN_PROGRESS
    assert body["executor_id"] == 41

    req = await _request_row(db_session_factory)
    assert req.status == C.REQUEST_STATUS_IN_PROGRESS
    assert req.executor_id == 41
    assert req.assignment_type == "individual"


@pytest.mark.asyncio
async def test_claim_notifies_group_peers_via_shared_helper(act_as, pool):
    """Паритет с ботом: после взятия — «заявку взял X» остальным дежурным
    группы (общий хелпер services/group_pool_notify)."""
    client = await act_as(41)
    assert (await client.post(CLAIM_URL)).status_code == 200
    pool.assert_awaited_once_with(NUMBER, 41)

    pool.reset_mock()
    client = await act_as(42)
    assert (await client.post(CLAIM_URL)).status_code == 409
    pool.assert_not_awaited()


@pytest.mark.asyncio
async def test_claim_already_taken_by_another_is_409(act_as, db_session_factory):
    client = await act_as(41)
    assert (await client.post(CLAIM_URL)).status_code == 200

    client = await act_as(42)
    r = await client.post(CLAIM_URL)
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "already_claimed"
    # взявший остался прежним
    assert (await _request_row(db_session_factory)).executor_id == 41


@pytest.mark.asyncio
async def test_claim_repeat_by_same_executor_is_idempotent(act_as):
    """Двойной тап взявшего — не ошибка: заявка уже его."""
    client = await act_as(41)
    assert (await client.post(CLAIM_URL)).status_code == 200
    r = await client.post(CLAIM_URL)
    assert r.status_code == 200, r.text
    assert r.json()["executor_id"] == 41


@pytest.mark.asyncio
async def test_claim_without_shift_is_403(act_as, db_session_factory):
    client = await act_as(43)
    r = await client.post(CLAIM_URL)
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "not_eligible"
    req = await _request_row(db_session_factory)
    assert req.status == C.REQUEST_STATUS_NEW and req.executor_id is None


@pytest.mark.asyncio
async def test_taken_request_is_403_for_executor_without_shift(act_as):
    """Сек-ревью: «занята ли заявка» видит только тот, кто сам мог бы её
    взять. Исполнителю без смены — единый 403, не оракул 409."""
    client = await act_as(41)
    assert (await client.post(CLAIM_URL)).status_code == 200

    client = await act_as(43)
    r = await client.post(CLAIM_URL)
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "not_eligible"


@pytest.mark.asyncio
async def test_taken_request_is_403_for_foreign_specialization(act_as, db_session_factory):
    async with db_session_factory() as s:
        s.add_all([_executor(44, spec="electric"), _on_shift(44)])
        await s.commit()
    client = await act_as(41)
    assert (await client.post(CLAIM_URL)).status_code == 200

    client = await act_as(44)
    r = await client.post(CLAIM_URL)
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "not_eligible"


@pytest.mark.asyncio
async def test_claim_requires_executor_role(act_as, manager_user):
    client = await act_as(manager_user.id)
    r = await client.post(CLAIM_URL)
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_claim_unknown_request_is_404(act_as):
    client = await act_as(41)
    r = await client.post("/api/v2/requests/260925-999/claim")
    assert r.status_code == 404, r.text


# ─── Остальные status-переходы исполнителя из карточки TWA (реальный канон) ───

async def _assign_to(factory, status: str, executor_id: int = 41) -> None:
    """Заявка уже взята исполнителем `executor_id` и стоит в `status`."""
    async with factory() as s:
        req = await s.get(Request, NUMBER)
        req.status = status
        req.executor_id = executor_id
        req.assignment_type = "individual"
        await s.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [C.REQUEST_STATUS_PURCHASE,
                                    C.REQUEST_STATUS_CLARIFICATION])
async def test_executor_back_to_work_patch_allowed(act_as, db_session_factory, status):
    """«В работу» из Закуп/Уточнение — EXECUTOR_RESUME: кнопка TWA рабочая."""
    await _assign_to(db_session_factory, status)
    client = await act_as(41)
    r = await client.patch(PATCH_URL, json={"status": C.REQUEST_STATUS_IN_PROGRESS})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == C.REQUEST_STATUS_IN_PROGRESS


@pytest.mark.asyncio
async def test_executor_cannot_move_to_clarification(act_as, db_session_factory):
    """CLARIFY_REQUEST — только менеджер: поэтому в TWA исполнителя кнопки
    «Уточнение» нет (раньше комментарий уходил, а PATCH падал 422)."""
    await _assign_to(db_session_factory, C.REQUEST_STATUS_IN_PROGRESS)
    client = await act_as(41)
    r = await client.patch(PATCH_URL, json={"status": C.REQUEST_STATUS_CLARIFICATION})
    assert r.status_code == 422, r.text
