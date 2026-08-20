"""Бот-флоу исправления ФИО: маршрутизация, право, запись, отказы.

Отдельно проверяется РАЗРЕШЕНИЕ роутинга: класс «до хендлера не доходит
апдейт» юнит-тестом не ловится (BUG-155 п.3, BUG-179), а здесь его два —
общий вход `rename_user_*` и legacy-вход `edit_employee_name_*`, который
раньше принадлежал другому роутеру.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import uk_management_bot.handlers.user_rename as rn
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.handlers.employee_management import router as employee_router
from uk_management_bot.handlers.user_management import router as user_mgmt_router
from uk_management_bot.handlers.user_rename import router as rename_router
from uk_management_bot.keyboards.user_management import get_user_actions_keyboard
from uk_management_bot.tests.handlers.routing_probe import make_callback, resolve_ctx

_engine = create_engine("sqlite:///:memory:", echo=False)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

#: Порядок как в main.py: общий флоу включается ПЕРЕД обоими разделами.
ROUTERS = [rename_router, user_mgmt_router, employee_router]

MANAGER_CTX = {"roles": ["manager"], "user": MagicMock(roles='["manager"]')}


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


def _user(db, *, uid, tg, first="Иванав", last="Иван", roles='["applicant"]'):
    u = User(id=uid, telegram_id=tg, first_name=first, last_name=last,
             roles=roles, status="approved", language="ru")
    db.add(u)
    db.commit()
    return u


def _callback(data: str):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = 1
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _message(text: str, from_id: int = 900):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = from_id
    msg.answer = AsyncMock()
    return msg


class _State:
    """Мини-FSM: реальный FSMContext здесь не нужен, нужен его контракт."""

    def __init__(self, data=None):
        self._data = dict(data or {})
        self.state = None
        self.cleared = False

    async def update_data(self, **kw):
        self._data.update(kw)

    async def get_data(self):
        return dict(self._data)

    async def set_state(self, state):
        self.state = state

    async def clear(self):
        self.cleared = True
        self._data = {}


# ═══════════════════════ маршрутизация ═══════════════════════


class TestRouting:

    def test_resident_entry_reaches_shared_flow(self):
        got = resolve_ctx(ROUTERS, make_callback("rename_user_res_42"), **MANAGER_CTX)
        assert got == ("uk_management_bot.handlers.user_rename", "handle_rename_start")

    def test_employee_entry_reaches_shared_flow(self):
        got = resolve_ctx(ROUTERS, make_callback("rename_user_emp_42"), **MANAGER_CTX)
        assert got == ("uk_management_bot.handlers.user_rename", "handle_rename_start")

    def test_legacy_employee_entry_still_reaches_flow(self):
        # Клавиатуры, отрисованные до этой правки, шлют старый callback —
        # он обязан открывать ту же форму, а не проваливаться в никуда.
        got = resolve_ctx(ROUTERS, make_callback("edit_employee_name_42"), **MANAGER_CTX)
        assert got == ("uk_management_bot.handlers.user_rename", "handle_rename_start")

    @pytest.mark.parametrize("data", [
        "rename_user_42",            # без origin
        "rename_user_xxx_42",        # чужой origin
        "rename_user_res_abc",       # не число
        "rename_user_res_42_extra",  # хвост
    ])
    def test_malformed_entries_are_not_taken(self, data):
        # callback_data присылает КЛИЕНТ: открытый префикс уже приводил к
        # перехвату чужих кнопок (BUG-179).
        assert resolve_ctx(ROUTERS, make_callback(data), **MANAGER_CTX) is None

    def test_employee_edit_menu_entry_not_shadowed(self):
        # `edit_employee_42` (меню) не должен уходить в форму ФИО.
        got = resolve_ctx(ROUTERS, make_callback("edit_employee_42"), **MANAGER_CTX)
        assert got is not None
        assert got[1] == "edit_employee_entry"


class TestResidentCardButton:

    def test_card_offers_rename(self):
        user = MagicMock()
        user.id = 42
        user.telegram_id = 4242
        user.status = "approved"
        user.roles = ["applicant"]
        kb = get_user_actions_keyboard(user, "ru")
        callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
        assert "rename_user_res_42" in callbacks


# ═══════════════════════ право ═══════════════════════


class TestAuthorization:

    @pytest.mark.asyncio
    async def test_non_manager_denied_on_entry(self, monkeypatch, db):
        monkeypatch.setattr(rn, "has_admin_access", lambda **kw: False)
        cb, state = _callback("rename_user_res_42"), _State()
        await rn.handle_rename_start(cb, state, roles=["applicant"], user=MagicMock(),
                                     language="ru", _db=db)
        cb.message.edit_text.assert_not_awaited()
        assert state.state is None

    @pytest.mark.asyncio
    async def test_role_lost_between_steps_is_refused(self, monkeypatch, db):
        # Состояние FSM переживает смену роли: форма открыта менеджером, ввод
        # приходит уже от разжалованного — писать нельзя.
        _user(db, uid=42, tg=4242)
        monkeypatch.setattr(rn, "has_admin_access", lambda **kw: False)
        msg = _message("Иванов Иван")
        state = _State({"target_user_id": 42, "origin": "res"})
        await rn.handle_rename_input(msg, state, roles=["applicant"], user=MagicMock(),
                                     language="ru", _db=db)
        assert db.get(User, 42).first_name == "Иванав"
        assert state.cleared is True

    @pytest.mark.asyncio
    async def test_privileged_target_refused_before_form(self, monkeypatch, db):
        _user(db, uid=43, tg=4343, roles='["manager"]')
        monkeypatch.setattr(rn, "has_admin_access", lambda **kw: True)
        cb, state = _callback("rename_user_emp_43"), _State()
        await rn.handle_rename_start(cb, state, roles=["manager"], user=MagicMock(),
                                     language="ru", _db=db)
        cb.message.edit_text.assert_not_awaited()
        assert state.state is None
        cb.answer.assert_awaited_once()
        assert cb.answer.await_args.kwargs.get("show_alert") is True


# ═══════════════════════ запись ═══════════════════════


class TestWrite:

    @pytest.mark.asyncio
    async def test_saves_and_audits(self, monkeypatch, db):
        _user(db, uid=42, tg=4242)
        _user(db, uid=9, tg=900, first="Мен", last="Еджер", roles='["manager"]')
        monkeypatch.setattr(rn, "has_admin_access", lambda **kw: True)

        msg = _message("  Иванов   Иван Иванович ")
        state = _State({"target_user_id": 42, "origin": "res"})
        await rn.handle_rename_input(msg, state, roles=["manager"], user=MagicMock(),
                                     language="ru", _db=db)

        fresh = db.get(User, 42)
        assert (fresh.first_name, fresh.last_name) == ("Иванов", "Иван Иванович")
        log = db.query(AuditLog).one()
        assert log.action == "user_renamed"
        assert log.user_id == 9          # актор найден по telegram_id сообщения
        assert log.telegram_user_id == 4242
        assert state.cleared is True

    @pytest.mark.asyncio
    async def test_back_button_returns_to_origin_card(self, monkeypatch, db):
        _user(db, uid=42, tg=4242)
        monkeypatch.setattr(rn, "has_admin_access", lambda **kw: True)

        for origin, expected in (("res", "back_to_user_details_42"),
                                 ("emp", "edit_employee_42")):
            msg = _message(f"Петров Пётр {origin}")
            await rn.handle_rename_input(
                msg, _State({"target_user_id": 42, "origin": origin}),
                roles=["manager"], user=MagicMock(), language="ru", _db=db,
            )
            kb = msg.answer.await_args.kwargs["reply_markup"]
            assert kb.inline_keyboard[0][0].callback_data == expected

    @pytest.mark.asyncio
    async def test_invalid_input_keeps_state_and_row(self, monkeypatch, db):
        _user(db, uid=42, tg=4242)
        monkeypatch.setattr(rn, "has_admin_access", lambda **kw: True)

        msg = _message("   ")
        state = _State({"target_user_id": 42, "origin": "res"})
        await rn.handle_rename_input(msg, state, roles=["manager"], user=MagicMock(),
                                     language="ru", _db=db)

        # Состояние НЕ сброшено: менеджер поправит ввод следующим сообщением.
        assert state.cleared is False
        assert db.get(User, 42).first_name == "Иванав"
        assert db.query(AuditLog).count() == 0
        # Ответ без клавиатуры «Назад» — это подсказка, а не финал.
        assert "reply_markup" not in msg.answer.await_args.kwargs

    @pytest.mark.asyncio
    async def test_unchanged_name_writes_no_audit(self, monkeypatch, db):
        _user(db, uid=42, tg=4242, first="Иванов", last="Иван")
        monkeypatch.setattr(rn, "has_admin_access", lambda **kw: True)

        msg = _message("Иванов Иван")
        await rn.handle_rename_input(
            msg, _State({"target_user_id": 42, "origin": "res"}),
            roles=["manager"], user=MagicMock(), language="ru", _db=db,
        )
        assert db.query(AuditLog).count() == 0

    @pytest.mark.asyncio
    async def test_missing_target_reports_not_found(self, monkeypatch, db):
        monkeypatch.setattr(rn, "has_admin_access", lambda **kw: True)
        msg = _message("Иванов Иван")
        state = _State({"target_user_id": 777, "origin": "res"})
        await rn.handle_rename_input(msg, state, roles=["manager"], user=MagicMock(),
                                     language="ru", _db=db)
        assert state.cleared is True
        assert db.query(AuditLog).count() == 0

    @pytest.mark.asyncio
    async def test_privileged_target_refused_at_write(self, monkeypatch, db):
        # Цель могли повысить между открытием формы и вводом — запись обязана
        # проверить заново, а не полагаться на преflight.
        _user(db, uid=44, tg=4444, roles='["admin"]')
        monkeypatch.setattr(rn, "has_admin_access", lambda **kw: True)
        msg = _message("Новое Имя")
        await rn.handle_rename_input(
            msg, _State({"target_user_id": 44, "origin": "emp"}),
            roles=["manager"], user=MagicMock(), language="ru", _db=db,
        )
        assert db.get(User, 44).first_name == "Иванав"
        assert db.query(AuditLog).count() == 0


class TestEscaping:

    @pytest.mark.asyncio
    async def test_html_in_name_is_escaped(self, monkeypatch, db):
        # Бот шлёт с parse_mode=HTML: неэкранированное имя ломает разметку
        # (а в худшем случае подделывает её).
        _user(db, uid=42, tg=4242, first="<b>Ваня", last="</b>")
        monkeypatch.setattr(rn, "has_admin_access", lambda **kw: True)

        cb, state = _callback("rename_user_res_42"), _State()
        await rn.handle_rename_start(cb, state, roles=["manager"], user=MagicMock(),
                                     language="ru", _db=db)

        text = cb.message.edit_text.await_args.args[0]
        assert "&lt;b&gt;Ваня" in text
        assert "<b>Ваня" not in text
