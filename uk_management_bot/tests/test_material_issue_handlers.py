"""Тесты FSM-сценария списания материалов исполнителем (handlers/requests/materials.py).

Реальная in-memory sqlite-сессия (create_all) вместо мок-цепочек query:
проверяем настоящие эффекты — issue+allocations+декремент партии+RequestComment
одной транзакцией, guard'ы при прямом вызове callback'ов.
"""
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.material import (
    Material,
    MaterialIssue,
    MaterialIssueAllocation,
    MaterialReceipt,
)
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_comment import RequestComment
from uk_management_bot.database.models.user import User
from uk_management_bot.handlers.requests import materials as handlers
from uk_management_bot.states.material_issue import MaterialIssueStates

EXECUTOR_TG = 111
STRANGER_TG = 222


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    @contextmanager
    def fake_scope(_):
        yield session

    monkeypatch.setattr(handlers, "_db_scope", fake_scope)

    async def fake_lang(**kwargs):
        return "ru"

    monkeypatch.setattr(handlers, "_get_user_language", fake_lang)
    yield session
    session.close()


@pytest.fixture
def seed(db):
    """Исполнитель + чужой юзер + заявка «В работе» + материал с партией 10×100."""
    executor = User(telegram_id=EXECUTOR_TG, first_name="Exec",
                    roles='["executor"]', active_role="executor", status="approved")
    stranger = User(telegram_id=STRANGER_TG, first_name="Other",
                    roles='["executor"]', active_role="executor", status="approved")
    db.add_all([executor, stranger])
    db.flush()
    request = Request(request_number="260705-001", user_id=executor.id,
                      category="electrics", status="В работе",
                      description="тест", urgency="medium", address="x",
                      executor_id=executor.id)
    material = Material(name="Кабель", unit="m", is_active=True)
    db.add_all([request, material])
    db.flush()
    receipt = MaterialReceipt(
        material_id=material.id, doc_type="purchase",
        qty=Decimal("10"), qty_remaining=Decimal("10"),
        unit_price=Decimal("100.00"), total_amount=Decimal("1000.00"),
        material_name="Кабель", unit="m", created_by=executor.id,
    )
    db.add(receipt)
    db.commit()
    return {"executor": executor, "stranger": stranger,
            "request": request, "material": material, "receipt": receipt}


def _callback(data: str, telegram_id: int = EXECUTOR_TG):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = telegram_id
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _message(text: str, telegram_id: int = EXECUTOR_TG):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = telegram_id
    msg.answer = AsyncMock()
    return msg


def _state(data: dict | None = None):
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=data or {})
    return state


def _confirm_data(seed, qty="4"):
    return {
        "mat_request_number": seed["request"].request_number,
        "mat_material_id": seed["material"].id,
        "mat_material_name": "Кабель",
        "mat_material_unit": "m",
        "mat_qty": qty,
    }


# ── Guard'ы (callback можно вызвать напрямую — кнопка не защита) ────

@pytest.mark.asyncio
async def test_start_rejects_stranger_executor(db, seed):
    cb = _callback("matissue_start_260705-001", telegram_id=STRANGER_TG)
    state = _state()
    await handlers.start_material_issue(cb, state)
    cb.answer.assert_awaited_once()
    assert cb.answer.await_args.kwargs.get("show_alert") is True
    state.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_rejects_wrong_status(db, seed):
    seed["request"].status = "Выполнена"
    db.commit()
    cb = _callback("matissue_start_260705-001")
    state = _state()
    await handlers.start_material_issue(cb, state)
    assert cb.answer.await_args.kwargs.get("show_alert") is True
    state.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_rejects_missing_request(db, seed):
    cb = _callback("matissue_start_999999-999")
    state = _state()
    await handlers.start_material_issue(cb, state)
    assert cb.answer.await_args.kwargs.get("show_alert") is True
    state.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_pick_rejects_inactive_material(db, seed):
    seed["material"].is_active = False
    db.commit()
    cb = _callback(f"matpick_{seed['material'].id}")
    state = _state()
    await handlers.pick_material(cb, state)
    assert cb.answer.await_args.kwargs.get("show_alert") is True
    state.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_recheck_guards_after_status_change(db, seed):
    """Между подтверждением и стартом заявка ушла из «В работе» → отказ."""
    seed["request"].status = "Выполнена"
    db.commit()
    cb = _callback("matconfirm")
    state = _state(_confirm_data(seed))
    await handlers.confirm_material_issue(cb, state)
    state.clear.assert_awaited()
    assert cb.answer.await_args.kwargs.get("show_alert") is True
    db.rollback()
    assert db.query(MaterialIssue).count() == 0


