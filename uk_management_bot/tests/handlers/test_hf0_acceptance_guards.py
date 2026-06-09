"""HF-0: тесты приёмки/возврата заявителем — предикат awaiting_applicant + guard'ы.

Закрывает два verified-бага:
1. Подтверждённые менеджером заявки (Выполнена+manager_confirmed) не попадали
   в список приёмки (фильтр только status=="Исполнено").
2. Guard'ы дырявые: save_rating не проверял состояние заявки (принять можно
   было что угодно поддельным callback'ом); process_return_request не проверял
   ни владельца, ни состояние.

Семантика прав (HF-0): can_accept = владелец ИЛИ одобренный сосед по квартире
заявки (текущая семантика списка); can_return = только владелец.
Возвращённые (Исполнено+is_returned=True) НЕ доступны заявителю до reconfirm.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.rating import Rating
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_EXECUTED,
)
from uk_management_bot.utils.workflow_predicates import (
    awaiting_applicant_clause,
    can_accept,
    can_return,
    is_awaiting_applicant,
)

OWNER_TG = 111
NEIGHBOR_TG = 222
STRANGER_TG = 333
APARTMENT_ID = 10


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    session.add_all([
        User(id=1, telegram_id=OWNER_TG, first_name="Owner",
             role="applicant", roles='["applicant"]', status="approved", language="ru"),
        User(id=2, telegram_id=NEIGHBOR_TG, first_name="Neighbor",
             role="applicant", roles='["applicant"]', status="approved", language="ru"),
        User(id=3, telegram_id=STRANGER_TG, first_name="Stranger",
             role="applicant", roles='["applicant"]', status="approved", language="ru"),
        # Одобренное соседство: neighbor ↔ квартира заявки владельца
        UserApartment(user_id=2, apartment_id=APARTMENT_ID, status="approved"),
    ])
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _mk_request(db, number, status, *, manager_confirmed=False, is_returned=False,
                user_id=1, apartment_id=APARTMENT_ID):
    req = Request(
        request_number=number,
        user_id=user_id,
        category="Электрика",
        status=status,
        description="test",
        urgency="low",
        apartment_id=apartment_id,
        manager_confirmed=manager_confirmed,
        is_returned=is_returned,
        # Колонка updated_at заполняется только onupdate — в хендлере списка
        # по ней strftime, поэтому фикстура задаёт значение явно.
        updated_at=datetime.now(timezone.utc),
    )
    db.add(req)
    db.commit()
    return req


# ---------------------------------------------------------------------------
# Предикат: Python-форма
# ---------------------------------------------------------------------------

class TestIsAwaitingApplicant:
    @pytest.mark.parametrize(
        "status,confirmed,returned,expected",
        [
            (REQUEST_STATUS_COMPLETED, False, False, True),    # Исполнено (web-канон)
            (REQUEST_STATUS_COMPLETED, True, False, True),     # Исполнено + confirmed
            (REQUEST_STATUS_COMPLETED, False, True, False),    # возвращена — ЖДЁТ менеджера
            (REQUEST_STATUS_EXECUTED, True, False, True),      # Telegram-композит
            (REQUEST_STATUS_EXECUTED, False, False, False),    # не подтверждена
            (REQUEST_STATUS_EXECUTED, True, True, False),      # подтверждена, но возвращена
            ("В работе", False, False, False),
            ("Новая", False, False, False),
            (REQUEST_STATUS_APPROVED, False, False, False),    # уже принята
        ],
    )
    def test_truth_table(self, status, confirmed, returned, expected):
        req = SimpleNamespace(status=status, manager_confirmed=confirmed,
                              is_returned=returned)
        assert is_awaiting_applicant(req) is expected


# ---------------------------------------------------------------------------
# Предикат: SQL-форма (паритет с Python-формой)
# ---------------------------------------------------------------------------

class TestAwaitingApplicantClause:
    def test_sql_matches_python(self, db):
        fixtures = [
            ("260610-001", REQUEST_STATUS_COMPLETED, False, False),
            ("260610-002", REQUEST_STATUS_COMPLETED, False, True),
            ("260610-003", REQUEST_STATUS_EXECUTED, True, False),
            ("260610-004", REQUEST_STATUS_EXECUTED, False, False),
            ("260610-005", "В работе", False, False),
            ("260610-006", REQUEST_STATUS_APPROVED, False, False),
        ]
        for number, status, confirmed, returned in fixtures:
            _mk_request(db, number, status,
                        manager_confirmed=confirmed, is_returned=returned)

        sql_numbers = {
            r.request_number
            for r in db.query(Request).filter(awaiting_applicant_clause()).all()
        }
        py_numbers = {
            r.request_number
            for r in db.query(Request).all()
            if is_awaiting_applicant(r)
        }
        assert sql_numbers == py_numbers == {"260610-001", "260610-003"}


# ---------------------------------------------------------------------------
# Право-проверки
# ---------------------------------------------------------------------------

class TestPermissions:
    def test_can_accept_owner(self):
        req = SimpleNamespace(user_id=1, apartment_id=None)
        assert can_accept(req, SimpleNamespace(id=1), frozenset())

    def test_can_accept_approved_neighbor(self):
        req = SimpleNamespace(user_id=1, apartment_id=APARTMENT_ID)
        assert can_accept(req, SimpleNamespace(id=2), frozenset({APARTMENT_ID}))

    def test_can_accept_stranger_rejected(self):
        req = SimpleNamespace(user_id=1, apartment_id=APARTMENT_ID)
        assert not can_accept(req, SimpleNamespace(id=3), frozenset())

    def test_can_return_owner_only(self):
        req = SimpleNamespace(user_id=1, apartment_id=APARTMENT_ID)
        assert can_return(req, SimpleNamespace(id=1))
        assert not can_return(req, SimpleNamespace(id=2))  # сосед НЕ возвращает


# ---------------------------------------------------------------------------
# Список приёмки: dual-filter + исключение возвращённых
# ---------------------------------------------------------------------------

def _mk_message(telegram_id):
    msg = MagicMock()
    msg.from_user.id = telegram_id
    msg.answer = AsyncMock()
    return msg


class TestPendingAcceptanceList:
    @pytest.mark.asyncio
    async def test_list_includes_confirmed_and_excludes_returned(self, db):
        from uk_management_bot.handlers.request_acceptance import (
            show_pending_acceptance_requests,
        )

        _mk_request(db, "260610-101", REQUEST_STATUS_COMPLETED)             # видна
        _mk_request(db, "260610-102", REQUEST_STATUS_EXECUTED,
                    manager_confirmed=True)                                  # видна (БАГ №1)
        _mk_request(db, "260610-103", REQUEST_STATUS_COMPLETED,
                    is_returned=True)                                        # НЕ видна (БАГ №2)
        _mk_request(db, "260610-104", REQUEST_STATUS_EXECUTED)              # НЕ видна

        msg = _mk_message(OWNER_TG)
        await show_pending_acceptance_requests(msg, db=db)

        msg.answer.assert_awaited()
        text = msg.answer.await_args.args[0]
        assert "260610-101" in text
        assert "260610-102" in text, "Выполнена+manager_confirmed must be listed"
        assert "260610-103" not in text, "returned request must NOT be listed"
        assert "260610-104" not in text


# ---------------------------------------------------------------------------
# Accept-guard (save_rating)
# ---------------------------------------------------------------------------

def _mk_rate_callback(request_number, telegram_id, rating=5):
    cb = MagicMock()
    cb.from_user.id = telegram_id
    cb.data = f"rate_{request_number}_{rating}"
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    return cb


NOTIFY = "uk_management_bot.handlers.request_acceptance.async_notify_request_status_changed"


class TestAcceptGuard:
    @pytest.mark.asyncio
    async def test_owner_accepts_confirmed_request(self, db):
        """Выполнена+manager_confirmed принимается (раньше её не было в списке)."""
        from uk_management_bot.handlers.request_acceptance import save_rating

        req = _mk_request(db, "260610-201", REQUEST_STATUS_EXECUTED,
                          manager_confirmed=True)
        cb = _mk_rate_callback(req.request_number, OWNER_TG)
        with patch(NOTIFY, new=AsyncMock()):
            await save_rating(cb, db=db)

        db.refresh(req)
        assert req.status == REQUEST_STATUS_APPROVED
        assert db.query(Rating).filter_by(request_number=req.request_number).count() == 1

    @pytest.mark.asyncio
    async def test_returned_request_cannot_be_accepted(self, db):
        """Возвращённая (Исполнено+is_returned) НЕ принимается до reconfirm."""
        from uk_management_bot.handlers.request_acceptance import save_rating

        req = _mk_request(db, "260610-202", REQUEST_STATUS_COMPLETED,
                          is_returned=True)
        cb = _mk_rate_callback(req.request_number, OWNER_TG)
        with patch(NOTIFY, new=AsyncMock()):
            await save_rating(cb, db=db)

        db.refresh(req)
        assert req.status == REQUEST_STATUS_COMPLETED, "status must not change"
        assert db.query(Rating).count() == 0
        cb.answer.assert_awaited()
        assert cb.answer.await_args.kwargs.get("show_alert") is True

    @pytest.mark.asyncio
    async def test_forged_callback_in_progress_rejected(self, db):
        """Поддельный callback rate_* на заявку 'В работе' — отклонён."""
        from uk_management_bot.handlers.request_acceptance import save_rating

        req = _mk_request(db, "260610-203", "В работе")
        cb = _mk_rate_callback(req.request_number, OWNER_TG)
        with patch(NOTIFY, new=AsyncMock()):
            await save_rating(cb, db=db)

        db.refresh(req)
        assert req.status == "В работе"
        assert db.query(Rating).count() == 0

    @pytest.mark.asyncio
    async def test_stranger_cannot_accept(self, db):
        from uk_management_bot.handlers.request_acceptance import save_rating

        req = _mk_request(db, "260610-204", REQUEST_STATUS_COMPLETED)
        cb = _mk_rate_callback(req.request_number, STRANGER_TG)
        with patch(NOTIFY, new=AsyncMock()):
            await save_rating(cb, db=db)

        db.refresh(req)
        assert req.status == REQUEST_STATUS_COMPLETED
        assert db.query(Rating).count() == 0

    @pytest.mark.asyncio
    async def test_approved_neighbor_can_accept(self, db):
        """Сосед с одобренной квартирой принимает (семантика списка сохранена)."""
        from uk_management_bot.handlers.request_acceptance import save_rating

        req = _mk_request(db, "260610-205", REQUEST_STATUS_COMPLETED)
        cb = _mk_rate_callback(req.request_number, NEIGHBOR_TG)
        with patch(NOTIFY, new=AsyncMock()):
            await save_rating(cb, db=db)

        db.refresh(req)
        assert req.status == REQUEST_STATUS_APPROVED


# ---------------------------------------------------------------------------
# Return-guard (process_return_request)
# ---------------------------------------------------------------------------

def _mk_state(request_number):
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "request_number": request_number,
        "return_reason": "Не устранено",
        "return_media": [],
    })
    state.clear = AsyncMock()
    return state


class TestReturnGuard:
    @pytest.mark.asyncio
    async def test_owner_returns_completed_request(self, db):
        from uk_management_bot.handlers.request_acceptance import (
            process_return_request,
        )

        req = _mk_request(db, "260610-301", REQUEST_STATUS_COMPLETED)
        message_obj = MagicMock()
        message_obj.answer = AsyncMock()
        message_obj.bot = MagicMock()
        with patch(NOTIFY, new=AsyncMock()):
            await process_return_request(OWNER_TG, _mk_state(req.request_number),
                                         db=db, message_obj=message_obj)

        db.refresh(req)
        assert req.is_returned is True
        assert req.return_reason == "Не устранено"

    @pytest.mark.asyncio
    async def test_already_returned_cannot_be_returned_again(self, db):
        from uk_management_bot.handlers.request_acceptance import (
            process_return_request,
        )

        req = _mk_request(db, "260610-302", REQUEST_STATUS_COMPLETED,
                          is_returned=True)
        req.return_reason = "первый возврат"
        db.commit()
        message_obj = MagicMock()
        message_obj.answer = AsyncMock()
        with patch(NOTIFY, new=AsyncMock()):
            await process_return_request(OWNER_TG, _mk_state(req.request_number),
                                         db=db, message_obj=message_obj)

        db.refresh(req)
        assert req.return_reason == "первый возврат", "second return must be rejected"

    @pytest.mark.asyncio
    async def test_neighbor_cannot_return(self, db):
        """Сосед может принять, но НЕ вернуть (can_return = owner only)."""
        from uk_management_bot.handlers.request_acceptance import (
            process_return_request,
        )

        req = _mk_request(db, "260610-303", REQUEST_STATUS_COMPLETED)
        message_obj = MagicMock()
        message_obj.answer = AsyncMock()
        with patch(NOTIFY, new=AsyncMock()):
            await process_return_request(NEIGHBOR_TG, _mk_state(req.request_number),
                                         db=db, message_obj=message_obj)

        db.refresh(req)
        assert req.is_returned is False, "neighbor must not be able to return"

    @pytest.mark.asyncio
    async def test_stranger_cannot_return(self, db):
        from uk_management_bot.handlers.request_acceptance import (
            process_return_request,
        )

        req = _mk_request(db, "260610-304", REQUEST_STATUS_COMPLETED)
        message_obj = MagicMock()
        message_obj.answer = AsyncMock()
        with patch(NOTIFY, new=AsyncMock()):
            await process_return_request(STRANGER_TG, _mk_state(req.request_number),
                                         db=db, message_obj=message_obj)

        db.refresh(req)
        assert req.is_returned is False
