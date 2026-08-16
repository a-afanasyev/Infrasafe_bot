"""BUG-160: исполнитель не узнавал о назначении на смену.

`handlers/shift_management/assignment_b.py` звал
`notification_service.send_shift_assignment_notification` — метода с таким
именем не существовало НИГДЕ в репозитории, `AttributeError` гасился
broad-except, и в логах оставалась только строка «Не удалось отправить
уведомление». Принудительное назначение (`force_assign`) не пыталось уведомить
вовсе. При этом массовое авто-назначение исполнителей уведомляет
(`shift_assignment_service._notify_successful_assignments`) — то есть уведомление
о назначении是 принятая практика, дыра была именно в двух ручных путях.

Тесты первые на этот путь: до фикса ни один из них не проходил.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.datetime_utils import utc_now


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _user(db, uid, tg, *, roles='["executor"]', language="ru", spec='["electric"]'):
    u = User(id=uid, telegram_id=tg, username=f"u{uid}", first_name="Иван", last_name="Петров",
             roles=roles, status="approved", language=language, specialization=spec)
    db.add(u)
    db.commit()
    return u


def _shift(db, sid, *, specs=None, user_id=None):
    start = utc_now() + timedelta(days=1)
    s = Shift(id=sid, user_id=user_id, start_time=start, end_time=start + timedelta(hours=8),
              status="scheduled", specialization_focus=specs if specs is not None else ["electric"])
    db.add(s)
    db.commit()
    return s


def _callback(data: str, from_id: int = 555):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = from_id
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.bot = MagicMock()
    return cb


# ══════════════════════════════════════════════════════════════════════════════
# Рендер текста
# ══════════════════════════════════════════════════════════════════════════════

class TestAssignmentMessage:
    def test_message_has_date_time_and_specialization(self, db):
        from uk_management_bot.services.notification_service import build_shift_assignment_message

        executor = _user(db, 1, 111)
        shift = _shift(db, 10)

        text = build_shift_assignment_message(executor, shift)

        from uk_management_bot.utils.business_time import fmt_date, fmt_time
        assert fmt_date(shift.start_time) in text
        assert fmt_time(shift.start_time) in text
        assert fmt_time(shift.end_time) in text

    def test_language_is_the_recipients_one(self, db):
        """Язык — получателя, а не инициатора (канон B3/BUG-153 п.1)."""
        from uk_management_bot.services.notification_service import build_shift_assignment_message

        ru_executor = _user(db, 1, 111, language="ru")
        uz_executor = _user(db, 2, 222, language="uz")
        shift = _shift(db, 10)

        ru_text = build_shift_assignment_message(ru_executor, shift)
        uz_text = build_shift_assignment_message(uz_executor, shift)

        assert ru_text != uz_text, "UZ-исполнитель обязан получить узбекский текст"

    def test_forced_assignment_is_marked(self, db):
        from uk_management_bot.services.notification_service import build_shift_assignment_message

        executor = _user(db, 1, 111)
        shift = _shift(db, 10)

        assert build_shift_assignment_message(executor, shift, forced=True) != \
            build_shift_assignment_message(executor, shift, forced=False)

    def test_open_ended_shift_does_not_crash(self, db):
        """end_time=None — смена без явного конца (планировщик такие создаёт)."""
        from uk_management_bot.services.notification_service import build_shift_assignment_message

        executor = _user(db, 1, 111)
        shift = _shift(db, 10)
        shift.end_time = None
        db.commit()

        assert build_shift_assignment_message(executor, shift)


# ══════════════════════════════════════════════════════════════════════════════
# Хендлеры: обычное и принудительное назначение
# ══════════════════════════════════════════════════════════════════════════════

class TestHandlersNotifyExecutor:
    @pytest.mark.asyncio
    async def test_assign_executor_notifies(self, db):
        from uk_management_bot.handlers.shift_management import assignment_b

        manager = _user(db, 5, 555, roles='["manager"]')
        _user(db, 1, 111)
        _shift(db, 10)

        sent = AsyncMock(return_value=True)
        with patch("uk_management_bot.services.notification_service.shifts.send_to_user", sent):
            await assignment_b.handle_assign_executor_to_shift(
                _callback("assign_executor_to_shift:10:1"), MagicMock(),
                db=db, user=manager, roles=["manager"],
            )

        assert sent.await_count == 1, "исполнитель должен получить уведомление о назначении"
        assert sent.await_args.args[1] == 111, "уведомление уходит на telegram_id исполнителя"

        db.expire_all()
        assert db.get(Shift, 10).user_id == 1, "смена должна быть назначена"

    @pytest.mark.asyncio
    async def test_force_assign_notifies(self, db):
        from uk_management_bot.handlers.shift_management import assignment_b

        manager = _user(db, 5, 555, roles='["manager"]')
        _user(db, 1, 111)
        _shift(db, 10)

        sent = AsyncMock(return_value=True)
        with patch("uk_management_bot.services.notification_service.shifts.send_to_user", sent):
            await assignment_b.handle_force_assign(
                _callback("force_assign:10:1"), MagicMock(),
                db=db, user=manager, roles=["manager"],
            )

        assert sent.await_count == 1, "принудительное назначение тоже обязано уведомлять"
        assert sent.await_args.args[1] == 111

    @pytest.mark.asyncio
    async def test_assignment_reports_success_not_error(self, db):
        """BUG-161: обычное назначение отвечало «Ошибка назначения исполнителя».

        В хендлере был локальный `from ...utils.specializations import
        translate_specializations` (функции там нет вовсе), из-за которого имя
        становилось локальным для ВСЕЙ функции — обращение к нему в обычной
        ветке давало UnboundLocalError уже ПОСЛЕ коммита назначения: смена
        назначена, а менеджер видит ошибку.
        """
        from uk_management_bot.handlers.shift_management import assignment_b

        manager = _user(db, 5, 555, roles='["manager"]')
        _user(db, 1, 111)
        _shift(db, 10)

        cb = _callback("assign_executor_to_shift:10:1")
        with patch("uk_management_bot.services.notification_service.shifts.send_to_user",
                   AsyncMock(return_value=True)):
            await assignment_b.handle_assign_executor_to_shift(
                cb, MagicMock(), db=db, user=manager, roles=["manager"],
            )

        cb.message.edit_text.assert_awaited()
        shown = cb.message.edit_text.await_args.args[0]
        assert "Ошибка" not in shown, f"менеджеру показана ошибка при успешном назначении: {shown!r}"

    @pytest.mark.asyncio
    async def test_missing_specialization_branch_is_reachable(self, db):
        """BUG-161, второй симптом: ветка «нет нужной специализации» падала ImportError."""
        from uk_management_bot.handlers.shift_management import assignment_b

        manager = _user(db, 5, 555, roles='["manager"]')
        _user(db, 1, 111, spec='["plumbing"]')      # у исполнителя не та специализация
        _shift(db, 10, specs=["electric"])

        cb = _callback("assign_executor_to_shift:10:1")
        await assignment_b.handle_assign_executor_to_shift(
            cb, MagicMock(), db=db, user=manager, roles=["manager"],
        )

        cb.message.edit_text.assert_awaited()
        db.expire_all()
        assert db.get(Shift, 10).user_id is None, "без нужной специализации смена не назначается"

    @pytest.mark.asyncio
    async def test_send_failure_does_not_break_assignment(self, db):
        """Сбой Telegram не должен отменять уже выполненное назначение."""
        from uk_management_bot.handlers.shift_management import assignment_b

        manager = _user(db, 5, 555, roles='["manager"]')
        _user(db, 1, 111)
        _shift(db, 10)

        boom = AsyncMock(side_effect=RuntimeError("telegram down"))
        cb = _callback("assign_executor_to_shift:10:1")
        with patch("uk_management_bot.services.notification_service.shifts.send_to_user", boom):
            await assignment_b.handle_assign_executor_to_shift(
                cb, MagicMock(), db=db, user=manager, roles=["manager"],
            )

        db.expire_all()
        assert db.get(Shift, 10).user_id == 1
        cb.message.edit_text.assert_awaited()
