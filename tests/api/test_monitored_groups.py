"""CRUD реестра мониторимых ТГ-групп (Group Intake), /api/v2/monitored-groups.

Только manager; дубль chat_id → 409; PATCH/DELETE оставляют audit-строку и
updated_by. chat_id — BigInteger (supergroup -100xxxxxxxxxx).
"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.monitored_group import MonitoredGroup

SUPERGROUP_ID = -1002345678901  # заведомо за пределами int4


@pytest.mark.asyncio
async def test_crud_roundtrip(client, db_session: AsyncSession, manager_user):
    # create
    resp = await client.post(
        "/api/v2/monitored-groups",
        json={"chat_id": SUPERGROUP_ID, "title": "ЖК Ромашка", "kind": "residents"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["chat_id"] == SUPERGROUP_ID
    assert body["kind"] == "residents"
    assert body["is_active"] is True
    group_id = body["id"]

    # list
    resp = await client.get("/api/v2/monitored-groups")
    assert resp.status_code == 200
    listing = resp.json()
    assert listing["total"] == 1
    assert listing["items"][0]["chat_id"] == SUPERGROUP_ID

    # toggle off
    resp = await client.patch(
        f"/api/v2/monitored-groups/{group_id}", json={"is_active": False}
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    row = (
        await db_session.execute(
            select(MonitoredGroup).where(MonitoredGroup.id == group_id)
        )
    ).scalar_one()
    assert row.is_active is False
    assert row.updated_by == manager_user.id

    # delete
    resp = await client.delete(f"/api/v2/monitored-groups/{group_id}")
    assert resp.status_code == 204
    remaining = (
        await db_session.execute(select(MonitoredGroup))
    ).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_duplicate_chat_id_is_409(client):
    first = await client.post(
        "/api/v2/monitored-groups", json={"chat_id": SUPERGROUP_ID}
    )
    assert first.status_code == 201
    dup = await client.post(
        "/api/v2/monitored-groups", json={"chat_id": SUPERGROUP_ID, "title": "dup"}
    )
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_invalid_kind_is_422(client):
    resp = await client.post(
        "/api/v2/monitored-groups", json={"chat_id": 1, "kind": "aliens"}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_non_manager_is_403(client, db_session: AsyncSession, resident_user):
    """Подмена current_user на applicant — все ручки закрыты."""
    from uk_management_bot.api.dependencies import get_current_user
    from uk_management_bot.api.main import app

    async def override_resident():
        return resident_user

    app.dependency_overrides[get_current_user] = override_resident
    try:
        assert (await client.get("/api/v2/monitored-groups")).status_code == 403
        assert (
            await client.post("/api/v2/monitored-groups", json={"chat_id": 5})
        ).status_code == 403
        assert (
            await client.patch(
                "/api/v2/monitored-groups/1", json={"is_active": False}
            )
        ).status_code == 403
        assert (
            await client.delete("/api/v2/monitored-groups/1")
        ).status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_toggle_and_delete_write_audit(client, db_session: AsyncSession, manager_user):
    resp = await client.post(
        "/api/v2/monitored-groups", json={"chat_id": SUPERGROUP_ID}
    )
    group_id = resp.json()["id"]

    await client.patch(f"/api/v2/monitored-groups/{group_id}", json={"is_active": False})
    await client.delete(f"/api/v2/monitored-groups/{group_id}")

    actions = [
        a
        for (a,) in (
            await db_session.execute(select(AuditLog.action).order_by(AuditLog.id))
        ).all()
    ]
    assert "monitored_group.created" in actions
    assert "monitored_group.updated" in actions
    assert "monitored_group.deleted" in actions

    updated = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "monitored_group.updated")
        )
    ).scalar_one()
    assert updated.user_id == manager_user.id
    assert updated.details["is_active"] == {"old": True, "new": False}


@pytest.mark.asyncio
async def test_patch_missing_group_is_404(client):
    resp = await client.patch(
        "/api/v2/monitored-groups/9999", json={"is_active": False}
    )
    assert resp.status_code == 404
