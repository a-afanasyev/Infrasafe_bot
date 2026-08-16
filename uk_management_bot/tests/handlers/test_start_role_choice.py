"""Экран выбора «житель / сотрудник» после /start.

Зачем: ссылка-приглашение сотрудника — статический `https://t.me/<бот>` без
параметров, роль едет отдельным 246-символьным токеном. Человек жмёт «Начать»,
попадает в обычный /start и молча регистрируется ЖИТЕЛЕМ. Замерено на проде
16.08.2026: 12 выданных токенов, 0 погашенных, двое сотрудников в жителях.

Развилка показывается ТОЛЬКО на первом входе и ТОЛЬКО из cmd_start — /menu
переспрашивать роль не должен, а прямые вызовы handle_regular_start (на них
стоят test_handler_base.py и test_base_register_button.py) обязаны сохранить
прежнее поведение.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup
from aiogram.types import User as TgUser


# ─── Фабрики (стиль test_handler_base.py) ───────────────────────────────────

def _make_tg_user(user_id=123):
    u = MagicMock(spec=TgUser)
    u.id = user_id
    u.first_name = "Test"
    u.last_name = "User"
    u.username = "testuser"
    return u


def _make_message(text="", user_id=123):
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = _make_tg_user(user_id)
    msg.answer = AsyncMock()
    msg.bot = MagicMock()
    return msg


def _make_callback(data="", user_id=123):
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = _make_tg_user(user_id)
    cb.answer = AsyncMock()
    cb.message = _make_message(user_id=user_id)
    cb.message.edit_reply_markup = AsyncMock()
    return cb


def _make_state():
    st = AsyncMock()
    st.get_data = AsyncMock(return_value={})
    st.update_data = AsyncMock()
    st.set_state = AsyncMock()
    st.clear = AsyncMock()
    return st


def _make_db_user(*, status="pending", phone=None, roles='["applicant"]', apartments=None):
    user = MagicMock()
    user.id = 1
    user.telegram_id = 123
    user.status = status
    user.phone = phone
    user.roles = roles
    user.active_role = "applicant"
    user.user_apartments = apartments if apartments is not None else []
    return user


def _apartment(status="pending"):
    ua = MagicMock()
    ua.status = status
    return ua


def _ctx(**kwargs):
    """_MenuContext с дефолтами «первый вход»."""
    from uk_management_bot.handlers.base import _MenuContext

    defaults = dict(
        status="pending",
        phone=None,
        has_approved_apartment=False,
        has_any_apartment=False,
        db_roles=["applicant"],
        active_role="applicant",
    )
    defaults.update(kwargs)
    return _MenuContext(**defaults)


def _callback_datas(markup):
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


# ─── 1. Предикат развилки ───────────────────────────────────────────────────

class TestNeedsRoleChoice:
    def test_first_entry_needs_choice(self):
        from uk_management_bot.handlers.base import _needs_role_choice

        assert _needs_role_choice(_ctx()) is True

    @pytest.mark.parametrize("override, why", [
        ({"status": "approved"}, "уже одобрен"),
        ({"status": "blocked"}, "заблокирован"),
        ({"phone": "+998901234567"}, "телефон уже оставлен"),
        ({"has_any_apartment": True}, "заявка на квартиру подана (любой статус)"),
        ({"has_any_apartment": True, "has_approved_apartment": True}, "квартира одобрена"),
        ({"db_roles": ["applicant", "executor"]}, "роль сотрудника уже выдана"),
        ({"db_roles": ["manager"]}, "менеджер"),
    ])
    def test_not_first_entry(self, override, why):
        from uk_management_bot.handlers.base import _needs_role_choice

        assert _needs_role_choice(_ctx(**override)) is False, why

    def test_pending_apartment_does_not_leak(self):
        """Житель подал заявку на квартиру и не дал телефон — вопрос «кто вы»
        второй раз задавать нельзя. has_approved_apartment такого не ловит."""
        from uk_management_bot.handlers.base import _menu_context, _needs_role_choice

        user = _make_db_user(apartments=[_apartment("pending")])
        ctx = _menu_context(user)

        assert ctx.has_approved_apartment is False
        assert ctx.has_any_apartment is True
        assert _needs_role_choice(ctx) is False


# ─── 2-4. Врезка в /start ───────────────────────────────────────────────────

class TestStartFork:
    @pytest.mark.asyncio
    async def test_cmd_start_offers_choice_to_new_user(self):
        from uk_management_bot.handlers.base import cmd_start

        msg = _make_message(text="/start")
        state = _make_state()

        with patch("uk_management_bot.handlers.base.AuthService") as MockAuth:
            MockAuth.return_value.get_or_create_user_sync = MagicMock(return_value=_make_db_user())
            await cmd_start(msg, state, _db=MagicMock())

        msg.answer.assert_called_once()
        markup = msg.answer.call_args.kwargs.get("reply_markup")
        assert isinstance(markup, InlineKeyboardMarkup)
        assert sorted(_callback_datas(markup)) == ["start_role:employee", "start_role:resident"]

    @pytest.mark.asyncio
    async def test_cmd_start_skips_choice_when_phone_already_given(self):
        """Профиль начат — развилки быть не должно, только обычный онбординг."""
        from uk_management_bot.handlers.base import cmd_start

        msg = _make_message(text="/start")
        state = _make_state()

        with patch("uk_management_bot.handlers.base.AuthService") as MockAuth:
            MockAuth.return_value.get_or_create_user_sync = MagicMock(
                return_value=_make_db_user(phone="+998901234567")
            )
            await cmd_start(msg, state, _db=MagicMock())

        markup = msg.answer.call_args.kwargs.get("reply_markup")
        assert isinstance(markup, ReplyKeyboardMarkup)

    @pytest.mark.asyncio
    async def test_handle_regular_start_without_flag_never_offers_choice(self):
        """Контракт, на котором стоят test_handler_base.py и
        test_base_register_button.py: прямой вызов ведёт себя как раньше."""
        from uk_management_bot.handlers.base import handle_regular_start

        msg = _make_message()

        with patch("uk_management_bot.handlers.base.AuthService") as MockAuth:
            MockAuth.return_value.get_or_create_user_sync = MagicMock(return_value=_make_db_user())
            await handle_regular_start(msg, _db=MagicMock())

        markup = msg.answer.call_args.kwargs.get("reply_markup")
        assert isinstance(markup, ReplyKeyboardMarkup)


# ─── 5-6, 11. Колбэки экрана ────────────────────────────────────────────────

class TestChoiceCallbacks:
    @pytest.mark.asyncio
    async def test_resident_shows_existing_onboarding_screen(self, monkeypatch):
        """Житель получает ТОТ ЖЕ экран, включая WebApp-кнопку регистрации:
        собственная сборка экрана незаметно потеряла бы её."""
        from uk_management_bot.handlers import base
        from uk_management_bot.handlers.start_role_choice import choose_resident

        monkeypatch.setattr(base.settings, "FRONTEND_URL", "https://example.test")
        cb = _make_callback("start_role:resident")
        state = _make_state()

        with patch("uk_management_bot.handlers.base.AuthService") as MockAuth:
            MockAuth.return_value.get_or_create_user_sync = MagicMock(return_value=_make_db_user())
            await choose_resident(cb, state, _db=MagicMock())

        markup = cb.message.answer.call_args.kwargs.get("reply_markup")
        assert isinstance(markup, ReplyKeyboardMarkup)
        webapp_urls = [
            btn.web_app.url
            for row in markup.keyboard for btn in row
            if getattr(btn, "web_app", None) is not None
        ]
        assert any(url.endswith("/register") for url in webapp_urls)
        state.set_state.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_employee_asks_for_token_without_touching_rate_limiter(self):
        """Лимитер считает КАЖДУЮ проверку (3 попытки / 600 c). Тратить их на
        нажатие кнопки нельзя — человек заблокирует себе своё же приглашение."""
        from uk_management_bot.handlers.start_role_choice import choose_employee
        from uk_management_bot.states.registration import RegistrationStates

        cb = _make_callback("start_role:employee")
        state = _make_state()

        with patch("uk_management_bot.handlers.auth.InviteRateLimiter.is_allowed",
                   new=AsyncMock(return_value=True)) as limiter:
            await choose_employee(cb, state)

        state.set_state.assert_awaited_with(RegistrationStates.waiting_for_invite_token)
        cb.message.answer.assert_awaited()
        limiter.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_token_button_returns_to_resident_flow(self):
        from uk_management_bot.handlers.start_role_choice import no_invite_token

        cb = _make_callback("start_role:no_token")
        state = _make_state()

        with patch("uk_management_bot.handlers.base.AuthService") as MockAuth:
            MockAuth.return_value.get_or_create_user_sync = MagicMock(return_value=_make_db_user())
            await no_invite_token(cb, state, _db=MagicMock())

        state.clear.assert_awaited()
        cb.message.answer.assert_awaited()


# ─── 7. Извлечение токена ───────────────────────────────────────────────────

_TOKEN = "invite_v1:eyJyb2xlIjoiZXhlY3V0b3IifQ." + "a" * 64


class TestTokenExtraction:
    @pytest.mark.parametrize("raw, why", [
        (_TOKEN, "голый токен"),
        (f"/join {_TOKEN}", "скопирована команда целиком"),
        (f"`{_TOKEN}`", "токен в бэктиках — ровно так его печатает инструкция менеджера"),
        (f"  {_TOKEN}  ", "пробелы по краям"),
        (f"Вот ваш код:\n{_TOKEN}\nждём вас", "форвард сообщения менеджера целиком"),
        (f"{_TOKEN}\n", "перевод строки от мобильной вставки"),
        (f"Invite_v1:{_TOKEN.split(':', 1)[1]}", "автокапитализация iOS"),
    ])
    def test_extracts_same_token(self, raw, why):
        from uk_management_bot.handlers.start_role_choice import extract_invite_token

        assert extract_invite_token(raw) == _TOKEN, why

    @pytest.mark.parametrize("raw", ["привет", "", "/menu", "/login", "12345", None])
    def test_rejects_non_token(self, raw):
        from uk_management_bot.handlers.start_role_choice import extract_invite_token

        assert extract_invite_token(raw) is None


# ─── 8-10. Шаг приёма токена ────────────────────────────────────────────────

class TestReceiveToken:
    @pytest.mark.asyncio
    async def test_passes_extracted_token_to_shared_flow(self):
        from uk_management_bot.handlers import start_role_choice

        msg = _make_message(text=f"/join {_TOKEN}")
        state = _make_state()

        with patch.object(start_role_choice, "start_invite_registration",
                          new=AsyncMock(return_value=("ok", "executor"))) as shared:
            await start_role_choice.receive_invite_token(msg, state, _db=MagicMock())

        assert shared.await_args.args[2] == _TOKEN
        state.clear.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_garbage_keeps_state_and_never_calls_shared_flow(self):
        from uk_management_bot.handlers import start_role_choice

        msg = _make_message(text="привет")
        state = _make_state()

        with patch.object(start_role_choice, "start_invite_registration",
                          new=AsyncMock()) as shared:
            await start_role_choice.receive_invite_token(msg, state, _db=MagicMock())

        shared.assert_not_awaited()
        state.clear.assert_not_awaited()
        msg.answer.assert_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("text", ["❌ Отмена", "/menu"])
    async def test_escape_hatches_leave_the_state(self, text):
        """Состояние ввода съедает любой текст — без выхода человек заперт."""
        from uk_management_bot.handlers import start_role_choice

        msg = _make_message(text=text)
        state = _make_state()

        with patch.object(start_role_choice, "start_invite_registration",
                          new=AsyncMock()) as shared:
            await start_role_choice.receive_invite_token(msg, state, _db=MagicMock())

        shared.assert_not_awaited()
        state.clear.assert_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("verdict, should_clear", [
        ("invalid", False),
        ("rate_limited", False),
        ("error", False),
        ("already_registered", True),
        ("registration_pending", True),
    ])
    async def test_verdict_policy(self, verdict, should_clear):
        from uk_management_bot.handlers import start_role_choice

        msg = _make_message(text=_TOKEN)
        state = _make_state()

        with patch.object(start_role_choice, "start_invite_registration",
                          new=AsyncMock(return_value=(verdict, None))):
            await start_role_choice.receive_invite_token(msg, state, _db=MagicMock())

        assert state.clear.await_count == (1 if should_clear else 0)

    @pytest.mark.asyncio
    async def test_employee_branch_asks_for_staff_only_check(self):
        """Ветка сотрудника обязана просить staff_only: роль «Заявитель» есть в
        клавиатуре инвайтов (keyboards/admin.py:83), а process_invite_join_sync
        для неё ничего не добавляет — человек прошёл бы анкету, сжёг токен и
        остался жителем, ровно в той яме, ради которой всё и делается."""
        from uk_management_bot.handlers import start_role_choice

        msg = _make_message(text=_TOKEN)
        state = _make_state()

        with patch.object(start_role_choice, "start_invite_registration",
                          new=AsyncMock(return_value=("ok", "executor"))) as shared:
            await start_role_choice.receive_invite_token(msg, state, _db=MagicMock())

        assert shared.await_args.kwargs.get("staff_only") is True

    @pytest.mark.asyncio
    async def test_applicant_token_returns_user_to_resident_flow(self):
        from uk_management_bot.handlers import start_role_choice

        msg = _make_message(text=_TOKEN)
        state = _make_state()

        with patch.object(start_role_choice, "start_invite_registration",
                          new=AsyncMock(return_value=("applicant_token", "applicant"))), \
             patch("uk_management_bot.handlers.base.AuthService") as MockAuth:
            MockAuth.return_value.get_or_create_user_sync = MagicMock(return_value=_make_db_user())
            await start_role_choice.receive_invite_token(msg, state, _db=MagicMock())

        state.clear.assert_awaited()
        markup = msg.answer.call_args.kwargs.get("reply_markup")
        assert isinstance(markup, ReplyKeyboardMarkup), "должен вернуться экран жителя"


# ─── 12. Локали ─────────────────────────────────────────────────────────────

class TestLocales:
    KEYS = [
        "title", "hint", "btn_resident", "btn_employee",
        "token_prompt", "btn_no_token", "no_token_hint",
        "token_not_recognized", "applicant_token",
    ]

    def _load(self, lang):
        path = (Path(__file__).resolve().parents[2] / "config" / "locales" / f"{lang}.json")
        return json.loads(path.read_text(encoding="utf-8"))

    @pytest.mark.parametrize("lang", ["ru", "uz"])
    def test_all_keys_present(self, lang):
        section = self._load(lang).get("start_role", {})
        missing = [k for k in self.KEYS if not section.get(k)]
        assert not missing, f"{lang}.json: нет ключей {missing}"

    def test_translations_differ(self):
        """Скопированный ru-текст в uz.json — самый частый способ «локализовать»."""
        ru, uz = self._load("ru")["start_role"], self._load("uz")["start_role"]
        same = [k for k in self.KEYS if ru[k] == uz[k]]
        assert not same, f"uz не переведён для {same}"
