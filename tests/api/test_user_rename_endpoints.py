"""Исправление ФИО менеджером: две точки входа, одно поведение.

Обе карточки — жителя и сотрудника — пишут одно и то же поле, поэтому право,
валидация и идемпотентность пинятся на КАЖДОМ эндпоинте отдельно: общий
сервис-слой легко обойти, добавив «маленькую особенность» в один из роутеров.
"""
import json

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User
from uk_management_bot.services.users.rename import AUDIT_ACTION
from uk_management_bot.utils.person_name import MAX_FULL_NAME_LEN

pytestmark = pytest.mark.asyncio

RESIDENTS = "/api/v2/residents"
EMPLOYEES = "/api/v2/shifts/employees"


async def _user(db, tg, *, roles='["applicant"]', first="Иванав", last="Иван") -> User:
    u = User(telegram_id=tg, first_name=first, last_name=last, roles=roles,
             active_role="applicant", status="approved", language="ru")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _audit_rows(db, target_id: int) -> list[dict]:
    db.expire_all()
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == AUDIT_ACTION)
    )).scalars().all()
    out = []
    for r in rows:
        details = json.loads(r.details) if isinstance(r.details, str) else (r.details or {})
        if details.get("target_user_id") == target_id:
            out.append(details)
    return out


async def _reload(db, user: User) -> User:
    # id снимается ДО expire_all: после него любой атрибут инстанса требует
    # синхронной подгрузки, которой в async-сессии взяться неоткуда.
    user_id = user.id
    db.expire_all()
    return (await db.execute(select(User).where(User.id == user_id))).scalar_one()


@pytest_asyncio.fixture
def as_user():
    """Подменить актора запроса (по умолчанию conftest даёт менеджера)."""
    prev = app.dependency_overrides.get(get_current_user)
    applied = []

    def _apply(user):
        app.dependency_overrides[get_current_user] = lambda: user
        applied.append(True)

    yield _apply
    if applied:
        if prev is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = prev


# ═══════════════════════ успешный путь ═══════════════════════


