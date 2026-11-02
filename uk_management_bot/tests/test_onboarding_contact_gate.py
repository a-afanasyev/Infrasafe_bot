"""Обязательный контакт в онбординге жителя (спека 2026-09-03, §3.1–3.3).

Телефон только из Telegram-контакта: экран онбординга без телефона показывает
ровно «Поделиться контактом» (request_contact) и «Регистрация (форма)»;
«Выбрать квартиру» появляется после телефона; ручной ввод номера удалён;
вход в выбор квартиры без телефона отказывает и просит контакт.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from uk_management_bot.handlers.base import _MenuContext, _build_onboarding_screen
from uk_management_bot.utils.helpers import get_text

FRONTEND = "https://example.test"


def _ctx(phone, *, approved=False, any_apartment=False, doc=False, verification="pending"):
    return _MenuContext(
        status="pending", phone=phone, has_approved_apartment=approved,
        has_any_apartment=any_apartment or approved, db_roles=["applicant"],
        active_role="applicant", has_property_doc=doc, verification_status=verification,
    )


def _rows(markup):
    return [[(b.text, bool(b.request_contact)) for b in row] for row in markup.keyboard]


@pytest.fixture(autouse=True)
def _frontend_url(monkeypatch):
    from uk_management_bot.handlers import base
    monkeypatch.setattr(base.settings, "FRONTEND_URL", FRONTEND)


def _t(key):
    return get_text(key, language="ru")


# ─── §3.1 экран онбординга ───────────────────────────────────────────────────

def test_screen_without_phone_offers_contact_and_form_only():
    _, kb = _build_onboarding_screen(_ctx(None), "ru")
    assert _rows(kb) == [
        [(_t("base.handlers.btn_share_contact"), True)],
        [(_t("base.handlers.btn_register_webapp"), False)],
    ]


def test_screen_with_phone_offers_apartment_and_form():
    _, kb = _build_onboarding_screen(_ctx("+998901234567"), "ru")
    assert _rows(kb) == [
        [(_t("base.handlers.btn_select_apartment"), False)],
        [(_t("base.handlers.btn_register_webapp"), False)],
    ]


def test_screen_without_frontend_url_has_no_form_button(monkeypatch):
    from uk_management_bot.handlers import base
    monkeypatch.setattr(base.settings, "FRONTEND_URL", "")
    _, kb = _build_onboarding_screen(_ctx(None), "ru")
    assert _rows(kb) == [[(_t("base.handlers.btn_share_contact"), True)]]


def test_complete_profile_has_no_keyboard():
    _, kb = _build_onboarding_screen(_ctx("+998901234567", approved=True, doc=True), "ru")
    assert kb is None


# ─── Документ на квартиру обязателен (2026-11-03) ────────────────────────────

def test_approved_apartment_without_document_is_not_complete():
    """Квартиру подтвердили, документ не загружен, проверка открыта — онбординг
    не закончен: иначе /start не дойдёт до кнопки загрузки."""
    from uk_management_bot.handlers.base import _profile_complete, needs_onboarding_redraw

    ctx = _ctx("+998901234567", approved=True)
    assert not _profile_complete(ctx)
    assert needs_onboarding_redraw(ctx)
    _, kb = _build_onboarding_screen(ctx, "ru")
    assert kb is not None


@pytest.mark.parametrize("verification", ["verified", "rejected"])
def test_decided_verification_completes_without_document(verification):
    """После решения менеджера документы удалены — требовать их снова нельзя."""
    from uk_management_bot.handlers.base import _profile_complete

    assert _profile_complete(_ctx("+998901234567", approved=True, verification=verification))


@pytest.mark.parametrize("kwargs,expected", [
    ({"any_apartment": True}, True),                       # квартира выбрана, документа нет
    ({"approved": True}, True),                            # квартира подтверждена, документа нет
    ({"any_apartment": True, "doc": True}, False),         # документ есть
    ({"any_apartment": True, "verification": "verified"}, False),
    ({}, False),                                           # квартира ещё не выбрана
])
def test_needs_document_upload(kwargs, expected):
    from uk_management_bot.handlers.base import _needs_document_upload

    assert _needs_document_upload(_ctx("+998901234567", **kwargs)) is expected


@pytest.mark.asyncio
async def test_start_offers_inline_upload_when_document_missing():
    from unittest.mock import patch

    from uk_management_bot.handlers import base
    from uk_management_bot.keyboards.documents_entry import UPLOAD_DOCUMENTS_CB

    msg = MagicMock()
    msg.from_user = MagicMock(id=1, username="u", first_name="F", last_name="L")
    msg.answer = AsyncMock()
    ctx = _ctx("+998901234567", approved=True)
    with patch.object(base, "run_db", new=AsyncMock(return_value=ctx)):
        await base.handle_regular_start(msg, language="ru")

    markups = [c.kwargs.get("reply_markup") for c in msg.answer.await_args_list]
    inline = [m for m in markups if m is not None and hasattr(m, "inline_keyboard")]
    assert [b.callback_data for b in inline[0].inline_keyboard[0]] == [UPLOAD_DOCUMENTS_CB]


def test_welcome_names_complex_and_company(monkeypatch):
    from uk_management_bot.handlers import base

    monkeypatch.setattr(base.settings, "RESIDENTIAL_COMPLEX_NAME", "Olmazor Business City")
    monkeypatch.setattr(base.settings, "MANAGEMENT_COMPANY_NAME", "")
    text, _ = _build_onboarding_screen(_ctx(None), "ru")
    assert "жителей ЖК Olmazor Business City." in text
    assert text.endswith("С уважением, УК")
    assert "{" not in text


def test_welcome_without_names_has_no_placeholders(monkeypatch):
    from uk_management_bot.handlers import base

    monkeypatch.setattr(base.settings, "RESIDENTIAL_COMPLEX_NAME", "")
    monkeypatch.setattr(base.settings, "MANAGEMENT_COMPANY_NAME", "PROFK")
    for lang in ("ru", "uz"):
        text = base.onboarding_welcome_text(lang)
        assert "{" not in text and text.rstrip().endswith("PROFK")


# ─── §3.2 ручной ввод телефона удалён ────────────────────────────────────────

def test_manual_phone_handlers_removed():
    from uk_management_bot.handlers import onboarding
    for name in ("start_phone_input", "process_contact", "process_manual_phone"):
        assert not hasattr(onboarding, name), name


# ─── §3.3 гейт выбора квартиры ───────────────────────────────────────────────

def _message():
    msg = MagicMock()
    msg.from_user = MagicMock(id=123)
    msg.answer = AsyncMock()
    return msg


def _state():
    st = MagicMock()
    st.set_state = AsyncMock()
    st.update_data = AsyncMock()
    return st


def _db_with_phone(phone):
    from uk_management_bot.database.models.user import User
    user = MagicMock(spec=User)
    user.phone = phone
    user.telegram_id = 123
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    return db


@pytest.mark.asyncio
async def test_apartment_selection_without_phone_asks_for_contact():
    from uk_management_bot.handlers.user_apartment_selection import start_apartment_selection

    msg, st = _message(), _state()
    await start_apartment_selection(msg, st, language="ru", _db=_db_with_phone(None))

    msg.answer.assert_called_once()
    assert msg.answer.call_args.args[0] == _t("onboarding.phone_required")
    kb = msg.answer.call_args.kwargs["reply_markup"]
    assert any(b.request_contact for row in kb.keyboard for b in row)
    st.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_profile_apartment_selection_without_phone_asks_for_contact():
    from uk_management_bot.handlers.user_apartment_selection import (
        start_apartment_selection_for_profile,
    )

    cb = MagicMock()
    cb.from_user = MagicMock(id=123)
    cb.message = _message()
    cb.answer = AsyncMock()
    st = _state()
    await start_apartment_selection_for_profile(cb, st, language="ru", _db=_db_with_phone(None))

    cb.message.answer.assert_called_once()
    assert cb.message.answer.call_args.args[0] == _t("onboarding.phone_required")
    assert st.set_state.await_count == 0 or st.set_state.await_args is None
