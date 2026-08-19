"""Инвариант: «В работе» ⟺ у заявки есть исполнитель.

Решение владельца 2026-08-17: статус «В работе» означает, что заявку кто-то
ведёт. Групповое назначение — это указание НАЗНАЧИТЬ того, у кого есть
специализация и кто на смене, а не самостоятельное состояние ожидания.

Как было. `SYSTEM_DISPATCH_ASSIGN` переводил заявку в «В работе» безусловно —
и когда назначал человека, и когда назначал только группу-специализацию. При
групповом назначении `executor_id` оставался пустым, и если никто из дежурных
заявку не «брал», она висела «В работе» ничьей. На продах так накопилось девять
таких заявок, старейшая — с 16 июня.

Как стало:

* `SYSTEM_DISPATCH_ASSIGN` — только конкретный исполнитель, «Новая»→«В работе»;
  `group` в payload запрещён;
* `ASSIGN_GROUP` — только группа, статус НЕ меняет: заявка остаётся
  «Новая» с проставленной специализацией, её видят дежурные;
* `EXECUTOR_CLAIM` работает и из «Новой» — дежурный берёт заявку сам;
* `MANAGER_ASSIGN` без payload больше не переводит в «В работе»: «менеджер взял
  заявку, а исполнителя выберет потом» — это ровно ничья заявка.

Главный тест здесь — не сценарный, а структурный: `test_in_progress_always_sets_executor`
проверяет ВСЮ таблицу действий, поэтому новое действие с переходом в «В работе»
не сможет тихо завести десятую сироту.
"""
from unittest.mock import MagicMock

import pytest

from uk_management_bot.utils.constants import (
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_NEW,
)
from uk_management_bot.utils.request_workflow import (
    Action,
    ActionCommand,
    Op,
    PayloadInvalid,
    plan_transition,
)
from uk_management_bot.utils.request_workflow.specs import ACTION_TABLE

from .test_request_workflow import (  # переиспользуем канон-фикстуры
    DISPATCHER,
    EXECUTOR_ID,
    MANAGER,
    NOW,
    SYSTEM_PRINCIPAL,
    _patch_fields,
    _plan,
    _snap,
    _user,
)

# Исполнитель-дежурный: специализация совпадает с группой назначения.
DUTY = _user(EXECUTOR_ID, "executor", specializations={"plumber"})


def _group_snap(status=REQUEST_STATUS_NEW):
    """Заявка с активным НЕВЗЯТЫМ групповым назначением на сантехнику."""
    return _snap(status, assignment_type="group",
                 assignment_group="plumber", unclaimed=True, shift=True)


# ═══ Структурный инвариант по всей таблице действий ═══

_DUMMY_BY_TYPE = {int: 1, str: "x", list: [], bool: True, float: 1.0}


def _minimal_payload(action):
    """Минимальный payload, проходящий схему действия."""
    from uk_management_bot.utils.request_workflow.payloads import PAYLOAD_SCHEMAS
    schema = PAYLOAD_SCHEMAS[action]
    return {key: _DUMMY_BY_TYPE[typ] for key, typ in schema.required.items()}


IN_PROGRESS_ACTIONS = sorted(
    (a for a, spec in ACTION_TABLE.items()
     if spec.to_status == REQUEST_STATUS_IN_PROGRESS),
    key=lambda a: a.value,
)


