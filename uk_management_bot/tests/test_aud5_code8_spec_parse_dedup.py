"""AUD5-CODE-8: сведение копий парсинга специализаций и карточки сотрудника.

Три локальные копии парсинга `User.specialization` сведены к канону
`utils/specializations.parse_specializations`. Классы багов копий:

* `handlers/employee_management.change_employee_specialization` — json.loads
  без гейта `startswith('[')`: JSON-скаляр (`'123'`) парсился в int и ронял
  хендлер на `.copy()`; элементы JSON-списка не чистились от пробелов/пустых.
* `handlers/employee_management.process_specialization_change_comment` — та же
  схема для old_specializations в аудит-логе.
* `services/specialization_service.get_detailed_specialization_stats` —
  JSON-элементы не стрипались (`'["plumber "]'` выпадал из статистики), кривой
  JSON выкидывал сотрудника целиком вместо CSV-фолбэка.

Плюс: карточка сотрудника рендерится единственным хелпером
`_return_to_employee_info`, а имя — каноном `display_name` (REFACTOR-133).
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import uk_management_bot.handlers.employee_management as emp
import uk_management_bot.keyboards.employee_management as emp_kb
from uk_management_bot.services.specialization_service import SpecializationService


def _employee(spec, **kw):
    e = MagicMock()
    e.id = kw.get("id", 5)
    e.telegram_id = kw.get("telegram_id", 100500)
    e.first_name = kw.get("first_name", "Тест")
    e.last_name = kw.get("last_name", "Сотрудников")
    e.username = kw.get("username", "test_emp")
    e.specialization = spec
    e.status = "approved"
    return e


def _callback(data: str) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = 1
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    return cb


def _state(data=None) -> MagicMock:
    st = MagicMock()
    st.update_data = AsyncMock()
    st.set_state = AsyncMock()
    st.get_data = AsyncMock(return_value=data or {})
    st.clear = AsyncMock()
    return st


# ═══ Копия 1: change_employee_specialization ═══

async def _run_change_spec(monkeypatch, employee):
    monkeypatch.setattr(emp, "has_admin_access", lambda **kw: True)
    svc = MagicMock()
    svc.get_user_by_id.return_value = employee
    monkeypatch.setattr(emp, "UserManagementService", lambda db: svc)
    callback = _callback("change_employee_specialization_5")
    state = _state()
    await emp.change_employee_specialization(
        callback, state, _db=MagicMock(), roles=["manager"], user=MagicMock(), language="ru"
    )
    return callback, state


@pytest.mark.asyncio
async def test_change_spec_csv_string(monkeypatch):
    """CSV-кодировка ('plumber,electrician') разбирается на две специализации."""
    _cb, state = await _run_change_spec(monkeypatch, _employee("plumber,electrician"))
    state.update_data.assert_awaited_once()
    data = state.update_data.await_args.args[0]
    assert sorted(data["current_specializations"]) == ["electrician", "plumber"]


@pytest.mark.asyncio
async def test_change_spec_json_list_with_spaces(monkeypatch):
    """Элементы JSON-списка чистятся от пробелов и пустых значений."""
    _cb, state = await _run_change_spec(
        monkeypatch, _employee('["plumber ", " electrician", ""]')
    )
    state.update_data.assert_awaited_once()
    data = state.update_data.await_args.args[0]
    assert sorted(data["current_specializations"]) == ["electrician", "plumber"]


@pytest.mark.asyncio
async def test_change_spec_json_scalar_does_not_crash(monkeypatch):
    """JSON-скаляр ('123') раньше парсился в int и ронял хендлер на .copy()."""
    _cb, state = await _run_change_spec(monkeypatch, _employee("123"))
    state.update_data.assert_awaited_once()
    data = state.update_data.await_args.args[0]
    assert data["current_specializations"] == ["123"]


@pytest.mark.asyncio
async def test_change_spec_none(monkeypatch):
    """Пустая специализация → пустой список, без ошибок."""
    _cb, state = await _run_change_spec(monkeypatch, _employee(None))
    state.update_data.assert_awaited_once()
    data = state.update_data.await_args.args[0]
    assert data["current_specializations"] == []


# ═══ Копия 2: process_specialization_change_comment (old_specializations в аудит) ═══

@pytest.mark.asyncio
async def test_comment_audit_old_specs_use_canon(monkeypatch):
    target = _employee('["plumber ", " electrician", ""]')
    current_user = MagicMock()
    current_user.id = 9

    db = MagicMock()
    q = db.query.return_value.filter.return_value
    q.with_for_update.return_value = q  # TOCTOU-лок в цепочке юнита
    q.first.side_effect = [current_user, target]
    added = []
    db.add = added.append

    message = MagicMock()
    message.text = "коммент"
    message.from_user.id = 1
    message.answer = AsyncMock()
    state = _state({"target_employee_id": 5, "current_specializations": ["plumber"]})

    await emp.process_specialization_change_comment(message, state, _db=db, language="ru")

    assert len(added) == 1
    details = json.loads(added[0].details)
    assert sorted(details["old_specializations"]) == ["electrician", "plumber"]
    # новые специализации сохранены JSON-строкой
    assert json.loads(target.specialization) == ["plumber"]


# ═══ Копия 3: get_detailed_specialization_stats ═══

def _stats_for(executor):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [executor]
    return SpecializationService(db).get_detailed_specialization_stats()


def test_detailed_stats_json_with_spaces():
    """'["plumber ", "electrician"]' — раньше 'plumber ' выпадал из статистики."""
    stats = _stats_for(_employee('["plumber ", "electrician"]'))
    assert stats["plumber"]["count"] == 1
    assert stats["electrician"]["count"] == 1


def test_detailed_stats_csv():
    stats = _stats_for(_employee("plumber,electrician"))
    assert stats["plumber"]["count"] == 1
    assert stats["electrician"]["count"] == 1


def test_detailed_stats_none():
    stats = _stats_for(_employee(None))
    assert all(v["count"] == 0 for v in stats.values())


# ═══ Имена: _format_employee_name → канон display_name (REFACTOR-133) ═══

@pytest.mark.parametrize("fmt", [emp._format_employee_name, emp_kb._format_employee_name])
def test_format_name_only_last_name(fmt):
    """Канон показывает фамилию, даже когда first_name пуст (копии падали в @username)."""
    e = _employee(None, first_name=None, last_name="Иванов", username="ivn")
    assert fmt(e) == "Иванов"


@pytest.mark.parametrize("fmt", [emp._format_employee_name, emp_kb._format_employee_name])
def test_format_name_telegram_id_fallback(fmt):
    """Единый фолбэк канона: 'ID<telegram_id>' (в копиях был 'ID: <id>')."""
    e = _employee(None, first_name=None, last_name=None, username=None, telegram_id=42)
    assert fmt(e) == "ID42"


# ═══ Карточка сотрудника: show_employee_actions рендерит через единый хелпер ═══

@pytest.mark.asyncio
async def test_show_employee_actions_uses_card_helper(monkeypatch):
    monkeypatch.setattr(emp, "has_admin_access", lambda **kw: True)
    render = AsyncMock(return_value=True)
    monkeypatch.setattr(emp, "_return_to_employee_info", render)

    callback = _callback("employee_mgmt_employee_7")
    await emp.show_employee_actions(
        callback, _db=MagicMock(), roles=["manager"], user=MagicMock(), language="uz"
    )

    render.assert_awaited_once()
    args = render.await_args.args
    assert args[1] == 7 and args[2] == "uz"
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_show_employee_actions_not_found(monkeypatch):
    monkeypatch.setattr(emp, "has_admin_access", lambda **kw: True)
    render = AsyncMock(return_value=False)
    monkeypatch.setattr(emp, "_return_to_employee_info", render)

    callback = _callback("employee_mgmt_employee_7")
    await emp.show_employee_actions(
        callback, _db=MagicMock(), roles=["manager"], user=MagicMock(), language="ru"
    )

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
