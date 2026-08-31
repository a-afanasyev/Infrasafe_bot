"""Тройка «решено-но-несделано» из бэклога (решения владельца 2026-08-19).

BUG-171: кнопка «Общий комментарий» падала всегда — `general` не входил в канон
типов. Решение (а): добавить в `COMMENT_TYPES` (локали ru/uz уже несут ключи).
Попутно валидация в `add_comment` приведена к КАНОНУ (импорт `COMMENT_TYPES`),
а не к локальной копии списка — копии канона и породили BUG-166-класс.

BUG-164: инвайт с ролью «Заявитель» гасил одноразовый токен и не давал ничего
(applicant у самозарегистрировавшегося уже есть). Решение: убрать кнопку из
клавиатуры выдачи — житель регистрируется сам.

BUG-178: `reply_text` заявителя уходил менеджерам сырым при parse_mode=HTML —
инъекция разметки в «авторитетное» уведомление; кривой тег молча гасит доставку.
Канон — html.escape на любом свободном тексте (образец BUG-174).
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User


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


def _request(db, number, user_id, *, executor_id=None, status="Уточнение"):
    r = Request(request_number=number, user_id=user_id, executor_id=executor_id,
                category="Электрика", description="Не горит лампа",
                address="Дом 1", status=status)
    db.add(r)
    db.commit()
    return r


# ══════════════════════════════════════════════════════════════════════════════
# BUG-171 — тип general входит в канон, кнопка становится рабочей
# ══════════════════════════════════════════════════════════════════════════════

class TestBug171GeneralCommentType:
    def test_general_in_canon(self):
        from uk_management_bot.utils.constants import COMMENT_TYPES
        assert "general" in COMMENT_TYPES

    def test_add_comment_accepts_general(self, db):
        from uk_management_bot.services.comment_service import CommentService

        _user(db, 1, 111)
        _user(db, 3, 333, roles='["manager"]')
        _request(db, "260901-001", 1, status="Новая")

        comment, notices = CommentService(db).add_comment(
            request_id="260901-001", user_id=3,
            comment_text="Общий текст", comment_type="general",
        )
        assert comment.comment_type == "general"
        # Уведомление заявителю рендерится с человекочитаемым типом,
        # а не сырым ключом «general» (локаль comments.type_general).
        assert len(notices) == 1
        assert "general" not in notices[0].text

    def test_validation_uses_canon_not_local_copy(self):
        """Валидация обязана читать COMMENT_TYPES: новая константа в каноне
        не должна требовать второй правки в сервисе (урок BUG-166)."""
        import inspect
        from uk_management_bot.services import comment_service
        src = inspect.getsource(comment_service.CommentService.add_comment)
        assert "COMMENT_TYPES" in src

    def test_unknown_type_still_rejected(self, db):
        from uk_management_bot.services.comment_service import CommentService

        _user(db, 1, 111)
        _request(db, "260901-002", 1, status="Новая")

        with pytest.raises(ValueError):
            CommentService(db).add_comment(
                request_id="260901-002", user_id=1,
                comment_text="x", comment_type="nonsense",
            )


# ══════════════════════════════════════════════════════════════════════════════
# BUG-164 — «Заявитель» убран из клавиатуры выдачи приглашений
# ══════════════════════════════════════════════════════════════════════════════

class TestBug164InviteKeyboard:
    def _callbacks(self, language="ru"):
        from uk_management_bot.keyboards.admin import get_invite_role_keyboard
        kb = get_invite_role_keyboard(language=language)
        return [btn.callback_data for row in kb.inline_keyboard for btn in row]

    def test_applicant_button_gone(self):
        assert "invite_role_applicant" not in self._callbacks()

    def test_staff_roles_and_cancel_intact(self):
        cbs = self._callbacks()
        assert {"invite_role_executor", "invite_role_manager",
                "invite_role_inspector", "invite_cancel"} <= set(cbs)

    @pytest.mark.asyncio
    async def test_stale_applicant_callback_rejected_at_handler(self):
        """callback_data шлёт клиент (урок BUG-169): кнопки нет, но стейл-
        клавиатура или ручной callback обязаны отвергаться точкой записи."""
        from unittest.mock import AsyncMock, MagicMock

        from uk_management_bot.handlers.admin.invites import (
            handle_invite_role_selection,
        )

        cb = MagicMock()
        cb.data = "invite_role_applicant"
        cb.answer = AsyncMock()
        cb.message = MagicMock()
        cb.message.edit_text = AsyncMock()
        state = AsyncMock()

        await handle_invite_role_selection(
            cb, state, MagicMock(), roles=["manager"], active_role="manager",
            user=MagicMock(), language="ru",
        )

        cb.answer.assert_awaited_once()          # отказ «неверная роль»
        state.update_data.assert_not_awaited()   # роль НЕ сохранена
        cb.message.edit_text.assert_not_awaited()  # анкета НЕ продолжилась


# ══════════════════════════════════════════════════════════════════════════════
# BUG-178 — reply_text заявителя экранируется перед HTML-уведомлением менеджерам
# ══════════════════════════════════════════════════════════════════════════════

class TestBug178ReplyTextEscaped:
    def test_reply_text_is_html_escaped(self, db):
        from uk_management_bot.handlers.clarification_replies import _apply_reply

        _user(db, 1, 111)                              # заявитель
        _user(db, 2, 222, roles='["manager"]')         # менеджер-адресат
        _request(db, "260901-003", 1)

        payload = '<a href="https://evil">жмите</a> <b>срочно</b>'
        status, notices = _apply_reply(db, "260901-003", 111, payload, "ru")

        assert status == "ok"
        assert len(notices) == 1
        text = notices[0].text
        assert "<a href" not in text and "<b>" not in text
        assert "&lt;a href" in text and "&lt;b&gt;" in text
