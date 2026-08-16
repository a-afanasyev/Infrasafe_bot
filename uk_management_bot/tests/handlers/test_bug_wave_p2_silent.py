"""BUG-волна P2: пять молчащих дефектов, найденных при A2-конвертации.

Общая черта всех пяти: пользователь видит либо generic-ошибку, либо вообще
ничего — при том, что вызывающая сторона считает операцию выполненной. Ни на
один из путей до этой волны не было ни одного теста, поэтому каждый тест здесь
первый на своём флоу и написан как RED-проба против HEAD:

  * BUG-151 п.1 — `user_apartments._set_primary_apartment`: сырая SQL-строка без
    `text()` → `ArgumentError` до запроса, «Сделать основной» всегда падает.
  * BUG-152 п.1 — `address_moderation._render_user_notification`: импорт из
    несуществующего `config.localization` → `ModuleNotFoundError`, житель не
    узнаёт решение по своей квартире.
  * BUG-153 п.5 — `request_reports._add_revision_comment`: чужой kwarg
    `request_id=` + Telegram-id вместо `users.id` → причина доработки не
    сохраняется.
  * BUG-155 п.1 — `request_comments._apply_comment`: Telegram-id вместо
    `users.id` → `ValueError`, подтверждение комментария падает в алерт.
  * BUG-155 п.2 — `clarification_replies`: вызов несуществующего метода
    `NotificationService.send_notification_to_user` → менеджеры не узнают об
    ответе заявителя на уточнение.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_comment import RequestComment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _user(db, uid, tg, *, roles='["applicant"]', language="ru"):
    u = User(id=uid, telegram_id=tg, username=f"u{uid}", first_name="U",
             roles=roles, status="approved", language=language)
    db.add(u)
    db.commit()
    return u


def _request(db, number, user_id, *, status="Новая"):
    r = Request(request_number=number, user_id=user_id, category="Электрика",
                description="Не горит лампа", address="Дом 1", status=status)
    db.add(r)
    db.commit()
    return r


# ══════════════════════════════════════════════════════════════════════════════
# BUG-151 п.1 — «Сделать основной» (user_apartments)
# ══════════════════════════════════════════════════════════════════════════════

class TestSetPrimaryApartment:
    """Первый тест на `_set_primary_apartment`: до фикса — ArgumentError."""

    def _two_apartments(self, db):
        _user(db, 1, 111)
        first = UserApartment(id=10, user_id=1, apartment_id=100,
                              status="approved", is_primary=True)
        second = UserApartment(id=20, user_id=1, apartment_id=200,
                               status="approved", is_primary=False)
        db.add_all([first, second])
        db.commit()

    def test_primary_flag_moves_to_selected_apartment(self, db):
        from uk_management_bot.handlers.user_apartments import _set_primary_apartment

        self._two_apartments(db)

        assert _set_primary_apartment(db, 20, 111) == "ok"

        db.expire_all()
        assert db.get(UserApartment, 20).is_primary is True
        assert db.get(UserApartment, 10).is_primary is False

    def test_foreign_apartment_is_rejected(self, db):
        from uk_management_bot.handlers.user_apartments import _set_primary_apartment

        self._two_apartments(db)

        assert _set_primary_apartment(db, 20, 999) == "access_denied"

    def test_not_approved_apartment_is_rejected(self, db):
        from uk_management_bot.handlers.user_apartments import _set_primary_apartment

        _user(db, 1, 111)
        db.add(UserApartment(id=30, user_id=1, apartment_id=300,
                             status="pending", is_primary=False))
        db.commit()

        assert _set_primary_apartment(db, 30, 111) == "not_approved"


# ══════════════════════════════════════════════════════════════════════════════
# BUG-152 п.1 — уведомление жителю о решении по квартире (address_moderation)
# ══════════════════════════════════════════════════════════════════════════════

class TestApartmentDecisionNotification:
    """Первый тест на `_render_user_notification`: до фикса — ModuleNotFoundError."""

    def test_approval_text_is_rendered(self, db):
        from uk_management_bot.handlers.address_moderation import _render_user_notification

        _user(db, 1, 111)

        text = _render_user_notification(db, 111, "approval", apartment_address="кв. 5")

        assert text
        assert "кв. 5" in text

    def test_rejection_text_includes_comment(self, db):
        from uk_management_bot.handlers.address_moderation import _render_user_notification

        _user(db, 1, 111)

        text = _render_user_notification(db, 111, "rejection",
                                         apartment_address="кв. 5", comment="нет документов")

        assert text
        assert "нет документов" in text

    def test_unknown_user_gives_none(self, db):
        from uk_management_bot.handlers.address_moderation import _render_user_notification

        assert _render_user_notification(db, 404, "approval", apartment_address="кв. 5") is None


# ══════════════════════════════════════════════════════════════════════════════
# BUG-153 п.5 — причина доработки (request_reports)
# ══════════════════════════════════════════════════════════════════════════════

class TestRevisionComment:
    """Первый тест на `_add_revision_comment`: до фикса — TypeError на kwarg."""

    def test_revision_reason_is_persisted(self, db):
        from uk_management_bot.handlers.request_reports import _add_revision_comment

        _user(db, 7, 777)
        _request(db, "260816-001", 7)

        _add_revision_comment(db, "260816-001", 777, "Плитка не доложена")

        comments = db.query(RequestComment).all()
        assert len(comments) == 1
        assert "Плитка не доложена" in comments[0].comment_text
        # user_id в комментарии — внутренний users.id, а не Telegram-id
        assert comments[0].user_id == 7


# ══════════════════════════════════════════════════════════════════════════════
# BUG-155 п.1 — подтверждение комментария (request_comments)
# ══════════════════════════════════════════════════════════════════════════════

class TestApplyComment:
    """Первый тест на `_apply_comment`: до фикса — ValueError на Telegram-id."""

    def test_comment_saved_with_internal_user_id(self, db):
        from uk_management_bot.handlers.request_comments import _apply_comment

        _user(db, 7, 777)
        _request(db, "260816-002", 7)

        verdict = _apply_comment(db, "260816-002", 777, "Нужен доступ в подвал", "clarification")

        assert verdict == "ok"
        comment = db.query(RequestComment).one()
        assert comment.user_id == 7
        assert comment.comment_text == "Нужен доступ в подвал"

    def test_unknown_request_is_reported(self, db):
        from uk_management_bot.handlers.request_comments import _apply_comment

        _user(db, 7, 777)

        assert _apply_comment(db, "нет-такой", 777, "текст", "clarification") == "request_not_found"


# ══════════════════════════════════════════════════════════════════════════════
# BUG-155 п.2 — менеджеры узнают об ответе заявителя (clarification_replies)
# ══════════════════════════════════════════════════════════════════════════════

class TestClarificationReplyNotifiesManagers:
    """Первый тест на путь уведомления менеджеров: до фикса — ноль отправок."""

    def _state(self, data):
        store = dict(data)

        async def _get_data():
            return dict(store)

        st = AsyncMock()
        st.get_data = AsyncMock(side_effect=_get_data)
        return st

    @pytest.mark.asyncio
    async def test_managers_receive_reply(self, db):
        from uk_management_bot.handlers import clarification_replies

        _user(db, 1, 111)                                  # заявитель
        _user(db, 2, 222, roles='["manager"]')             # менеджер
        _user(db, 3, 333, roles='["manager"]', language="uz")
        _request(db, "260816-003", 1, status="Уточнение")

        msg = MagicMock()
        msg.from_user.id = 111
        msg.text = "Мастер не пришёл"
        msg.answer = AsyncMock()
        msg.bot = MagicMock()

        sent = AsyncMock(return_value=True)
        with patch("uk_management_bot.services.notification_service.send_to_user", sent):
            await clarification_replies.handle_reply_text(
                msg, self._state({"request_number": "260816-003"}), language="ru", _db=db,
            )

        recipients = {call.args[1] for call in sent.await_args_list}
        assert recipients == {222, 333}, "оба менеджера должны получить уведомление"
        assert all("260816-003" in call.args[2] for call in sent.await_args_list)
        assert any("Мастер не пришёл" in call.args[2] for call in sent.await_args_list)

    @pytest.mark.asyncio
    async def test_reply_is_stored_in_notes(self, db):
        from uk_management_bot.handlers import clarification_replies

        _user(db, 1, 111)
        _request(db, "260816-004", 1, status="Уточнение")

        msg = MagicMock()
        msg.from_user.id = 111
        msg.text = "Мастер не пришёл"
        msg.answer = AsyncMock()
        msg.bot = MagicMock()

        with patch("uk_management_bot.services.notification_service.send_to_user",
                   AsyncMock(return_value=True)):
            await clarification_replies.handle_reply_text(
                msg, self._state({"request_number": "260816-004"}), language="ru", _db=db,
            )

        db.expire_all()
        assert "Мастер не пришёл" in db.get(Request, "260816-004").notes
