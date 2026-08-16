"""Приглашённый сотрудник оставался ещё и жителем.

Строка пользователя создаётся на самом первом `/start` с `roles=["applicant"]`
— ДО того, как человек ответит на вопрос «кто вы». `process_invite_join_sync`
роль только добавляла, поэтому явный ответ «я сотрудник» ничего не отменял:
человек попадал и в «Жители», и в «Сотрудники» (профиль Назимы на проде —
`["applicant", "executor"]`).

Снимаем `applicant` ТОЛЬКО у того, кто жителем ещё не пожил: `status='pending'`
и роли ровно applicant (+ капабилити). Настоящего жителя, которого позже
пригласили сотрудником, трогать нельзя — он потеряет доступ к своим заявкам
и квартирам.
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base

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


def _user(db, *, roles, status="pending", active_role="applicant"):
    user = User(
        telegram_id=7452869102,
        first_name="Назима",
        roles=json.dumps(roles),
        active_role=active_role,
        status=status,
    )
    db.add(user)
    db.commit()
    return user


def _join(db, user, role, specialization=None):
    from uk_management_bot.services.auth_service import AuthService

    invite = {"role": role, "created_by": 1}
    if specialization:
        invite["specialization"] = specialization
    AuthService(db).process_invite_join_sync(
        telegram_id=user.telegram_id, invite_data=invite,
    )
    db.refresh(user)
    return json.loads(user.roles)


class TestFreshCandidate:
    @pytest.mark.parametrize("staff_role", ["executor", "manager", "inspector"])
    def test_staff_invite_drops_applicant(self, db, staff_role):
        user = _user(db, roles=["applicant"])

        roles = _join(db, user, staff_role)

        assert roles == [staff_role], "роль жителя должна быть снята"
        assert user.active_role == staff_role

    def test_capability_role_is_kept(self, db):
        """resource_meter_entry — капабилити Mini App, не «жительство»."""
        user = _user(db, roles=["applicant", "resource_meter_entry"])

        roles = _join(db, user, "executor")

        assert "applicant" not in roles
        assert set(roles) == {"executor", "resource_meter_entry"}

    def test_applicant_invite_keeps_applicant(self, db):
        """Приглашение жителя роль жителя не снимает — снимать нечего взамен."""
        user = _user(db, roles=["applicant"])

        roles = _join(db, user, "applicant")

        assert roles == ["applicant"]


class TestExistingResident:
    def test_real_resident_keeps_applicant(self, db):
        """Житель, которого позже пригласили сотрудником, роль сохраняет:
        иначе он потеряет доступ к собственным заявкам и квартирам."""
        user = _user(db, roles=["applicant"], status="approved")

        roles = _join(db, user, "executor")

        assert set(roles) == {"applicant", "executor"}

    def test_second_staff_role_does_not_wipe_the_first(self, db):
        user = _user(db, roles=["executor"], status="pending", active_role="executor")

        roles = _join(db, user, "manager")

        assert set(roles) == {"executor", "manager"}