@pytest.mark.parametrize("action", IN_PROGRESS_ACTIONS)
def test_in_progress_without_executor_is_refused(action):
    """НИ ОДНО действие не приводит в «В работе» заявку без исполнителя.

    Проверяется вся таблица, а не только переходы из «Новой». Первая версия
    этого ратчета смотрела 2 действия из 6, и ревью показало живую дыру: из
    «Новой» без исполнителя менеджер уводил заявку в «Закуп»/«Уточнение», а
    оттуда возвращал в «В работе» — `MANAGER_PURCHASE_DONE` и
    `CLARIFY_RESOLVED` ставят только статус, потому что «исполнитель уже есть».
    Он есть не всегда.

    Проверяется ЭФФЕКТ на снапшоте без исполнителя: либо действие само
    назначает (payload или `Op.SET_ACTOR`, как взятие заявки), либо
    `plan_transition` обязан отказать.
    """
    from uk_management_bot.utils.request_workflow import InvalidTransition

    spec = ACTION_TABLE[action]
    from_status = sorted(spec.from_statuses)[0]
    snap = _snap(from_status, assignment_type="group",
                 assignment_group="plumber", unclaimed=True, shift=True)
    actor = DUTY if action is Action.EXECUTOR_CLAIM else MANAGER
    principal = SYSTEM_PRINCIPAL if spec.system_only else None

    try:
        res = _plan(snap, action, DISPATCHER if spec.system_only else actor,
                    _minimal_payload(action),
                    **({"principal": principal} if principal else {}))
    except InvalidTransition:
        return  # канон отказал — инвариант соблюдён
    except Exception:
        return  # не наш класс отказа (payload/авторизация) — не про инвариант

    ops_by_field = {field: op for field, op, _ in res.patch}
    assert ops_by_field.get("executor_id") in (Op.SET, Op.SET_ACTOR), (
        f"{action.value}: приводит в «В работе» заявку без исполнителя и "
        f"исполнителя не выставляет — так и появляются ничьи заявки"
    )


def test_resume_from_purchase_without_executor_is_refused():
    """Живой сценарий дыры: «Новая» → «Закуп» → «В работе» без исполнителя."""
    from uk_management_bot.utils.constants import REQUEST_STATUS_PURCHASE
    from uk_management_bot.utils.request_workflow import InvalidTransition

    with pytest.raises(InvalidTransition):
        _plan(_snap(REQUEST_STATUS_PURCHASE), Action.MANAGER_PURCHASE_DONE, MANAGER)


def test_resume_from_purchase_with_executor_still_works():
    """…а обычный путь (заявку ведёт исполнитель) не сломан."""
    from uk_management_bot.utils.constants import REQUEST_STATUS_PURCHASE

    res = _plan(_snap(REQUEST_STATUS_PURCHASE, executor=EXECUTOR_ID),
                Action.MANAGER_PURCHASE_DONE, MANAGER)
    assert _patch_fields(res)["status"] == (Op.SET, REQUEST_STATUS_IN_PROGRESS)


# ═══ SYSTEM_DISPATCH_ASSIGN — только конкретный исполнитель ═══

def test_dispatch_assign_with_executor_goes_in_progress():
    res = plan_transition(
        _snap(REQUEST_STATUS_NEW),
        ActionCommand("c", Action.SYSTEM_DISPATCH_ASSIGN, {"executor_id": EXECUTOR_ID}),
        DISPATCHER, SYSTEM_PRINCIPAL, NOW)
    fields = _patch_fields(res)
    assert fields["status"] == (Op.SET, REQUEST_STATUS_IN_PROGRESS)
    assert fields["executor_id"] == (Op.SET, EXECUTOR_ID)


def test_dispatch_assign_rejects_group():
    """Группа больше не диспетчеризуется этим действием — у неё своё."""
    with pytest.raises(PayloadInvalid):
        plan_transition(
            _snap(REQUEST_STATUS_NEW),
            ActionCommand("c", Action.SYSTEM_DISPATCH_ASSIGN, {"group": "plumber"}),
            DISPATCHER, SYSTEM_PRINCIPAL, NOW)


def test_dispatch_assign_rejects_empty_payload():
    """Пустой payload = перевод в «В работе» без исполнителя."""
    with pytest.raises(PayloadInvalid):
        plan_transition(
            _snap(REQUEST_STATUS_NEW),
            ActionCommand("c", Action.SYSTEM_DISPATCH_ASSIGN, {}),
            DISPATCHER, SYSTEM_PRINCIPAL, NOW)


# ═══ ASSIGN_GROUP — статус не меняет ═══

