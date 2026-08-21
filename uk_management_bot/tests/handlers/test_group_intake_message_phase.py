"""Юнит-матрица message-фазы Group Intake (handlers/group_intake.py).

Хендлер зовётся напрямую (канон AUD3-37: БД через ``_db``-seam на sqlite),
Redis-хелперы и LLM-классификатор подменяются AsyncMock'ами. Порядок guard'ов
проверяется через «что НЕ было вызвано»: отсев раньше по цепочке обязан не
доводить ни до БД, ни до LLM.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import uk_management_bot.handlers.group_intake as gi
from uk_management_bot.config.settings import settings
from uk_management_bot.database.session import Base
from uk_management_bot.database.models import (
    Apartment,
    Building,
    MonitoredGroup,
    UserApartment,
    Yard,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.services.group_intake.classifier import (
    ClassificationResult,
    Outcome,
)

REQUEST_TEXT = "В подъезде не горит свет уже второй день, почините пожалуйста"


# ───────────────────────── фикстуры ─────────────────────────


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
    """Флаг включён + все внешние зависимости замоканы. Возвращает namespace
    с моками для ассертов."""
    monkeypatch.setattr(settings, "GROUP_INTAKE_ENABLED", True)
    monkeypatch.setattr(settings, "BOT_USERNAME", "test_bot")
    mocks = SimpleNamespace(
        mark_seen=AsyncMock(return_value=True),
        llm_allowed=AsyncMock(return_value=True),
        invite_allowed=AsyncMock(return_value=True),
        store_candidate=AsyncMock(return_value=True),
        classify=AsyncMock(
            return_value=ClassificationResult(
                outcome=Outcome.REQUEST,
                category="electricity",
                urgency="medium",
                confidence=0.9,
                location_scope="building",
                address_hint=None,
            )
        ),
    )
    monkeypatch.setattr(gi.pending, "mark_seen", mocks.mark_seen)
    monkeypatch.setattr(gi.pending, "llm_allowed", mocks.llm_allowed)
    monkeypatch.setattr(gi.pending, "invite_allowed", mocks.invite_allowed)
    monkeypatch.setattr(gi.pending, "store_candidate", mocks.store_candidate)
    monkeypatch.setattr(gi, "classify_message", mocks.classify)
    return mocks


def make_message(
    text=REQUEST_TEXT,
    *,
    chat_id=-100500,
    from_id=111,
    is_bot=False,
    via_bot=None,
    photo=None,
    caption=None,
    message_id=42,
):
    sent = SimpleNamespace(message_id=777, edit_reply_markup=AsyncMock())
    reply = AsyncMock(return_value=sent)
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id, type="supergroup"),
        from_user=SimpleNamespace(id=from_id, is_bot=is_bot, language_code="ru"),
        via_bot=via_bot,
        text=text,
        caption=caption,
        photo=photo,
        message_id=message_id,
        reply=reply,
        _sent=sent,
    )


def seed_group(db, *, kind="residents", is_active=True, chat_id=-100500):
    db.add(MonitoredGroup(chat_id=chat_id, title="Дом 12", kind=kind, is_active=is_active))
    db.commit()


def seed_resident(db, *, telegram_id=111, phone="+998901112233", roles='["applicant"]',
                  status="approved", with_apartment=True, is_primary=True):
    yard = Yard(name="Двор Тестовый", is_active=True)
    building = Building(address="ул. Тестовая, 12", yard=yard, is_active=True)
    apartment = Apartment(apartment_number="7", building=building, is_active=True)
    user = User(
        telegram_id=telegram_id, roles=roles, active_role="applicant",
        status=status, phone=phone, language="ru",
    )
    db.add_all([yard, building, apartment, user])
    db.commit()
    if with_apartment:
        db.add(UserApartment(
            user_id=user.id, apartment_id=apartment.id,
            status="approved", is_primary=is_primary,
        ))
        db.commit()
    return user, apartment


async def run_entry(message, db):
    await gi.group_message_entry(message, bot=SimpleNamespace(), _db=db)


# ───────────────────────── отсев до БД/LLM ─────────────────────────


async def test_flag_off_is_full_silence(monkeypatch, env, db):
    monkeypatch.setattr(settings, "GROUP_INTAKE_ENABLED", False)
    message = make_message()
    await run_entry(message, db)
    message.reply.assert_not_awaited()
    env.classify.assert_not_awaited()
    env.mark_seen.assert_not_awaited()


@pytest.mark.parametrize("kwargs", [
    {"is_bot": True},
    {"via_bot": SimpleNamespace(id=1)},
    {"text": None},
    {"text": "   "},
    {"text": "/start"},
    {"text": "/start@test_bot смотри"},
    {"text": "привет"},  # префильтр: короче 10
])
async def test_early_guards_never_reach_db_or_llm(env, db, kwargs):
    message = make_message(**kwargs)
    await run_entry(message, db)
    message.reply.assert_not_awaited()
    env.classify.assert_not_awaited()
    env.mark_seen.assert_not_awaited()


async def test_unmonitored_group_is_silent_before_dedup(env, db):
    message = make_message()  # реестр пуст
    await run_entry(message, db)
    message.reply.assert_not_awaited()
    env.mark_seen.assert_not_awaited()
    env.classify.assert_not_awaited()


@pytest.mark.parametrize("kind,is_active", [("staff", True), ("residents", False)])
async def test_staff_or_inactive_group_is_silent(env, db, kind, is_active):
    seed_group(db, kind=kind, is_active=is_active)
    message = make_message()
    await run_entry(message, db)
    message.reply.assert_not_awaited()
    env.classify.assert_not_awaited()


async def test_duplicate_message_skips_llm(env, db):
    seed_group(db)
    env.mark_seen.return_value = False
    message = make_message()
    await run_entry(message, db)
    env.classify.assert_not_awaited()
    message.reply.assert_not_awaited()


async def test_rate_limited_skips_llm(env, db, caplog):
    seed_group(db)
    env.llm_allowed.return_value = False
    message = make_message()
    with caplog.at_level("WARNING"):
        await run_entry(message, db)
    env.classify.assert_not_awaited()
    message.reply.assert_not_awaited()
    assert any("group_intake.rate_limited" in r.message for r in caplog.records)


@pytest.mark.parametrize("outcome", [Outcome.NOT_REQUEST, Outcome.PROCESSING_ERROR])
async def test_not_request_and_error_are_equally_silent(env, db, outcome):
    seed_group(db)
    seed_resident(db)
    env.classify.return_value = ClassificationResult(outcome=outcome)
    message = make_message()
    await run_entry(message, db)
    message.reply.assert_not_awaited()


# ───────────────────────── гейт автора → приглашения ─────────────────────────


async def test_unknown_author_gets_register_invite_with_deeplink(env, db):
    seed_group(db)
    message = make_message()
    await run_entry(message, db)
    message.reply.assert_awaited_once()
    text = message.reply.await_args.args[0]
    assert "https://t.me/test_bot?start=group" in text
    assert "повторите сообщение" in text
    env.store_candidate.assert_not_awaited()


async def test_invite_respects_cooldown(env, db):
    seed_group(db)
    env.invite_allowed.return_value = False
    message = make_message()
    await run_entry(message, db)
    message.reply.assert_not_awaited()


async def test_no_applicant_role_gets_invite(env, db):
    seed_group(db)
    seed_resident(db, roles='["executor"]')
    message = make_message()
    await run_entry(message, db)
    text = message.reply.await_args.args[0]
    assert "https://t.me/test_bot?start=group" in text
    env.store_candidate.assert_not_awaited()


async def test_no_phone_gets_invite(env, db):
    seed_group(db)
    seed_resident(db, phone=None)
    message = make_message()
    await run_entry(message, db)
    assert message.reply.await_count == 1
    env.store_candidate.assert_not_awaited()


async def test_no_approved_apartment_gets_address_invite(env, db):
    seed_group(db)
    seed_resident(db, with_apartment=False)
    message = make_message()
    await run_entry(message, db)
    assert message.reply.await_count == 1
    env.store_candidate.assert_not_awaited()


# ───────────────────────── успешный промпт ─────────────────────────


async def test_ok_prompts_and_stores_candidate(env, db):
    seed_group(db)
    _user, apartment = seed_resident(db)
    message = make_message()
    await run_entry(message, db)

    message.reply.assert_awaited_once()
    prompt = message.reply.await_args.args[0]
    markup = message.reply.await_args.kwargs["reply_markup"]
    # building-scope: публичная форма = адрес дома, без номера квартиры
    assert "ул. Тестовая, 12" in prompt
    assert "кв." not in prompt
    buttons = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert buttons == ["gint:yes", "gint:no", "gint:other"]

    env.store_candidate.assert_awaited_once()
    chat_id, prompt_message_id = env.store_candidate.await_args.args[:2]
    payload = env.store_candidate.await_args.args[2]
    assert (chat_id, prompt_message_id) == (-100500, 777)
    assert payload["author_id"] == 111
    assert payload["source_message_id"] == 42
    assert payload["kind"] == "residents"
    assert payload["category"] == "electricity"
    assert payload["selected_address"]["type"] == "building"
    assert payload["selected_address"]["id"] == apartment.building_id
    assert payload["truncated"] is False


async def test_apartment_scope_hides_apartment_number(env, db):
    seed_group(db)
    _user, apartment = seed_resident(db)
    env.classify.return_value = ClassificationResult(
        outcome=Outcome.REQUEST, category="plumbing", urgency="high",
        confidence=0.9, location_scope="apartment", address_hint=None,
    )
    message = make_message()
    await run_entry(message, db)
    prompt = message.reply.await_args.args[0]
    assert "ваша квартира" in prompt
    assert "кв. 7" not in prompt
    payload = env.store_candidate.await_args.args[2]
    assert payload["selected_address"]["type"] == "apartment"
    assert payload["selected_address"]["id"] == apartment.id
    # полный адрес (с номером) — только внутри pending
    assert "кв. 7" in payload["selected_address"]["label_full"]


async def test_photo_caption_flow_stores_file_id(env, db):
    seed_group(db)
    seed_resident(db)
    message = make_message(
        text=None,
        caption=REQUEST_TEXT,
        photo=[SimpleNamespace(file_id="small"), SimpleNamespace(file_id="big")],
    )
    await run_entry(message, db)
    payload = env.store_candidate.await_args.args[2]
    assert payload["photo_file_id"] == "big"


async def test_long_text_truncated_with_note(env, db):
    seed_group(db)
    seed_resident(db)
    long_text = "Прорвало трубу! " + "х" * 2100
    message = make_message(text=long_text)
    await run_entry(message, db)
    prompt = message.reply.await_args.args[0]
    assert "2000" in prompt  # пометка об обрезке
    payload = env.store_candidate.await_args.args[2]
    assert len(payload["text"]) == 2000
    assert payload["truncated"] is True


async def test_store_failure_removes_keyboard(env, db):
    seed_group(db)
    seed_resident(db)
    env.store_candidate.return_value = False
    message = make_message()
    await run_entry(message, db)
    message._sent.edit_reply_markup.assert_awaited_once_with(reply_markup=None)


# ───────────────────────── выбор адреса ─────────────────────────


async def test_address_hint_picks_matching_apartment(env, db):
    seed_group(db)
    user, _apartment = seed_resident(db)
    # вторая approved-квартира в другом доме, НЕ primary
    yard2 = Yard(name="Двор Второй", is_active=True)
    building2 = Building(address="пр. Другой, 3", yard=yard2, is_active=True)
    apartment2 = Apartment(apartment_number="15", building=building2, is_active=True)
    db.add_all([yard2, building2, apartment2])
    db.commit()
    db.add(UserApartment(user_id=user.id, apartment_id=apartment2.id,
                         status="approved", is_primary=False))
    db.commit()

    env.classify.return_value = ClassificationResult(
        outcome=Outcome.REQUEST, category="plumbing", urgency="medium",
        confidence=0.9, location_scope="building", address_hint="пр. Другой",
    )
    message = make_message()
    await run_entry(message, db)
    payload = env.store_candidate.await_args.args[2]
    assert payload["selected_address"]["id"] == building2.id


async def test_yard_scope_resolves_to_yard(env, db):
    seed_group(db)
    _user, apartment = seed_resident(db)
    env.classify.return_value = ClassificationResult(
        outcome=Outcome.REQUEST, category="territory", urgency="low",
        confidence=0.8, location_scope="yard", address_hint=None,
    )
    message = make_message()
    await run_entry(message, db)
    payload = env.store_candidate.await_args.args[2]
    assert payload["selected_address"]["type"] == "yard"
    assert payload["selected_address"]["label_public"] == "Двор Тестовый"
