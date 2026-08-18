"""Пять хендлеров назначения работали без проверки роли (секревью 2026-08-17).

`handlers/request_assignment.py` помечен «мёртвый кластер» и ждёт decision
владельца (BUG-154), но роутер ВКЛЮЧЁН в `main.py`, а `callback_data` присылает
клиент, а не наша клавиатура. Мёртвой была только наша клавиатура — не вход.

Рабочая цепочка эксплуатации (три callback'а, роль не проверялась ни разу):

1. ``return_request_<любой номер>`` — живой хендлер приёмки
   (`handlers/request_acceptance.py`) кладёт номер из callback_data в FSM-состояние
   БЕЗ проверки владения. Для своего потока это безопасно: канонический
   `APPLICANT_RETURN` авторизует только владельца. Но состояние — общее, и здесь
   оно становится примитивом «положи в state ЧУЖОЙ номер заявки».
2. ``specialization_<строка>`` либо ``executor_<id>`` — хендлеры этого модуля,
   роль не проверялась.
3. ``confirm_assignment`` — `AssignmentService.assign_to_group` отменяет активные
   назначения, ставит произвольный `assigned_group` и ОБНУЛЯЕТ `executor_id`,
   мимо канона `plan_transition`.

Решение владельца: поставить guard сейчас, ретайр кластера (BUG-150/154/158) —
отдельным движением.

⚠️ Guard берёт роли из middleware (`has_admin_access(roles=..., user=...)`), а не
`check_user_role(callback.from_user.id, ...)`, как три уже защищённых хендлера
выше по файлу: там в аргумент `user_id` уходит TELEGRAM-id, а функция сравнивает
его с `User.id`. Это fail-closed (посторонний не пройдёт) и на мёртвом пути
безвредно, поэтому оставлено байт-в-байт — но повторять этот вызов в новых
guard'ах нельзя, он отказал бы и настоящему менеджеру.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uk_management_bot.handlers import request_assignment as ra


APPLICANT_ROLES = ["applicant"]
MANAGER_ROLES = ["manager"]


class _FakeState:
    """FSM-состояние без хранилища: важен только факт чтения/записи."""

    def __init__(self, **data):
        self._data = dict(data)
        self.state = None
        self.cleared = False

    async def get_data(self):
        return dict(self._data)

    async def update_data(self, **kwargs):
        self._data.update(kwargs)
        return dict(self._data)

    async def set_state(self, state):
        self.state = state

    async def clear(self):
        self.cleared = True
        self._data = {}


def _callback(data: str, from_id: int = 777):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = from_id
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    return cb


def _db():
    """Сессия, которая громко падает: guard обязан отказать ДО обращения к БД."""
    db = MagicMock()
    db.query.side_effect = AssertionError("guard пропустил жителя к БД")
    return db


# ══════════════════════════════════════════════════════════════════════════════
# Житель не проходит ни в один хендлер цепочки
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_specialization_selection_denies_applicant():
    callback = _callback("specialization_electrician")
    state = _FakeState(request_number="260816-001")

    await ra.handle_specialization_selection(
        callback, state, _db(), language="ru", roles=APPLICANT_ROLES, user=None
    )

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_awaited()
    assert "specialization" not in await state.get_data()


@pytest.mark.asyncio
async def test_executor_selection_denies_applicant():
    callback = _callback("executor_42")
    state = _FakeState(request_number="260816-001")

    await ra.handle_executor_selection(
        callback, state, _db(), language="ru", roles=APPLICANT_ROLES, user=None
    )

    callback.answer.assert_awaited_once()
    callback.message.edit_text.assert_not_awaited()
    assert "executor_id" not in await state.get_data()


@pytest.mark.asyncio
async def test_confirmation_denies_applicant_and_writes_nothing():
    callback = _callback("confirm_assignment")
    state = _FakeState(request_number="260816-001", specialization="electrician")

    with patch.object(ra, "AssignmentService") as service_cls:
        await ra.handle_assignment_confirmation(
            callback, state, _db(), language="ru", roles=APPLICANT_ROLES, user=None
        )

    service_cls.assert_not_called()
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_view_assignments_denies_applicant():
    """Просмотр назначений чужой заявки — тоже утечка, не только запись."""
    callback = _callback("view_assignments_260816-001")
    state = _FakeState()

    with patch.object(ra, "AssignmentService") as service_cls:
        await ra.handle_view_assignments(
            callback, state, _db(), language="ru", roles=APPLICANT_ROLES, user=None
        )

    service_cls.assert_not_called()


@pytest.mark.asyncio
async def test_missing_roles_are_denied():
    """Ролей нет вовсе (middleware не отдал) — отказ, а не проход."""
    callback = _callback("confirm_assignment")
    state = _FakeState(request_number="260816-001", specialization="electrician")

    with patch.object(ra, "AssignmentService") as service_cls:
        await ra.handle_assignment_confirmation(
            callback, state, _db(), language="ru", roles=None, user=None
        )

    service_cls.assert_not_called()


@pytest.mark.asyncio
async def test_full_exploit_chain_writes_nothing():
    """Та самая цепочка целиком: чужой номер в state + три callback'а."""
    state = _FakeState(request_number="260816-001")  # положен через return_request_*

    with patch.object(ra, "AssignmentService") as service_cls:
        await ra.handle_specialization_selection(
            _callback("specialization_electrician"), state, _db(),
            language="ru", roles=APPLICANT_ROLES, user=None,
        )
        await ra.handle_assignment_confirmation(
            _callback("confirm_assignment"), state, _db(),
            language="ru", roles=APPLICANT_ROLES, user=None,
        )

    service_cls.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# Менеджер проходит — guard не должен закрывать путь целиком
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_confirmation_allows_manager():
    callback = _callback("confirm_assignment")
    state = _FakeState(request_number="260816-001", specialization="electrician")

    with patch.object(ra, "AssignmentService") as service_cls:
        await ra.handle_assignment_confirmation(
            callback, state, MagicMock(), language="ru", roles=MANAGER_ROLES, user=None
        )

    service_cls.return_value.assign_to_group.assert_called_once()


