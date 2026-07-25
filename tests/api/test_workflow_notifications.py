"""Адресные уведомления по `notify`-интентам движка.

Прод-жалоба 2026-07-25: житель не получал уведомление об уточнении. Причина
оказалась шире жалобы — интент `notify` выпускался движком на каждый переход, но
в API-роутере разбирался только `realtime`, а `notify` молча выбрасывался.
Значит НИ ОДИН переход, сделанный из дашборда, никого не уведомлял; бот слал
сообщение сам, внутри своего хендлера, минуя интент.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.services import workflow_notifications as wn
from uk_management_bot.utils.request_workflow import Action, EventIntent


def _intent(action: Action, kind: str = "notify") -> EventIntent:
    return EventIntent(kind, {"action": action.value, "request_number": "260725-001"})


async def _seed(db, *, with_executor=True) -> Request:
    applicant = User(telegram_id=900001, roles='["applicant"]', active_role="applicant",
                     status="approved", language="ru", first_name="Житель")
    db.add(applicant)
    executor = None
    if with_executor:
        executor = User(telegram_id=900002, roles='["executor"]', active_role="executor",
                        status="approved", language="ru", first_name="Исполнитель")
        db.add(executor)
    await db.flush()
    req = Request(
        request_number="260725-001", user_id=applicant.id, category="elevator",
        status="Уточнение", description="демо", urgency="low", is_returned=False,
        manager_confirmed=False, address="Yangi Olmazor, 14V, кв. 54",
        executor_id=executor.id if executor else None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(req)
    await db.commit()
    return req


@pytest.fixture
def sent(monkeypatch):
    """Перехватываем фактическую отправку в Telegram."""
    calls: list[tuple[int, str]] = []

    async def fake_send(bot, telegram_id, text):
        calls.append((telegram_id, text))
        return True

    monkeypatch.setattr(
        "uk_management_bot.services.notification_service.send_to_user", fake_send)
    monkeypatch.setattr(
        "uk_management_bot.services.notification_service._get_shared_bot",
        lambda: MagicMock())
    return calls


@pytest.mark.asyncio
async def test_clarify_request_notifies_applicant(db_session, sent):
    """Исходная жалоба: уточнение обязано дойти до жителя."""
    await _seed(db_session)

    delivered = await wn.dispatch_notify_intents(
        db_session, "260725-001", [_intent(Action.CLARIFY_REQUEST)])

    assert delivered == 1
    telegram_id, text = sent[0]
    assert telegram_id == 900001              # житель, не исполнитель
    assert "260725-001" in text
    assert "уточня" in text.lower()


@pytest.mark.asyncio
async def test_assign_notifies_both_sides(db_session, sent):
    await _seed(db_session)

    await wn.dispatch_notify_intents(
        db_session, "260725-001", [_intent(Action.MANAGER_ASSIGN)])

    assert sorted(t for t, _ in sent) == [900001, 900002]


@pytest.mark.asyncio
async def test_service_actions_stay_silent(db_session, sent):
    """Уведомление на каждый переход — спам, после которого их не читают.
    Служебные действия в матрице отсутствуют и молчат."""
    await _seed(db_session)

    await wn.dispatch_notify_intents(db_session, "260725-001", [
        _intent(Action.EXECUTOR_CLAIM),
        _intent(Action.CLARIFY_RESOLVED),
        _intent(Action.APPLICANT_ACCEPT),
    ])

    assert sent == []


@pytest.mark.asyncio
async def test_non_notify_intents_ignored(db_session, sent):
    await _seed(db_session)

    await wn.dispatch_notify_intents(db_session, "260725-001", [
        _intent(Action.CLARIFY_REQUEST, kind="realtime"),
        _intent(Action.CLARIFY_REQUEST, kind="audit"),
    ])

    assert sent == []


@pytest.mark.asyncio
async def test_executor_recipient_skipped_when_unassigned(db_session, sent):
    """Назначение адресовано двоим, но исполнителя может не быть (назначение на
    группу) — жителю сообщение всё равно уходит."""
    await _seed(db_session, with_executor=False)

    await wn.dispatch_notify_intents(
        db_session, "260725-001", [_intent(Action.MANAGER_ASSIGN)])

    assert [t for t, _ in sent] == [900001]


@pytest.mark.asyncio
async def test_send_failure_does_not_raise(db_session, monkeypatch):
    """Переход уже закоммичен: сбой рассылки не имеет права уронить ответ API."""
    await _seed(db_session)

    async def boom(bot, telegram_id, text):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(
        "uk_management_bot.services.notification_service.send_to_user", boom)
    monkeypatch.setattr(
        "uk_management_bot.services.notification_service._get_shared_bot",
        lambda: MagicMock())

    delivered = await wn.dispatch_notify_intents(
        db_session, "260725-001", [_intent(Action.CLARIFY_REQUEST)])

    assert delivered == 0


@pytest.mark.asyncio
async def test_missing_request_is_silent(db_session, sent):
    """Заявку могли удалить между коммитом перехода и рассылкой."""
    delivered = await wn.dispatch_notify_intents(
        db_session, "260725-999", [_intent(Action.CLARIFY_REQUEST)])

    assert delivered == 0
    assert sent == []


@pytest.mark.asyncio
async def test_unknown_action_is_silent(db_session, sent):
    """Незнакомое значение в интенте (старый формат, чужой продьюсер) не должно
    ронять рассылку остальных."""
    await _seed(db_session)
    bogus = EventIntent("notify", {"action": "no_such_action"})

    await wn.dispatch_notify_intents(
        db_session, "260725-001", [bogus, _intent(Action.CLARIFY_REQUEST)])

    assert len(sent) == 1


@pytest.mark.asyncio
async def test_text_uses_recipient_language(db_session, sent):
    """Язык получателя, а не актора: сообщение читает он."""
    req = await _seed(db_session)
    applicant = await db_session.get(User, req.user_id)
    applicant.language = "uz"
    await db_session.commit()

    await wn.dispatch_notify_intents(
        db_session, "260725-001", [_intent(Action.CLARIFY_REQUEST)])

    _, text = sent[0]
    assert "javob" in text.lower()


@pytest.mark.asyncio
async def test_address_with_apartment_is_fine_here(db_session, sent):
    """В отличие от публичной витрины, адресное уведомление идёт ЛИЧНО жителю —
    номер квартиры здесь не утечка, а полезный контекст."""
    await _seed(db_session)

    await wn.dispatch_notify_intents(
        db_session, "260725-001", [_intent(Action.CLARIFY_REQUEST)])

    _, text = sent[0]
    assert "кв. 54" in text
