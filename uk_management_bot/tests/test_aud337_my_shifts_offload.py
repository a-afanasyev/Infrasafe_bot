"""AUD3-37 волна B1 — my_shifts на run_db: thread-путь и sync-юниты.

Харнес thread-пути: sqlite in-memory с StaticPool + check_same_thread=False —
одно соединение делится между main-потоком (сид) и worker-потоком
``asyncio.to_thread`` (юнит). Обычный sqlite in-memory дал бы worker'у ПУСТУЮ
базу (новое соединение = новая база) — это и есть причина, по которой тестовый
seam ``_db`` исполняет юнит синхронно, а thread-путь проверяется здесь
отдельным контуром с monkeypatch фабрики сессий.
"""

import threading
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database import session as session_mod
from uk_management_bot.database.session import Base, run_db
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.handlers import my_shifts as ms
from uk_management_bot.utils.datetime_utils import utc_now

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


def _executor(db, *, db_id=7, tg_id=70707):
    user = User(id=db_id, telegram_id=tg_id, username="ex", first_name="E", last_name="X",
                roles='["executor"]', active_role="executor", status="approved", language="ru")
    db.add(user)
    db.commit()
    return user


# ─────────────────────────── run_db как таковой ───────────────────────────

@pytest.mark.asyncio
async def test_run_db_without_db_executes_unit_off_the_event_loop(thread_sessions):
    """Thread-путь: юнит исполняется НЕ в потоке event loop и видит сид."""
    _executor(thread_sessions, db_id=1, tg_id=111)
    loop_thread = threading.get_ident()
    seen = {}

    def unit(s):
        seen["thread"] = threading.get_ident()
        return s.query(User).filter(User.telegram_id == 111).first().id

    result = await run_db(unit)
    assert result == 1
    assert seen["thread"] != loop_thread


@pytest.mark.asyncio
async def test_run_db_with_db_runs_synchronously_on_that_session(db):
    """Тестовый seam: с переданной сессией — тот же поток, та же сессия."""
    _executor(db, db_id=2, tg_id=222)
    loop_thread = threading.get_ident()
    seen = {}

    def unit(s):
        seen["thread"] = threading.get_ident()
        assert s is db
        return s.query(User).count()

    assert await run_db(unit, db=db) == 1
    assert seen["thread"] == loop_thread


@pytest.mark.asyncio
async def test_run_db_thread_path_closes_its_session(thread_sessions, monkeypatch):
    """Сессия thread-пути закрывается даже когда юнит бросает исключение."""
    closed = []
    real_factory = _Session

    def tracking_factory(*a, **kw):
        s = real_factory(*a, **kw)
        orig_close = s.close
        s.close = lambda: (closed.append(True), orig_close())[1]
        return s

    monkeypatch.setattr(session_mod, "SessionLocal", tracking_factory)

    with pytest.raises(RuntimeError):
        await run_db(lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
    assert closed == [True]


# ─────────────────────────── юниты: переходы статусов ───────────────────────────

def test_start_shift_unit_transitions_planned_to_active(db):
    user = _executor(db)
    shift = Shift(user_id=user.id, status="planned", start_time=utc_now(),
                  planned_start_time=utc_now(), planned_end_time=utc_now() + timedelta(hours=8))
    db.add(shift)
    db.commit()

    user_found, row = ms._start_shift(db, user.telegram_id, None, shift.id)
    assert user_found and row is not None
    assert row.status == "active"
    assert row.start_time is not None
    db.expire_all()
    assert db.query(Shift).get(shift.id).status == "active"


def test_start_shift_unit_rejects_foreign_or_started_shift(db):
    user = _executor(db)
    other = User(id=8, telegram_id=80808, username="o", first_name="O", last_name="T",
                 roles='["executor"]', active_role="executor", status="approved", language="ru")
    db.add(other)
    foreign = Shift(user_id=other.id, status="planned", start_time=utc_now(),
                    planned_start_time=utc_now())
    already = Shift(user_id=user.id, status="active", start_time=utc_now())
    db.add_all([foreign, already])
    db.commit()

    assert ms._start_shift(db, user.telegram_id, None, foreign.id) == (True, None)
    assert ms._start_shift(db, user.telegram_id, None, already.id) == (True, None)


def test_end_shift_unit_returns_summary_dto(db, monkeypatch):
    # sqlite ронит tzinfo на roundtrip (aware сид перечитывается naive), поэтому
    # аварийно-честный aware-aware прода здесь моделируется naive-naive той же
    # арифметики: utc_now юнита пиннится naive-значением.
    naive_now = utc_now().replace(tzinfo=None)
    monkeypatch.setattr(ms, "utc_now", lambda: naive_now)

    user = _executor(db)
    start = naive_now - timedelta(hours=3)
    shift = Shift(user_id=user.id, status="active", start_time=start, current_request_count=4)
    db.add(shift)
    db.commit()

    user_found, summary = ms._end_shift(db, user.telegram_id, None, shift.id)
    assert user_found and summary is not None
    assert summary["request_count"] == 4
    assert 2.9 < summary["actual_duration"] < 3.1
    db.expire_all()
    assert db.query(Shift).get(shift.id).status == "completed"


def test_units_report_missing_user_distinctly(db):
    """user_found=False (сигнал error_occurred) ≠ «смена не найдена»."""
    assert ms._start_shift(db, 424242, None, 1) == (False, None)
    assert ms._load_shift_details(db, 424242, None, 1) == (False, None)
    assert ms._load_transfer_menu_counts(db, 424242) is None


# ─────────────────────────── DTO-правило ───────────────────────────

def test_units_return_dtos_not_orm_rows(db):
    """Через границу потока ходят DTO: у ORM-строки за пределами юнита нет
    живой сессии, lazy-доступ дал бы DetachedInstanceError."""
    user = _executor(db)
    db.add(Shift(user_id=user.id, status="active", start_time=utc_now()))
    db.commit()

    _, _, rows = ms._load_current_shifts(db, user.telegram_id, None)
    assert rows and all(isinstance(r, ms._ShiftRow) for r in rows)

    _, details = ms._load_shift_details(db, user.telegram_id, None, rows[0].id)
    assert isinstance(details, ms._ShiftRow)


# ─────────────────────────── хендлер через thread-путь ───────────────────────────

@pytest.mark.asyncio
async def test_handle_current_shifts_renders_via_thread_path(thread_sessions):
    """Полный контур: хендлер без _db → run_db → worker-поток → рендер сида."""
    db = thread_sessions
    user = _executor(db, db_id=5, tg_id=50505)
    db.add(Shift(user_id=user.id, status="active", start_time=utc_now()))
    db.commit()

    cb = MagicMock()
    cb.from_user = MagicMock(id=50505)
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    state = MagicMock()
    state.set_state = AsyncMock()

    with patch.object(ms, "get_text", side_effect=lambda key, language="ru", **kw: key):
        await ms.handle_current_shifts(cb, state, language="ru", user=None, roles=["executor"])

    cb.message.edit_text.assert_awaited_once()
    answers = [c.args[0] for c in cb.answer.await_args_list if c.args]
    assert "my_shifts.handlers.error_occurred" not in answers
