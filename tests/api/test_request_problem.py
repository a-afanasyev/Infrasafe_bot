"""POST /api/v2/requests/{number}/problem — «Проблема» исполнителя.

Решение владельца: шаблон (нет материала / не пустили / жителя нет дома /
нужен мастер) + необязательный текст → комментарий исполнителя в заявку,
статус не меняется, менеджерам — уведомление (best-effort, после ответа).
"""
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select

import uk_management_bot.api.requests.executor_actions as actions
import uk_management_bot.services.executor_problem as problem
import uk_management_bot.utils.constants as C
from uk_management_bot.api import telegram_send
from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_comment import RequestComment
from uk_management_bot.database.models.user import User

NUMBER = "260925-002"
URL = f"/api/v2/requests/{NUMBER}/problem"


def _user(uid: int, roles: str, *, lang: str = "ru", tg: int | None = None) -> User:
    return User(id=uid, telegram_id=tg if tg is not None else 80000 + uid,
                first_name=f"U{uid}", last_name="Тестов", roles=roles,
                active_role=roles.split('"')[1], status="approved", language=lang)


@pytest_asyncio.fixture
async def world(db_session, manager_user, monkeypatch):
    db_session.add_all([
        _user(51, '["executor"]'), _user(52, '["executor"]'),
        Request(request_number=NUMBER, user_id=manager_user.id, category="plumbing",
                description="течёт", status=C.REQUEST_STATUS_IN_PROGRESS,
                urgency="low", executor_id=51, assignment_type="individual",
                address="ул. <Тест>, 1"),
    ])
    await db_session.commit()
    notify = AsyncMock(return_value=1)
    monkeypatch.setattr(actions, "notify_managers_problem_detached", notify)
    return notify


@pytest.fixture
def act_as(client, db_session_factory, world):
    async def _switch(uid: int):
        async with db_session_factory() as s:
            user = await s.get(User, uid)
        app.dependency_overrides[get_current_user] = lambda: user
        return client
    return _switch


async def _comments(factory):
    async with factory() as s:
        return (await s.execute(select(RequestComment).where(
            RequestComment.request_number == NUMBER))).scalars().all()


async def _status(factory):
    async with factory() as s:
        return (await s.get(Request, NUMBER)).status


@pytest.mark.asyncio
async def test_problem_adds_executor_comment_and_notifies(act_as, world, db_session_factory):
    client = await act_as(51)
    r = await client.post(URL, json={"template": "not_let_in", "text": "звонил дважды"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["comment_type"] == "problem"
    assert body["user_id"] == 51
    assert body["is_internal"] is False
    assert body["comment_text"] == "Не пустили\nзвонил дважды"

    rows = await _comments(db_session_factory)
    assert len(rows) == 1 and rows[0].comment_type == C.COMMENT_TYPE_PROBLEM
    assert await _status(db_session_factory) == C.REQUEST_STATUS_IN_PROGRESS
    world.assert_awaited_once_with(NUMBER, 51, "not_let_in", "звонил дважды")


@pytest.mark.asyncio
async def test_problem_text_is_optional(act_as, world, db_session_factory):
    client = await act_as(51)
    r = await client.post(URL, json={"template": "no_material"})
    assert r.status_code == 201, r.text
    assert r.json()["comment_text"] == "Нет материала"
    world.assert_awaited_once_with(NUMBER, 51, "no_material", None)


@pytest.mark.asyncio
async def test_problem_on_foreign_request_is_403(act_as, world, db_session_factory):
    client = await act_as(52)
    r = await client.post(URL, json={"template": "need_master"})
    assert r.status_code == 403, r.text
    assert await _comments(db_session_factory) == []
    world.assert_not_awaited()


@pytest.mark.asyncio
async def test_problem_requires_executor_role(act_as, manager_user, world):
    client = await act_as(manager_user.id)
    assert (await client.post(URL, json={"template": "need_master"})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"template": "broken_pipe"},
    {"text": "без шаблона"},
    {"template": "need_master", "text": "x" * 2001},
    {"template": "need_master", "extra": 1},
])
async def test_problem_payload_validation_is_422(act_as, world, payload):
    client = await act_as(51)
    assert (await client.post(URL, json=payload)).status_code == 422
    world.assert_not_awaited()


