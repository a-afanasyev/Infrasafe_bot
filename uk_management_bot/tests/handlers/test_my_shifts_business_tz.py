"""ARCH-116: показ смен и дневные бакеты — в бизнес-зоне, не в UTC.

Дефект был двойным, и вторая половина хуже первой:
  (1) `strftime` по UTC-инстанту → исполнитель в Ташкенте видел время на 5 ч
      раньше своих часов;
  (2) бакет дня строился по UTC-дате (`date.today()` + `func.date(col)`) → смена,
      начинающаяся после местной полуночи, относилась к ПРЕДЫДУЩЕМУ дню: в
      «Текущие смены» не попадала вовсе, в расписании стояла не в своём дне.

Тесты гоняют настоящую sqlite-сессию, а не mock-цепочку `query.filter().all()`:
предмет здесь — сам SQL-предикат окна, и на моках он не исполняется.

Харнесс-факт (замерен): sqlite роняет `tzinfo` при bind и отдаёт naive при
чтении, но обе стороны сравнения сходятся одинаково — фильтр диапазоном с
aware-UTC границами ведёт себя как на Postgres, а `func.date()` в sqlite даёт ту
же UTC-дату. Поэтому дефект бакета воспроизводим здесь честно.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base

# 2026-07-29 21:00 UTC = 2026-07-30 02:00 Asia/Tashkent.
CROSSOVER_UTC = datetime(2026, 7, 29, 21, 0, tzinfo=timezone.utc)
BUSINESS_DAY = date(2026, 7, 30)

_engine = create_engine("sqlite:///:memory:", echo=False)
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


def _executor(db, db_id: int = 1, telegram_id: int = 9999) -> User:
    user = User(id=db_id, telegram_id=telegram_id, username="u", first_name="A",
                last_name="B", roles='["executor"]', active_role="executor",
                status="approved", language="ru")
    db.add(user)
    db.commit()
    return user


def _planned_shift(db, user_id: int, start_utc: datetime, hours: int = 8) -> Shift:
    """Плановая смена. `planned_*` и `start_time/end_time` синхронны — так их
    создают все три прод-пути (BUG-128)."""
    end_utc = start_utc + timedelta(hours=hours)
    shift = Shift(user_id=user_id, status="planned",
                  start_time=start_utc, end_time=end_utc,
                  planned_start_time=start_utc, planned_end_time=end_utc)
    db.add(shift)
    db.commit()
    return shift


def _callback(telegram_id: int = 9999, data: str = "view_current_shifts"):
    cb = MagicMock()
    cb.from_user = MagicMock(id=telegram_id)
    cb.data = data
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _state() -> AsyncMock:
    state = AsyncMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    return state


@contextmanager
def _business_today_is(module, day: date):
    """Фиксируем «сегодня» в бизнес-зоне ровно там, где его читает хендлер.

    `create=True` намеренно: без него тест против ДОФИКСНОГО кода падал бы на
    отсутствии атрибута, то есть проверял бы наличие импорта, а не поведение. С
    ним синтетический откат (вернуть `date.today()` + `func.date`) роняет тесты
    по СОДЕРЖИМОМУ экрана — так и должен работать регресс-гейт.
    """
    with patch.object(module, "business_today", return_value=day, create=True):
        yield


def _rendered(cb) -> str:
    args = cb.message.edit_text.await_args
    return args.args[0] if args.args else args.kwargs.get("text", "")


class TestCurrentShifts:
    """«🔥 Текущие смены» = сегодня+завтра ПО БИЗНЕС-ДАТЕ."""

    @pytest.mark.asyncio
    async def test_shift_after_local_midnight_is_in_today(self, db):
        from uk_management_bot.handlers import my_shifts as ms

        user = _executor(db)
        _planned_shift(db, user.id, CROSSOVER_UTC)

        cb, state = _callback(), _state()
        with _business_today_is(ms, BUSINESS_DAY), \
             patch.object(ms, "get_text", side_effect=lambda key, language="ru", **kw: key):
            await ms.handle_current_shifts(cb, state, language="ru", _db=db,
                                           user=user, roles=["executor"])

        text = _rendered(cb)
        assert "no_current_shifts" not in text, (
            "смена, начинающаяся 02:00 по Ташкенту, обязана попасть в «сегодня»; "
            "по UTC-дате она уезжала в предыдущий день и экран был пустым"
        )

    @pytest.mark.asyncio
    async def test_time_is_shown_in_business_wall_clock(self, db):
        from uk_management_bot.handlers import my_shifts as ms

        user = _executor(db)
        _planned_shift(db, user.id, CROSSOVER_UTC)

        cb, state = _callback(), _state()
        with _business_today_is(ms, BUSINESS_DAY), \
             patch.object(ms, "get_text", side_effect=lambda key, language="ru", **kw: key):
            await ms.handle_current_shifts(cb, state, language="ru", _db=db,
                                           user=user, roles=["executor"])

        text = _rendered(cb)
        assert "02:00 - 10:00" in text
        assert "21:00" not in text, "21:00 — UTC-часы, пользователь их не узнаёт"

    @pytest.mark.asyncio
    async def test_keyboard_label_is_business_wall_clock(self, db):
        """Подпись кнопки собирает `keyboards/my_shifts.py` — своя копия показа."""
        from uk_management_bot.handlers import my_shifts as ms

        user = _executor(db)
        _planned_shift(db, user.id, CROSSOVER_UTC)

        cb, state = _callback(), _state()
        with _business_today_is(ms, BUSINESS_DAY), \
             patch.object(ms, "get_text", side_effect=lambda key, language="ru", **kw: key):
            await ms.handle_current_shifts(cb, state, language="ru", _db=db,
                                           user=user, roles=["executor"])

        kb = cb.message.edit_text.await_args.kwargs["reply_markup"]
        labels = " | ".join(b.text for row in kb.inline_keyboard for b in row)
        assert "02:00" in labels
        assert "21:00" not in labels

    @pytest.mark.asyncio
    async def test_shift_of_previous_business_day_is_not_shown(self, db):
        """Контроль: окно не «разъехалось на сутки в обе стороны»."""
        from uk_management_bot.handlers import my_shifts as ms

        user = _executor(db)
        # 2026-07-28 21:00Z = 29.07 02:00 Ташкента — это ВЧЕРА относительно 30.07.
        _planned_shift(db, user.id, CROSSOVER_UTC - timedelta(days=1))

        cb, state = _callback(), _state()
        with _business_today_is(ms, BUSINESS_DAY), \
             patch.object(ms, "get_text", side_effect=lambda key, language="ru", **kw: key):
            await ms.handle_current_shifts(cb, state, language="ru", _db=db,
                                           user=user, roles=["executor"])

        assert "no_current_shifts" in _rendered(cb)


class TestWeekSchedule:
    """Расписание на неделю: смена стоит в своём БИЗНЕС-дне."""

    @pytest.mark.asyncio
    async def test_crossover_shift_sits_in_its_business_day(self, db):
        from uk_management_bot.handlers import my_shifts as ms

        user = _executor(db)
        _planned_shift(db, user.id, CROSSOVER_UTC)

        cb, state = _callback(data="view_week_schedule"), _state()
        with _business_today_is(ms, BUSINESS_DAY), \
             patch.object(ms, "get_text", side_effect=lambda key, language="ru", **kw: key):
            await ms.handle_week_schedule(cb, state, language="ru", _db=db,
                                          user=user, roles=["executor"])

        text = _rendered(cb)
        # Смена обязана стоять между заголовком своего дня (30.07) и следующего (31.07).
        assert "(30.07)" in text and "(31.07)" in text
        block = text.split("(30.07)")[1].split("(31.07)")[0]
        assert "02:00" in block, (
            "смена 02:00 по Ташкенту стояла в дне 29.07 — бакет считался по UTC-дате"
        )
