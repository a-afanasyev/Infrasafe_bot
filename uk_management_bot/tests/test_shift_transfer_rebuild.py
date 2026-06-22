"""REG-02: тесты перестроенной фичи передачи смен (ShiftTransferService).

Покрывают: create_transfer (happy/guards), assign_transfer (pending→assigned,
self/role guards), accept_transfer (перенос смены+заявок status-preserving;
скоуп по ShiftAssignment и fallback по executor_id; rollback при невалидной
цели — нет «висячего accepted»), reject_transfer, reassign_shift (прямой,
record_history, notification_jobs не рассылаются до commit), telegram_id↔user.id,
require_role-DI сигнатуры новых хендлеров.
"""
import inspect
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift_assignment import ShiftAssignment
from uk_management_bot.database.models.shift_transfer import ShiftTransfer


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _no_notifications():
    """Глушим NotificationService — отправка в тестах не нужна (best-effort)."""
    with patch("uk_management_bot.services.shift_transfer_service.NotificationService"):
        yield


def _service(db):
    from uk_management_bot.services.shift_transfer_service import ShiftTransferService
    return ShiftTransferService(db)


def _user(db, uid, tg, *, roles='["executor"]', status="approved", specialization=None):
    u = User(id=uid, telegram_id=tg, username=f"u{uid}", first_name="U", last_name=str(uid),
             roles=roles, status=status, language="ru", specialization=specialization)
    db.add(u)
    db.commit()
    return u


def _shift(db, sid, user_id, *, status="active", specs=None, hours=8):
    start = datetime(2026, 6, 22, 8, 0, tzinfo=timezone.utc)
    s = Shift(id=sid, user_id=user_id, status=status, start_time=start,
              end_time=start + timedelta(hours=hours), specialization_focus=specs)
    db.add(s)
    db.commit()
    return s


def _request(db, number, executor_id, *, status="В работе"):
    r = Request(request_number=number, user_id=999, category="plumbing",
                description="desc", status=status, executor_id=executor_id)
    db.add(r)
    db.commit()
    return r


def _individual_assignment(db, number, executor_id):
    a = RequestAssignment(request_number=number, assignment_type="individual",
                          executor_id=executor_id, status="active", created_by=executor_id)
    db.add(a)
    db.commit()
    return a


def _shift_assignment(db, shift_id, number, *, status="assigned"):
    sa = ShiftAssignment(shift_id=shift_id, request_number=number, status=status)
    db.add(sa)
    db.commit()
    return sa


# ========== create_transfer ==========

def test_create_transfer_happy(db):
    _user(db, 10, 1010)
    _shift(db, 1, 10, status="planned")
    res = _service(db).create_transfer(1, 10, "illness", "комментарий", "high")
    assert res["success"] is True
    tr = db.query(ShiftTransfer).filter(ShiftTransfer.id == res["transfer_id"]).first()
    assert tr.status == "pending"
    assert tr.from_executor_id == 10          # внутренний users.id, не telegram_id
    assert tr.reason == "illness"


def test_create_transfer_not_your_shift(db):
    _user(db, 10, 1010)
    _user(db, 11, 1111)
    _shift(db, 1, 11, status="planned")       # принадлежит другому
    res = _service(db).create_transfer(1, 10, "illness", "", "normal")
    assert res == {"success": False, "error": "not_your_shift"}


def test_create_transfer_duplicate_blocked(db):
    _user(db, 10, 1010)
    _shift(db, 1, 10, status="planned")
    svc = _service(db)
    assert svc.create_transfer(1, 10, "illness", "", "normal")["success"] is True
    res2 = svc.create_transfer(1, 10, "workload", "", "normal")
    assert res2 == {"success": False, "error": "transfer_already_exists"}


def test_create_transfer_terminal_shift(db):
    _user(db, 10, 1010)
    _shift(db, 1, 10, status="completed")
    res = _service(db).create_transfer(1, 10, "illness", "", "normal")
    assert res == {"success": False, "error": "shift_not_transferable"}


# ========== assign_transfer ==========

def test_assign_transfer_pending_to_assigned(db):
    _user(db, 10, 1010)
    _user(db, 20, 2020)          # получатель
    _user(db, 30, 3030, roles='["manager"]')
    _shift(db, 1, 10, status="planned")
    tid = _service(db).create_transfer(1, 10, "illness", "", "normal")["transfer_id"]

    res = _service(db).assign_transfer(tid, 20, manager_id=30)
    assert res["success"] is True
    tr = db.query(ShiftTransfer).filter(ShiftTransfer.id == tid).first()
    assert tr.status == "assigned"
    assert tr.to_executor_id == 20
    assert tr.assigned_by == 30


def test_assign_transfer_cannot_self(db):
    _user(db, 10, 1010)
    _shift(db, 1, 10, status="planned")
    tid = _service(db).create_transfer(1, 10, "illness", "", "normal")["transfer_id"]
    res = _service(db).assign_transfer(tid, 10, manager_id=30)
    assert res == {"success": False, "error": "cannot_assign_to_self"}


