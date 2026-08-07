"""AUD3-37 волна B4 — employee_management на run_db: sync-юниты и контуры.

Харнес thread-пути — как в волне B1 (test_aud337_my_shifts_offload.py):
sqlite in-memory с StaticPool + check_same_thread=False, чтобы worker-поток
``asyncio.to_thread`` видел сид main-потока. Юнит-тесты гоняются на реальной
sqlite-сессии через тестовый seam ``_db`` (sync-исполнение).
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database import session as session_mod
from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.handlers import employee_management as emp
from uk_management_bot.utils.helpers import get_text

_engine = create_engine(
    "sqlite:///:memory:",
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def thread_sessions(db, monkeypatch):
    """run_db без db открывает сессию через session_scope → SessionLocal;
    подменяем фабрику на StaticPool-движок теста (данные сида видны)."""
    monkeypatch.setattr(session_mod, "SessionLocal", _Session)
    return db


def _user(db, *, db_id, tg_id, roles='["executor"]', status="approved",
          first_name="Иван", last_name="Петров", username=None, phone=None,
          specialization=None, active_role="executor"):
    user = User(id=db_id, telegram_id=tg_id, username=username,
                first_name=first_name, last_name=last_name, phone=phone,
                roles=roles, active_role=active_role, status=status,
                specialization=specialization, language="ru")
    db.add(user)
    db.commit()
    return user


def _callback(data, tg_id=1):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = tg_id
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    return cb


def _state(data=None):
    st = MagicMock()
    st.get_data = AsyncMock(return_value=data or {})
    st.update_data = AsyncMock()
    st.set_state = AsyncMock()
    st.clear = AsyncMock()
    return st


# ─────────────────────────── DTO-правило юнитов ───────────────────────────

def test_load_employee_returns_dto_not_orm(db):
    _user(db, db_id=5, tg_id=555, phone="+998901112233")
    row = emp._load_employee(db, 5)
    assert isinstance(row, emp._EmployeeRow)
    assert not isinstance(row, User)
    assert (row.id, row.telegram_id, row.phone) == (5, 555, "+998901112233")
    assert emp._load_employee(db, 999) is None


def test_load_employees_page_wraps_rows_in_dtos(db):
    _user(db, db_id=1, tg_id=101)
    _user(db, db_id=2, tg_id=102, first_name="Олег", last_name=None)
    data = emp._load_employees_page(db, "active", 1)
    assert data["total_employees"] == 2
    assert data["current_page"] == 1
    assert all(isinstance(r, emp._EmployeeRow) for r in data["employees"])


def test_search_employees_returns_dtos(db):
    _user(db, db_id=1, tg_id=101, first_name="Иван")
    _user(db, db_id=2, tg_id=102, first_name="Олег", last_name="Смирнов")
    rows = emp._search_employees(db, "Смирнов")
    assert [r.id for r in rows] == [2]
    assert all(isinstance(r, emp._EmployeeRow) for r in rows)


# ─────────────────────────── мутационные юниты ───────────────────────────

def test_update_employee_name_splits_and_commits(db):
    _user(db, db_id=5, tg_id=555)
    assert emp._update_employee_name(db, 5, "Анна Каренина Облонская") is True
    fresh = db.get(User, 5)
    assert (fresh.first_name, fresh.last_name) == ("Анна", "Каренина Облонская")

    assert emp._update_employee_name(db, 5, "Мононим") is True
    fresh = db.get(User, 5)
    assert (fresh.first_name, fresh.last_name) == ("Мононим", None)

    assert emp._update_employee_name(db, 999, "Никто") is False


def test_update_employee_phone(db):
    _user(db, db_id=5, tg_id=555)
    assert emp._update_employee_phone(db, 5, "+998900000000") is True
    assert db.get(User, 5).phone == "+998900000000"
    assert emp._update_employee_phone(db, 999, "+1") is False


def test_apply_role_change_updates_roles_active_role_and_audit(db):
    _user(db, db_id=9, tg_id=900, roles='["manager"]', active_role="manager")   # actor
    _user(db, db_id=5, tg_id=555, roles='["executor"]', active_role="executor")  # target

    outcome = emp._apply_role_change(db, 900, 5, ["manager"], "коммент")
    assert outcome == "ok"

    fresh = db.get(User, 5)
    assert json.loads(fresh.roles) == ["manager"]
    # инвариант: active_role всегда ∈ roles — executor выпал, переводим на первую
    assert fresh.active_role == "manager"

    audit = db.query(AuditLog).filter(AuditLog.action == "role_change").one()
    details = json.loads(audit.details)
    assert details["old_roles"] == ["executor"]
    assert details["new_roles"] == ["manager"]
    assert audit.user_id == 9
    assert audit.telegram_user_id == 555


def test_apply_role_change_missing_actor_or_target(db):
    _user(db, db_id=9, tg_id=900)
    assert emp._apply_role_change(db, 111, 5, ["manager"], "c") == "no_actor"
    assert emp._apply_role_change(db, 900, 999, ["manager"], "c") == "no_target"


def test_apply_specialization_change_canon_parse_and_audit(db):
    _user(db, db_id=9, tg_id=900)                                    # actor
    _user(db, db_id=5, tg_id=555, specialization='["plumber ", ""]')  # target

    outcome = emp._apply_specialization_change(db, 900, 5, ["electrician"], "c")
    assert outcome == "ok"

    fresh = db.get(User, 5)
    assert json.loads(fresh.specialization) == ["electrician"]

    audit = db.query(AuditLog).filter(AuditLog.action == "specialization_change").one()
    details = json.loads(audit.details)
    # AUD5-CODE-8: старые специализации через канон-парсер (стрип + фильтр пустых)
    assert details["old_specializations"] == ["plumber"]
    assert details["new_specializations"] == ["electrician"]

    assert emp._apply_specialization_change(db, 111, 5, [], "c") == "no_actor"
    assert emp._apply_specialization_change(db, 900, 999, [], "c") == "no_target"


def test_moderate_employee_routes_to_auth_service(db, monkeypatch):
    _user(db, db_id=9, tg_id=900)
    auth = MagicMock()
    auth.approve_user.return_value = True
    monkeypatch.setattr(emp, "AuthService", lambda s: auth)

    assert emp._moderate_employee(db, 900, 5, "approve_user", "коммент") == "ok"
    auth.approve_user.assert_called_once_with(5, 9, "коммент")

    auth.approve_user.return_value = False
    assert emp._moderate_employee(db, 900, 5, "approve_user", "коммент") == "fail"

    assert emp._moderate_employee(db, 111, 5, "approve_user", "коммент") == "no_actor"


# ─────────────────────────── контуры хендлеров ───────────────────────────

@pytest.mark.asyncio
async def test_show_employee_list_renders_via_thread_path(thread_sessions, monkeypatch):
    """Полный контур без seam: юнит уходит в worker-поток и видит сид."""
    monkeypatch.setattr(emp, "has_admin_access", lambda **kw: True)
    _user(thread_sessions, db_id=1, tg_id=101, first_name="Иван")

    callback = _callback("employee_mgmt_list_active_1")
    await emp.show_employee_list(callback, roles=["manager"], user=MagicMock(), language="ru")

    callback.message.edit_text.assert_awaited_once()
    kb = callback.message.edit_text.await_args.kwargs["reply_markup"]
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "employee_mgmt_employee_1" in callbacks
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_role_change_comment_full_contour_on_seam(db, monkeypatch):
    monkeypatch.setattr(emp, "has_admin_access", lambda **kw: True)
    _user(db, db_id=9, tg_id=900, roles='["manager"]', active_role="manager")
    _user(db, db_id=5, tg_id=555, roles='["executor"]', active_role="executor")

    message = MagicMock()
    message.text = "повышение"
    message.from_user.id = 900
    message.answer = AsyncMock()
    state = _state({"target_employee_id": 5, "current_roles": ["manager", "executor"]})

    await emp.process_role_change_comment(message, state, language="ru", _db=db)

    fresh = db.get(User, 5)
    assert json.loads(fresh.roles) == ["manager", "executor"]
    state.clear.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert text == get_text("employee_mgmt.handlers.roles_updated", language="ru").format(
        roles="manager, executor")


@pytest.mark.asyncio
async def test_return_to_employee_info_renders_card_from_dto(db):
    _user(db, db_id=5, tg_id=555, phone="+998901112233", roles='["executor"]')

    callback = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    assert await emp._return_to_employee_info(callback, 5, "ru", _db=db) is True
    callback.message.edit_text.assert_awaited_once()
    text = callback.message.edit_text.await_args.args[0]
    assert "Иван Петров" in text
    assert "+998901112233" in text
    callback.answer.assert_not_awaited()  # render-only: caller owns the answer
