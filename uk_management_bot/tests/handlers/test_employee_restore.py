"""Бот: удалённые из веба сотрудники и их восстановление.

Удаление из дашборда мягкое (запись остаётся со статусом `deleted`). Такие
сотрудники всплывали в списках «Исполнители»/«Менеджеры» с сырым статусом и
без способа вернуть. Теперь у них свой список, подпись и «Восстановить»:
запись возвращается в очередь одобрения — права возвращает одобрение, а не
само восстановление.
"""
import datetime
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.handlers.employee_management._units import _restore_employee
from uk_management_bot.keyboards.employee_management import (
    get_employee_actions_keyboard,
    get_employee_management_main_keyboard,
)
from uk_management_bot.services.user_management_service import UserManagementService
from uk_management_bot.utils.employee_display import format_user_status

WHEN = datetime.datetime(2026, 11, 2, tzinfo=datetime.timezone.utc)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _user(db, tg, *, roles, status="approved", **extra):
    user = User(telegram_id=tg, first_name="U", last_name=str(tg), roles=json.dumps(roles),
                active_role=roles[0], status=status, **extra)
    db.add(user)
    db.commit()
    return user


def _callbacks(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def test_deleted_have_own_list_and_leave_the_working_ones(db):
    working = _user(db, 1, roles=["executor"])
    gone = _user(db, 2, roles=["executor"], status="deleted", deleted_at=WHEN)
    service = UserManagementService(db)
    assert [u.id for u in service.get_employees_list("deleted")["employees"]] == [gone.id]
    assert [u.id for u in service.get_employees_list("executors")["employees"]] == [working.id]


def test_deleted_status_has_a_label_and_menu_entry():
    assert format_user_status("deleted", "ru") == "🗑️ Удалён"
    assert "O'chirilgan" in format_user_status("deleted", "uz")
    stats = {"pending": 0, "active": 0, "blocked": 0, "executors": 0, "managers": 0}
    assert "employee_mgmt_list_deleted_1" in _callbacks(get_employee_management_main_keyboard(stats, "ru"))


def test_deleted_card_offers_only_restore():
    callbacks = _callbacks(get_employee_actions_keyboard(7, "deleted", "ru"))
    assert callbacks == ["restore_employee_7", "employee_mgmt_main"]


def test_restore_returns_employee_to_approval_queue(db):
    manager = _user(db, 10, roles=["manager"])
    gone = _user(db, 11, roles=["executor"], status="deleted", deleted_at=WHEN,
                 deleted_by=manager.id, deletion_reason="уволен")

    assert _restore_employee(db, manager.telegram_id, gone.id) == "ok"

    db.refresh(gone)
    assert (gone.status, gone.deleted_at, gone.deleted_by, gone.deletion_reason) == ("pending", None, None, None)
    assert json.loads(gone.roles) == ["executor"], "роли возвращаются как были"
    audit = db.query(AuditLog).filter(AuditLog.action == "user_restored").one()
    assert audit.user_id == manager.id
    assert json.loads(audit.details)["restored_user_id"] == gone.id


def test_restore_refuses_working_employee_and_unknown_actor(db):
    manager = _user(db, 20, roles=["manager"])
    working = _user(db, 21, roles=["executor"])
    gone = _user(db, 22, roles=["executor"], status="deleted", deleted_at=WHEN)
    assert _restore_employee(db, manager.telegram_id, working.id) == "fail"
    assert _restore_employee(db, 999, gone.id) == "no_actor"
    db.refresh(working)
    assert working.status == "approved"


# ── A12-06: восстановление и одобрение не обходят защиту привилегированных ──

def test_restore_refuses_privileged_target(db):
    """Удалённого менеджера рядовой менеджер из бота не возвращает: иначе
    «восстановить → одобрить» обходило бы A10-INT-01."""
    manager = _user(db, 30, roles=["manager"])
    gone = _user(db, 31, roles=["manager"], status="deleted", deleted_at=WHEN)
    assert _restore_employee(db, manager.telegram_id, gone.id) == "fail"
    db.refresh(gone)
    assert gone.status == "deleted" and gone.deleted_at is not None
    assert db.query(AuditLog).filter(AuditLog.action == "user_restored").count() == 0


@pytest.mark.parametrize("status", ["blocked", "deleted"])
def test_approve_refuses_privileged_target_outside_pending(db, status):
    from uk_management_bot.services.auth_service import AuthService

    manager = _user(db, 40, roles=["manager"])
    target = _user(db, 41, roles=["manager"], status=status)
    assert AuthService(db).approve_user(target.id, manager.id, "c") == "error"
    db.refresh(target)
    assert target.status == status


def test_approve_still_admits_invited_manager(db):
    """Новый менеджер после инвайта — `pending`: его одобрение остаётся рабочим путём."""
    from uk_management_bot.services.auth_service import AuthService

    manager = _user(db, 50, roles=["manager"])
    invited = _user(db, 51, roles=["manager"], status="pending", phone="+998901112233")
    assert AuthService(db).approve_user(invited.id, manager.id, "c") == "ok"
    db.refresh(invited)
    assert invited.status == "approved"


@pytest.mark.parametrize("roles, status, expected", [
    (["manager"], "blocked", "already_registered"),
    (["manager"], "deleted", "already_registered"),
    (["executor"], "blocked", "ok"),  # прежнее поведение для непривилегированных
])
def test_invite_does_not_launder_blocked_manager_into_pending(db, monkeypatch, roles, status, expected):
    """Инвайт переводит в `pending`, а из `pending` одобрение разрешено: без этого
    отказа заблокированный менеджер возвращался бы цепочкой инвайт -> одобрение."""
    from uk_management_bot.handlers import auth as auth_handlers

    monkeypatch.setattr(auth_handlers.InviteService, "validate_invite", lambda self, token: {"role": "executor"})
    target = _user(db, 60, roles=roles, status=status)
    assert auth_handlers._load_join_gate(db, "token", target.telegram_id)[0] == expected
