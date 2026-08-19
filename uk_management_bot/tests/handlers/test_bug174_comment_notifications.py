"""BUG-174: уведомления о комментариях к заявке не уходили НИКОМУ.

`CommentService._notify_comment_added` звал несуществующий
`NotificationService.send_notification`, `AttributeError` гасился except'ом —
ни заявитель, ни исполнитель о комментарии не узнавали никогда, автор видел
успех. Лечение — B3-раскрой (образец `clarification_replies._apply_reply`):
сервис возвращает `CommentNotice(telegram_id, text-на-языке-получателя)`,
async-слой шлёт через `send_to_user` вне сессии.

Каждый тест здесь — первый на своём свойстве и написан RED-первым против HEAD.
Старые `TestNotifyCommentAdded` в `tests/services/test_comment_service.py` были
вакуумными: сервис целиком MagicMock, атрибут `send_notification` создавался
автоматически — зелёные на сломанном проде.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from unittest.mock import AsyncMock, MagicMock, patch

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


def _request(db, number, user_id, *, executor_id=None, status="Новая"):
    r = Request(request_number=number, user_id=user_id, executor_id=executor_id,
                category="Электрика", description="Не горит лампа",
                address="Дом 1", status=status)
    db.add(r)
    db.commit()
    return r


# ══════════════════════════════════════════════════════════════════════════════
# Коллектор: add_comment возвращает (comment, notices)
# ══════════════════════════════════════════════════════════════════════════════

class TestCollectNotices:
    """Адресаты и язык каждого получателя — свойства, которых раньше не было."""

    def test_applicant_and_executor_get_localized_notices(self, db):
        from uk_management_bot.services.comment_service import CommentService

        _user(db, 1, 111, language="ru")                          # заявитель
        _user(db, 2, 222, roles='["executor"]', language="uz")    # исполнитель
        _user(db, 3, 333, roles='["manager"]')                    # автор
        _request(db, "260819-001", 1, executor_id=2)

        comment, notices = CommentService(db).add_comment(
            request_id="260819-001", user_id=3,
            comment_text="Проверьте щиток", comment_type="clarification",
        )

        assert comment.comment_type == "clarification"
        by_tg = {n.telegram_id: n.text for n in notices}
        assert set(by_tg) == {111, 222}
        assert all("260819-001" in text for text in by_tg.values())
        assert all("Проверьте щиток" in text for text in by_tg.values())
        # Язык получателя, не автора: ru- и uz-тексты обязаны различаться.
        assert by_tg[111] != by_tg[222]

    def test_author_is_never_notified(self, db):
        from uk_management_bot.services.comment_service import CommentService

        _user(db, 1, 111)
        _request(db, "260819-002", 1)  # без исполнителя

        _, notices = CommentService(db).add_comment(
            request_id="260819-002", user_id=1,
            comment_text="сам себе", comment_type="clarification",
        )

        assert notices == []

    def test_recipient_without_telegram_id_is_skipped(self, db):
        """telegram_id=0 — реальный кейс: системный аккаунт InfraSafe (tg=0)."""
        from uk_management_bot.services.comment_service import CommentService

        _user(db, 1, 0)                                           # системный, tg=0
        _user(db, 2, 222, roles='["executor"]')
        _user(db, 3, 333, roles='["manager"]')
        _request(db, "260819-003", 1, executor_id=2)

        _, notices = CommentService(db).add_comment(
            request_id="260819-003", user_id=3,
            comment_text="текст", comment_type="clarification",
        )

        assert {n.telegram_id for n in notices} == {222}


# ══════════════════════════════════════════════════════════════════════════════
# Sync-юниты прод-вызывающих возвращают notices наверх
# ══════════════════════════════════════════════════════════════════════════════

class TestUnitsReturnNotices:
    def test_apply_comment_returns_notices(self, db):
        from uk_management_bot.handlers.request_comments import _apply_comment

        _user(db, 1, 111)
        _user(db, 2, 222, roles='["manager"]')
        _request(db, "260819-004", 1)

        verdict, notices = _apply_comment(
            db, "260819-004", 222, "Комментарий менеджера", "clarification"
        )

        assert verdict == "ok"
        assert {n.telegram_id for n in notices} == {111}

    def test_revision_comment_returns_notices(self, db):
        from uk_management_bot.handlers.request_reports import _add_revision_comment

        _user(db, 1, 111)
        _user(db, 2, 222, roles='["manager"]')
        _request(db, "260819-005", 1)

        notices = _add_revision_comment(db, "260819-005", 222, "переделать")

        assert {n.telegram_id for n in notices} == {111}
        assert any("260819-005" in n.text for n in notices)

    def test_revision_comment_unknown_actor_returns_empty(self, db):
        from uk_management_bot.handlers.request_reports import _add_revision_comment

        _user(db, 1, 111)
        _request(db, "260819-006", 1)

        assert _add_revision_comment(db, "260819-006", 999, "причина") == []

    def test_apply_purchase_outcome_carries_notices(self, db):
        from uk_management_bot.handlers.request_status_management._units import (
            _apply_purchase,
        )

        _user(db, 1, 111)
        _user(db, 2, 222, roles='["executor"]')
        _request(db, "260819-007", 1, executor_id=2, status="Закуп")

        res = _apply_purchase(db, "260819-007", "кабель 3м", 222, 2)

        assert res.outcome == "ok"
        assert {n.telegram_id for n in res.notices} == {111}


# ══════════════════════════════════════════════════════════════════════════════
# Доставка: async-слой реально шлёт через send_to_user
# ══════════════════════════════════════════════════════════════════════════════

class TestDelivery:
    def _state(self, data):
        store = dict(data)

        async def _get_data():
            return dict(store)

        st = AsyncMock()
        st.get_data = AsyncMock(side_effect=_get_data)
        return st

    @pytest.mark.asyncio
    async def test_comment_confirmation_delivers_to_recipients(self, db):
        from uk_management_bot.handlers import request_comments

        _user(db, 1, 111, language="ru")
        _user(db, 2, 222, roles='["executor"]', language="uz")
        _user(db, 3, 333, roles='["manager"]')
        _request(db, "260819-008", 1, executor_id=2)

        cb = MagicMock()
        cb.from_user.id = 333
        cb.message.edit_text = AsyncMock()
        cb.message.answer = AsyncMock()
        cb.answer = AsyncMock()
        cb.bot = MagicMock()

        sent = AsyncMock(return_value=True)
        with patch("uk_management_bot.services.notification_service.send_to_user", sent):
            await request_comments.handle_comment_confirmation(
                cb,
                self._state({
                    "comment_request_number": "260819-008",
                    "comment_type": "clarification",
                    "comment_text": "Проверьте щиток",
                }),
                language="ru",
                _db=db,
            )

        recipients = {call.args[1] for call in sent.await_args_list}
        assert recipients == {111, 222}, "заявитель и исполнитель должны получить уведомление"
        assert all("260819-008" in call.args[2] for call in sent.await_args_list)


class TestSendSitesAst:
    """Пин по AST: каждый из четырёх прод-вызывающих реально шлёт notices.

    Урок #471: подстрочный ассерт зелен на закомментированной отправке —
    поэтому проверяются имена ВЫЗОВОВ в теле функции, а не текст исходника.
    """

    @pytest.mark.parametrize(
        "module_path,func_name",
        [
            ("uk_management_bot.handlers.request_comments", "handle_comment_confirmation"),
            ("uk_management_bot.handlers.request_reports", "handle_revision_reason_input"),
            ("uk_management_bot.handlers.request_status_management.executor_actions", "handle_materials_input"),
            ("uk_management_bot.handlers.admin.materials", "handle_materials_edit_text"),
        ],
    )
    def test_caller_awaits_send_to_user(self, module_path, func_name):
        import importlib

        mod = importlib.import_module(module_path)
        src = textwrap.dedent(inspect.getsource(getattr(mod, func_name)))
        called = {
            getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            for node in ast.walk(ast.parse(src))
            if isinstance(node, ast.Call)
        }
        assert "send_to_user" in called, (
            f"{module_path}.{func_name} обязан отправлять notices через send_to_user — "
            "иначе флоу снова молчит (класс BUG-174/BUG-155 п.2)"
        )
