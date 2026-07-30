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


# ═══════════════════════════════════════════════════════════════════════════
# AUD6 (P1-6 + P2-07): бот исполняет ту же матрицу; подстановки экранируются
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_address_with_html_chars_is_escaped(db_session, sent):
    """A6-P2-07: адрес с `&`/`<` раньше давал Telegram 400 «can't parse
    entities» (боты в parse_mode=HTML) — уведомление молча терялось. Ровно
    жалоба, ради которой модуль писался."""
    applicant = User(telegram_id=900001, roles='["applicant"]', active_role="applicant",
                     status="approved", language="ru", first_name="Житель")
    db_session.add(applicant)
    await db_session.flush()
    db_session.add(Request(
        request_number="260725-001", user_id=applicant.id, category="elevator",
        status="Уточнение", description="демо", urgency="low", is_returned=False,
        manager_confirmed=False, address='дом <5> & корпус "Б"',
        created_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()

    delivered = await wn.dispatch_notify_intents(
        db_session, "260725-001", [_intent(Action.CLARIFY_REQUEST)])

    assert delivered == 1
    _, text = sent[0]
    assert "&lt;5&gt;" in text and "&amp;" in text
    assert "<5>" not in text


@pytest.mark.asyncio
async def test_applicant_return_notifies_executor(db_session, sent):
    """AUD6-P1-6: возврат ЖИТЕЛЕМ из приёмки — исполнитель обязан узнать, что
    работу переделывать (симметрия с MANAGER_RETURN_TO_WORK). До матричной
    записи API/TWA-путь не уведомлял никого."""
    await _seed(db_session)

    delivered = await wn.dispatch_notify_intents(
        db_session, "260725-001", [_intent(Action.APPLICANT_RETURN)])

    assert delivered == 1
    telegram_id, text = sent[0]
    assert telegram_id == 900002              # исполнитель, не житель
    assert "возвращена" in text.lower()


@pytest.mark.asyncio
async def test_clarify_with_text_uses_rich_template_and_escapes(db_session, sent):
    """Вопрос менеджера доезжает до жителя (богатый шаблон), и он экранирован."""
    await _seed(db_session)

    await wn.dispatch_notify_intents(
        db_session, "260725-001", [_intent(Action.CLARIFY_REQUEST)],
        clarification_text="Какой <этаж> и & подъезд?")

    _, text = sent[0]
    assert "Какой &lt;этаж&gt; и &amp; подъезд?" in text
    assert "/reply_260725-001" in text        # команда ответа из богатого шаблона


@pytest.mark.asyncio
async def test_clarify_text_applies_only_to_clarify(db_session, sent):
    """clarification_text не протекает в чужие действия той же пачки интентов."""
    await _seed(db_session)

    await wn.dispatch_notify_intents(
        db_session, "260725-001", [_intent(Action.CANCEL)],
        clarification_text="не должен появиться")

    _, text = sent[0]
    assert "не должен появиться" not in text
    assert "отменена" in text.lower()


# ── Паритет sync-диспетчера с async (бот-путь = API-путь) ───────────────────
import pytest_asyncio  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession as _AS  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from uk_management_bot.database.session import Base  # noqa: E402


@pytest.fixture
def parity_db(tmp_path):
    """Файловая sqlite: её видят и sync-движок (бот), и async-движок (API)."""
    return tmp_path / "notify-parity.sqlite3"


@pytest.fixture
def parity_sync_factory(parity_db):
    engine = create_engine(f"sqlite:///{parity_db}")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest_asyncio.fixture
async def parity_async_factory(parity_db, parity_sync_factory):
    engine = create_async_engine(f"sqlite+aiosqlite:///{parity_db}")
    yield async_sessionmaker(engine, class_=_AS, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_sync_and_async_dispatchers_are_identical(
    parity_sync_factory, parity_async_factory, sent
):
    """Суть AUD6-P1-6: один переход из бота и из дашборда обязан дать ОДНИХ
    получателей и ОДИН текст. Обе реализации гоняются по одной БД и одной
    пачке интентов; сравниваются фактические отправки."""
    with parity_sync_factory() as db:
        applicant = User(telegram_id=900001, roles='["applicant"]',
                         active_role="applicant", status="approved",
                         language="ru", first_name="Житель")
        executor = User(telegram_id=900002, roles='["executor"]',
                        active_role="executor", status="approved",
                        language="uz", first_name="Исполнитель")
        db.add_all([applicant, executor])
        db.flush()
        db.add(Request(
            request_number="260725-001", user_id=applicant.id, category="elevator",
            status="В работе", description="демо", urgency="low",
            is_returned=False, manager_confirmed=False,
            address="Yangi Olmazor, 14V & <кв. 54>", executor_id=executor.id,
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()

    intents = [_intent(Action.MANAGER_ASSIGN), _intent(Action.MANAGER_RETURN_TO_WORK)]

    async with parity_async_factory() as adb:
        delivered_async = await wn.dispatch_notify_intents(adb, "260725-001", intents)
    async_calls = sorted(sent)
    sent.clear()

    with parity_sync_factory() as sdb:
        delivered_sync = await wn.dispatch_notify_intents_sync(
            sdb, "260725-001", intents)
    sync_calls = sorted(sent)

    assert delivered_async == delivered_sync == 4  # 2 действия × (житель+исполнитель)
    assert async_calls == sync_calls, "бот и API разослали разное — SSOT сломан"


@pytest.mark.asyncio
async def test_clarify_rich_escapes_legacy_category_fallback(db_session, sent):
    """Security-review PR #305 (borderline → закрыто): подпись категории обычно
    словарная, но fallback get_category_display для НЕИЗВЕСТНОГО ключа отдаёт
    сырое значение из БД — у legacy-заявки категория с '<'/'&' роняла бы
    отправку Telegram-400 и уведомление молча терялось."""
    applicant = User(telegram_id=900001, roles='["applicant"]', active_role="applicant",
                     status="approved", language="ru", first_name="Житель")
    db_session.add(applicant)
    await db_session.flush()
    db_session.add(Request(
        request_number="260725-001", user_id=applicant.id,
        category="<Прочее & разное>",  # legacy-значение вне канон-словаря
        status="Уточнение", description="демо", urgency="low", is_returned=False,
        manager_confirmed=False, address="Yangi Olmazor, 14V",
        created_at=datetime.now(timezone.utc),
    ))
    await db_session.commit()

    delivered = await wn.dispatch_notify_intents(
        db_session, "260725-001", [_intent(Action.CLARIFY_REQUEST)],
        clarification_text="какой подъезд?")

    assert delivered == 1
    _, text = sent[0]
    assert "&lt;Прочее &amp; разное&gt;" in text
    assert "<Прочее" not in text


@pytest.mark.asyncio
async def test_detached_dispatch_opens_own_session(
    db_session, db_session_factory, sent, monkeypatch
):
    """AUD6-P2-02: BackgroundTasks-вариант работает на СВОЕЙ короткой сессии —
    request-scoped к моменту исполнения фоновой задачи уже закрыта."""
    await _seed(db_session)
    monkeypatch.setattr(
        "uk_management_bot.database.session.AsyncSessionLocal", db_session_factory)

    delivered = await wn.dispatch_notify_intents_detached(
        "260725-001", [_intent(Action.CLARIFY_REQUEST)])

    assert delivered == 1
    telegram_id, _ = sent[0]
    assert telegram_id == 900001  # житель