@pytest.mark.asyncio
async def test_problem_on_finalized_request_is_409(act_as, world, db_session_factory):
    async with db_session_factory() as s:
        (await s.get(Request, NUMBER)).status = C.REQUEST_STATUS_APPROVED
        await s.commit()
    client = await act_as(51)
    r = await client.post(URL, json={"template": "resident_absent"})
    assert r.status_code == 409, r.text
    assert await _comments(db_session_factory) == []


@pytest.mark.asyncio
async def test_problem_unknown_request_is_404(act_as, world):
    client = await act_as(51)
    r = await client.post("/api/v2/requests/260925-998/problem", json={"template": "need_master"})
    assert r.status_code == 404


# ── уведомление менеджерам ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_managers_in_their_language_escaped(db_session, db_session_factory,
                                                         manager_user, monkeypatch):
    db_session.add_all([
        _user(51, '["executor"]'),
        _user(61, '["manager"]', lang="uz"),
        _user(62, '["manager"]', tg=0),  # без Telegram — пропускается
        Request(request_number=NUMBER, user_id=manager_user.id, category="plumbing",
                description="течёт", status=C.REQUEST_STATUS_IN_PROGRESS,
                urgency="low", executor_id=51, address="ул. <Тест>, 1"),
    ])
    await db_session.commit()
    monkeypatch.setattr(problem, "AsyncSessionLocal", db_session_factory)
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append((chat_id, text, kw))
        return telegram_send.TelegramResult(status=telegram_send.STATUS_OK)

    monkeypatch.setattr(telegram_send, "send_message", fake_send)

    delivered = await problem.notify_managers_problem_detached(
        NUMBER, 51, "not_let_in", "<b>дверь</b>")

    by_chat = {chat: text for chat, text, _ in sent}
    assert manager_user.telegram_id in by_chat and 80061 in by_chat
    assert 80062 not in by_chat and 0 not in by_chat
    assert delivered == len(sent) == 2
    ru, uz = by_chat[manager_user.telegram_id], by_chat[80061]
    assert "Не пустили" in ru and NUMBER in ru
    assert "Ichkariga kiritishmadi" in uz
    assert "&lt;b&gt;дверь&lt;/b&gt;" in ru and "<b>дверь</b>" not in ru
    assert "&lt;Тест&gt;" in ru
    assert all(kw.get("parse_mode") == "HTML" for _, _, kw in sent)


@pytest.mark.asyncio
async def test_notify_never_raises_and_hides_raw_exception(db_session, db_session_factory,
                                                           manager_user, monkeypatch, caplog):
    db_session.add_all([
        _user(51, '["executor"]'),
        Request(request_number=NUMBER, user_id=manager_user.id, category="plumbing",
                description="течёт", status=C.REQUEST_STATUS_IN_PROGRESS,
                urgency="low", executor_id=51),
    ])
    await db_session.commit()
    monkeypatch.setattr(problem, "AsyncSessionLocal", db_session_factory)

    async def boom(*_a, **_k):
        raise RuntimeError("https://api.telegram.org/bot123:SECRET/sendMessage")

    monkeypatch.setattr(telegram_send, "send_message", boom)
    assert await problem.notify_managers_problem_detached(NUMBER, 51, "need_master", None) == 0
    assert "SECRET" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_schema_templates_match_service_canon():
    """Список шаблонов в схеме запроса и в сервисе — один и тот же."""
    from typing import get_args

    from uk_management_bot.api.requests.schemas import ProblemBody

    assert set(get_args(ProblemBody.model_fields["template"].annotation)) == set(
        problem.PROBLEM_TEMPLATES)
