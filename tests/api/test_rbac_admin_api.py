"""API админки ролей: /api/v2/shifts/employees/rbac/* и /employees/{id}/roles.

Смотреть — `rbac.view` (менеджер) и суперадмин; менять — только суперадмин
из ADMIN_USER_IDS. Права читаются API из таблиц напрямую, поэтому ответы
сразу отражают только что сохранённое.
"""
import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from uk_management_bot.api.dependencies import get_current_user, get_db
from uk_management_bot.api.main import app
from uk_management_bot.authz import get_action
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.rbac import RbacRole, RbacRolePermission, RbacState
from uk_management_bot.database.models.user import User

BASE = "/api/v2/shifts/employees"
SUPERADMIN_TG = 7001
SYSTEM = ("applicant", "executor", "manager", "inspector", "admin", "system_admin",
          "security_operator", "resource_meter_entry")


def _user(uid: int, roles: list[str], tg: int | None = None, status: str = "approved", **kw) -> User:
    return User(id=uid, telegram_id=tg or 100000 + uid, roles=json.dumps(roles),
                active_role=roles[0] if roles else None, status=status, language="ru",
                verification_status="verified", **kw)


@pytest.fixture(autouse=True)
def superadmin_env(monkeypatch):
    from uk_management_bot.config.settings import settings

    monkeypatch.setattr(settings, "ADMIN_USER_IDS", [SUPERADMIN_TG])


@pytest_asyncio.fixture
async def seeded(db_session_factory):
    """Как после миграции 023: системные роли и версия прав."""
    async with db_session_factory() as s:
        s.add_all(RbacRole(key=k, title=k, is_system=True) for k in SYSTEM)
        s.add(RbacState(id=1, version=1))
        s.add_all([
            _user(1, ["manager"]),
            _user(2, ["applicant"], tg=SUPERADMIN_TG),
            _user(3, ["executor"]),
        ])
        await s.commit()
    return db_session_factory


@pytest_asyncio.fixture
async def client(seeded):
    clients: list[AsyncClient] = []

    async def override_get_db():
        async with seeded() as session:
            yield session

    async def _make(uid: int) -> AsyncClient:
        async with seeded() as s:
            actor = await s.get(User, uid)
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: actor
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(c)
        return c

    yield _make
    for c in clients:
        await c.aclose()
    app.dependency_overrides.clear()


MANAGER, SUPERADMIN, EXECUTOR = 1, 2, 3


# ── чтение ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manager_reads_roles_but_cannot_edit(client):
    resp = await (await client(MANAGER)).get(f"{BASE}/rbac/roles")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["can_edit"] is False
    manager = next(r for r in body["roles"] if r["key"] == "manager")
    assert "staff.manage" in manager["actions"] and manager["users_count"] == 1
    assert {r["key"] for r in body["roles"]} == set(SYSTEM)


@pytest.mark.asyncio
async def test_executor_has_no_access(client):
    resp = await (await client(EXECUTOR)).get(f"{BASE}/rbac/roles")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_catalog_lists_every_action(client):
    resp = await (await client(MANAGER)).get(f"{BASE}/rbac/catalog")
    keys = {a["key"]: a for a in resp.json()}
    assert keys["rbac.manage"]["superadmin_only"] is True
    assert keys["staff.manage"]["area"] == "Персонал и смены"


# ── изменение: только суперадмин ────────────────────────────────────────

@pytest.mark.asyncio
async def test_manager_cannot_change_anything(client):
    c = await client(MANAGER)
    assert (await c.post(f"{BASE}/rbac/roles", json={"key": "senior", "title": "S"})).status_code == 403
    assert (await c.put(f"{BASE}/rbac/roles/manager", json={"actions": []})).status_code == 403
    assert (await c.put(f"{BASE}/{EXECUTOR}/roles", json={"roles": ["manager"]})).status_code == 403


