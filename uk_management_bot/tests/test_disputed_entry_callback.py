"""Callback-хендлер ответа жителя на спорный въезд (§6.4, §9.4, §16.2).

Бот шлёт жителю сообщение с кнопками «Подтвердить/Отклонить»; нажатие приходит
коллбэком ``acc_dispute:{decision_id}:{confirm|deny}``. Хендлер резолвит жителя
по telegram_id (роль applicant), зовёт ОБЩИЙ сервис ``confirm_disputed_entry`` на
своей sync-сессии (он совещательный — шлагбаум НЕ открывает), при успехе правит
сообщение и убирает клавиатуру. Идемпотентно (повтор → upsert в сервисе).

Тестируется чистая логика хендлера: db/resident-сервис/коллбэк замоканы.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import uk_management_bot.handlers.access_control as ac
from access_control.services.resident import DecisionNotFound, EntryNotOwned


def _db_with_resident(roles: str = '["applicant"]'):
    user = MagicMock()
    user.id = 1
    user.telegram_id = 555
    user.roles = roles
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    return db, user


def _callback(data: str, telegram_id: int = 555):
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock()
    cb.from_user.id = telegram_id
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    return cb


class TestDisputeCallback:
    async def test_confirm_calls_service_and_edits(self, monkeypatch) -> None:
        db, user = _db_with_resident()
        called = {}

        def fake_confirm(db_, *, actor_user_id, decision_id, response, **kw):
            called["args"] = (actor_user_id, decision_id, response)
            return MagicMock(decision_id=decision_id, response=response)

        monkeypatch.setattr(ac, "confirm_disputed_entry", fake_confirm)
        cb = _callback("acc_dispute:77:confirm")

        await ac.ac_dispute_response(cb, db, language="ru")

        assert called["args"] == (1, 77, "confirm")
        cb.message.edit_text.assert_awaited_once()
        cb.answer.assert_awaited()

    async def test_deny_calls_service_with_deny(self, monkeypatch) -> None:
        db, _ = _db_with_resident()
        captured = {}

        def fake_confirm(db_, *, actor_user_id, decision_id, response, **kw):
            captured["response"] = response
            return MagicMock(decision_id=decision_id, response=response)

        monkeypatch.setattr(ac, "confirm_disputed_entry", fake_confirm)
        cb = _callback("acc_dispute:77:deny")

        await ac.ac_dispute_response(cb, db, language="ru")

        assert captured["response"] == "deny"
        cb.message.edit_text.assert_awaited_once()

    async def test_foreign_entry_does_not_crash(self, monkeypatch) -> None:
        db, _ = _db_with_resident()

        def fake_confirm(db_, **kw):
            raise EntryNotOwned("not yours")

        monkeypatch.setattr(ac, "confirm_disputed_entry", fake_confirm)
        cb = _callback("acc_dispute:77:confirm")

        await ac.ac_dispute_response(cb, db, language="ru")

        cb.answer.assert_awaited()  # понятный ответ
        cb.message.edit_text.assert_not_awaited()  # чужое сообщение не правим

    async def test_decision_not_found_does_not_crash(self, monkeypatch) -> None:
        db, _ = _db_with_resident()

        def fake_confirm(db_, **kw):
            raise DecisionNotFound("nope")

        monkeypatch.setattr(ac, "confirm_disputed_entry", fake_confirm)
        cb = _callback("acc_dispute:77:confirm")

        await ac.ac_dispute_response(cb, db, language="ru")
        cb.answer.assert_awaited()
        cb.message.edit_text.assert_not_awaited()

    async def test_not_resident_rejected(self, monkeypatch) -> None:
        db, _ = _db_with_resident(roles='["executor"]')  # не applicant
        spy = MagicMock()
        monkeypatch.setattr(ac, "confirm_disputed_entry", spy)
        cb = _callback("acc_dispute:77:confirm")

        await ac.ac_dispute_response(cb, db, language="ru")

        spy.assert_not_called()
        cb.answer.assert_awaited()

    async def test_bad_response_token_ignored(self, monkeypatch) -> None:
        db, _ = _db_with_resident()
        spy = MagicMock()
        monkeypatch.setattr(ac, "confirm_disputed_entry", spy)
        cb = _callback("acc_dispute:77:hack")

        await ac.ac_dispute_response(cb, db, language="ru")

        spy.assert_not_called()
        cb.answer.assert_awaited()

    async def test_non_int_decision_ignored(self, monkeypatch) -> None:
        db, _ = _db_with_resident()
        spy = MagicMock()
        monkeypatch.setattr(ac, "confirm_disputed_entry", spy)
        cb = _callback("acc_dispute:abc:confirm")

        await ac.ac_dispute_response(cb, db, language="ru")

        spy.assert_not_called()
        cb.answer.assert_awaited()

    async def test_idempotent_repeat(self, monkeypatch) -> None:
        """Повторное нажатие снова зовёт сервис (он upsert'ит) и не падает."""
        db, _ = _db_with_resident()
        calls = []

        def fake_confirm(db_, *, actor_user_id, decision_id, response, **kw):
            calls.append(response)
            return MagicMock(decision_id=decision_id, response=response)

        monkeypatch.setattr(ac, "confirm_disputed_entry", fake_confirm)
        cb = _callback("acc_dispute:77:confirm")

        await ac.ac_dispute_response(cb, db, language="ru")
        await ac.ac_dispute_response(cb, db, language="ru")

        assert calls == ["confirm", "confirm"]
