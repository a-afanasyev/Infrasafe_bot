"""T10 (Ф5): бот лифтёра — кнопка меню, гейт по специализации, навигация двор → дом → лифт → карточка.

Свойства (RED-первыми):
1. Кнопка «🛗 Лифты» в меню executor только при ``ELEVATORS_ENABLED``.
2. Вход: executor без специализации → отказ; ``elevator`` и алиас ``maintenance`` → дворы;
   менеджер без роли executor → отказ; флаг выключен → «модуль выключен».
3. Навигация строит клавиатуры из данных юнита: ``elvm:yard:{id}`` → дома с числом лифтов →
   ``elvm:bld:{id}`` → лифты с эмодзи статуса → ``elvm:card:{id}``.
4. Карточка: label, статус, доступность, ближайший план, открытые заявки, кнопка ТО
   только при planned ≤ сегодня+7; невведённый лифт — без кнопки статуса.
5. Роутер несёт RoleGate; ``elvm:`` без роли executor не доходит до хендлера.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from uk_management_bot.config.settings import settings
from uk_management_bot.handlers import elevators as pkg
from uk_management_bot.handlers._role_gate import RoleGate
from uk_management_bot.handlers.elevators import _common, card, maintenance, menu, repair, status
from uk_management_bot.tests.handlers import elevators_harness as h
from uk_management_bot.utils.business_time import business_today
from uk_management_bot.utils.helpers import get_text, load_locale

MODULES = (_common, menu, card, status, repair, maintenance)


@pytest.fixture()
def db():
    session = h.make_db()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)


@pytest.fixture(autouse=True)
def _run_db_on_sqlite(db):
    run = h.run_db_on(db)
    patches = [patch.object(m, "run_db", run) for m in MODULES]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()


@pytest.fixture()
def world(db):
    return h.build_world(db, today=business_today())


# ── 1. кнопка меню ───────────────────────────────────────────────────────


def test_executor_menu_has_elevators_button_when_enabled():
    from uk_management_bot.keyboards.base import get_main_keyboard_for_role

    markup = get_main_keyboard_for_role("executor", ["executor"], language="ru")
    texts = [b.text for row in markup.keyboard for b in row]
    assert get_text("main_menu.elevators", language="ru") in texts


def test_executor_menu_hides_elevators_button_when_disabled(monkeypatch):
    from uk_management_bot.keyboards.base import get_main_keyboard_for_role

    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    markup = get_main_keyboard_for_role("executor", ["executor"], language="ru")
    texts = [b.text for row in markup.keyboard for b in row]
    assert get_text("main_menu.elevators", language="ru") not in texts


def test_applicant_menu_has_no_elevators_button():
    from uk_management_bot.keyboards.base import get_main_keyboard_for_role

    markup = get_main_keyboard_for_role("applicant", ["applicant"], language="ru")
    texts = [b.text for row in markup.keyboard for b in row]
    assert get_text("main_menu.elevators", language="ru") not in texts


def test_button_texts_cover_both_languages():
    from uk_management_bot.utils.button_texts import get_elevators_texts

    texts = get_elevators_texts()
    assert get_text("main_menu.elevators", language="ru") in texts
    assert get_text("main_menu.elevators", language="uz") in texts


# ── 2. гейт входа ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_entry_denied_without_specialization(world):
    msg = h.make_message("🛗 Лифты", from_id=h.PLAIN_TG)
    await menu.handle_elevators_button(msg, h.FakeState(), language="ru")
    assert msg.answer.await_args.args[0] == get_text("elevators.bot.no_spec", language="ru")


@pytest.mark.asyncio
async def test_entry_denied_for_manager_without_executor_role(world):
    msg = h.make_message("🛗 Лифты", from_id=h.MANAGER_TG)
    await menu.handle_elevators_button(msg, h.FakeState(), language="ru")
    # роль executor отсутствует — это отказ доступа, а не «нет специализации»
    assert msg.answer.await_args.args[0] == get_text("auth.no_access", language="ru")


@pytest.mark.asyncio
@pytest.mark.parametrize("tg_id", [h.TECH_TG, h.ALIAS_TG])
async def test_entry_shows_yards_for_elevator_and_alias_specialization(world, tg_id):
    msg = h.make_message("🛗 Лифты", from_id=tg_id)
    await menu.handle_elevators_button(msg, h.FakeState(), language="ru")
    args, kwargs = msg.answer.await_args.args, msg.answer.await_args.kwargs
    assert args[0] == get_text("elevators.bot.yards_title", language="ru")
    assert f"elvm:yard:{world['yard'].id}" in h.callbacks_of(kwargs["reply_markup"])


@pytest.mark.asyncio
async def test_entry_when_flag_off(world, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    msg = h.make_message("🛗 Лифты")
    await menu.handle_elevators_button(msg, h.FakeState(), language="ru")
    assert msg.answer.await_args.args[0] == get_text("elevators.bot.disabled", language="ru")


@pytest.mark.asyncio
async def test_callback_denied_without_specialization(world):
    cb = h.make_callback(f"elvm:yard:{world['yard'].id}", from_id=h.PLAIN_TG)
    await menu.handle_yard(cb, language="ru")
    assert cb.answer.await_args.args[0] == get_text("elevators.bot.no_spec", language="ru")
    assert cb.answer.await_args.kwargs.get("show_alert") is True
    cb.message.edit_text.assert_not_awaited()


# ── 3. навигация ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_yard_lists_buildings_with_elevator_count(world):
    cb = h.make_callback(f"elvm:yard:{world['yard'].id}")
    await menu.handle_yard(cb, language="ru")
    args, kwargs = cb.message.edit_text.await_args.args, cb.message.edit_text.await_args.kwargs
    assert "Двор Лифтовый" in args[0]
    markup = kwargs["reply_markup"]
    assert f"elvm:bld:{world['building'].id}" in h.callbacks_of(markup)
    building_button = [t for t in h.texts_of(markup) if "ул. Лифтовая, 1" in t][0]
    assert building_button == get_text(  # два неархивных лифта
        "elevators.bot.building_button", language="ru", address="ул. Лифтовая, 1", count=2)
    assert "elvm:yards" in h.callbacks_of(markup)


@pytest.mark.asyncio
async def test_building_lists_elevators_with_status(world):
    cb = h.make_callback(f"elvm:bld:{world['building'].id}")
    await menu.handle_building(cb, language="ru")
    kwargs = cb.message.edit_text.await_args.kwargs
    markup = kwargs["reply_markup"]
    callbacks = h.callbacks_of(markup)
    assert f"elvm:card:{world['working'].id}" in callbacks
    assert f"elvm:card:{world['raw'].id}" in callbacks
    texts = h.texts_of(markup)
    assert any(get_text("elevators.status.working", language="ru") in t for t in texts)
    assert any(get_text("elevators.status.none", language="ru") in t for t in texts)
    assert f"elvm:yard:{world['yard'].id}" in callbacks


@pytest.mark.asyncio
async def test_yards_back_button_returns_yard_list(world):
    cb = h.make_callback("elvm:yards")
    await menu.handle_yards(cb, h.FakeState(), language="ru")
    args, kwargs = cb.message.edit_text.await_args.args, cb.message.edit_text.await_args.kwargs
    assert args[0] == get_text("elevators.bot.yards_title", language="ru")
    assert f"elvm:yard:{world['yard'].id}" in h.callbacks_of(kwargs["reply_markup"])


@pytest.mark.asyncio
async def test_unknown_building_is_reported(world):
    cb = h.make_callback("elvm:bld:99999")
    await menu.handle_building(cb, language="ru")
    assert cb.answer.await_args.args[0] == get_text("elevators.bot.not_found", language="ru")


# ── 4. карточка ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_card_shows_metrics_and_actions(world):
    elevator_id = world["working"].id
    cb = h.make_callback(f"elvm:card:{elevator_id}")
    await card.handle_card(cb, h.FakeState(), language="ru")
    args, kwargs = cb.message.edit_text.await_args.args, cb.message.edit_text.await_args.kwargs
    text = args[0]
    assert "ул. Лифтовая, 1" in text
    assert get_text("elevators.status.working", language="ru") in text
    assert "01.09.2026" in text                       # status_since в бизнес-зоне
    assert "Открытых заявок: 1" in text
    assert get_text("elevators.bot.kind.maintenance", language="ru") in text
    assert kwargs.get("parse_mode") == "HTML"
    callbacks = h.callbacks_of(kwargs["reply_markup"])
    assert f"elvm:st:{elevator_id}" in callbacks
    assert f"elvm:rep:{elevator_id}" in callbacks
    assert f"elvm:occs:{elevator_id}" in callbacks    # planned ТО через 3 дня ≤ +7
    assert f"elvm:bld:{world['building'].id}" in callbacks


@pytest.mark.asyncio
async def test_card_without_due_soon_hides_maintenance_button(world, db):
    world["soon"].state = "cancelled"
    db.commit()
    elevator_id = world["working"].id
    cb = h.make_callback(f"elvm:card:{elevator_id}")
    await card.handle_card(cb, h.FakeState(), language="ru")
    callbacks = h.callbacks_of(cb.message.edit_text.await_args.kwargs["reply_markup"])
    assert f"elvm:occs:{elevator_id}" not in callbacks
    assert f"elvm:rep:{elevator_id}" in callbacks


@pytest.mark.asyncio
async def test_card_of_uncommissioned_elevator_has_no_status_and_repair_buttons(world):
    elevator_id = world["raw"].id
    cb = h.make_callback(f"elvm:card:{elevator_id}")
    await card.handle_card(cb, h.FakeState(), language="ru")
    args, kwargs = cb.message.edit_text.await_args.args, cb.message.edit_text.await_args.kwargs
    assert get_text("elevators.status.none", language="ru") in args[0]
    callbacks = h.callbacks_of(kwargs["reply_markup"])
    assert f"elvm:st:{elevator_id}" not in callbacks
    assert f"elvm:rep:{elevator_id}" not in callbacks
    assert f"elvm:bld:{world['building'].id}" in callbacks


@pytest.mark.asyncio
async def test_card_unknown_elevator(world):
    cb = h.make_callback("elvm:card:99999")
    await card.handle_card(cb, h.FakeState(), language="ru")
    assert cb.answer.await_args.args[0] == get_text("elevators.bot.not_found", language="ru")


@pytest.mark.asyncio
async def test_cancel_clears_state_and_returns_to_card(world):
    state = h.FakeState()
    await state.update_data(elvm_elevator_id=world["working"].id, elvm_status="working")
    await state.set_state("x")
    cb = h.make_callback("elvm:cancel")
    await menu.handle_cancel(cb, state, language="ru")
    assert state.state is None and state.data == {}
    assert cb.message.edit_text.await_args.args[0] == get_text("elevators.bot.cancelled", language="ru")
    callbacks = h.callbacks_of(cb.message.answer.await_args.kwargs["reply_markup"])
    assert f"elvm:st:{world['working'].id}" in callbacks


# ── 5. роутер и локали ───────────────────────────────────────────────────


def test_router_carries_executor_role_gate():
    gates = [f.callback for f in pkg.router.callback_query._handler.filters or []]
    msg_gates = [f.callback for f in pkg.router.message._handler.filters or []]
    assert any(isinstance(g, RoleGate) and "executor" in g.allowed_roles for g in gates)
    assert any(isinstance(g, RoleGate) and "executor" in g.allowed_roles for g in msg_gates)


def test_router_registered_in_main_before_base():
    import re
    from pathlib import Path

    import uk_management_bot.main as main_mod

    order = re.findall(r"dp\.include_router\((\w+)\)", Path(main_mod.__file__).read_text())
    assert "elevators_router" in order
    assert order.index("elevators_router") < order.index("base_router")


def _lookup(locale: dict, dotted: str):
    node = locale
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


@pytest.mark.parametrize("lang", ["ru", "uz"])
def test_locale_keys_present(lang):
    keys = [
        "main_menu.elevators",
        *[f"elevators.bot.{k}" for k in (
            "no_spec", "disabled", "yards_title", "no_yards", "yard_title", "building_button",
            "no_buildings", "building_title", "elevator_button", "no_elevators", "card",
            "availability_unknown", "next_none", "next_item", "since_unknown",
            "kind.maintenance", "kind.certification", "btn_status", "btn_repair",
            "btn_maintenance", "btn_back", "btn_yards", "btn_cancel", "btn_skip", "btn_no_reason",
            "btn_yes", "btn_no", "status_prompt", "status_not_commissioned", "reason_prompt",
            "reason_too_long", "status_changed", "status_unchanged", "status_rejected",
            "not_found", "error", "cancelled", "text_only", "repair_description_prompt",
            "repair_description_short", "repair_urgency_prompt", "repair_failed",
            "repair_created", "repair_reason", "repair_status_kept", "occ_title", "occ_button",
            "occ_overdue_mark", "occ_none", "occ_comment_prompt", "cert_number_prompt",
            "cert_number_invalid", "cert_valid_until_prompt", "cert_date_invalid",
            "cert_url_prompt", "cert_url_invalid", "occ_done", "occ_state_error", "occ_invalid",
            "repair_not_commissioned", "request_mismatch", "pick_urgency",
        )],
    ]
    locale = load_locale(lang)
    missing = [k for k in keys if _lookup(locale, k) is None]
    assert not missing, (lang, missing)