def test_assign_transfer_target_not_executor(db):
    _user(db, 10, 1010)
    _user(db, 20, 2020, roles='["applicant"]')   # не исполнитель
    _shift(db, 1, 10, status="planned")
    tid = _service(db).create_transfer(1, 10, "illness", "", "normal")["transfer_id"]
    res = _service(db).assign_transfer(tid, 20, manager_id=30)
    assert res == {"success": False, "error": "not_executor"}


# ========== accept_transfer ==========

def test_accept_moves_shift_and_requests_scope_shift_assignment(db):
    _user(db, 10, 1010)
    _user(db, 20, 2020)
    _shift(db, 1, 10, status="active")
    _request(db, "T-1", 10, status="Закуп")
    _individual_assignment(db, "T-1", 10)
    _shift_assignment(db, 1, "T-1", status="assigned")
    svc = _service(db)
    tid = svc.create_transfer(1, 10, "illness", "", "normal")["transfer_id"]
    svc.assign_transfer(tid, 20, manager_id=30)

    res = svc.accept_transfer(tid, 20)
    assert res["success"] is True

    db.expire_all()
    shift = db.query(Shift).filter(Shift.id == 1).first()
    req = db.query(Request).filter(Request.request_number == "T-1").first()
    assignment = db.query(RequestAssignment).filter(RequestAssignment.request_number == "T-1").first()
    tr = db.query(ShiftTransfer).filter(ShiftTransfer.id == tid).first()
    assert shift.user_id == 20
    assert req.executor_id == 20
    assert req.status == "Закуп"          # статус НЕ изменился (status-preserving)
    assert assignment.executor_id == 20
    assert tr.status == "completed"


def test_accept_fallback_by_executor_id_when_no_shift_assignment(db):
    _user(db, 10, 1010)
    _user(db, 20, 2020)
    _shift(db, 1, 10, status="active")
    _request(db, "T-9", 10, status="В работе")    # без ShiftAssignment
    svc = _service(db)
    tid = svc.create_transfer(1, 10, "illness", "", "normal")["transfer_id"]
    svc.assign_transfer(tid, 20, manager_id=30)
    assert svc.accept_transfer(tid, 20)["success"] is True

    db.expire_all()
    assert db.query(Request).filter(Request.request_number == "T-9").first().executor_id == 20


def test_accept_planned_shift_no_fallback_move(db):
    _user(db, 10, 1010)
    _user(db, 20, 2020)
    _shift(db, 1, 10, status="planned")
    _request(db, "T-3", 10, status="В работе")    # planned-смена → fallback не срабатывает
    svc = _service(db)
    tid = svc.create_transfer(1, 10, "illness", "", "normal")["transfer_id"]
    svc.assign_transfer(tid, 20, manager_id=30)
    res = svc.accept_transfer(tid, 20)
    assert res["success"] is True
    assert res["moved_requests"] == 0

    db.expire_all()
    assert db.query(Request).filter(Request.request_number == "T-3").first().executor_id == 10
    assert db.query(Shift).filter(Shift.id == 1).first().user_id == 20


def test_accept_rollback_when_target_invalid_no_dangling_accepted(db):
    _user(db, 10, 1010)
    recipient = _user(db, 20, 2020)
    _shift(db, 1, 10, status="planned")
    svc = _service(db)
    tid = svc.create_transfer(1, 10, "illness", "", "normal")["transfer_id"]
    svc.assign_transfer(tid, 20, manager_id=30)

    # Гонка: получатель потерял подтверждение между assign и accept.
    recipient.status = "pending"
    db.commit()

    res = svc.accept_transfer(tid, 20)
    assert res["success"] is False
    assert res["error"] == "not_approved"

    db.expire_all()
    tr = db.query(ShiftTransfer).filter(ShiftTransfer.id == tid).first()
    assert tr.status == "assigned"          # НЕ «висячий accepted»
    assert db.query(Shift).filter(Shift.id == 1).first().user_id == 10


def test_accept_not_your_transfer(db):
    _user(db, 10, 1010)
    _user(db, 20, 2020)
    _user(db, 21, 2121)
    _shift(db, 1, 10, status="planned")
    svc = _service(db)
    tid = svc.create_transfer(1, 10, "illness", "", "normal")["transfer_id"]
    svc.assign_transfer(tid, 20, manager_id=30)
    res = svc.accept_transfer(tid, 21)      # отвечает не тот исполнитель
    assert res == {"success": False, "error": "not_your_transfer"}


# ========== reject_transfer ==========

def test_reject_transfer_keeps_shift(db):
    _user(db, 10, 1010)
    _user(db, 20, 2020)
    _shift(db, 1, 10, status="planned")
    svc = _service(db)
    tid = svc.create_transfer(1, 10, "illness", "", "normal")["transfer_id"]
    svc.assign_transfer(tid, 20, manager_id=30)

    assert svc.reject_transfer(tid, 20)["success"] is True
    db.expire_all()
    assert db.query(ShiftTransfer).filter(ShiftTransfer.id == tid).first().status == "rejected"
    assert db.query(Shift).filter(Shift.id == 1).first().user_id == 10   # смена не менялась


