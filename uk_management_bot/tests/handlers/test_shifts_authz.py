"""Волна D аудита 2026-08-18: смены — роль (D2) и владение (D3).

D2 (находка 7): `manager_active_shifts` отдавал список ВСЕХ активных смен по
тексту кнопки любому пользователю — с ложным комментарием «проверка роли
происходит отдельно» (никто её не делал). Теперь `@require_role`.

D3 (находка 8): `end_shift_select:<id>` показывал детали ЧУЖОЙ смены с
номерами её заявок — `_load_shift_end_view` грузил смену без фильтра владения,
а shift_id присылает клиент. Теперь фильтр `Shift.user_id == owner.id`
(зеркало `_end_shift_by_id_unit`) на РЕАЛЬНОЙ sqlite-сессии — мок БД здесь
не может упасть по построению (сравнение живёт в SQL).
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.handlers import shifts as sh
from uk_management_bot.utils.datetime_utils import utc_now
from uk_management_bot.utils.helpers import get_text


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _user(db, uid, tg):
    u = User(id=uid, telegram_id=tg, username=f"u{uid}", first_name="Иван",
             last_name="Петров", roles='["executor"]', status="approved", language="ru")
    db.add(u)
    db.commit()
    return u


def _shift(db, sid, user_id):
    start = utc_now() - timedelta(hours=2)
    s = Shift(id=sid, user_id=user_id, start_time=start, status="active",
              specialization_focus=["electric"])
    db.add(s)
    db.commit()
    return s


# D2 (`manager_active_shifts` под `@require_role`) снят вместе с хендлером:
# BUG-150 ретайр 2026-08-19 — текст кнопки «🟢 Активные смены» не рендерила ни
# одна клавиатура, вход закрыт целиком. Что теперь на него никто не отвечает —
# пиннит `tests/handlers/test_dead_handlers_retired.py` (обе локали, обе роли).


# ══════════════════════════════════════════════════════════════════════════════
# D3: _load_shift_end_view — владение на реальной сессии
# ══════════════════════════════════════════════════════════════════════════════

def test_shift_end_view_owner_sees_own_shift(db):
    owner = _user(db, 10, 111)
    _shift(db, 5, owner.id)

    assert sh._load_shift_end_view(db, 5, telegram_id=111) is not None


def test_shift_end_view_foreign_shift_is_invisible(db):
    owner = _user(db, 10, 111)
    _user(db, 20, 222)
    _shift(db, 5, owner.id)

    assert sh._load_shift_end_view(db, 5, telegram_id=222) is None


def test_shift_end_view_unknown_user_is_denied(db):
    owner = _user(db, 10, 111)
    _shift(db, 5, owner.id)

    assert sh._load_shift_end_view(db, 5, telegram_id=999) is None


def test_shift_end_view_missing_shift_and_foreign_are_indistinguishable(db):
    """«Чужая смена» и «нет смены» возвращают одинаковый None (анти-оракул)."""
    owner = _user(db, 10, 111)
    _user(db, 20, 222)
    _shift(db, 5, owner.id)

    assert sh._load_shift_end_view(db, 404, telegram_id=111) \
        == sh._load_shift_end_view(db, 5, telegram_id=222) is None


@pytest.mark.asyncio
async def test_handle_shift_selection_passes_caller_telegram_id(db):
    """Хендлер передаёт telegram_id ИНИЦИАТОРА callback'а: у callback.message
    from_user — БОТ, выводить владельца из message нельзя."""
    owner = _user(db, 10, 111)
    _shift(db, 5, owner.id)

    cb = MagicMock()
    cb.data = "end_shift_select:5"
    cb.from_user.id = 222  # чужак
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    _user(db, 20, 222)

    await sh.handle_shift_selection(cb, language="ru", _db=db)

    # чужак получил «смена не найдена», а не детали
    sent = cb.message.answer.await_args.args[0]
    assert sent == get_text("shifts.shift_not_found", language="ru")