class TestResidentRename:

    async def test_updates_columns_and_returns_full_name(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        u = await _user(db_session, 8101)
        r = await client.patch(f"{RESIDENTS}/{u.id}/name",
                               json={"full_name": "Иванов Иван Иванович"})
        assert r.status_code == 200, r.text
        assert r.json() == {
            "id": u.id,
            "first_name": "Иванов",
            "last_name": "Иван Иванович",
            "full_name": "Иванов Иван Иванович",
        }
        fresh = await _reload(db_session, u)
        assert (fresh.first_name, fresh.last_name) == ("Иванов", "Иван Иванович")

    async def test_writes_audit_with_old_and_new(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        u = await _user(db_session, 8102, first="Иванав", last="Иван")
        await client.patch(f"{RESIDENTS}/{u.id}/name", json={"full_name": "Иванов Иван"})
        rows = await _audit_rows(db_session, u.id)
        assert len(rows) == 1
        assert rows[0]["old_full_name"] == "Иванав Иван"
        assert rows[0]["new_full_name"] == "Иванов Иван"

    async def test_normalizes_whitespace_and_invisibles(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        u = await _user(db_session, 8103)
        r = await client.patch(f"{RESIDENTS}/{u.id}/name",
                               json={"full_name": "  Пет​ров   Пётр\n"})
        assert r.status_code == 200, r.text
        assert r.json()["full_name"] == "Петров Пётр"

    async def test_same_name_is_idempotent_and_writes_no_audit(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        u = await _user(db_session, 8104, first="Иванов", last="Иван")
        r = await client.patch(f"{RESIDENTS}/{u.id}/name", json={"full_name": "Иванов   Иван"})
        assert r.status_code == 200
        assert await _audit_rows(db_session, u.id) == []

    async def test_multirole_resident_can_be_renamed(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        # Осознанное отличие от approve/block/unblock: те трогают общий на все
        # роли `status`, поэтому у мультиролевого запрещены. ФИО тоже одно на
        # все роли — но именно поэтому его правка отсюда законна, иначе
        # опечатку жителя-исполнителя нельзя было бы исправить в его карточке.
        u = await _user(db_session, 8105, roles='["applicant","executor"]')
        r = await client.patch(f"{RESIDENTS}/{u.id}/name", json={"full_name": "Сидоров Сидор"})
        assert r.status_code == 200, r.text


class TestEmployeeRename:

    async def test_updates_columns(self, client: AsyncClient, db_session: AsyncSession):
        u = await _user(db_session, 8201, roles='["executor"]')
        r = await client.patch(f"{EMPLOYEES}/{u.id}/name",
                               json={"full_name": "Петров Пётр Петрович"})
        assert r.status_code == 200, r.text
        assert r.json()["full_name"] == "Петров Пётр Петрович"
        fresh = await _reload(db_session, u)
        assert (fresh.first_name, fresh.last_name) == ("Петров", "Пётр Петрович")

    async def test_writes_audit(self, client: AsyncClient, db_session: AsyncSession):
        u = await _user(db_session, 8202, roles='["executor"]', first="Петрав", last="Пётр")
        await client.patch(f"{EMPLOYEES}/{u.id}/name", json={"full_name": "Петров Пётр"})
        rows = await _audit_rows(db_session, u.id)
        assert len(rows) == 1
        assert rows[0]["old_full_name"] == "Петрав Пётр"


# ═══════════════════════ право ═══════════════════════


class TestAuthorization:

    async def test_resident_endpoint_rejects_non_manager(
        self, client: AsyncClient, db_session: AsyncSession, as_user
    ):
        u = await _user(db_session, 8301)
        as_user(u)
        r = await client.patch(f"{RESIDENTS}/{u.id}/name", json={"full_name": "Кто Угодно"})
        assert r.status_code == 403

    async def test_employee_endpoint_rejects_non_manager(
        self, client: AsyncClient, db_session: AsyncSession, as_user
    ):
        u = await _user(db_session, 8302, roles='["executor"]')
        as_user(u)
        r = await client.patch(f"{EMPLOYEES}/{u.id}/name", json={"full_name": "Кто Угодно"})
        assert r.status_code == 403

    @pytest.mark.parametrize("privileged,tg", [("manager", 8311), ("admin", 8312)])
    async def test_privileged_target_refused_on_employee_endpoint(
        self, client: AsyncClient, db_session: AsyncSession, privileged, tg
    ):
        u = await _user(db_session, tg, roles=f'["{privileged}"]')
        r = await client.patch(f"{EMPLOYEES}/{u.id}/name", json={"full_name": "Новое Имя"})
        assert r.status_code == 403, r.text
        fresh = await _reload(db_session, u)
        assert fresh.first_name == "Иванав"

    @pytest.mark.parametrize("privileged,tg", [("manager", 8321), ("admin", 8322)])
    async def test_privileged_target_refused_on_resident_endpoint(
        self, client: AsyncClient, db_session: AsyncSession, privileged, tg
    ):
        # Роль applicant обязательна: без неё раздел «Жители» ответит 404 по
        # scope и отказ прилетел бы не от того guard'а, который проверяется.
        u = await _user(db_session, tg, roles=f'["applicant","{privileged}"]')
        r = await client.patch(f"{RESIDENTS}/{u.id}/name", json={"full_name": "Новое Имя"})
        assert r.status_code == 403, r.text
        fresh = await _reload(db_session, u)
        assert fresh.first_name == "Иванав"


# ═══════════════════════ scope и отсутствие ═══════════════════════


class TestScope:

    async def test_resident_endpoint_refuses_non_resident_id(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        # Пользователь без роли applicant в разделе «Жители» не существует —
        # иначе эндпоинт переименовывал бы кого угодно по id.
        u = await _user(db_session, 8401, roles='["executor"]')
        r = await client.patch(f"{RESIDENTS}/{u.id}/name", json={"full_name": "Новое Имя"})
        assert r.status_code == 404

    async def test_unknown_id_404(self, client: AsyncClient):
        for base in (RESIDENTS, EMPLOYEES):
            r = await client.patch(f"{base}/99999999/name", json={"full_name": "Новое Имя"})
            assert r.status_code == 404, f"{base}: {r.text}"


# ═══════════════════════ валидация ═══════════════════════


class TestValidation:

    @pytest.mark.parametrize("value", ["", "   ", "​​"])
    async def test_blank_rejected(self, client: AsyncClient, db_session: AsyncSession, value):
        u = await _user(db_session, 8500 + len(value))
        r = await client.patch(f"{RESIDENTS}/{u.id}/name", json={"full_name": value})
        assert r.status_code == 422, r.text

    async def test_without_letters_rejected(self, client: AsyncClient, db_session: AsyncSession):
        u = await _user(db_session, 8510)
        r = await client.patch(f"{RESIDENTS}/{u.id}/name", json={"full_name": "12345"})
        assert r.status_code == 422

    async def test_too_long_rejected(self, client: AsyncClient, db_session: AsyncSession):
        u = await _user(db_session, 8511)
        r = await client.patch(f"{RESIDENTS}/{u.id}/name",
                               json={"full_name": "Я" * (MAX_FULL_NAME_LEN + 1)})
        assert r.status_code == 422

    async def test_rejected_input_leaves_row_untouched(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        u = await _user(db_session, 8512, first="Иванав", last="Иван")
        uid = u.id
        await client.patch(f"{RESIDENTS}/{uid}/name", json={"full_name": "   "})
        fresh = await _reload(db_session, u)
        assert (fresh.first_name, fresh.last_name) == ("Иванав", "Иван")
        assert await _audit_rows(db_session, uid) == []
