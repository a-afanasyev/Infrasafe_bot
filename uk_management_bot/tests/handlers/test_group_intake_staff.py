"""Staff-ветка Group Intake (фаза 2, менеджерская приёмка).

Три блока:
1. Message-фаза: гейт сотрудника ДО dedup/LLM (посторонний в служебном чате —
   полная тишина, Anthropic не вызывается), адрес по СПРАВОЧНИКУ (0/1/2–4
   кандидата), staff-клавиатура без «Другой адрес».
2. Callback-фаза: выбор адреса ``gint:addr:<n>``, kind-aware ре-гейт, crafted
   callback_data (его шлёт КЛИЕНТ — сервер проверяет всё сам).
3. Настоящий save_request_sync на sqlite: role='staff_group' резолвит дом без
   принадлежности, строка несёт acceptance_mode='manager' + reported_by
   (урок PR #477: мок save_request рассинхрон ключей data не ловит).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import uk_management_bot.handlers.group_intake as gi
from uk_management_bot.config.settings import settings
from uk_management_bot.database.session import Base
from uk_management_bot.database.models import Building, MonitoredGroup, Yard
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.services.group_intake.classifier import (
    ClassificationResult,
    Outcome,
)
from uk_management_bot.utils.constants import ACCEPTANCE_MODE_MANAGER

REQUEST_TEXT = "На фасаде дома 12 отвалилась плитка, опасно для прохожих"
CHAT_ID = -100600
STAFF_ID = 222
PROMPT_ID = 777


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
                category="other",
                urgency="high",
                confidence=0.9,
                location_scope="building",
                address_hint="Тестовая",
            )
        ),
    )
    monkeypatch.setattr(gi.pending, "mark_seen", mocks.mark_seen)
    monkeypatch.setattr(gi.pending, "llm_allowed", mocks.llm_allowed)
    monkeypatch.setattr(gi.pending, "invite_allowed", mocks.invite_allowed)
    monkeypatch.setattr(gi.pending, "store_candidate", mocks.store_candidate)
    monkeypatch.setattr(gi, "classify_message", mocks.classify)
    return mocks


def make_message(text=REQUEST_TEXT, *, from_id=STAFF_ID, photo=None):
    sent = SimpleNamespace(message_id=PROMPT_ID, edit_reply_markup=AsyncMock())
    reply = AsyncMock(return_value=sent)
    return SimpleNamespace(
        chat=SimpleNamespace(id=CHAT_ID, type="supergroup"),
        from_user=SimpleNamespace(id=from_id, is_bot=False, language_code="ru"),
        via_bot=None,
        text=text,
        caption=None,
        photo=photo,
        message_id=42,
        reply=reply,
        _sent=sent,
    )


def seed_staff_group(db, *, is_active=True):
    db.add(MonitoredGroup(chat_id=CHAT_ID, title="Бригада", kind="staff",
                          is_active=is_active))
    db.commit()


def seed_staff_user(db, *, telegram_id=STAFF_ID, roles='["executor"]',
                    status="approved"):
    user = User(telegram_id=telegram_id, roles=roles, active_role="executor",
                status=status, language="ru")
    db.add(user)
    db.commit()
    return user


def seed_directory(db, addresses=("ул. Тестовая, 12",), yard_names=("Двор Центральный",)):
    """Справочник: дворы + дома (дома вешаются на первый двор)."""
    yards = [Yard(name=name, is_active=True) for name in yard_names]
    db.add_all(yards)
    buildings = [
        Building(address=address, yard=yards[0], is_active=True)
        for address in addresses
    ]
    db.add_all(buildings)
    db.commit()
    return yards, buildings


async def run_entry(message, db):
    await gi.group_message_entry(message, bot=SimpleNamespace(), _db=db)


# ───────────────────── гейт сотрудника ДО LLM ─────────────────────


async def test_outsider_in_staff_group_is_full_silence_no_llm(env, db):
    """Посторонний (незарегистрированный) в служебном чате: ни ответа, ни
    приглашения, ни вызова Anthropic — и даже dedup не тратится."""
    seed_staff_group(db)
    message = make_message()
    await run_entry(message, db)
    message.reply.assert_not_awaited()
    env.classify.assert_not_awaited()
    env.mark_seen.assert_not_awaited()
    env.invite_allowed.assert_not_awaited()


async def test_resident_in_staff_group_is_silent(env, db):
    """Житель (applicant без staff-ролей) в staff-группе — тоже тишина."""
    seed_staff_group(db)
    seed_staff_user(db, roles='["applicant"]')
    message = make_message()
    await run_entry(message, db)
    message.reply.assert_not_awaited()
    env.classify.assert_not_awaited()


async def test_pending_staff_user_is_silent(env, db):
    seed_staff_group(db)
    seed_staff_user(db, status="pending")
    message = make_message()
    await run_entry(message, db)
    message.reply.assert_not_awaited()
    env.classify.assert_not_awaited()


@pytest.mark.parametrize("roles", ['["executor"]', '["inspector"]', '["manager"]'])
async def test_each_staff_role_passes_gate(env, db, roles):
    seed_staff_group(db)
    seed_staff_user(db, roles=roles)
    seed_directory(db)
    message = make_message()
    await run_entry(message, db)
    env.classify.assert_awaited_once()
    message.reply.assert_awaited_once()


# ───────────────────── адрес по справочнику ─────────────────────


async def test_single_match_prompts_confirm_without_other_button(env, db):
    seed_staff_group(db)
    seed_staff_user(db)
    _yards, buildings = seed_directory(db)
    message = make_message()
    await run_entry(message, db)

    prompt = message.reply.await_args.args[0]
    markup = message.reply.await_args.kwargs["reply_markup"]
    assert "ул. Тестовая, 12" in prompt
    buttons = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert buttons == ["gint:yes", "gint:no"], "у staff-промпта нет «Другой адрес»"

    payload = env.store_candidate.await_args.args[2]
    assert payload["kind"] == "staff"
    assert payload["selected_address"]["type"] == "building"
    assert payload["selected_address"]["id"] == buildings[0].id
    assert "address_options" not in payload


async def test_multiple_matches_offer_pick_buttons(env, db):
    seed_staff_group(db)
    seed_staff_user(db)
    seed_directory(db, addresses=("ул. Тестовая, 12", "ул. Тестовая, 14"))
    message = make_message()
    await run_entry(message, db)

    markup = message.reply.await_args.kwargs["reply_markup"]
    buttons = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert buttons == ["gint:addr:0", "gint:addr:1"]

    payload = env.store_candidate.await_args.args[2]
    assert len(payload["address_options"]) == 2
    assert "selected_address" not in payload


# Текст без цифр: иначе фолбэк по токенам текста (фикс smoke №3) найдёт дом
# и тест «адрес не найден» проверял бы не ту ветку.
NO_ADDRESS_TEXT = "У подъезда отвалилась плитка и висит провод, это опасно"


async def test_no_match_asks_for_address_with_cooldown(env, db):
    seed_staff_group(db)
    seed_staff_user(db)
    seed_directory(db)  # справочник есть, но ни hint, ни текст не матчатся
    env.classify.return_value = ClassificationResult(
        outcome=Outcome.REQUEST, category="other", urgency="low",
        confidence=0.8, location_scope="building", address_hint="Несуществующая",
    )
    message = make_message(text=NO_ADDRESS_TEXT)
    await run_entry(message, db)
    text = message.reply.await_args.args[0]
    assert "дом" in text.lower()
    env.store_candidate.assert_not_awaited()

    # cooldown исчерпан → тишина
    env.invite_allowed.return_value = False
    message2 = make_message(text=NO_ADDRESS_TEXT)
    await run_entry(message2, db)
    message2.reply.assert_not_awaited()


async def test_no_hint_asks_for_address(env, db):
    seed_staff_group(db)
    seed_staff_user(db)
    seed_directory(db)
    env.classify.return_value = ClassificationResult(
        outcome=Outcome.REQUEST, category="other", urgency="low",
        confidence=0.8, location_scope="unknown", address_hint=None,
    )
    message = make_message(text=NO_ADDRESS_TEXT)
    await run_entry(message, db)
    env.store_candidate.assert_not_awaited()
    assert message.reply.await_count == 1


async def test_house_number_only_in_text_still_matches(env, db):
    """Номер дома есть только в тексте (LLM-хинт пуст) → дом находится."""
    seed_staff_group(db)
    seed_staff_user(db)
    _yards, buildings = seed_directory(db)
    env.classify.return_value = ClassificationResult(
        outcome=Outcome.REQUEST, category="other", urgency="low",
        confidence=0.8, location_scope="building", address_hint=None,
    )
    message = make_message(text=REQUEST_TEXT)  # «…дома 12…»
    await run_entry(message, db)
    payload = env.store_candidate.await_args.args[2]
    assert payload["selected_address"]["id"] == buildings[0].id


async def test_yard_scope_searches_yards(env, db):
    seed_staff_group(db)
    seed_staff_user(db)
    yards, _buildings = seed_directory(db, yard_names=("Двор Центральный",))
    # Хинт в регистре справочника: sqlite LIKE регистронезависим только для
    # ASCII; кириллическое сворачивание регистра — PG-ветка ci_contains (ICU).
    env.classify.return_value = ClassificationResult(
        outcome=Outcome.REQUEST, category="territory", urgency="low",
        confidence=0.9, location_scope="yard", address_hint="Центральн",
    )
    message = make_message()
    await run_entry(message, db)
    payload = env.store_candidate.await_args.args[2]
    assert payload["selected_address"]["type"] == "yard"
    assert payload["selected_address"]["id"] == yards[0].id


# ─────────────────── матчер: юнит-свойства ───────────────────


def test_matcher_escapes_like_metacharacters(db):
    seed_directory(db, addresses=("ул. Тестовая, 12",))
    assert gi._match_staff_address_sync(db, "building", "%") == []
    assert gi._match_staff_address_sync(db, "building", "_") == []


def test_matcher_caps_at_limit(db):
    seed_directory(
        db, addresses=tuple(f"ул. Тестовая, {n}" for n in range(1, 7))
    )
    options = gi._match_staff_address_sync(db, "building", "Тестовая")
    assert len(options) == gi._STAFF_MATCH_LIMIT


def test_matcher_treats_apartment_scope_as_building(db):
    _yards, buildings = seed_directory(db)
    options = gi._match_staff_address_sync(db, "apartment", "Тестовая")
    assert [o["type"] for o in options] == ["building"]
    assert options[0]["id"] == buildings[0].id


def test_matcher_transliterates_cyrillic_hint_to_latin(db):
    """Живой кейс smoke на profk: справочник латинский («Yangi Olmazor, 14V»),
    сотрудник пишет «14в» кириллицей — матчер обязан найти дом сам."""
    _yards, buildings = seed_directory(
        db, addresses=("Yangi Olmazor, 14V", "Yangi Olmazor, 15V")
    )
    options = gi._match_staff_address_sync(db, "building", "14в")
    assert [o["id"] for o in options] == [buildings[0].id]


def test_matcher_transliterates_cyrillic_words(db):
    """«Янги Олмазор» → yangi olmazor: оба дома в выбор."""
    seed_directory(
        db, addresses=("Yangi Olmazor, 14V", "Yangi Olmazor, 15V")
    )
    options = gi._match_staff_address_sync(db, "building", "Янги Олмазор")
    assert len(options) == 2


def test_matcher_latin_hint_still_matches(db):
    _yards, buildings = seed_directory(db, addresses=("Yangi Olmazor, 14V",))
    options = gi._match_staff_address_sync(db, "building", "14v")
    assert [o["id"] for o in options] == [buildings[0].id]


def test_matcher_translit_yard_scope(db):
    yards, _b = seed_directory(db, yard_names=("Olmazor City Phase 1",))
    options = gi._match_staff_address_sync(db, "yard", "Олмазор")
    assert [o["id"] for o in options] == [yards[0].id]


def test_matcher_token_fallback_for_verbose_hint(db):
    """Живой кейс smoke №2: LLM отдал «у дома 14в» — целиком не подстрока,
    но токен с цифрой обязан найти дом."""
    _yards, buildings = seed_directory(
        db, addresses=("Yangi Olmazor, 14V", "Yangi Olmazor, 15V")
    )
    options = gi._match_staff_address_sync(db, "building", "у дома 14в")
    assert [o["id"] for o in options] == [buildings[0].id]


def test_matcher_prefers_full_hint_over_tokens(db):
    """Полный хинт нашёлся → токены не пробуются (не расширяем выбор зря)."""
    _yards, buildings = seed_directory(
        db, addresses=("Yangi Olmazor, 14V", "Boshqa 99")
    )
    options = gi._match_staff_address_sync(db, "building", "Olmazor, 14V")
    assert [o["id"] for o in options] == [buildings[0].id]


def test_hint_needles_order_prefers_digit_tokens():
    needles = gi._hint_needles("у дома 14в")
    assert needles[0] == "у дома 14в"
    assert needles[1] == "14в"  # токен с цифрой раньше слов длиннее


def test_matcher_falls_back_to_message_text(db):
    """Живой smoke №3: LLM выбросил номер дома из хинта («dom 2 podyezd»
    при тексте «21v dom 2 podyezd…») — номер достаётся из ПОЛНОГО текста."""
    _yards, buildings = seed_directory(
        db, addresses=("Yangi Olmazor, 21V", "Yangi Olmazor, 14V")
    )
    options = gi._match_staff_address_sync(
        db, "building", "dom 2 podyezd",
        "21v dom 2 podyezd eshik tagidagi skameykalar podvalga tushirilgan",
    )
    assert [o["id"] for o in options] == [buildings[0].id]


def test_matcher_hint_wins_over_text_fallback(db):
    """Хинт, нашедший дом, выигрывает — текст не пробуется."""
    _yards, buildings = seed_directory(
        db, addresses=("Yangi Olmazor, 21V", "Yangi Olmazor, 14V")
    )
    options = gi._match_staff_address_sync(
        db, "building", "14в", "болтовня про 21v в тексте"
    )
    assert [o["id"] for o in options] == [buildings[1].id]


def test_matcher_no_hint_no_digits_in_text_is_empty(db):
    seed_directory(db)
    assert gi._match_staff_address_sync(
        db, "building", None, "просто болтовня без адреса"
    ) == []


def test_digit_tokens_filters_and_orders():
    tokens = gi._digit_tokens("21v dom 2 podyezd 14в skameyka")
    assert tokens == ["21v", "14в"]  # «2» короче двух символов — отсев


def test_digit_tokens_capped(db):
    """Security-review: текст, набитый digit-токенами, не порождает
    неограниченный список кандидатов."""
    text = " ".join(f"{i}x" for i in range(10, 40))
    assert len(gi._digit_tokens(text)) == gi._MAX_TEXT_DIGIT_TOKENS


def test_matcher_caps_query_attempts(db, monkeypatch):
    """Security-review: одно сообщение не может породить больше
    _MAX_MATCH_ATTEMPTS SQL-запросов матчера."""
    seed_directory(db)
    calls = []
    monkeypatch.setattr(
        gi, "_query_staff_addresses",
        lambda *a, **k: (calls.append(1), [])[1],
    )
    gi._match_staff_address_sync(
        db, "building", "штука одна другая третья четвёртая пятая",
        " ".join(f"{i}x" for i in range(10, 40)),
    )
    assert len(calls) <= gi._MAX_MATCH_ATTEMPTS


async def test_prompt_escapes_address_html(env, db):
    """Security-review: адрес справочника — свободный текст; `&`/`<` без
    экранирования = Telegram-400 (parse_mode=HTML) и потерянный промпт."""
    seed_staff_group(db)
    seed_staff_user(db)
    seed_directory(db, addresses=('Дом <Ё> & К, 12',))
    env.classify.return_value = ClassificationResult(
        outcome=Outcome.REQUEST, category="other", urgency="low",
        confidence=0.9, location_scope="building", address_hint="12",
    )
    message = make_message(text="У дома 12 отвалилась плитка, опасно")
    await run_entry(message, db)
    prompt = message.reply.await_args.args[0]
    assert "&lt;Ё&gt; &amp; К" in prompt
    assert "<Ё>" not in prompt


# ───────────────────── callback-фаза ─────────────────────


def make_staff_candidate(**overrides):
    candidate = {
        "v": 1,
        "kind": "staff",
        "author_id": STAFF_ID,
        "source_message_id": 42,
        "text": REQUEST_TEXT,
        "truncated": False,
        "category": "other",
        "urgency": "high",
        "confidence": 0.9,
        "location_scope": "building",
        "photo_file_id": None,
        "selected_address": {
            "type": "building", "id": 5,
            "label_public": "ул. Тестовая, 12 (Двор Центральный)",
            "label_full": "ул. Тестовая, 12 (Двор Центральный)",
        },
        "lang": "ru",
    }
    candidate.update(overrides)
    return candidate


@pytest.fixture()
def cb_env(monkeypatch):
    monkeypatch.setattr(settings, "GROUP_INTAKE_ENABLED", True)
    monkeypatch.setattr(settings, "BOT_USERNAME", "test_bot")
    mocks = SimpleNamespace(
        get_candidate=AsyncMock(return_value=make_staff_candidate()),
        pop_candidate=AsyncMock(return_value=make_staff_candidate()),
        store_candidate=AsyncMock(return_value=True),
        save_request=AsyncMock(return_value="260822-005"),
    )
    monkeypatch.setattr(gi.pending, "get_candidate", mocks.get_candidate)
    monkeypatch.setattr(gi.pending, "pop_candidate", mocks.pop_candidate)
    monkeypatch.setattr(gi.pending, "store_candidate", mocks.store_candidate)
    monkeypatch.setattr(
        "uk_management_bot.handlers.requests.create.save_request", mocks.save_request
    )
    return mocks


def make_callback(action="yes", from_id=STAFF_ID):
    return SimpleNamespace(
        data=f"gint:{action}",
        from_user=SimpleNamespace(id=from_id, language_code="ru"),
        message=SimpleNamespace(
            chat=SimpleNamespace(id=CHAT_ID, type="supergroup"),
            message_id=PROMPT_ID,
            edit_text=AsyncMock(),
        ),
        answer=AsyncMock(),
    )


async def run_cb(callback, db):
    await gi.group_intake_callback(callback, bot=SimpleNamespace(), _db=db)


OPTIONS = [
    {"type": "building", "id": 5, "label_public": "ул. Тестовая, 12 (Двор)",
     "label_full": "ул. Тестовая, 12 (Двор)"},
    {"type": "building", "id": 6, "label_public": "ул. Тестовая, 14 (Двор)",
     "label_full": "ул. Тестовая, 14 (Двор)"},
]


async def test_addr_pick_stores_selection_and_shows_confirm(cb_env, db):
    cb_env.get_candidate.return_value = make_staff_candidate(
        selected_address=None, address_options=OPTIONS
    )
    callback = make_callback("addr:1")
    await run_cb(callback, db)

    callback.answer.assert_awaited_once_with()
    cb_env.store_candidate.assert_awaited_once()
    updated = cb_env.store_candidate.await_args.args[2]
    assert updated["selected_address"] == OPTIONS[1]
    assert updated["address_options"] is None
    assert "v" not in updated  # версию проставляет сам store_candidate

    edited = callback.message.edit_text.await_args
    assert "ул. Тестовая, 14" in edited.args[0]
    buttons = [
        b.callback_data
        for row in edited.kwargs["reply_markup"].inline_keyboard
        for b in row
    ]
    assert buttons == ["gint:yes", "gint:no"]


@pytest.mark.parametrize("action", ["addr:5", "addr:-1", "addr:x"])
async def test_addr_pick_invalid_index_does_nothing(cb_env, db, action):
    cb_env.get_candidate.return_value = make_staff_candidate(
        selected_address=None, address_options=OPTIONS
    )
    callback = make_callback(action)
    await run_cb(callback, db)
    cb_env.store_candidate.assert_not_awaited()
    callback.message.edit_text.assert_not_awaited()


async def test_addr_pick_on_residents_candidate_is_ignored(cb_env, db):
    """callback_data шлёт клиент: addr на жительском кандидате — no-op."""
    cb_env.get_candidate.return_value = make_staff_candidate(kind="residents")
    callback = make_callback("addr:0")
    await run_cb(callback, db)
    cb_env.store_candidate.assert_not_awaited()
    callback.message.edit_text.assert_not_awaited()


async def test_crafted_other_on_staff_candidate_keeps_candidate(cb_env, db):
    callback = make_callback("other")
    await run_cb(callback, db)
    cb_env.pop_candidate.assert_not_awaited()
    callback.message.edit_text.assert_not_awaited()


async def test_crafted_yes_without_selected_address_is_ignored(cb_env, db):
    cb_env.get_candidate.return_value = make_staff_candidate(
        selected_address=None, address_options=OPTIONS
    )
    callback = make_callback("yes")
    await run_cb(callback, db)
    cb_env.pop_candidate.assert_not_awaited()
    cb_env.save_request.assert_not_awaited()


async def test_yes_creates_staff_request_with_manager_acceptance(cb_env, db):
    seed_staff_group(db)
    user = seed_staff_user(db)
    callback = make_callback("yes")
    await run_cb(callback, db)

    cb_env.save_request.assert_awaited_once()
    data, author_tg_id = cb_env.save_request.await_args.args[:2]
    kwargs = cb_env.save_request.await_args.kwargs
    assert author_tg_id == STAFF_ID
    assert kwargs["role"] == "staff_group"
    assert kwargs["source"] == "group"
    assert data["acceptance_mode"] == ACCEPTANCE_MODE_MANAGER
    assert data["reported_by_user_id"] == user.id
    assert data["source_chat_id"] == CHAT_ID
    edited = callback.message.edit_text.await_args.args[0]
    assert "260822-005" in edited


async def test_regate_rejects_non_staff_presser(cb_env, db):
    """За жизнь кандидата у автора отняли staff-роль → expired, не создаём."""
    seed_staff_group(db)
    seed_staff_user(db, roles='["applicant"]')
    callback = make_callback("yes")
    await run_cb(callback, db)
    cb_env.save_request.assert_not_awaited()
    edited = callback.message.edit_text.await_args.args[0]
    assert "устарело" in edited


async def test_regate_rejects_kind_flip(cb_env, db):
    """Группу перевели в residents за жизнь staff-кандидата → expired."""
    db.add(MonitoredGroup(chat_id=CHAT_ID, title="Бригада", kind="residents",
                          is_active=True))
    db.commit()
    seed_staff_user(db)
    callback = make_callback("yes")
    await run_cb(callback, db)
    cb_env.save_request.assert_not_awaited()


# ───────────── настоящий save_request_sync (role=staff_group) ─────────────


@pytest.fixture()
def _no_dispatch(monkeypatch):
    import uk_management_bot.services.dispatch as dispatch_mod

    monkeypatch.setattr(
        dispatch_mod, "auto_dispatch_new_request_sync", MagicMock()
    )


def test_real_save_staff_group_role_and_fields(db, _no_dispatch):
    """Дом из справочника резолвится БЕЗ принадлежности; строка несёт
    acceptance_mode='manager', reported_by и provenance."""
    from uk_management_bot.handlers.requests.create import save_request_sync

    user = seed_staff_user(db)
    _yards, buildings = seed_directory(db)
    saved = save_request_sync(
        {
            "category": "other",
            "urgency": "high",
            "address_type": "building",
            "address_id": buildings[0].id,
            "description": REQUEST_TEXT,
            "media_files": [],
            "source_chat_id": CHAT_ID,
            "source_message_id": 42,
            "acceptance_mode": ACCEPTANCE_MODE_MANAGER,
            "reported_by_user_id": user.id,
        },
        STAFF_ID, db, source="group", role="staff_group",
    )
    assert saved is not None
    request = db.query(Request).filter(Request.request_number == saved[0]).one()
    assert request.acceptance_mode == ACCEPTANCE_MODE_MANAGER
    assert request.reported_by_user_id == user.id
    assert request.address_type == "building"
    assert request.building_id == buildings[0].id
    assert request.source_chat_id == CHAT_ID


def test_real_save_staff_group_rejects_apartment_level(db, _no_dispatch):
    """Квартирный уровень для staff_group запрещён схемой уровней."""
    from uk_management_bot.database.models import Apartment
    from uk_management_bot.handlers.requests.create import save_request_sync

    seed_staff_user(db)
    _yards, buildings = seed_directory(db)
    apartment = Apartment(apartment_number="7", building=buildings[0], is_active=True)
    db.add(apartment)
    db.commit()
    saved = save_request_sync(
        {
            "category": "other",
            "urgency": "high",
            "address_type": "apartment",
            "address_id": apartment.id,
            "description": REQUEST_TEXT,
            "media_files": [],
        },
        STAFF_ID, db, source="group", role="staff_group",
    )
    assert saved is None
