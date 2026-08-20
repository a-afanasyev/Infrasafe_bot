"""Единственный писатель ФИО: guard, идемпотентность, аудит.

Сессия здесь настоящая (sqlite), а не мок: проверяется в том числе то, что
`apply_rename` НИЧЕГО не коммитит сам — иначе бот-вызов внутри `run_db` и
API-вызов внутри своей транзакции получили бы два разных контракта.
"""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.users.rename import (
    AUDIT_ACTION,
    RenameForbidden,
    apply_rename,
    ensure_renamable,
    plan_rename,
)
from uk_management_bot.utils.person_name import InvalidFullName

_engine = create_engine("sqlite:///:memory:", echo=False)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


def _user(db, *, first="Иванов", last="Иван", roles='["applicant"]', tg=555001):
    u = User(telegram_id=tg, first_name=first, last_name=last, roles=roles, status="approved")
    db.add(u)
    db.commit()
    return u


class TestGuard:
    @pytest.mark.parametrize("roles", ['["manager"]', '["admin"]', '["applicant","manager"]'])
    def test_privileged_target_refused(self, db, roles):
        u = _user(db, roles=roles)
        with pytest.raises(RenameForbidden):
            ensure_renamable(u)

    @pytest.mark.parametrize("roles", ['["applicant"]', '["executor"]', '["inspector"]',
                                       '["applicant","executor"]', None])
    def test_ordinary_target_allowed(self, db, roles):
        u = _user(db, roles=roles)
        ensure_renamable(u)  # не бросает

    def test_resource_meter_entry_is_not_privileged(self, db):
        # Капабилити контролёра показаний — не стафф-роль (тот же вывод, что у
        # guard'а раздела «Жители»): опечатку такому аккаунту править можно.
        u = _user(db, roles='["applicant","resource_meter_entry"]')
        ensure_renamable(u)


class TestPlan:
    def test_splits_and_keeps_old_name(self, db):
        u = _user(db, first="Иванов", last="Иван")
        plan = plan_rename(u, "  Петров   Пётр Петрович ")
        assert plan.old_full_name == "Иванов Иван"
        assert plan.new_full_name == "Петров Пётр Петрович"
        assert (plan.first_name, plan.last_name) == ("Петров", "Пётр Петрович")
        assert plan.changed is True

    def test_same_name_is_not_a_change(self, db):
        u = _user(db, first="Иванов", last="Иван")
        assert plan_rename(u, " Иванов    Иван ").changed is False

    def test_invalid_input_raises(self, db):
        u = _user(db)
        with pytest.raises(InvalidFullName):
            plan_rename(u, "   ")

    def test_target_without_name_has_none_as_old(self, db):
        u = _user(db, first=None, last=None)
        assert plan_rename(u, "Сидоров").old_full_name is None


class TestApply:
    def test_writes_fields_and_audit(self, db):
        u = _user(db, first="Иванов", last="Иван", tg=770001)
        actor = _user(db, first="Мен", last="Еджер", roles='["manager"]', tg=770002)

        assert apply_rename(db, u, plan_rename(u, "Петров Пётр"), actor_id=actor.id) is True
        db.commit()

        db.refresh(u)
        assert (u.first_name, u.last_name) == ("Петров", "Пётр")

        log = db.query(AuditLog).filter(AuditLog.action == AUDIT_ACTION).one()
        assert log.user_id == actor.id
        assert log.telegram_user_id == 770001
        details = json.loads(log.details)
        assert details == {
            "target_user_id": u.id,
            "old_full_name": "Иванов Иван",
            "new_full_name": "Петров Пётр",
        }

    def test_noop_writes_nothing(self, db):
        u = _user(db, first="Иванов", last="Иван")
        assert apply_rename(db, u, plan_rename(u, "Иванов Иван"), actor_id=None) is False
        db.commit()
        assert db.query(AuditLog).count() == 0

    def test_does_not_commit_by_itself(self, db):
        # Контракт «коммитит вызывающий»: без commit откат обязан вернуть
        # старое ФИО и убрать строку аудита.
        u = _user(db, first="Иванов", last="Иван")
        apply_rename(db, u, plan_rename(u, "Петров Пётр"), actor_id=None)
        db.rollback()
        db.refresh(u)
        assert (u.first_name, u.last_name) == ("Иванов", "Иван")
        assert db.query(AuditLog).count() == 0

    def test_single_word_clears_last_name(self, db):
        u = _user(db, first="Иванов", last="Иван")
        apply_rename(db, u, plan_rename(u, "Сидоров"), actor_id=None)
        db.commit()
        db.refresh(u)
        assert u.first_name == "Сидоров"
        assert u.last_name is None
