"""«Готово» исполнителя в рабочей группе → личка основным ботом (Фаза 4).

Хендлер группового приёма зовётся напрямую (AUD3-37: БД через ``_db`` на
sqlite); LLM, Redis-хелперы и send-only основной бот — моки. Проверяется:
исполнитель + тег + «готово» — тишина в группе, LLM не зовётся, в личку
список заявок (web_app «Готово» + «Все»); фото — байтами с callback-кнопками;
житель / не-исполнитель / нет тега / нет слова — обычный путь.
Только «В работе»: «Возвращена» разбирает менеджер (решение владельца).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import uk_management_bot.handlers.group_intake as gi
import uk_management_bot.handlers.group_intake_done as gi_done
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models import Apartment, Building, MonitoredGroup, Yard
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.group_intake.classifier import (
    ClassificationResult,
    Outcome,
)
from uk_management_bot.utils import twa_links

CHAT_ID = -100700
EXEC_TG = 501
FRONTEND = "https://example.test"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setattr(settings, "GROUP_INTAKE_ENABLED", True)
    monkeypatch.setattr(settings, "BOT_USERNAME", "test_bot")
    monkeypatch.setattr(twa_links.settings, "FRONTEND_URL", FRONTEND)
    sender = SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock())
    mocks = SimpleNamespace(
        mark_seen=AsyncMock(return_value=True),
        llm_allowed=AsyncMock(return_value=True),
        invite_allowed=AsyncMock(return_value=True),
        store_candidate=AsyncMock(return_value=True),
        classify=AsyncMock(return_value=ClassificationResult(
            outcome=Outcome.NOT_REQUEST, category=None, urgency=None,
            confidence=0.1, location_scope=None, address_hint=None,
        )),
        sender=sender,
    )
    monkeypatch.setattr(gi.pending, "mark_seen", mocks.mark_seen)
    monkeypatch.setattr(gi.pending, "llm_allowed", mocks.llm_allowed)
    monkeypatch.setattr(gi.pending, "invite_allowed", mocks.invite_allowed)
    monkeypatch.setattr(gi.pending, "store_candidate", mocks.store_candidate)
    monkeypatch.setattr(gi, "classify_message", mocks.classify)
    monkeypatch.setattr(gi_done, "_main_bot", lambda: sender)
    return mocks


def seed(db, *, kind="staff", roles='["executor"]', status="approved", tasks=(
        ("260925-001", "В работе"), ("260925-002", "Возвращена"), ("260925-003", "Выполнена"))):
    db.add(MonitoredGroup(chat_id=CHAT_ID, title="Бригада", kind=kind,
                          is_active=True, require_tag=True))
    user = User(telegram_id=EXEC_TG, roles=roles, active_role="executor",
                status=status, language="ru")
    applicant = User(telegram_id=9001, roles='["applicant"]', status="approved")
    db.add_all([user, applicant])
    yard = Yard(name="Двор", is_active=True)
    building = Building(address="Yangi <Olmazor>, 14V", yard=yard, is_active=True)
    apartment = Apartment(building=building, apartment_number="12", is_active=True)
    db.add_all([yard, building, apartment])
    db.flush()
    for number, status_ in tasks:
        db.add(Request(request_number=number, user_id=applicant.id, executor_id=user.id,
                       category="other", description="d", status=status_,
                       building_id=building.id, apartment_id=apartment.id))
    db.commit()
    return user


def make_message(text, *, photo=None, from_id=EXEC_TG):
    return SimpleNamespace(
        chat=SimpleNamespace(id=CHAT_ID, type="supergroup"),
        from_user=SimpleNamespace(id=from_id, is_bot=False, language_code="ru"),
        via_bot=None, text=None if photo else text, caption=text if photo else None,
        photo=photo, video=None, video_note=None, message_id=42,
        reply=AsyncMock(),
    )


def _group_bot(photo_bytes=b"\xff\xd8\xff\xe0jpeg"):
    async def download_file(path, buffer):
        buffer.write(photo_bytes)

    return SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="photos/x.jpg")),
        download_file=AsyncMock(side_effect=download_file),
    )


async def run(message, db, bot=None):
    await gi.group_message_entry(message, bot=bot or SimpleNamespace(), _db=db)


def _buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


async def test_executor_done_text_goes_to_dm_silently(env, db):
    seed(db)
    message = make_message("#ариза сделал, 14V")
    await run(message, db)

    env.classify.assert_not_awaited()
    message.reply.assert_not_awaited()
    env.sender.send_message.assert_awaited_once()
    args, kwargs = env.sender.send_message.call_args
    assert args[0] == EXEC_TG
    text = args[1]
    assert "Какую заявку закрыли?" in text
    # Адрес — HTML-экранирован в тексте.
    assert "&lt;Olmazor&gt;" in text and "<Olmazor>" not in text
    buttons = _buttons(kwargs["reply_markup"])
    urls = [b.web_app.url for b in buttons]
    # Только «В работе»: ни «Возвращена», ни «Выполнена»; последняя — «Все».
    assert urls == [
        f"{FRONTEND}/uk/twa/exec/tasks/260925-001?action=done",
        f"{FRONTEND}/uk/twa/exec",
    ]
    assert "260925-002" not in text
    assert "кв. 12" in buttons[0].text


async def test_latin_done_word_and_other_tag(env, db):
    seed(db)
    await run(make_message("#zayavka tayyor"), db)
    env.classify.assert_not_awaited()
    env.sender.send_message.assert_awaited_once()


@pytest.mark.parametrize("status", ["Выполнена", "Возвращена"])
async def test_no_open_tasks_short_answer(env, db, status):
    seed(db, tasks=(("260925-003", status),))
    await run(make_message("#ариза готово"), db)
    args, kwargs = env.sender.send_message.call_args
    assert args[1] == "У вас нет заявок в работе."
    assert kwargs["reply_markup"] is None


async def test_at_most_five_task_buttons(env, db):
    seed(db, tasks=tuple((f"260925-{i:03d}", "В работе") for i in range(1, 8)))
    await run(make_message("#ариза готово"), db)
    _args, kwargs = env.sender.send_message.call_args
    assert len(_buttons(kwargs["reply_markup"])) == 5 + 1


@pytest.mark.parametrize("text", [
    "сделал всё, подъезд 3 чистый",  # нет тега
    "#ариза течёт кран на 3 этаже в подъезде",  # нет слова «готово»
])
async def test_not_done_report_goes_normal_path(env, db, text):
    seed(db)
    await run(make_message(text), db)
    env.sender.send_message.assert_not_awaited()


async def test_non_executor_staff_goes_normal_path(env, db):
    seed(db, roles='["inspector"]')
    await run(make_message("#ариза готово? когда почините"), db)
    env.sender.send_message.assert_not_awaited()
    env.classify.assert_awaited_once()


async def test_executor_done_question_is_not_report(env, db):
    """«готово?» с вопросом от исполнителя — не отчёт, обычный путь."""
    seed(db)
    await run(make_message("#ариза готово? когда почините лифт"), db)
    env.sender.send_message.assert_not_awaited()
    env.classify.assert_awaited_once()


async def test_executor_done_in_residents_group_goes_normal_path(env, db):
    """Детектор «готово» — только в рабочих (staff) группах: в группе жителей
    исполнитель проходит обычный приём, лички нет."""
    seed(db, kind="residents")
    await run(make_message("#ariza готово"), db)
    env.sender.send_message.assert_not_awaited()
    env.sender.send_photo.assert_not_awaited()
    env.classify.assert_awaited_once()


async def test_resident_done_question_goes_normal_path(env, db):
    seed(db, kind="residents", roles='["applicant"]')
    await run(make_message("#ариза готово? когда почините"), db)
    env.sender.send_message.assert_not_awaited()
    env.classify.assert_awaited_once()


async def test_forbidden_is_logged_quietly(env, db, caplog):
    seed(db)
    env.sender.send_message.side_effect = TelegramForbiddenError(
        method=MagicMock(), message="Forbidden: bot can't initiate conversation")
    await run(make_message("#ариза готово"), db)  # не бросает
    env.classify.assert_not_awaited()


async def test_redelivery_is_deduplicated(env, db):
    seed(db)
    env.mark_seen.return_value = False
    await run(make_message("#ариза готово"), db)
    env.sender.send_message.assert_not_awaited()
    env.classify.assert_not_awaited()


async def test_photo_done_sends_bytes_with_callback_buttons(env, db):
    seed(db)
    photo = [SimpleNamespace(file_id="small"), SimpleNamespace(file_id="group-big")]
    group_bot = _group_bot()
    await run(make_message("#ариза сделал", photo=photo), db, bot=group_bot)

    group_bot.get_file.assert_awaited_once_with("group-big")
    env.sender.send_message.assert_not_awaited()
    env.sender.send_photo.assert_awaited_once()
    args, kwargs = env.sender.send_photo.call_args
    assert args[0] == EXEC_TG
    assert args[1].data == b"\xff\xd8\xff\xe0jpeg"
    assert kwargs["caption"].startswith("📷 Закрыть этим фото?")
    # Только «В работе»: «Возвращена» исполнитель закрыть не может.
    assert [b.callback_data for b in _buttons(kwargs["reply_markup"])] == ["exdone:260925-001"]


async def test_photo_without_in_progress_says_no_tasks(env, db):
    seed(db, tasks=(("260925-002", "Возвращена"),))
    photo = [SimpleNamespace(file_id="group-big")]
    await run(make_message("#ариза сделал", photo=photo), db, bot=_group_bot())
    env.sender.send_photo.assert_not_awaited()
    assert env.sender.send_message.call_args.args[1] == "У вас нет заявок в работе."