# ── Полная FSM-цепочка ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_chain_start_pick_qty_confirm(db, seed):
    # старт
    cb = _callback("matissue_start_260705-001")
    state = _state()
    await handlers.start_material_issue(cb, state)
    state.set_state.assert_awaited_with(MaterialIssueStates.selecting_material)
    cb.message.answer.assert_awaited()  # список материалов показан

    # выбор материала
    cb2 = _callback(f"matpick_{seed['material'].id}")
    state2 = _state()
    await handlers.pick_material(cb2, state2)
    state2.set_state.assert_awaited_with(MaterialIssueStates.entering_quantity)

    # количество
    msg = _message("4")
    state3 = _state({"mat_material_id": seed["material"].id,
                     "mat_material_name": "Кабель", "mat_material_unit": "m",
                     "mat_request_number": "260705-001"})
    await handlers.enter_quantity(msg, state3)
    state3.set_state.assert_awaited_with(MaterialIssueStates.confirming)
    state3.update_data.assert_awaited_with(mat_qty="4")

    # подтверждение
    cb4 = _callback("matconfirm")
    state4 = _state(_confirm_data(seed))
    await handlers.confirm_material_issue(cb4, state4)
    state4.clear.assert_awaited()

    issue = db.query(MaterialIssue).one()
    assert issue.doc_type == "request"
    assert issue.request_number == "260705-001"
    assert Decimal(str(issue.qty)) == Decimal("4")
    assert Decimal(str(issue.total_cost)) == Decimal("400.00")
    assert db.query(MaterialIssueAllocation).count() == 1
    assert Decimal(str(seed["receipt"].qty_remaining)) == Decimal("6")
    comment = db.query(RequestComment).one()
    assert comment.comment_type == "material"
    assert "Кабель" in comment.comment_text and "4" in comment.comment_text


@pytest.mark.asyncio
async def test_quantity_validation_and_soft_stock_check(db, seed):
    base = {"mat_material_id": seed["material"].id, "mat_material_name": "Кабель",
            "mat_material_unit": "m", "mat_request_number": "260705-001"}
    for bad in ("abc", "0", "-2"):
        msg = _message(bad)
        state = _state(dict(base))
        await handlers.enter_quantity(msg, state)
        state.set_state.assert_not_awaited()
    # больше остатка (10) → мягкий отказ без смены состояния
    msg = _message("11")
    state = _state(dict(base))
    await handlers.enter_quantity(msg, state)
    state.set_state.assert_not_awaited()
    # запятая как разделитель принимается
    msg = _message("2,5")
    state = _state(dict(base))
    await handlers.enter_quantity(msg, state)
    state.set_state.assert_awaited_with(MaterialIssueStates.confirming)


@pytest.mark.asyncio
async def test_confirm_insufficient_stock_alert(db, seed):
    """Жёсткая проверка в локе: остаток украли между экранами → alert, отката всё."""
    cb = _callback("matconfirm")
    state = _state(_confirm_data(seed, qty="8"))
    seed["receipt"].qty_remaining = Decimal("3")  # «украли» между экранами
    db.commit()
    await handlers.confirm_material_issue(cb, state)
    state.clear.assert_awaited()
    assert cb.answer.await_args.kwargs.get("show_alert") is True
    db.rollback()
    assert db.query(MaterialIssue).count() == 0
    assert db.query(RequestComment).count() == 0


@pytest.mark.asyncio
async def test_issue_and_comment_are_atomic(db, seed, monkeypatch):
    """Ошибка на этапе комментария откатывает и списание (единый commit).

    RequestComment импортируется в issue_material_with_comment локально —
    патчим класс в его модуле, локальный импорт увидит подмену.
    """
    class Boom(Exception):
        pass

    def broken_comment(**kwargs):
        raise Boom("comment failed")

    monkeypatch.setattr(
        "uk_management_bot.database.models.request_comment.RequestComment",
        broken_comment,
    )
    cb = _callback("matconfirm")
    state = _state(_confirm_data(seed))
    await handlers.confirm_material_issue(cb, state)
    # commit не состоялся → после отката эффектов нет
    db.rollback()
    assert db.query(MaterialIssue).count() == 0
    assert db.query(MaterialIssueAllocation).count() == 0
    assert Decimal(str(seed["receipt"].qty_remaining)) == Decimal("10")


@pytest.mark.asyncio
async def test_cancel_clears_state(db, seed):
    cb = _callback("matcancel")
    state = _state()
    await handlers.cancel_material_issue(cb, state)
    state.clear.assert_awaited()
    cb.message.edit_text.assert_awaited()