@pytest.mark.asyncio
async def test_specialization_selection_allows_manager():
    callback = _callback("specialization_electrician")
    state = _FakeState(request_number="260816-001")
    db = MagicMock()

    await ra.handle_specialization_selection(
        callback, state, db, language="ru", roles=MANAGER_ROLES, user=None
    )

    callback.message.edit_text.assert_awaited_once()
    assert (await state.get_data())["specialization"] == "electrician"


# ══════════════════════════════════════════════════════════════════════════════
# Ратчет: guard стоит в КАЖДОМ хендлере модуля и ДО работы с данными
# ══════════════════════════════════════════════════════════════════════════════

_AUTH_CALLS = {"has_admin_access", "check_user_role"}
_DATA_CALLS = {"query", "AssignmentService"}


def _callback_handlers(tree: ast.Module):
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            func = deco.func
            if isinstance(func, ast.Attribute) and func.attr == "callback_query":
                yield node
                break


def _module_tree() -> ast.Module:
    source = Path(inspect.getsourcefile(ra)).read_text(encoding="utf-8")
    return ast.parse(source)


def test_every_callback_handler_is_role_guarded():
    handlers = list(_callback_handlers(_module_tree()))
    assert len(handlers) == 8, "изменился состав хендлеров — проверить ратчет"

    unguarded = []
    for handler in handlers:
        names = set()
        for node in ast.walk(handler):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    names.add(func.id)
                elif isinstance(func, ast.Attribute):
                    names.add(func.attr)
        if not (names & _AUTH_CALLS):
            unguarded.append(handler.name)

    assert not unguarded, f"хендлеры без проверки роли: {unguarded}"


def test_guard_precedes_any_data_access():
    """Авторизация — ДО обращения к БД и сервису.

    Порядок здесь не косметика: проверка после чтения заявки превращает коды
    ответов в оракул («заявка есть / её нет») для того, кому отказано.
    """
    late = []
    for handler in _callback_handlers(_module_tree()):
        auth_line = None
        data_line = None
        for node in ast.walk(handler):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name in _AUTH_CALLS and (auth_line is None or node.lineno < auth_line):
                auth_line = node.lineno
            if name in _DATA_CALLS and (data_line is None or node.lineno < data_line):
                data_line = node.lineno
        if data_line is not None and (auth_line is None or auth_line > data_line):
            late.append(handler.name)

    assert not late, f"проверка роли стоит после работы с данными: {late}"