@pytest.mark.asyncio
async def test_superadmin_creates_custom_role_with_audit(client, seeded):
    c = await client(SUPERADMIN)
    resp = await c.post(f"{BASE}/rbac/roles", json={
        "key": "senior_exec", "title": "Старший исполнитель", "actions": ["requests.execute", "shifts.manage"]})
    assert resp.status_code == 201, resp.text
    roles = (await c.get(f"{BASE}/rbac/roles")).json()
    assert roles["can_edit"] is True
    senior = next(r for r in roles["roles"] if r["key"] == "senior_exec")
    assert senior["actions"] == ["requests.execute", "shifts.manage"] and senior["is_system"] is False
    async with seeded() as s:
        logs = (await s.execute(select(AuditLog).where(AuditLog.action == "rbac.role.created"))).scalars().all()
        version = (await s.get(RbacState, 1)).version
    assert len(logs) == 1 and version == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,code", [
    ({"key": "manager", "title": "X"}, 409),
    ({"key": "Bad-Key", "title": "X"}, 422),
    ({"key": "ok_role", "title": "X", "actions": ["rbac.manage"]}, 422),
    ({"key": "ok_role", "title": "X", "actions": ["no.such"]}, 422),
])
async def test_create_role_validation(client, payload, code):
    resp = await (await client(SUPERADMIN)).post(f"{BASE}/rbac/roles", json=payload)
    assert resp.status_code == code, resp.text


@pytest.mark.asyncio
async def test_edit_and_reset_system_role(client):
    c = await client(SUPERADMIN)
    current = set(get_action("requests.stats").default_roles)
    assert "manager" in current
    manager_now = next(r for r in (await c.get(f"{BASE}/rbac/roles")).json()["roles"] if r["key"] == "manager")
    reduced = [a for a in manager_now["actions"] if a != "requests.stats"]
    resp = await c.put(f"{BASE}/rbac/roles/manager", json={"actions": reduced})
    assert resp.status_code == 200, resp.text
    assert resp.json()["customized"] == ["requests.stats"]
    reset = await c.post(f"{BASE}/rbac/roles/manager/reset")
    assert reset.status_code == 200 and "requests.stats" in reset.json()["actions"]


async def _rows(seeded, role):
    async with seeded() as s:
        rows = (await s.execute(select(RbacRolePermission).where(RbacRolePermission.role_key == role))).scalars()
        return {(r.action_key, r.allowed) for r in rows}


@pytest.mark.asyncio
async def test_only_differences_from_catalog_are_stored(client, seeded):
    """Совпадающее с каталогом не хранится — будущая правка кода дойдёт до роли."""
    c = await client(SUPERADMIN)
    manager_now = next(r for r in (await c.get(f"{BASE}/rbac/roles")).json()["roles"] if r["key"] == "manager")
    await c.put(f"{BASE}/rbac/roles/manager", json={"actions": manager_now["actions"]})
    assert await _rows(seeded, "manager") == set()
    reduced = [a for a in manager_now["actions"] if a != "requests.stats"]
    await c.put(f"{BASE}/rbac/roles/manager", json={"actions": reduced})
    assert await _rows(seeded, "manager") == {("requests.stats", False)}
    await c.post(f"{BASE}/rbac/roles/manager/reset")
    assert await _rows(seeded, "manager") == set()
    await c.post(f"{BASE}/rbac/roles", json={"key": "senior_exec", "title": "S", "actions": ["requests.stats"]})
    assert await _rows(seeded, "senior_exec") == {("requests.stats", True)}


@pytest.mark.asyncio
async def test_every_write_bumps_version(client, seeded):
    c = await client(SUPERADMIN)
    await c.post(f"{BASE}/rbac/roles", json={"key": "temp_role", "title": "T"})
    await c.put(f"{BASE}/rbac/roles/temp_role", json={"title": "T2"})
    await c.post(f"{BASE}/rbac/roles/manager/reset")
    await c.delete(f"{BASE}/rbac/roles/temp_role")
    async with seeded() as s:
        assert (await s.get(RbacState, 1)).version == 5


@pytest.mark.asyncio
async def test_delete_rules(client):
    c = await client(SUPERADMIN)
    assert (await c.delete(f"{BASE}/rbac/roles/manager")).status_code == 400
    await c.post(f"{BASE}/rbac/roles", json={"key": "temp_role", "title": "T"})
    await c.put(f"{BASE}/{EXECUTOR}/roles", json={"roles": ["executor", "temp_role"]})
    assert (await c.delete(f"{BASE}/rbac/roles/temp_role")).status_code == 409
    await c.put(f"{BASE}/{EXECUTOR}/roles", json={"roles": ["executor"]})
    assert (await c.delete(f"{BASE}/rbac/roles/temp_role")).status_code == 204