# ========== reassign_shift (прямой менеджерский) ==========

def test_reassign_shift_records_history_and_returns_jobs_without_dispatch(db):
    _user(db, 10, 1010)
    _user(db, 20, 2020)
    _user(db, 30, 3030, roles='["manager"]')
    _shift(db, 1, 10, status="active")
    svc = _service(db)

    res = svc.reassign_shift(1, 20, actor_manager_id=30, record_history=True)
    assert res["success"] is True
    assert len(res["notification_jobs"]) == 2          # новый + старый исполнитель
    # Ядро НЕ рассылает само (jobs шлёт владелец после commit) и НЕ коммитит.
    svc.notification_service.notify_user.assert_not_called()

    db.commit()            # владелец транзакции коммитит (как делает хендлер)
    db.expire_all()
    assert db.query(Shift).filter(Shift.id == 1).first().user_id == 20
    hist = db.query(ShiftTransfer).filter(
        ShiftTransfer.shift_id == 1, ShiftTransfer.status == "completed"
    ).first()
    assert hist is not None
    assert hist.auto_assigned is True
    assert hist.assigned_by == 30
    assert hist.from_executor_id == 10
    assert hist.to_executor_id == 20
    assert hist.reason == "manager_reassign"


def test_reassign_shift_same_executor_rejected(db):
    _user(db, 10, 1010)
    _shift(db, 1, 10, status="active")
    res = _service(db).reassign_shift(1, 10, actor_manager_id=30, record_history=True)
    assert res == {"success": False, "error": "same_executor", "notification_jobs": []}


def test_reassign_shift_spec_mismatch(db):
    _user(db, 10, 1010)
    _user(db, 20, 2020, specialization='["electric"]')
    _shift(db, 1, 10, status="active", specs=["plumbing"])
    res = _service(db).reassign_shift(1, 20, actor_manager_id=30, record_history=True)
    assert res["success"] is False
    assert res["error"] == "spec_mismatch"


def test_reassign_shift_unassigned_or_terminal_not_transferable(db):
    # Code-review HIGH-4/MED-1: смена без владельца (from_executor_id=None → NOT
    # NULL) и completed/cancelled-смена не переназначаются мягким guard'ом.
    _user(db, 20, 2020)
    _shift(db, 1, None, status="planned")        # без владельца
    _shift(db, 2, 20, status="completed")        # терминальная
    svc = _service(db)
    res_unassigned = svc.reassign_shift(1, 20, actor_manager_id=30, record_history=True)
    res_terminal = svc.reassign_shift(2, 20, actor_manager_id=30, record_history=True)
    assert res_unassigned["error"] == "shift_not_transferable"
    assert res_terminal["error"] == "shift_not_transferable"


def test_reassign_shift_overlap_rejected(db):
    _user(db, 10, 1010)
    _user(db, 20, 2020)
    _shift(db, 1, 10, status="active")
    _shift(db, 2, 20, status="active")    # у 20 уже есть пересекающаяся смена
    res = _service(db).reassign_shift(1, 20, actor_manager_id=30, record_history=True)
    assert res["success"] is False
    assert res["error"] == "overlap"


def test_reassign_shift_spec_ok_when_executor_has_specs(db):
    _user(db, 10, 1010)
    _user(db, 20, 2020, specialization='["plumbing", "electric"]')
    _shift(db, 1, 10, status="active", specs=["plumbing"])
    res = _service(db).reassign_shift(1, 20, actor_manager_id=30, record_history=True)
    assert res["success"] is True


# ========== require_role-DI сигнатуры новых хендлеров ==========

@pytest.mark.parametrize("module_path, func_name", [
    ("uk_management_bot.handlers.shift_transfer", "cmd_transfer_shift"),
    ("uk_management_bot.handlers.shift_transfer", "cmd_pending_transfers"),
    ("uk_management_bot.handlers.shift_transfer", "cmd_assign_transfer"),
    ("uk_management_bot.handlers.shift_transfer", "handle_transfer_assign_executor"),
    ("uk_management_bot.handlers.shift_transfer", "handle_transfer_response"),
    ("uk_management_bot.handlers.shift_transfer", "cmd_my_transfers"),
    ("uk_management_bot.handlers.shift_management", "handle_reassign_shift_pick"),
    ("uk_management_bot.handlers.shift_management", "handle_reassign_executor"),
])
def test_require_role_handlers_declare_di_params(module_path, func_name):
    import importlib
    mod = importlib.import_module(module_path)
    func = getattr(mod, func_name)
    params = inspect.signature(func).parameters
    assert "roles" in params, f"{func_name}: нет roles в сигнатуре (require_role-DI)"
    assert "db" in params and "user" in params