def test_dispatch_group_keeps_status_new():
    res = plan_transition(
        _snap(REQUEST_STATUS_NEW),
        ActionCommand("c", Action.ASSIGN_GROUP, {"group": "plumber"}),
        DISPATCHER, SYSTEM_PRINCIPAL, NOW)
    fields = _patch_fields(res)
    assert fields["status"] == (Op.SET, REQUEST_STATUS_NEW), \
        "групповое назначение не должно двигать заявку в «В работе»"
    assert fields["assigned_group"] == (Op.SET, "plumber")
    assert "executor_id" not in fields or fields["executor_id"][0] is not Op.SET


def test_dispatch_group_creates_assignment():
    res = plan_transition(
        _snap(REQUEST_STATUS_NEW),
        ActionCommand("c", Action.ASSIGN_GROUP, {"group": "plumber"}),
        DISPATCHER, SYSTEM_PRINCIPAL, NOW)
    assert [d.kind for d in res.domain_ops] == ["create_assignment"]


def test_dispatch_group_rejects_executor():
    with pytest.raises(PayloadInvalid):
        plan_transition(
            _snap(REQUEST_STATUS_NEW),
            ActionCommand("c", Action.ASSIGN_GROUP, {"executor_id": 7}),
            DISPATCHER, SYSTEM_PRINCIPAL, NOW)


# ═══ EXECUTOR_CLAIM — теперь и из «Новой» ═══

def test_executor_claims_from_new():
    """Дежурный берёт нераспределённую заявку сам — она становится «В работе»."""
    res = _plan(_group_snap(REQUEST_STATUS_NEW), Action.EXECUTOR_CLAIM, DUTY)
    fields = _patch_fields(res)
    assert fields["status"] == (Op.SET, REQUEST_STATUS_IN_PROGRESS)
    assert [d.kind for d in res.domain_ops] == ["claim_group_assignment"]


def test_executor_claim_still_works_from_in_progress():
    """Legacy-заявки, уже висящие «В работе» с группой, берутся как раньше."""
    res = _plan(_group_snap(REQUEST_STATUS_IN_PROGRESS), Action.EXECUTOR_CLAIM, DUTY)
    assert _patch_fields(res)["status"] == (Op.SET, REQUEST_STATUS_IN_PROGRESS)


def test_claim_honours_universal_joker():
    """BUG-166 в гварде взятия: сравнение шло сырым membership.

    Универсал («умеет всё») не мог взять заявку ни одной группы.
    """
    universal = _user(EXECUTOR_ID, "executor", specializations={"universal"})
    res = _plan(_group_snap(), Action.EXECUTOR_CLAIM, universal)
    assert _patch_fields(res)["status"] == (Op.SET, REQUEST_STATUS_IN_PROGRESS)


def test_claim_still_refused_for_wrong_specialization():
    from uk_management_bot.utils.request_workflow import NotAuthorized
    other = _user(EXECUTOR_ID, "executor", specializations={"cleaning"})
    with pytest.raises(NotAuthorized):
        _plan(_group_snap(), Action.EXECUTOR_CLAIM, other)


# ═══ MANAGER_ASSIGN без исполнителя больше не создаёт ничью заявку ═══

def test_manager_assign_requires_executor_from_new():
    """«Менеджер взял заявку, исполнителя выберет потом» = ничья заявка."""
    with pytest.raises(PayloadInvalid):
        _plan(_snap(REQUEST_STATUS_NEW), Action.MANAGER_ASSIGN, MANAGER)


def test_manager_assign_rejects_group():
    """Адресовать группе — отдельным действием, а не этим."""
    with pytest.raises(PayloadInvalid):
        _plan(_snap(REQUEST_STATUS_NEW), Action.MANAGER_ASSIGN, MANAGER,
              {"group": "plumber"})


def test_manager_can_assign_group_without_moving_status():
    """Менеджер вправе адресовать заявку группе — но не двигая её статус."""
    res = _plan(_snap(REQUEST_STATUS_NEW), Action.ASSIGN_GROUP, MANAGER,
                {"group": "plumber"})
    fields = _patch_fields(res)
    assert fields["status"] == (Op.SET, REQUEST_STATUS_NEW)
    assert fields["assigned_group"] == (Op.SET, "plumber")


# ═══ Путь создания заявки: подобрать дежурного, иначе оставить «Новая» ═══