# ── роли сотрудника ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_user_roles_read_and_assign(client):
    view = await (await client(MANAGER)).get(f"{BASE}/{EXECUTOR}/roles")
    assert view.status_code == 200 and view.json()["can_edit"] is False
    c = await client(SUPERADMIN)
    resp = await c.put(f"{BASE}/{EXECUTOR}/roles", json={"roles": ["security_operator"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["roles"] == ["security_operator"]
    assert resp.json()["active_role"] == "security_operator"
    bad = await c.put(f"{BASE}/{EXECUTOR}/roles", json={"roles": ["ghost"]})
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_custom_role_goes_with_a_system_role(client):
    """Своя роль — только вместе с системной; режим меню остаётся системным."""
    c = await client(SUPERADMIN)
    await c.post(f"{BASE}/rbac/roles", json={"key": "senior_exec", "title": "S"})
    alone = await c.put(f"{BASE}/{EXECUTOR}/roles", json={"roles": ["senior_exec"]})
    assert alone.status_code == 422
    both = await c.put(f"{BASE}/{EXECUTOR}/roles", json={"roles": ["senior_exec", "manager"]})
    assert both.status_code == 200 and both.json()["active_role"] == "manager"


@pytest.mark.asyncio
async def test_rbac_paths_do_not_fall_into_employee_routes(client):
    """/employees/rbac/... обслуживает админка, а не /employees/{user_id}."""
    resp = await (await client(MANAGER)).get(f"{BASE}/rbac/catalog")
    assert resp.status_code == 200


# ── защита и границы ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_superadmin_flag_visible_only_to_superadmin(client):
    as_manager = await (await client(MANAGER)).get(f"{BASE}/{SUPERADMIN}/roles")
    assert as_manager.status_code == 200 and as_manager.json()["is_superadmin"] is False
    as_superadmin = await (await client(SUPERADMIN)).get(f"{BASE}/{SUPERADMIN}/roles")
    assert as_superadmin.json()["is_superadmin"] is True


@pytest.mark.asyncio
async def test_manager_cannot_block_superadmin(client):
    """Суперадмин без менеджерских ролей всё равно защищён от блокировки."""
    resp = await (await client(MANAGER)).patch(f"{BASE}/{SUPERADMIN}/block")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_holder_of_staff_rights_via_custom_role_is_protected(client, monkeypatch):
    """Своя роль с управлением сотрудниками защищает так же, как роль manager."""
    from uk_management_bot.authz import store

    # Проверки читают права через store (синхронная сессия процесса), а не
    # через тестовую async-базу — даём ему то, что он прочитал бы после правки.
    hr_snapshot = store.Snapshot(version=2, overrides={("hr_lead", "staff.manage"): True},
                                 roles=frozenset({*SYSTEM, "hr_lead"}))
    monkeypatch.setattr(store, "current_snapshot", lambda: hr_snapshot)
    sa = await client(SUPERADMIN)
    await sa.post(f"{BASE}/rbac/roles", json={"key": "hr_lead", "title": "HR", "actions": ["staff.manage"]})
    await sa.put(f"{BASE}/{EXECUTOR}/roles", json={"roles": ["executor", "hr_lead"]})
    resp = await (await client(MANAGER)).patch(f"{BASE}/{EXECUTOR}/block")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_payload_size_is_bounded(client):
    c = await client(SUPERADMIN)
    too_many_roles = await c.put(f"{BASE}/{EXECUTOR}/roles", json={"roles": ["executor"] * 33})
    assert too_many_roles.status_code == 422
    too_many_actions = await c.put(f"{BASE}/rbac/roles/manager", json={"actions": ["x"] * 501})
    assert too_many_actions.status_code == 422


# ── сироты и подсчёт ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_write_purges_rows_of_removed_actions(client, seeded):
    """Переопределение действия, которого нет в каталоге, удаляется при записи."""
    async with seeded() as s:
        s.add(RbacRolePermission(role_key="manager", action_key="gone.action", allowed=True))
        await s.commit()
    await (await client(SUPERADMIN)).post(f"{BASE}/rbac/roles/executor/reset")
    assert await _rows(seeded, "manager") == set()


@pytest.mark.asyncio
async def test_users_count_is_exact_and_skips_deleted(client, seeded):
    async with seeded() as s:
        s.add_all([
            _user(10, ["manager", "executor"]),
            _user(11, ["manager"], status="deleted"),
            _user(12, ["manager_assistant"]),
        ])
        await s.commit()
    roles = (await (await client(MANAGER)).get(f"{BASE}/rbac/roles")).json()["roles"]
    counts = {r["key"]: r["users_count"] for r in roles}
    # MANAGER и id 10; удалённый и «manager_assistant» (похожий ключ) не считаются.
    assert counts["manager"] == 2
    assert counts["executor"] == 2