def test_dispatch_assigns_duty_executor_when_found(monkeypatch):
    from uk_management_bot.services import dispatch as mod

    monkeypatch.setattr(mod, "_auto_assign_enabled_sync", lambda db=None: True)
    monkeypatch.setattr(mod, "pick_duty_executor_id", lambda spec, db=None: 42)
    captured = {}
    import uk_management_bot.services.workflow_runner as runner
    monkeypatch.setattr(runner, "run_command_sync",
                        lambda factory, number, principal, command, **kw:
                        captured.setdefault("cmd", command))

    mod.auto_dispatch_new_request_sync("260817-001", "plumbing", _db=MagicMock())

    assert captured["cmd"].action is Action.SYSTEM_DISPATCH_ASSIGN
    assert captured["cmd"].payload == {"executor_id": 42}


# ─────────────────── pick_duty_executor_id: strict-режим ───────────────────
#
# Фоновый диспетчер идёт ПОСЛЕ commit создания заявки и не вправе её уронить,
# поэтому по умолчанию ошибка подбора гасится в None. Интерактивному
# переназначению это врёт: None там печатается как «нет дежурного», и авария БД
# выглядела бы как пустой результат.


def test_pick_duty_swallows_errors_by_default(monkeypatch):
    from uk_management_bot.services import dispatch as mod
    import uk_management_bot.services.auto_manager.rule_engine as engine

    def _boom(*a, **kw):
        raise RuntimeError("БД недоступна")

    monkeypatch.setattr(engine, "select_executor", _boom)
    assert mod.pick_duty_executor_id("plumber", db=MagicMock()) is None


def test_pick_duty_strict_reraises(monkeypatch):
    from uk_management_bot.services import dispatch as mod
    import uk_management_bot.services.auto_manager.rule_engine as engine

    def _boom(*a, **kw):
        raise RuntimeError("БД недоступна")

    monkeypatch.setattr(engine, "select_executor", _boom)
    with pytest.raises(RuntimeError):
        mod.pick_duty_executor_id("plumber", db=MagicMock(), strict=True)


def test_pick_duty_forwards_exclude_to_select_executor(monkeypatch):
    from uk_management_bot.services import dispatch as mod
    import uk_management_bot.services.auto_manager.rule_engine as engine

    seen = {}

    def _spy(session, spec, now, snapshot=None, exclude_user_ids=frozenset()):
        seen["exclude"] = exclude_user_ids
        return None

    monkeypatch.setattr(engine, "select_executor", _spy)
    mod.pick_duty_executor_id("plumber", db=MagicMock(),
                              exclude_user_ids=frozenset({7}))
    assert seen["exclude"] == frozenset({7})


def test_dispatch_falls_back_to_group_without_moving_status(monkeypatch):
    """Дежурного нет → группа, статус не двигается (ASSIGN_GROUP)."""
    from uk_management_bot.services import dispatch as mod

    monkeypatch.setattr(mod, "_auto_assign_enabled_sync", lambda db=None: True)
    monkeypatch.setattr(mod, "pick_duty_executor_id", lambda spec, db=None: None)
    captured = {}
    import uk_management_bot.services.workflow_runner as runner
    monkeypatch.setattr(runner, "run_command_sync",
                        lambda factory, number, principal, command, **kw:
                        captured.setdefault("cmd", command))

    mod.auto_dispatch_new_request_sync("260817-002", "plumbing", _db=MagicMock())

    assert captured["cmd"].action is Action.ASSIGN_GROUP
    assert captured["cmd"].payload == {"group": "plumber"}


def test_dispatch_does_nothing_when_toggle_off(monkeypatch):
    from uk_management_bot.services import dispatch as mod

    monkeypatch.setattr(mod, "_auto_assign_enabled_sync", lambda db=None: False)
    called = []
    import uk_management_bot.services.workflow_runner as runner
    monkeypatch.setattr(runner, "run_command_sync",
                        lambda *a, **kw: called.append(1))

    mod.auto_dispatch_new_request_sync("260817-003", "plumbing", _db=MagicMock())
    assert called == [], "при выключенном автоназначении заявка не трогается вовсе"
